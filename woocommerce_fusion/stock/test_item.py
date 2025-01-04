import unittest
import frappe
from woocommerce_fusion.stock.item import get_woocommerce_product

class TestStockItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test data
        if not frappe.db.exists("Item", "_Test Item WC"):
            item = frappe.get_doc({
                "doctype": "Item",
                "item_code": "_Test Item WC",
                "item_name": "Test Item WC",
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 1
            })
            item.insert()

        if not frappe.db.exists("WooCommerce Server", "_Test Server"):
            wc_server = frappe.get_doc({
                "doctype": "WooCommerce Server",
                "woocommerce_server_name": "_Test Server",
                "woocommerce_server_url": "https://test.example.com",
                "api_consumer_key": "test_key",
                "api_consumer_secret": "test_secret",
                "enable_sync": 1
            })
            wc_server.insert()

        # Link item to WooCommerce server
        item = frappe.get_doc("Item", "_Test Item WC")
        item.append("woocommerce_servers", {
            "woocommerce_server": "_Test Server",
            "woocommerce_id": "123",
            "enabled": 1
        })
        item.save()

    def test_get_woocommerce_product_with_valid_item(self):
        # Test with valid item
        result = get_woocommerce_product("_Test Item WC")
        self.assertTrue(isinstance(result, list))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["server"], "_Test Server")
        self.assertTrue("url" in result[0])
        self.assertTrue("wrapper=1" in result[0]["url"])

    def test_get_woocommerce_product_with_invalid_item(self):
        # Test with non-existent item
        result = get_woocommerce_product("NonExistentItem")
        self.assertTrue(isinstance(result, dict))
        self.assertTrue("error" in result)

    def test_get_woocommerce_product_with_multiple_servers(self):
        # Create second test server
        if not frappe.db.exists("WooCommerce Server", "_Test Server 2"):
            wc_server = frappe.get_doc({
                "doctype": "WooCommerce Server",
                "woocommerce_server_name": "_Test Server 2",
                "woocommerce_server_url": "https://test2.example.com",
                "api_consumer_key": "test_key_2",
                "api_consumer_secret": "test_secret_2",
                "enable_sync": 1
            })
            wc_server.insert()

        # Link item to second server
        item = frappe.get_doc("Item", "_Test Item WC")
        item.append("woocommerce_servers", {
            "woocommerce_server": "_Test Server 2",
            "woocommerce_id": "456",
            "enabled": 1
        })
        item.save()

        # Test with multiple servers
        result = get_woocommerce_product("_Test Item WC")
        self.assertTrue(isinstance(result, list))
        self.assertEqual(len(result), 2)
        server_names = [r["server"] for r in result]
        self.assertTrue("_Test Server" in server_names)
        self.assertTrue("_Test Server 2" in server_names)

    @classmethod
    def tearDownClass(cls):
        # Clean up test data
        if frappe.db.exists("Item", "_Test Item WC"):
            frappe.delete_doc("Item", "_Test Item WC")
        if frappe.db.exists("WooCommerce Server", "_Test Server"):
            frappe.delete_doc("WooCommerce Server", "_Test Server")
        if frappe.db.exists("WooCommerce Server", "_Test Server 2"):
            frappe.delete_doc("WooCommerce Server", "_Test Server 2")
