import frappe
from woocommerce_fusion.wordpress import WordpressAPI

class WordpressMedia(WordpressAPI):
	def __init__(self, server=None, version="wp-json/wp/v2", *args, **kwargs):
		super(WordpressMedia, self).__init__(server=server, version=version, *args, **kwargs)

	def get_list(self, params={}):
		"""Récupère la liste des médias avec pagination"""
		return self.get("media", params=params)

	def create_img(self, data, headers={}):
		"""Crée une nouvelle image dans la bibliothèque média"""
		return self.post("media", files=data, headers=headers).json()

	def delete_img(self, media_id):
		"""Supprime une image de la bibliothèque média"""
		return self.delete(f"media/{media_id}", params={"force": True})

def get_img_id(name, server=None):
	"""
	Recherche une image par son nom dans la bibliothèque média
	Args:
		name: Nom de l'image à rechercher
		server: Instance du serveur WooCommerce (optionnel)
	Returns:
		Premier média trouvé ou liste vide
	"""
	wp_api = WordpressMedia(server=server)
	response = wp_api.get_list({"search": name})
	if response.status_code == 200:
		results = response.json()
		return results[0] if results else []
	return []

def create_image(data, server=None, headers={}):
	"""
	Crée une nouvelle image dans la bibliothèque média
	Args:
		data: Données de l'image (fichier)
		server: Instance du serveur WooCommerce (optionnel)
		headers: En-têtes HTTP additionnels
	Returns:
		Réponse de l'API WordPress
	"""
	wp_api = WordpressMedia(server=server)
	return wp_api.create_img(data, headers)

def delete_image(media_id, server=None):
	"""
	Supprime une image de la bibliothèque média
	Args:
		media_id: ID du média à supprimer
		server: Instance du serveur WooCommerce (optionnel)
	Returns:
		Réponse de l'API WordPress
	"""
	wp_api = WordpressMedia(server=server)
	return wp_api.delete_img(media_id)