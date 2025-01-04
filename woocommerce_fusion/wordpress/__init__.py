import frappe
import requests
import base64

class WordpressAPI:
	def __init__(self, server=None, version="wp-json", *args, **kwargs):
		if not server:
			server = frappe.get_doc("WooCommerce Server", {"enable_sync_wp": 1})
		self.server = server
		self.version = version +"/"

		if self.server.woocommerce_server_url and self.server.api_user_wp and self.server.api_application_code_wp:
			creds = self.server.api_user_wp + ":" + self.server.api_application_code_wp
			token = base64.b64encode(creds.encode())
			self.header = {'Authorization': 'Basic ' + token.decode('utf-8')}
			self.url = self.server.woocommerce_server_url + "/"

	def get(self, path, params={}):
		res = requests.get(self.url + self.version + path, headers=self.header,params=params)
		if res.status_code and int(res.status_code) > 399:
			frappe.log_error("response error get api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(params,res.text))
		#frappe.log_error("response get api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		return self.validate_response(res)

	def post(self, path, data={}, headers = {}, files = {}):
		new_headers = {**self.header, **headers}
		res = requests.post(self.url + self.version + path, headers=new_headers, data=data, files=files)
		if res.status_code and int(res.status_code) > 399:
			frappe.log_error("response error post api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		#frappe.log_error("response post api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		return self.validate_response(res)

	def put(self, path, data={}, headers = {}):
		new_headers = {**self.header, **headers}
		res = requests.put(self.url + self.version + path, headers=new_headers, data=data)
		if res.status_code and int(res.status_code) > 399:
			frappe.log_error("response error put api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		#frappe.log_error("response put api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		return self.validate_response(res)

	def delete(self, path, params={}):
		res = requests.delete(self.url + self.version + path, headers=self.header, params=params)
		if res.status_code and int(res.status_code) > 399:
			frappe.log_error("response error delete api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(params,res.text))
		#frappe.log_error("response delete api text","data:\n{0}\n\n\n\nResponse:\n{1}".format(data,res.text))
		return self.validate_response(res)

	def validate_response(self, response):
		response.raise_for_status()
		return response
