frappe.ui.form.on('Item', {
	refresh: function(frm) {
		// Add button to view WooCommerce Product
		if (frm.doc.woocommerce_servers && frm.doc.woocommerce_servers.length > 0) {
			// Add a custom button to sync Item Stock with WooCommerce
			frm.add_custom_button(__("Sync this Item's Stock Levels to WooCommerce"), function () {
				frm.trigger("sync_item_stock");
			}, __('Actions'));

			// Add a custom button to sync Item Price with WooCommerce
			frm.add_custom_button(__("Sync this Item's Price to WooCommerce"), function () {
				frm.trigger("sync_item_price");
			}, __('Actions'));

			// Add a custom button to sync Item with WooCommerce
			frm.add_custom_button(__("Sync this Item with WooCommerce"), function () {
				frm.trigger("sync_item");
			}, __('Actions'));

			frm.add_custom_button(__('View WooCommerce Product'), function() {
				// Get WooCommerce Product details
				frappe.call({
					method: 'woocommerce_fusion.stock.item.get_woocommerce_product',
					args: {
						item_code: frm.doc.name
					},
					callback: function(r) {
						if (r.message.error) {
							frappe.msgprint(r.message.error);
							return;
						}

						let products = r.message;
						if (products.length === 0) {
							frappe.msgprint(__('No WooCommerce Product found for this item'));
							return;
						}

						// Create dialog content
						let dialog_content = '<div class="woocommerce-iframe">';
						
						// Add CSS to hide unwanted elements
						dialog_content += `
							<style>
								.woocommerce-iframe iframe {
									width: 100%;
									height: 800px;
									border: none;
								}
								/* Hide elements in iframe */
								.woocommerce-iframe iframe {
									opacity: 0;
									transition: opacity 0.3s;
								}
								.woocommerce-iframe iframe.loaded {
									opacity: 1;
								}
							</style>
						`;
						
						// If multiple products, add tabs
						if (products.length > 1) {
							dialog_content += '<ul class="nav nav-tabs" role="tablist">';
							products.forEach(function(p, index) {
								dialog_content += `
									<li class="nav-item" role="presentation">
										<a class="nav-link ${index === 0 ? 'active' : ''}" 
										   id="tab-${index}" 
										   data-toggle="tab" 
										   href="#content-${index}" 
										   role="tab">
											${p.server}
										</a>
									</li>`;
							});
							dialog_content += '</ul>';
							
							dialog_content += '<div class="tab-content">';
							products.forEach(function(p, index) {
								dialog_content += `
									<div class="tab-pane fade ${index === 0 ? 'show active' : ''}" 
										 id="content-${index}" 
										 role="tabpanel">
										<iframe src="${p.url}"
												onload="(function(iframe) {
													var style = iframe.contentDocument.createElement('style');
													style.textContent = 'header, .page-head, .page-breadcrumbs, .layout-side-section, .sticky-top, .page-title .sidebar-toggle-btn { display: none !important; } .layout-main-section { width: 100% !important; padding: 0 !important; } .form-layout { margin: 0 !important; } .page-head { top: 0 !important; } .form-tabs-list { position: inherit !important; } body.full-width .container { width: 100% !important; }';
													iframe.contentDocument.head.appendChild(style);
													iframe.classList.add('loaded');
												})(this)"
												title="WooCommerce Product Editor">
										</iframe>
									</div>`;
							});
							dialog_content += '</div>';
						} else {
							// Single product
							dialog_content += `
								<iframe src="${products[0].url}"
										onload="(function(iframe) {
											var style = iframe.contentDocument.createElement('style');
											style.textContent = 'header, .page-head, .page-breadcrumbs, .layout-side-section, .sticky-top, .page-title .sidebar-toggle-btn { display: none !important; } .layout-main-section { width: 100% !important; padding: 0 !important; } .form-layout { margin: 0 !important; } .page-head { top: 0 !important; } .form-tabs-list { position: inherit !important; } body.full-width .container { width: 100% !important; }';
											iframe.contentDocument.head.appendChild(style);
											iframe.classList.add('loaded');
										})(this)"
										title="WooCommerce Product Editor">
								</iframe>`;
						}
						
						dialog_content += '</div>';

						// Show dialog
						let d = new frappe.ui.Dialog({
							title: __('WooCommerce Product'),
							fields: [{
								fieldtype: 'HTML',
								fieldname: 'product_view',
								options: dialog_content
							}]
						});
						
						// Make dialog larger
						d.$wrapper.find('.modal-dialog').css('max-width', '90%');
						d.$wrapper.find('.modal-body').css('height', '850px');
						d.show();
					}
				});
			}, __('View'));
		}
	},

	sync_item_stock: function(frm) {
		// Sync this Item
		frappe.dom.freeze(__("Sync Item Stock with WooCommerce..."));
		frappe.call({
			method: "woocommerce_fusion.tasks.stock_update.update_stock_levels_on_woocommerce_site",
			args: {
				item_code: frm.doc.name
			},
			callback: function(r) {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message:__('Synchronised stock level to WooCommerce for enabled servers'),
					indicator:'green'
				}, 5);
				frm.reload_doc();
			},
			error: (r) => {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message: __('There was an error processing the request. See Error Log.'),
					indicator: 'red'
				}, 5);
			}
		});
	},

	sync_item_price: function(frm) {
		// Sync this Item's Price
		frappe.dom.freeze(__("Sync Item Price with WooCommerce..."));
		frappe.call({
			method: "woocommerce_fusion.tasks.sync_item_prices.run_item_price_sync",
			args: {
				item_code: frm.doc.name
			},
			callback: function(r) {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message:__('Synchronised item price to WooCommerce'),
					indicator:'green'
				}, 5);
				frm.reload_doc();
			},
			error: (r) => {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message: __('There was an error processing the request. See Error Log.'),
					indicator: 'red'
				}, 5);
			}
		});
	},

	sync_item: function(frm) {
		// Sync this Item
		frappe.dom.freeze(__("Sync Item with WooCommerce..."));
		frappe.call({
			method: "woocommerce_fusion.tasks.sync_items.run_item_sync",
			args: {
				item_code: frm.doc.name
			},
			callback: function(r) {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message:__('Sync completed successfully'),
					indicator:'green'
				}, 5);
				frm.reload_doc();
			},
			error: (r) => {
				frappe.dom.unfreeze();
				frappe.show_alert({
					message: __('There was an error processing the request. See Error Log.'),
					indicator: 'red'
				}, 5);
			}
		});
	}
});

frappe.ui.form.on('Item WooCommerce Server', {
	view_product: function(frm, cdt, cdn) {
		let current_row_doc = locals[cdt][cdn];
		console.log(current_row_doc);
		frappe.set_route("Form", "WooCommerce Product", `${current_row_doc.woocommerce_server}~${current_row_doc.woocommerce_id}` );
	}
})