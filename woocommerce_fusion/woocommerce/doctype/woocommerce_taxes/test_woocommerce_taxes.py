import unittest
import frappe
from frappe.test_runner import make_test_records

class TestWooCommerceTaxes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test account for taxes
        if not frappe.db.exists("Account", "_Test Tax Account - WC"):
            company = frappe.db.get_single_value('Global Defaults', 'default_company')
            if not company:
                company = frappe.get_all("Company")[0].name
            
            tax_account = frappe.get_doc({
                "doctype": "Account",
                "account_name": "_Test Tax Account - WC",
                "parent_account": f"Duties and Taxes - {frappe.get_cached_value('Company', company, 'abbr')}",
                "company": company,
                "account_type": "Tax",
                "is_group": 0
            })
            tax_account.insert()

    def setUp(self):
        # Create test tax record
        self.test_tax = frappe.get_doc({
            "doctype": "WooCommerce Taxes",
            "woocommerce_tax_id": 123,
            "woocommerce_tax_name": "_Test Tax",
            "country": "FR",
            "rate": 20.0,
            "tax_class": "standard",
            "account": "_Test Tax Account - WC"
        })
        self.test_tax.insert()

    def test_tax_creation(self):
        # Test if tax record was created correctly
        tax = frappe.get_doc("WooCommerce Taxes", self.test_tax.name)
        self.assertEqual(tax.woocommerce_tax_id, 123)
        self.assertEqual(tax.rate, 20.0)
        self.assertEqual(tax.country, "FR")
        self.assertEqual(tax.account, "_Test Tax Account - WC")

    def test_tax_validation(self):
        # Test tax rate validation
        with self.assertRaises(frappe.ValidationError):
            invalid_tax = frappe.get_doc({
                "doctype": "WooCommerce Taxes",
                "woocommerce_tax_id": 456,
                "woocommerce_tax_name": "_Test Invalid Tax",
                "country": "FR",
                "rate": -10.0,  # Invalid negative rate
                "tax_class": "standard",
                "account": "_Test Tax Account - WC"
            })
            invalid_tax.insert()

    def test_tax_update(self):
        # Test tax record update
        tax = frappe.get_doc("WooCommerce Taxes", self.test_tax.name)
        tax.rate = 25.0
        tax.save()
        
        updated_tax = frappe.get_doc("WooCommerce Taxes", self.test_tax.name)
        self.assertEqual(updated_tax.rate, 25.0)

    def test_tax_account_validation(self):
        # Test tax account validation
        with self.assertRaises(frappe.ValidationError):
            invalid_tax = frappe.get_doc({
                "doctype": "WooCommerce Taxes",
                "woocommerce_tax_id": 789,
                "woocommerce_tax_name": "_Test Invalid Tax Account",
                "country": "FR",
                "rate": 20.0,
                "tax_class": "standard",
                "account": "Invalid Account"  # Non-existent account
            })
            invalid_tax.insert()

    def tearDown(self):
        # Clean up test tax record
        if frappe.db.exists("WooCommerce Taxes", self.test_tax.name):
            frappe.delete_doc("WooCommerce Taxes", self.test_tax.name)

    @classmethod
    def tearDownClass(cls):
        # Clean up test account
        if frappe.db.exists("Account", "_Test Tax Account - WC"):
            frappe.delete_doc("Account", "_Test Tax Account - WC")
