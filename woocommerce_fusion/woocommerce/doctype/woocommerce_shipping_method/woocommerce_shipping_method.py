# Copyright (c) 2024, Dirk van der Laarse and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from woocommerce_fusion.woocommerce.woocommerce_api import WooCommerceResource


class WooCommerceShippingMethod(WooCommerceResource):
	"""
	Virtual doctype for WooCommerce Shipping Methods
	"""

	doctype = "WooCommerce Shipping Method"
	resource: str = "shipping_methods"
	field_setter_map = {"woocommerce_id": "id"}

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_list(args):
		return WooCommerceShippingMethod.get_list_of_records(args)

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_count(args) -> int:
		return WooCommerceShippingMethod.get_count_of_records(args)

	def load_from_db(self):
		frappe.throw(_("This action is not supported for WooCommerce Shipping Methods"))
