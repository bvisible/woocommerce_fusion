// Copyright (c) 2023, Dirk van der Laarse and contributors
// For license information, please see license.txt

frappe.ui.form.on('WooCommerce Server', {
	refresh: function(frm) {
		// Only list enabled warehouses
		frm.fields_dict.warehouses.get_query = function (doc) {
			return {
				filters: {
					disabled: 0,
					is_group: 0
				}
			};
		}

		// Setup tax class field for grid
		frm.fields_dict['woocommerce_taxes'].grid.update_docfield_property(
			'tax_class',
			'fieldtype',
			'Select'
		);

		// Default options
		let tax_classes = ['standard', 'reduced-rate', 'zero-rate'];
		frm.fields_dict['woocommerce_taxes'].grid.update_docfield_property(
			'tax_class',
			'options',
			tax_classes.join('\n')
		);

		// Get tax classes from WooCommerce
		frappe.call({
			method: 'woocommerce_fusion.woocommerce.woocommerce_api.get_tax_classes',
			args: {
				woocommerce_server: frm.doc.name
			},
			callback: function(r) {
				if (r.message) {
					frm.fields_dict['woocommerce_taxes'].grid.update_docfield_property(
						'tax_class',
						'options',
						r.message
					);
					frm.refresh_field('woocommerce_taxes');
				}
			}
		});

		// Set the Options for erpnext_field_name field on 'Fields Mapping' child table
		frappe.call({
			method: "get_item_docfields",
			doc: frm.doc,
			callback: function(r) {
				// Sort the array of objects alphabetically by the label property
				r.message.sort((a, b) => a.label.localeCompare(b.label));

				// Use map to create an array of strings in the desired format
				const formattedStrings = r.message.map(fields => `${fields.fieldname} | ${fields.label}`);

				// Join the strings with newline characters to create the final string
				const options = formattedStrings.join('\n');

				// Set the Options property
				frm.fields_dict.item_field_map.grid.update_docfield_property(
					"erpnext_field_name",
					"options",
					options
				);
			}
		});

		if (frm.doc.enable_shipping_methods_sync) {
			frm.trigger('setup_shipping_methods');
		}

		if (frm.doc.enable_shipping_methods_sync && !frm.fields_dict.shipping_rule_map.grid.get_docfield("wc_shipping_method_id").options) {
			frm.trigger('get_shipping_methods');
		}

		if (frm.doc.enable_so_status_sync && !frm.fields_dict.sales_order_status_map.grid.get_docfield("woocommerce_sales_order_status").options) {
			frm.trigger('get_woocommerce_order_status_list');
		}

		// Add Get tax accounts button under woocommerce_taxes table
		frm.fields_dict['woocommerce_taxes'].grid.add_custom_button(__('Get tax accounts'), function() {
			// First get tax classes
			frappe.call({
				method: 'woocommerce_fusion.woocommerce.woocommerce_api.get_tax_classes',
				args: {
					woocommerce_server: frm.doc.name
				},
				callback: function(tax_classes_r) {
					if (tax_classes_r.message) {
						// Update tax_class field options
						frm.fields_dict['woocommerce_taxes'].grid.update_docfield_property(
							'tax_class',
							'options',
							tax_classes_r.message
						);
					}
					
					// Then get tax accounts
					frappe.call({
						method: 'woocommerce_fusion.woocommerce.woocommerce_api.sync_woocommerce_taxes',
						args: {
							woocommerce_server: frm.doc.name
						},
						callback: function(r) {
							if (r.message) {
								if (r.message.error) {
									frappe.msgprint({
										title: __('Error'),
										indicator: 'red',
										message: r.message.error
									});
								} else {
									// Display taxes in dialog
									let taxes_html = '<div><p>' + r.message.message + '</p><table class="table table-bordered table-hover">';
									taxes_html += '<thead><tr>' +
										'<th>ID</th>' +
										'<th>Name</th>' +
										'<th>Country</th>' +
										'<th>State</th>' +
										'<th>Rate</th>' +
										'<th>Class</th>' +
										'<th>Priority</th>' +
										'<th>Compound</th>' +
										'<th>Shipping</th>' +
										'</tr></thead><tbody>';
									
									r.message.taxes.forEach(function(tax) {
										taxes_html += `<tr>
											<td>${tax.woocommerce_tax_id}</td>
											<td>${tax.woocommerce_tax_name}</td>
											<td>${tax.country || '*'}</td>
											<td>${tax.state || '*'}</td>
											<td>${tax.rate}%</td>
											<td>${tax.tax_class}</td>
											<td>${tax.priority}</td>
											<td>${tax.compound ? '✓' : ''}</td>
											<td>${tax.shipping ? '✓' : ''}</td>
										</tr>`;
									});
									
									taxes_html += '</tbody></table></div>';
									
									let d = new frappe.ui.Dialog({
										title: __('WooCommerce Taxes'),
										fields: [{
											fieldtype: 'HTML',
											fieldname: 'taxes_html',
											options: taxes_html
										}],
										primary_action_label: __('Add to Table'),
										primary_action: function() {
											// Store existing accounts
											let existing_accounts = {};
											(frm.doc.woocommerce_taxes || []).forEach(function(tax) {
												existing_accounts[tax.woocommerce_tax_id] = tax.account;
											});
											
											// Clear existing rows
											frm.doc.woocommerce_taxes = [];
											
											// Add new rows
											r.message.taxes.forEach(function(tax) {
												let row = frm.add_child('woocommerce_taxes');
												row.woocommerce_tax_id = tax.woocommerce_tax_id;
												row.woocommerce_tax_name = tax.woocommerce_tax_name;
												row.country = tax.country;
												row.state = tax.state;
												row.rate = tax.rate;
												row.tax_class = tax.tax_class;
												row.priority = tax.priority;
												row.compound = tax.compound;
												row.shipping = tax.shipping;
												// Use existing account if available, otherwise use default
												row.account = existing_accounts[tax.woocommerce_tax_id] || r.message.default_tax_account;
											});
											
											frm.refresh_field('woocommerce_taxes');
											frappe.show_alert({
												message: __('Taxes added to table'),
												indicator: 'green'
											});
											d.hide();
										}
									});
									d.$wrapper.find('.modal-dialog').css('max-width', '90%');
									d.show();
								}
							}
						}
					});
				}
			});
		});

		// Add Update WooCommerce button under woocommerce_taxes table
		frm.fields_dict['woocommerce_taxes'].grid.add_custom_button(__('Update WooCommerce'), function() {
			let taxes = frm.doc.woocommerce_taxes || [];
			if (!taxes.length) {
				frappe.msgprint(__('No taxes to update'));
				return;
			}

			frappe.confirm(
				__('This will update the tax names, rates, and countries in WooCommerce. Continue?'),
				function() {
					frappe.call({
						method: 'woocommerce_fusion.woocommerce.woocommerce_api.update_woocommerce_taxes',
						args: {
							woocommerce_server: frm.doc.name,
							taxes: taxes
						},
						callback: function(r) {
							if (r.message) {
								if (r.message.error) {
									frappe.msgprint({
										title: __('Error'),
										indicator: 'red',
										message: r.message.error
									});
								} else {
									frappe.msgprint({
										title: __('Success'),
										indicator: 'green',
										message: r.message.message
									});
								}
							}
						}
					});
				}
			);
		});

		// Set Options field for 'Sales Order Status Sync' section
		warningHTML = `
			<div class="form-message red">
				<div>
					${__("This setting is Experimental. Monitor your Error Log after enabling this setting")}
				</div>
			</div>
			`
		frm.set_df_property('enable_so_status_sync_warning_html', 'options', warningHTML);
		frm.refresh_field('enable_so_status_sync_warning_html');

		// Add button click handler for WordPress connection test
		frm.page.add_action_item(__('Test WordPress Connection'), function() {
			frm.call({
				doc: frm.doc,
				method: 'test_wordpress_connection',
				freeze: true,
				freeze_message: __('Testing WordPress Connection...'),
			});
		});
	},

	setup_shipping_methods: function(frm) {
		console.log('Setting up shipping methods');

		// Setup shipping method title field for grid
		frm.fields_dict['shipping_rule_map'].grid.update_docfield_property(
			'wc_shipping_method_title',
			'fieldtype',
			'Select'
		);

		// Permettre temporairement la modification du champ ID
		frm.fields_dict['shipping_rule_map'].grid.update_docfield_property(
			'wc_shipping_method_id',
			'read_only',
			0
		);

		// Get shipping methods from WooCommerce
		frappe.call({
			method: 'woocommerce_fusion.woocommerce.doctype.woocommerce_server.woocommerce_server.get_shipping_methods',
			args: {
				'woocommerce_server': frm.doc.name
			},
			callback: function(r) {
				console.log('Received shipping methods:', r.message);
				if (!r.message) return;

				// Create a mapping of titles to method IDs
				const titleToId = {};
				r.message.forEach(method => {
					console.log('Processing method:', method);
					titleToId[method.title] = method.method_id;
				});

				// Update the options for the select field
				const titles = r.message.map(method => method.title);
				console.log('Setting options with titles:', titles);

				// Get the grid field
				const grid = frm.fields_dict['shipping_rule_map'].grid;
				console.log('Grid field:', grid);

				// Update the field properties
				grid.update_docfield_property(
					'wc_shipping_method_title',
					'options',
					titles.join('\n')
				);

				// Set up the field change handler
				frappe.ui.form.on('WooCommerce Server Shipping Rule', {
					wc_shipping_method_title: function(frm, cdt, cdn) {
						let row = locals[cdt][cdn];
						console.log('Title changed for row:', row);
						const methodId = titleToId[row.wc_shipping_method_title];
						console.log('Found method ID:', methodId, 'for title:', row.wc_shipping_method_title);
						
						if (methodId) {
							frappe.model.set_value(cdt, cdn, 'wc_shipping_method_id', methodId)
								.then(() => {
									console.log('Successfully updated method ID to:', methodId);
									// Remettre le champ en read_only après la mise à jour
									frm.fields_dict['shipping_rule_map'].grid.update_docfield_property(
										'wc_shipping_method_id',
										'read_only',
										1
									);
								})
								.catch((err) => {
									console.error('Error updating method ID:', err);
								});
						}
					}
				});

				frm.refresh_field('shipping_rule_map');
			}
		});
	},

	enable_shipping_methods_sync: function(frm) {
		if (frm.doc.enable_shipping_methods_sync) {
			console.log('Shipping methods sync enabled');
			frm.trigger('setup_shipping_methods');
		}
	},

	get_shipping_methods: function(frm){
		frappe.dom.freeze(__("Fetching Shipping Methods from WooCommerce"));
		frappe.call({
			method: "get_shipping_methods",
			doc: frm.doc,
			callback: function(r) {
				// Join the strings with newline characters to create the final string
				const options = r.message.join('\n');

				// Set the Options property
				frm.fields_dict.shipping_rule_map.grid.update_docfield_property(
					"wc_shipping_method_id",
					"options",
					options
				);

				frappe.dom.unfreeze();
			}
		});
	},

	get_woocommerce_order_status_list: function(frm){
		frappe.call({
			method: "get_woocommerce_order_status_list",
			doc: frm.doc,
			callback: function(r) {
				// Join the strings with newline characters to create the final string
				const options = r.message.join('\n');

				// Set the Options property
				frm.fields_dict.sales_order_status_map.grid.update_docfield_property(
					"woocommerce_sales_order_status",
					"options",
					options
				);
			}
		});
	},

	view_webhook_config: function(frm) {
		let d = new frappe.ui.Dialog({
			title: __('WooCommerce Webhook Settings'),
			fields: [
				{
					label: __('Status'),
					fieldname: 'status',
					fieldtype: 'Data',
					default: 'Active',
					read_only: 1
				},
				{
					label: __('Topic'),
					fieldname: 'topic',
					fieldtype: 'Data',
					default: 'Order created',
					read_only: 1
				},
				{
					label: __('Delivery URL'),
					fieldname: 'url',
					fieldtype: 'Data',
					default: '<site url here>/api/method/woocommerce_fusion.woocommerce_endpoint.order_created',
					read_only: 1
				},
				{
					label: __('Secret'),
					fieldname: 'secret',
					fieldtype: 'Code',
					default: frm.doc.secret,
					read_only: 1
				},
				{
					label: __('API Version'),
					fieldname: 'api_version',
					fieldtype: 'Data',
					default: 'WP REST API Integration v3',
					read_only: 1
				}
			],
			size: 'large', // small, large, extra-large
			primary_action_label: __('OK'),
			primary_action(values) {
				d.hide();
			}
		});

		d.show();

	}
});
