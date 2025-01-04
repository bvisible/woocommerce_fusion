import unittest
import frappe
import json
from unittest.mock import Mock, patch
from woocommerce_fusion.wordpress.media import WordpressMedia, get_img_id, create_image, delete_image

class TestWordpressMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test WooCommerce server
        if not frappe.db.exists("WooCommerce Server", "_Test Server"):
            wc_server = frappe.get_doc({
                "doctype": "WooCommerce Server",
                "woocommerce_server_name": "_Test Server",
                "woocommerce_server_url": "https://test.example.com",
                "api_consumer_key": "test_key",
                "api_consumer_secret": "test_secret",
                "enable_sync": 1,
                "enable_sync_wp": 1
            })
            wc_server.insert()

    def setUp(self):
        self.server = frappe.get_doc("WooCommerce Server", "_Test Server")
        self.wp_media = WordpressMedia(server=self.server)

    @patch('woocommerce_fusion.wordpress.media.WordpressMedia.get')
    def test_get_img_id(self, mock_get):
        # Mock response for successful image search
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            "id": 123,
            "source_url": "https://test.example.com/image.jpg",
            "title": {"rendered": "Test Image"}
        }]
        mock_get.return_value = mock_response

        # Test successful image search
        result = get_img_id("image.jpg", server=self.server)
        self.assertEqual(result["id"], 123)
        mock_get.assert_called_with("media", params={"search": "image.jpg"})

        # Test empty response
        mock_response.json.return_value = []
        result = get_img_id("nonexistent.jpg", server=self.server)
        self.assertEqual(result, [])

    @patch('woocommerce_fusion.wordpress.media.WordpressMedia.post')
    def test_create_image(self, mock_post):
        # Mock response for successful image creation
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 456,
            "source_url": "https://test.example.com/new-image.jpg"
        }
        mock_post.return_value = mock_response

        # Test image creation
        test_data = {"file": ("test.jpg", b"test content", "image/jpeg")}
        result = create_image(test_data, server=self.server)
        self.assertEqual(result["id"], 456)
        mock_post.assert_called_with("media", files=test_data, headers={})

    @patch('woocommerce_fusion.wordpress.media.WordpressMedia.delete')
    def test_delete_image(self, mock_delete):
        # Mock response for successful image deletion
        mock_response = Mock()
        mock_response.status_code = 200
        mock_delete.return_value = mock_response

        # Test image deletion
        result = delete_image(789, server=self.server)
        self.assertEqual(result.status_code, 200)
        mock_delete.assert_called_with("media/789", params={"force": True})

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        # Clean up test data
        if frappe.db.exists("WooCommerce Server", "_Test Server"):
            frappe.delete_doc("WooCommerce Server", "_Test Server")
