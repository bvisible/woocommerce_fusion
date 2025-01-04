# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

from typing import List, Dict
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.caching import redis_cache
from woocommerce import API

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
)
from woocommerce_fusion.woocommerce.woocommerce_api import parse_domain_from_url
from woocommerce_fusion.wordpress import WordpressAPI
from woocommerce_fusion.tasks.utils import APIWithRequestLogging

class WooCommerceServer(Document):
	def autoname(self):
		"""
		Derive name from woocommerce_server_url field
		"""
		self.name = parse_domain_from_url(self.woocommerce_server_url)

	def validate(self):
		# Validate URL
		result = urlparse(self.woocommerce_server_url)
		if not all([result.scheme, result.netloc]):
			frappe.throw(_("Please enter a valid WooCommerce Server URL"))

		# Get Shipment Providers if the "Advanced Shipment Tracking" woocommerce plugin is used
		if self.enable_sync and self.wc_plugin_advanced_shipment_tracking:
			self.get_shipment_providers()

		if not self.secret:
			self.secret = frappe.generate_hash()

		self.validate_so_status_map()
		
		# Update shipping method IDs if shipping methods sync is enabled
		if self.enable_shipping_methods_sync and self.shipping_rule_map:
			self.update_shipping_method_ids()

	def validate_so_status_map(self):
		"""
		Validate Sales Order Status Map to have unique mappings
		"""
		erpnext_so_statuses = [map.erpnext_sales_order_status for map in self.sales_order_status_map]
		if len(erpnext_so_statuses) != len(set(erpnext_so_statuses)):
			frappe.throw(_("Duplicate ERPNext Sales Order Statuses found in Sales Order Status Map"))
		wc_so_statuses = [map.woocommerce_sales_order_status for map in self.sales_order_status_map]
		if len(wc_so_statuses) != len(set(wc_so_statuses)):
			frappe.throw(_("Duplicate WooCommerce Sales Order Statuses found in Sales Order Status Map"))

	def update_shipping_method_ids(self):
		"""
		Update the IDs of shipping methods in shipping_rule_map using the WooCommerce API
		"""
		shipping_methods = self.get_shipping_methods()
		method_id_to_title = {method["method_id"]: method["title"] for method in shipping_methods}
		
		for rule in self.shipping_rule_map:
			if rule.wc_shipping_method_title in method_id_to_title.values():
				rule.wc_shipping_method_id = [method["method_id"] for method in shipping_methods if method["title"] == rule.wc_shipping_method_title][0]

	@frappe.whitelist()
	@redis_cache(ttl=600)
	def get_shipping_methods(self) -> List[Dict[str, str]]:
		"""
		Retrieve list of Shipping Methods with their titles from WooCommerce API
		Returns a list of dicts with method_id and title
		"""
		wc_api = APIWithRequestLogging(
			url=self.woocommerce_server_url,
			consumer_key=self.api_consumer_key,
			consumer_secret=self.api_consumer_secret,
			version="wc/v3",
			timeout=40,
		)
		
		try:
			# Get all shipping methods directly
			methods_response = wc_api.get("shipping/methods")
			if methods_response.status_code != 200:
				frappe.log_error(f"Failed to get shipping methods. Status code: {methods_response.status_code}")
				return []
			
			methods = methods_response.json()
			if not isinstance(methods, list):
				frappe.log_error(f"Invalid methods response format: {methods}")
				return []
			
			shipping_methods = []
			for method in methods:
				if isinstance(method, dict) and 'id' in method and 'title' in method:
					shipping_methods.append({
						'method_id': method['id'],
						'title': method['title']
					})
			
			return shipping_methods
			
		except Exception as e:
			frappe.log_error(f"Error getting shipping methods: {str(e)}")
			return []

	@frappe.whitelist()
	@redis_cache(ttl=600)
	def get_shipping_method_options(self) -> List[str]:
		"""
		Get list of shipping method titles for the Select field
		"""
		try:
			methods = self.get_shipping_methods()
			if not methods:
				return []
			
			return [method['title'] for method in methods]
			
		except Exception as e:
			frappe.log_error(f"Error getting shipping method options: {str(e)}")
			return []

	@frappe.whitelist()
	@redis_cache(ttl=86400)
	def get_item_docfields(self):
		"""
		Get a list of DocFields for the Item Doctype
		"""
		invalid_field_types = [
			"Column Break",
			"Fold",
			"Heading",
			"Read Only",
			"Section Break",
			"Tab Break",
			"Table",
			"Table MultiSelect",
		]
		docfields = frappe.get_all(
			"DocField",
			fields=["label", "name", "fieldname"],
			filters=[["fieldtype", "not in", invalid_field_types], ["parent", "=", "Item"]],
		)
		custom_fields = frappe.get_all(
			"Custom Field",
			fields=["label", "name", "fieldname"],
			filters=[["fieldtype", "not in", invalid_field_types], ["dt", "=", "Item"]],
		)
		return docfields + custom_fields

	@frappe.whitelist()
	@redis_cache(ttl=86400)
	def get_woocommerce_order_status_list(self) -> List[str]:
		"""
		Retrieve list of WooCommerce Order Statuses
		"""
		return [key for key in WC_ORDER_STATUS_MAPPING.keys()]

	@frappe.whitelist()
	def test_wordpress_connection(self):
		"""Test the WordPress connection using the current settings"""
		if not self.enable_sync_wp:
			frappe.throw(_("WordPress API is not enabled"))

		try:
			wp = WordpressAPI(self)
			# Test connection by getting WordPress info
			response = wp.get("wp/v2/users/me")
			if response.status_code == 200:
				frappe.msgprint(_("WordPress connection successful!"))
			else:
				frappe.throw(_("WordPress connection failed. Status code: {0}").format(response.status_code))
		except Exception as e:
			frappe.throw(_("WordPress connection failed: {0}").format(str(e)))


@frappe.whitelist()
def get_woocommerce_shipment_providers(woocommerce_server):
	"""
	Return the Shipment Providers for a given WooCommerce Server domain
	"""
	wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_server)
	return wc_server.wc_ast_shipment_providers

@frappe.whitelist()
def get_shipping_methods(woocommerce_server):
	"""Get all shipping methods from WooCommerce"""
	from woocommerce_fusion.tasks.utils import APIWithRequestLogging
	
	# Get WooCommerce server details
	server = frappe.get_doc("WooCommerce Server", woocommerce_server)
	
	# Initialize WooCommerce API
	wc = APIWithRequestLogging(
		url=server.woocommerce_server_url,
		consumer_key=server.api_consumer_key,
		consumer_secret=server.api_consumer_secret,
		version="wc/v3",
		timeout=40
	)
	
	# Get all shipping zones
	shipping_zones = wc.get("shipping/zones").json()
	
	# Initialize list to store all shipping methods
	all_methods = []
	
	# For each zone, get its shipping methods
	for zone in shipping_zones:
		zone_methods = wc.get(f"shipping/zones/{zone['id']}/methods").json()
		
		# Add each method to our list
		for method in zone_methods:
			all_methods.append({
				'method_id': method['method_id'],
				'title': method['title']  # This is the user-configured title
			})
	
	return all_methods
