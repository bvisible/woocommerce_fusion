import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import frappe
from erpnext.stock.doctype.item.item import Item
from frappe import _, _dict
from frappe.query_builder import Criterion
from frappe.utils import get_datetime, now

from woocommerce import API
from woocommerce_fusion.exceptions import SyncDisabledError
from woocommerce_fusion.tasks.sync import SynchroniseWooCommerce
from woocommerce_fusion.woocommerce.doctype.woocommerce_product.woocommerce_product import (
	WooCommerceProduct,
)
from woocommerce_fusion.woocommerce.doctype.woocommerce_server.woocommerce_server import (
	WooCommerceServer,
)
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)

def safe_log_error(message: str, title: str = "WooCommerce Error", max_len: int = 140):
	"""
    Tronque le message de log si nécessaire pour éviter l'erreur
    'CharacterLengthExceededError' dans ERPNext
    """
	if len(message) > max_len:
		message = message[:max_len] + "... (truncated)"

	frappe.log_error(message, title)


def run_item_sync_from_hook(doc, method):
	"""
    Intended to be triggered by a Document Controller hook from Item
    """
	if (
			doc.doctype == "Item"
			and not doc.flags.get("created_by_sync", None)
			and len(doc.woocommerce_servers) > 0
	):
		frappe.msgprint(
			_("Background sync to WooCommerce triggered for {}").format(frappe.bold(doc.name)),
			indicator="blue",
			alert=True,
		)
		frappe.enqueue(clear_sync_hash_and_run_item_sync, item_code=doc.name)


@frappe.whitelist()
def run_item_sync(
		item_code: Optional[str] = None,
		item: Optional[Item] = None,
		woocommerce_product_name: Optional[str] = None,
		woocommerce_product: Optional[WooCommerceProduct] = None,
		enqueue=False,
) -> Tuple[Optional[Item], Optional[WooCommerceProduct]]:
	"""
    Helper function that prepares arguments for item sync
    """
	# Validate inputs, at least one of the parameters should be provided
	if not any([item_code, item, woocommerce_product_name, woocommerce_product]):
		raise ValueError(
			(
				"At least one of item_code, item, woocommerce_product_name, "
				"woocommerce_product parameters required"
			)
		)

	# Get ERPNext Item and WooCommerce product if they exist
	if woocommerce_product or woocommerce_product_name:
		if not woocommerce_product:
			woocommerce_product = frappe.get_doc(
				{"doctype": "WooCommerce Product", "name": woocommerce_product_name}
			)
			woocommerce_product.load_from_db()

		# Trigger sync
		sync = SynchroniseItem(woocommerce_product=woocommerce_product)
		if enqueue:
			frappe.enqueue(sync.run)
		else:
			sync.run()

	elif item or item_code:
		if not item:
			item = frappe.get_doc("Item", item_code)
		if not item.woocommerce_servers:
			frappe.throw(_("No WooCommerce Servers defined for Item {0}").format(item_code))
		for wc_server in item.woocommerce_servers:
			# Trigger sync for every linked server
			sync = SynchroniseItem(
				item=ERPNextItemToSync(item=item, item_woocommerce_server_idx=wc_server.idx)
			)
			if enqueue:
				frappe.enqueue(sync.run)
			else:
				sync.run()

	return (
		sync.item.item if sync and sync.item else None,
		sync.woocommerce_product if sync else None,
	)


def sync_woocommerce_products_modified_since(date_time_from=None):
	"""
    Get list of WooCommerce products modified since date_time_from
    """
	wc_settings = frappe.get_doc("WooCommerce Integration Settings")

	if not date_time_from:
		date_time_from = wc_settings.wc_last_sync_date_items

	# Validate
	if not date_time_from:
		error_text = _(
			"'Last Items Synchronisation Date' field on 'WooCommerce Integration Settings' is missing"
		)
		frappe.log_error("WooCommerce Items Sync Task Error", error_text)
		raise ValueError(error_text)

	wc_products = get_list_of_wc_products(date_time_from=date_time_from)
	for wc_product in wc_products:
		try:
			run_item_sync(woocommerce_product=wc_product, enqueue=True)
		except Exception:
			pass

	wc_settings.reload()
	wc_settings.wc_last_sync_date_items = now()
	wc_settings.flags.ignore_mandatory = True
	wc_settings.save()


def format_erpnext_img_url(image_details):
	file_url = image_details[1]
	if image_details[2] == 0:  # is_private == 0
		if file_url.startswith("http"):
			return file_url

		site_config = frappe.get_site_config()
		domains = site_config.get("domains", [])
		if domains:
			domain = domains[0]
			return f"https://{domain}{file_url}"
	return None


def check_existing_file(filename: str, content_hash: str = None) -> str:
	"""
    Vérifie si un fichier existe déjà et retourne son URL
    """
	filters = {"name": filename}
	if content_hash:
		filters["content_hash"] = content_hash

	existing_file = frappe.get_all(
		"File",
		filters=filters,
		fields=["file_url"],
		limit=1
	)

	return existing_file[0].file_url if existing_file else None


def handle_file_upload(doc, method):
	"""Hook avant l'insertion d'un fichier"""
	if doc.content_hash:
		existing_url = check_existing_file(doc.file_name, doc.content_hash)
		if existing_url:
			doc.file_url = existing_url
			return

	# Si le nom existe mais hash différent, générer un nouveau nom
	if frappe.db.exists("File", {"name": doc.file_name}):
		doc.file_name = (
			f"{doc.file_name.rsplit('.', 1)[0]}_{frappe.generate_hash()[:6]}"
			f".{doc.file_name.rsplit('.', 1)[1]}"
		)


def run_file_sync_from_hook(doc, method):
	"""Triggered when a File is added/modified/deleted"""
	if (
			doc.doctype == "File"
			and doc.attached_to_doctype == "Item"
			and (not doc.is_private or method == "on_trash")
			and (
			doc.file_url
			and any(doc.file_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"])
	)
	):
		item = frappe.get_doc("Item", doc.attached_to_name)
		if item.woocommerce_servers:
			frappe.enqueue(
				clear_sync_hash_and_run_item_sync,
				item_code=item.name
			)


@dataclass
class ERPNextItemToSync:
	"""Class for keeping track of an ERPNext Item and the relevant WooCommerce Server to sync to"""

	item: Item
	item_woocommerce_server_idx: int

	@property
	def item_woocommerce_server(self):
		return self.item.woocommerce_servers[self.item_woocommerce_server_idx - 1]


class SynchroniseItem(SynchroniseWooCommerce):
	"""
    Class for managing synchronisation of WooCommerce Product with ERPNext Item
    """

	def __init__(
			self,
			servers: List[WooCommerceServer | _dict] = None,
			item: Optional[ERPNextItemToSync] = None,
			woocommerce_product: Optional[WooCommerceProduct] = None,
	) -> None:
		super().__init__(servers)
		self.item = item
		self.woocommerce_product = woocommerce_product
		self.settings = frappe.get_cached_doc("WooCommerce Integration Settings")

		# Initialiser l'API WooCommerce ici
		if woocommerce_product and woocommerce_product.woocommerce_server:
			self.init_wc_api(woocommerce_product.woocommerce_server)
		elif item and item.item_woocommerce_server:
			self.init_wc_api(item.item_woocommerce_server.woocommerce_server)

	def init_wc_api(self, server_name):
		"""Initialize WooCommerce API for the given server"""
		wc_server = frappe.get_cached_doc("WooCommerce Server", server_name)
		self.current_wc_api = API(
			url=wc_server.woocommerce_server_url,
			consumer_key=wc_server.api_consumer_key,
			consumer_secret=wc_server.api_consumer_secret,
			version="wc/v3",
			timeout=40,
		)

	def run(self):
		"""
        Run synchronisation
        """
		try:
			self.get_corresponding_item_or_product()
			self.sync_wc_product_with_erpnext_item()
		except Exception as err:
			# Tronquer le message si trop long
			err_msg = (
				f"{frappe.get_traceback()}\n\n"
				f"Item Data: \n{str(self.item) if self.item else ''}\n\n"
				f"WC Product Data \n{str(self.woocommerce_product.as_dict() if isinstance(self.woocommerce_product, WooCommerceProduct) else self.woocommerce_product)}"
			)
			safe_log_error(err_msg, "WooCommerce Error", max_len=1000)  # tronqué à 1000
			raise err

	def get_corresponding_item_or_product(self):
		"""
        If we have an ERPNext Item, get the corresponding WooCommerce Product
        If we have a WooCommerce Product, get the corresponding ERPNext Item
        """
		if (
				self.item
				and not self.woocommerce_product
				and self.item.item_woocommerce_server.woocommerce_id
		):
			# Validate that this Item's WooCommerce Server has sync enabled
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.item.item_woocommerce_server.woocommerce_server
			)
			if not wc_server.enable_sync:
				raise SyncDisabledError(wc_server)

			wc_products = get_list_of_wc_products(item=self.item)
			if len(wc_products) == 0:
				raise ValueError(
					f"No WooCommerce Product found with ID {self.item.item_woocommerce_server.woocommerce_id} "
					f"on {self.item.item_woocommerce_server.woocommerce_server}"
				)
			self.woocommerce_product = wc_products[0]

		if self.woocommerce_product and not self.item:
			self.get_erpnext_item()

	def get_erpnext_item(self):
		"""
        Get erpnext item for a WooCommerce Product
        """
		if not all(
				[self.woocommerce_product.woocommerce_server, self.woocommerce_product.woocommerce_id]
		):
			raise ValueError("Both woocommerce_server and woocommerce_id required")

		iws = frappe.qb.DocType("Item WooCommerce Server")
		itm = frappe.qb.DocType("Item")

		and_conditions = [
			iws.woocommerce_server == self.woocommerce_product.woocommerce_server,
			iws.woocommerce_id == self.woocommerce_product.woocommerce_id,
			]

		item_codes = (
			frappe.qb.from_(iws)
			.join(itm)
			.on(iws.parent == itm.name)
			.where(Criterion.all(and_conditions))
			.select(iws.parent, iws.name)
			.limit(1)
		).run(as_dict=True)

		found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None
		if found_item:
			self.item = ERPNextItemToSync(
				item=found_item,
				item_woocommerce_server_idx=next(
					server.idx for server in found_item.woocommerce_servers
					if server.name == item_codes[0].name
				),
			)

	def sync_wc_product_with_erpnext_item(self):
		"""
        Syncronise Item between ERPNext and WooCommerce
        """
		if self.item and not self.woocommerce_product:
			# create missing product in WooCommerce
			self.create_woocommerce_product(self.item)
		elif self.woocommerce_product and not self.item:
			# create missing item in ERPNext
			self.create_item(self.woocommerce_product)
		elif self.item and self.woocommerce_product:
			# both exist, check sync hash
			if (
					self.woocommerce_product.woocommerce_date_modified
					!= self.item.item_woocommerce_server.woocommerce_last_sync_hash
			):
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) > get_datetime(
						self.item.item.modified
				):
					self.update_item(self.woocommerce_product, self.item)
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) < get_datetime(
						self.item.item.modified
				):
					self.update_woocommerce_product(self.woocommerce_product, self.item)

	def update_item(self, woocommerce_product: WooCommerceProduct, item: ERPNextItemToSync):
		"""
        Update the ERPNext Item with fields from its corresponding WooCommerce Product
        """
		if item.item.item_name != woocommerce_product.woocommerce_name:
			item.item.item_name = woocommerce_product.woocommerce_name
			item.item.flags.created_by_sync = True
			item.item.save()
		self.set_item_fields()

		self.set_sync_hash()

	def check_wc_image_exists(self, image_url: str):
		"""
		Vérifie si l'image existe déjà dans la bibliothèque de médias WordPress
		Args:
			image_url: URL de l'image à vérifier
		Returns:
			ID du média si trouvé, None sinon
		"""
		from woocommerce_fusion.wordpress.media import get_img_id
		
		# Extraire le nom du fichier de l'URL
		filename = image_url.split("/")[-1]
		
		# Récupérer le serveur WooCommerce
		wc_server = None
		if self.woocommerce_product:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.woocommerce_product.woocommerce_server
			)
		elif self.item and self.item.item_woocommerce_server:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.item.item_woocommerce_server.woocommerce_server
			)
			
		if not wc_server or not wc_server.enable_sync_wp:
			return None
			
		# Rechercher l'image dans la bibliothèque média
		media = get_img_id(filename, server=wc_server)
		return media.get("id") if media else None

	def get_image_details(self, item, file_url):
		"""
        Récupère les détails d'une image à partir de ERPNext
        """
		return frappe.get_value(
			"File",
			{
				"file_url": file_url,
				"attached_to_doctype": "Item",
				"attached_to_name": item.item.name,
			},
			["file_name", "file_url", "is_private", "modified"],
			as_dict=True,
		)

	def compare_and_update_images(self, wc_product: WooCommerceProduct, item: ERPNextItemToSync) -> dict:
		"""
        Compare et met à jour les images en évitant les duplications
        et en gérant à la fois l'image principale et la galerie
        """
		try:
			current_images = json.loads(wc_product.images) if wc_product.images else []
			new_images = []
			seen_urls = set()
			has_changes = False

			# Récupérer toutes les images attachées
			attached_files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Item",
					"attached_to_name": item.item.name,
					"is_private": 0,
				},
				fields=["file_name", "file_url", "is_private", "modified"],
				order_by="creation",
			)

			# Filtrer pour ne garder que les images valides
			valid_extensions = (".jpg", ".jpeg", ".png", ".gif")
			valid_files = [
				f
				for f in attached_files
				if any(f.file_url.lower().endswith(ext) for ext in valid_extensions)
			]

			def process_image(file_details):
				image_url = format_erpnext_img_url(
					[file_details.file_name, file_details.file_url, file_details.is_private]
				)
				if not image_url or image_url in seen_urls:
					return None

				seen_urls.add(image_url)

				# 1. Vérifier dans les images actuelles du produit
				existing_image = next((img for img in current_images if img["src"] == image_url), None)
				if existing_image:
					return existing_image

				# 2. Vérifier dans la bibliothèque média WordPress
				media_id = self.check_wc_image_exists(image_url)
				if media_id:
					return {
						"id": media_id,
						"src": image_url,
						"date_created": file_details.modified.isoformat(),
					}

				# 3. Créer une nouvelle entrée si on ne la trouve nulle part
				return {
					"src": image_url,
					"date_created": file_details.modified.isoformat(),
				}

			# Traiter d'abord l'image principale si elle existe
			if item.item.image:
				main_image = next((f for f in valid_files if f.file_url == item.item.image), None)
				if main_image:
					main_image_data = process_image(main_image)
					if main_image_data:
						new_images.append(main_image_data)
						# S’il n’y avait pas d’image principale avant
						# ou si l’URL a changé, on considère qu’il y a changement
						has_changes = (
								not current_images
								or current_images[0]["src"] != main_image_data["src"]
						)

			# Traiter les autres images de la galerie
			for file_details in valid_files:
				# Ignorer l'image principale déjà traitée
				if file_details.file_url == item.item.image:
					continue

				image_data = process_image(file_details)
				if image_data:
					new_images.append(image_data)
					has_changes = True  # on a ajouté une image

			# Vérifier les changements globaux
			if not has_changes:
				# Si la longueur diffère ou si une URL diffère
				has_changes = (
						len(new_images) != len(current_images)
						or any(
					new_img["src"] != old_img["src"]
					for new_img, old_img in zip(new_images, current_images)
				)
				)

			return {
				"images": new_images,
				"has_changes": has_changes,
			}

		except Exception as e:
			safe_log_error(
				f"Error in compare_and_update_images: {str(e)}",
				"WooCommerce Error",
				max_len=500,
			)
			return {"images": json.loads(wc_product.images) if wc_product.images else [], "has_changes": False}

	def update_woocommerce_product(self, wc_product: WooCommerceProduct, item: ERPNextItemToSync) -> None:
		"""
        Met à jour le produit WooCommerce avec gestion optimisée des images
        """
		try:
			# Recharger le document pour éviter les conflits de version
			wc_product.reload()
			wc_product_dirty = False

			# Mise à jour des images
			if item.item.image:
				image_update = self.compare_and_update_images(wc_product, item)
				if image_update["has_changes"]:
					wc_product.images = json.dumps(image_update["images"])
					wc_product_dirty = True

			# Autres mises à jour
			if wc_product.woocommerce_name != item.item.item_name:
				wc_product.woocommerce_name = item.item.item_name
				wc_product_dirty = True

			# Update manage_stock based on is_stock_item
			if wc_product.manage_stock != item.item.is_stock_item:
				wc_product.manage_stock = True if item.item.is_stock_item else False
				wc_product_dirty = True

			if self.set_product_fields(wc_product, item):
				wc_product_dirty = True

			# Sauvegarder si nécessaire
			if wc_product_dirty:
				wc_product.flags.ignore_version = True
				wc_product.save()

			self.woocommerce_product = wc_product
			self.set_sync_hash()

		except Exception as e:
			safe_log_error(
				f"Error updating WooCommerce product: {str(e)}", "WooCommerce Error", max_len=500
			)
			raise

	def create_woocommerce_product(self, item: ERPNextItemToSync) -> None:
		"""
        Create the WooCommerce Product with fields from its corresponding ERPNext Item
        """
		if (
				item.item_woocommerce_server.woocommerce_server
				and item.item_woocommerce_server.enabled
				and not item.item_woocommerce_server.woocommerce_id
		):
			# Create a new WooCommerce Product doc
			wc_product = frappe.get_doc({"doctype": "WooCommerce Product"})
			wc_product.type = "simple"
			
			# Get default status from WooCommerce Server settings
			wc_server = frappe.get_doc("WooCommerce Server", item.item_woocommerce_server.woocommerce_server)
			wc_product.status = wc_server.default_product_status or "draft"

			# Set manage_stock based on is_stock_item
			wc_product.manage_stock = True if item.item.is_stock_item else False

			# Handle variants
			if item.item.has_variants:
				wc_product.type = "variable"
				wc_product_attributes = []
				for row in item.item.attributes:
					item_attribute = frappe.get_doc("Item Attribute", row.attribute)
					wc_product_attributes.append(
						{
							"name": row.attribute,
							"slug": row.attribute.lower().replace(" ", "_"),
							"visible": True,
							"variation": True,
							"options": [opt.attribute_value for opt in item_attribute.item_attribute_values],
						}
					)
				wc_product.attributes = json.dumps(wc_product_attributes)

			if item.item.variant_of:
				# Check if parent exists
				parent_item = frappe.get_doc("Item", item.item.variant_of)
				parent_item, parent_wc_product = run_item_sync(item_code=parent_item.item_code)
				wc_product.parent_id = parent_wc_product.woocommerce_id
				wc_product.type = "variation"
				# Handle attributes
				wc_product_attributes = [
					{
						"name": row.attribute,
						"slug": row.attribute.lower().replace(" ", "_"),
						"option": row.attribute_value,
					}
					for row in item.item.attributes
				]
				wc_product.attributes = json.dumps(wc_product_attributes)

			# Image principale
			if item.item.image:
				image_details = frappe.db.get_value(
					"File",
					{"file_url": item.item.image},
					["file_name", "file_url", "is_private", "content_hash", "creation"],
				)
				if image_details:
					image_url = format_erpnext_img_url(image_details)
					if image_url:
						date_created_str = (
							image_details[4].isoformat()
							if image_details[4]
							else datetime.now().isoformat()
						)
						wc_product.images = json.dumps(
							[{"src": image_url, "date_created": date_created_str}]
						)

			# Set properties
			wc_product.woocommerce_server = item.item_woocommerce_server.woocommerce_server
			wc_product.woocommerce_name = item.item.item_name
			wc_product.regular_price = get_item_price_rate(item) or "0"

			self.set_product_fields(wc_product, item)

			wc_product.insert()
			self.woocommerce_product = wc_product

			# Reload ERPNext Item
			item.item.reload()
			item.item_woocommerce_server.woocommerce_id = wc_product.woocommerce_id
			item.item.flags.created_by_sync = True
			item.item.save()

			self.set_sync_hash()

	def create_item(self, wc_product: WooCommerceProduct) -> None:
		"""
        Create an ERPNext Item from the given WooCommerce Product
        """
		wc_server = frappe.get_cached_doc("WooCommerce Server", wc_product.woocommerce_server)

		# Create Item
		item = frappe.new_doc("Item")

		# Handle variants' attributes
		if wc_product.type in ["variable", "variation"]:
			self.create_or_update_item_attributes(wc_product)
			wc_attributes = json.loads(wc_product.attributes)
			for wc_attribute in wc_attributes:
				row = item.append("attributes")
				row.attribute = wc_attribute["name"]
				if wc_product.type == "variation":
					row.attribute_value = wc_attribute["option"]

		# Handle variants
		if wc_product.type == "variable":
			item.has_variants = 1

		if wc_product.type == "variation":
			# Check if parent exists
			woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
				wc_product.woocommerce_server, wc_product.parent_id
			)
			parent_item, parent_wc_product = run_item_sync(
				woocommerce_product_name=woocommerce_product_name
			)
			item.variant_of = parent_item.item_code

		# Définir item_code selon la config du Woocommerce Server
		item.item_code = (
			wc_product.sku
			if wc_server.name_by == "Product SKU" and wc_product.sku
			else str(wc_product.woocommerce_id)
		)
		item.stock_uom = wc_server.uom or _("Nos")
		item.item_group = wc_server.item_group
		item.item_name = wc_product.woocommerce_name

		row = item.append("woocommerce_servers")
		row.woocommerce_id = wc_product.woocommerce_id
		row.woocommerce_server = wc_server.name

		item.flags.ignore_mandatory = True
		item.flags.created_by_sync = True
		item.insert()

		self.item = ERPNextItemToSync(
			item=item,
			item_woocommerce_server_idx=next(
				iws.idx
				for iws in item.woocommerce_servers
				if iws.woocommerce_server == wc_product.woocommerce_server
			),
		)

		self.set_item_fields()
		self.set_sync_hash()

	def create_or_update_item_attributes(self, wc_product: WooCommerceProduct):
		"""
        Create or update an Item Attribute
        """
		if wc_product.attributes:
			wc_attributes = json.loads(wc_product.attributes)
			for wc_attribute in wc_attributes:
				if frappe.db.exists("Item Attribute", wc_attribute["name"]):
					# Get existing Item Attribute
					item_attribute = frappe.get_doc("Item Attribute", wc_attribute["name"])
				else:
					# Create a new Item Attribute
					item_attribute = frappe.get_doc(
						{"doctype": "Item Attribute", "attribute_name": wc_attribute["name"]}
					)

				# Dans un produit variable => "options" (liste)
				# Dans un produit "variation" => "option" (unique)
				options = (
					wc_attribute["options"]
					if wc_product.type == "variable"
					else [wc_attribute["option"]]
				)

				# Remplace ou met à jour les valeurs s’il y a un écart
				existing_values = {val.attribute_value for val in item_attribute.item_attribute_values}
				if existing_values != set(options):
					item_attribute.item_attribute_values = []
					for option in options:
						row = item_attribute.append("item_attribute_values")
						row.attribute_value = option
						row.abbr = option.replace(" ", "")

				item_attribute.flags.ignore_mandatory = True
				if not item_attribute.name:
					item_attribute.insert()
				else:
					item_attribute.save()

	def set_item_fields(self):
		"""
        Si des "Field Mappings" existent sur `WooCommerce Server`, on synchronise
        leurs valeurs de WooCommerce => ERPNext
        """
		if self.item and self.woocommerce_product:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.woocommerce_product.woocommerce_server
			)
			if wc_server.item_field_map:
				for map in wc_server.item_field_map:
					erpnext_item_field_name = map.erpnext_field_name.split(" | ")
					woocommerce_product_field_value = self.woocommerce_product.get(map.woocommerce_field_name)

					frappe.db.set_value(
						"Item",
						self.item.item.name,
						erpnext_item_field_name[0],
						woocommerce_product_field_value,
						update_modified=False,
					)

	def set_product_fields(
			self, woocommerce_product: WooCommerceProduct, item: ERPNextItemToSync
	) -> bool:
		"""
        Si des "Field Mappings" existent sur `WooCommerce Server`, on synchronise
        leurs valeurs de ERPNext => WooCommerce

        Retourne True si le doc a été modifié
        """
		wc_product_dirty = False
		if item and woocommerce_product:
			wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_product.woocommerce_server)
			if wc_server.item_field_map:
				for map in wc_server.item_field_map:
					erpnext_item_field_name = map.erpnext_field_name.split(" | ")
					erpnext_item_field_value = getattr(item.item, erpnext_item_field_name[0])

					if erpnext_item_field_value != getattr(woocommerce_product, map.woocommerce_field_name):
						setattr(
							woocommerce_product, map.woocommerce_field_name, erpnext_item_field_value
						)
						wc_product_dirty = True

		return wc_product_dirty

	def set_sync_hash(self):
		"""
        On enregistre la date de modification dans le champ "woocommerce_last_sync_hash"
        sans passer par les triggers Frappe (pour éviter de toucher le timestamp
        "modified" de l'Item WooCommerce Server).
        """
		if self.item and self.woocommerce_product:
			frappe.db.set_value(
				"Item WooCommerce Server",
				self.item.item_woocommerce_server.name,
				"woocommerce_last_sync_hash",
				self.woocommerce_product.woocommerce_date_modified,
				update_modified=False,
			)

			# On s'assure que l'Item est activé pour la synchro
			frappe.db.set_value(
				"Item WooCommerce Server",
				self.item.item_woocommerce_server.name,
				"enabled",
				1,
				update_modified=False,
			)


def get_list_of_wc_products(
		item: Optional[ERPNextItemToSync] = None, date_time_from: Optional[datetime] = None
) -> List[WooCommerceProduct]:
	"""
    Récupère les produits WooCommerce selon un range de dates
    ou liés à un Item précis. Minimum un des deux paramètres requis.
    """
	if not any([date_time_from, item]):
		raise ValueError("At least one of date_time_from or item parameters are required")

	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	wc_products = []
	servers = None

	# Build filters
	if date_time_from:
		filters.append(["WooCommerce Product", "date_modified", ">", date_time_from])
	if item:
		filters.append(["WooCommerce Product", "id", "=", item.item_woocommerce_server.woocommerce_id])
		servers = [item.item_woocommerce_server.woocommerce_server]

	while new_results:
		woocommerce_product = frappe.get_doc({"doctype": "WooCommerce Product"})
		new_results = woocommerce_product.get_list(
			args={
				"filters": filters,
				"page_lenth": page_length,
				"start": start,
				"servers": servers,
				"as_doc": True,
			}
		)
		for wc_product in new_results:
			wc_products.append(wc_product)
		start += page_length
		if len(new_results) < page_length:
			new_results = []

	return wc_products


def get_item_price_rate(item: ERPNextItemToSync):
	"""
    Retourne le prix de l'Item s'il existe et si la synchro de liste de prix est activée
    """
	wc_server = frappe.get_cached_doc(
		"WooCommerce Server", item.item_woocommerce_server.woocommerce_server
	)
	if wc_server.enable_price_list_sync:
		item_prices = frappe.get_all(
			"Item Price",
			filters={"item_code": item.item.item_name, "price_list": wc_server.price_list},
			fields=["price_list_rate", "valid_upto"],
		)
		return next(
			(
				price.price_list_rate
				for price in item_prices
				if not price.valid_upto or price.valid_upto > now()
			),
			None,
		)


def clear_sync_hash_and_run_item_sync(item_code: str):
	"""
    Efface le dernier hash de synchro pour relancer la synchro
    """
	iws = frappe.qb.DocType("Item WooCommerce Server")

	iwss = (
		frappe.qb.from_(iws)
		.where(iws.enabled == 1)
		.where(iws.parent == item_code)
		.select(iws.name)
	).run(as_dict=True)

	for iws_doc in iwss:
		frappe.db.set_value(
			"Item WooCommerce Server",
			iws_doc.name,
			"woocommerce_last_sync_hash",
			None,
			update_modified=False,
		)

	if len(iwss) > 0:
		run_item_sync(item_code=item_code, enqueue=True)
