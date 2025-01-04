import frappe
from frappe import _

@frappe.whitelist()
def get_woocommerce_product(item_code):
    """Get WooCommerce Product Frappe URL for the given Item"""
    # Get all WooCommerce Servers linked to this item
    item_wc_servers = frappe.get_all(
        "Item WooCommerce Server",
        filters={"parent": item_code, "enabled": 1},
        fields=["woocommerce_server", "woocommerce_id"]
    )
    
    if not item_wc_servers:
        return {"error": _("No WooCommerce Server linked to this item")}
    
    products = []
    for server in item_wc_servers:
        if not server.woocommerce_id:
            continue
            
        # Construct Frappe URL for WooCommerce Product with wrapper-1
        frappe_url = f"/app/woocommerce-product/{server.woocommerce_server}~{server.woocommerce_id}?wrapper=1"
        
        products.append({
            "server": server.woocommerce_server,
            "url": frappe_url
        })
    
    return products
