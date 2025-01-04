import frappe
from woocommerce_fusion.wordpress import WordpressAPI

class WordpressMedia(WordpressAPI):
	def __init__(self, server=None, version="wp-json/wp/v2", *args, **kwargs):
		super(WordpressMedia, self).__init__(server=server, version=version, *args, **kwargs)

	def get_list(self, params={}):
		"""Get the list of media with pagination"""
		return self.get("media", params=params)

	def create_img(self, data, headers={}):
		"""Create a new image in the media library"""
		return self.post("media", files=data, headers=headers).json()

	def delete_img(self, media_id):
		"""Delete an image from the media library"""
		return self.delete(f"media/{media_id}", params={"force": True})

def get_img_id(name, server=None):
	"""
	Search for an image by name in the media library
	Args:
		name: Name of the image to search for
		server: WooCommerce server instance (optional)
	Returns:
		First media found or empty list
	"""
	wp_api = WordpressMedia(server=server)
	response = wp_api.get_list({"search": name})
	if response.status_code == 200:
		results = response.json()
		return results[0] if results else []
	return []

def create_image(data, server=None, headers={}):
	"""
	Create a new image in the media library
	Args:
		data: Image data (file)
		server: WooCommerce server instance (optional)
		headers: Additional HTTP headers
	Returns:
		WordPress API response
	"""
	wp_api = WordpressMedia(server=server)
	return wp_api.create_img(data, headers)

def delete_image(media_id, server=None):
	"""
	Delete an image from the media library
	Args:
		media_id: ID of the media to delete
		server: WooCommerce server instance (optional)
	Returns:
		WordPress API response
	"""
	wp_api = WordpressMedia(server=server)
	return wp_api.delete_img(media_id)