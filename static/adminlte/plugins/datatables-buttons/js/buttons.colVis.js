/*!
 * Column visibility buttons for Buttons and DataTables.
 * 2016 SpryMedia Ltd - datatables.net/license
 */

((factory) => {
	if (typeof define === "function" && define.amd) {
		// AMD
		define(["jquery", "datatables.net", "datatables.net-buttons"], ($) =>
			factory($, window, document));
	} else if (typeof exports === "object") {
		// CommonJS
		module.exports = (root, $) => {
			if (!root) {
				root = window;
			}

			if (!$ || !$.fn.dataTable) {
				$ = require("datatables.net")(root, $).$;
			}

			if (!$.fn.dataTable.Buttons) {
				require("datatables.net-buttons")(root, $);
			}

			return factory($, root, root.document);
		};
	} else {
		// Browser
		factory(jQuery, window, document);
	}
})(($, window, document, undefined) => {
	var DataTable = $.fn.dataTable;

	$.extend(DataTable.ext.buttons, {
		// A collection of column visibility buttons
		colvis: (dt, conf) => {
			var node = null;
			var buttonConf = {
				extend: "collection",
				init: (dt, n) => {
					node = n;
				},
				text: (dt) => dt.i18n("buttons.colvis", "Column visibility"),
				className: "buttons-colvis",
				closeButton: false,
				buttons: [
					{
						extend: "columnsToggle",
						columns: conf.columns,
						columnText: conf.columnText,
					},
				],
			};

			// Rebuild the collection with the new column structure if columns are reordered
			dt.on("column-reorder.dt" + conf.namespace, (e, settings, details) => {
				// console.log(node);
				// console.log('node', dt.button(null, node).node());
				dt.button(null, dt.button(null, node).node()).collectionRebuild([
					{
						extend: "columnsToggle",
						columns: conf.columns,
						columnText: conf.columnText,
					},
				]);
			});

			return buttonConf;
		},

		// Selected columns with individual buttons - toggle column visibility
		columnsToggle: (dt, conf) => {
			var columns = dt
				.columns(conf.columns)
				.indexes()
				.map((idx) => ({
					extend: "columnToggle",
					columns: idx,
					columnText: conf.columnText,
				}))
				.toArray();

			return columns;
		},

		// Single button to toggle column visibility
		columnToggle: (dt, conf) => ({
			extend: "columnVisibility",
			columns: conf.columns,
			columnText: conf.columnText,
		}),

		// Selected columns with individual buttons - set column visibility
		columnsVisibility: (dt, conf) => {
			var columns = dt
				.columns(conf.columns)
				.indexes()
				.map((idx) => ({
					extend: "columnVisibility",
					columns: idx,
					visibility: conf.visibility,
					columnText: conf.columnText,
				}))
				.toArray();

			return columns;
		},

		// Single button to set column visibility
		columnVisibility: {
			columns: undefined, // column selector
			text: (dt, button, conf) => conf._columnText(dt, conf),
			className: "buttons-columnVisibility",
			action: (e, dt, button, conf) => {
				var col = dt.columns(conf.columns);
				var curr = col.visible();

				col.visible(
					conf.visibility !== undefined
						? conf.visibility
						: !(curr.length ? curr[0] : false),
				);
			},
			init: function (dt, button, conf) {
				button.attr("data-cv-idx", conf.columns);

				dt.on("column-visibility.dt" + conf.namespace, (e, settings) => {
					if (
						!settings.bDestroying &&
						settings.nTable == dt.settings()[0].nTable
					) {
						this.active(dt.column(conf.columns).visible());
					}
				}).on("column-reorder.dt" + conf.namespace, (e, settings, details) => {
					// Button has been removed from the DOM
					if (conf.destroying) {
						return;
					}

					if (dt.columns(conf.columns).count() !== 1) {
						return;
					}

					// This button controls the same column index but the text for the column has
					// changed
					this.text(conf._columnText(dt, conf));

					// Since its a different column, we need to check its visibility
					this.active(dt.column(conf.columns).visible());
				});

				this.active(dt.column(conf.columns).visible());
			},
			destroy: (dt, button, conf) => {
				dt.off("column-visibility.dt" + conf.namespace).off(
					"column-reorder.dt" + conf.namespace,
				);
			},

			_columnText: (dt, conf) => {
				// Use DataTables' internal data structure until this is presented
				// is a public API. The other option is to use
				// `$( column(col).node() ).text()` but the node might not have been
				// populated when Buttons is constructed.
				var idx = dt.column(conf.columns).index();
				var title = dt.settings()[0].aoColumns[idx].sTitle;

				if (!title) {
					title = dt.column(idx).header().innerHTML;
				}

				title = title
					.replace(/\n/g, " ") // remove new lines
					.replace(/<br\s*\/?>/gi, " ") // replace line breaks with spaces
					.replace(/<select(.*?)<\/select>/g, "") // remove select tags, including options text
					.replace(/<!--.*?-->/g, "") // strip HTML comments
					.replace(/<.*?>/g, "") // strip HTML
					.replace(/^\s+|\s+$/g, ""); // trim

				return conf.columnText ? conf.columnText(dt, idx, title) : title;
			},
		},

		colvisRestore: {
			className: "buttons-colvisRestore",

			text: (dt) => dt.i18n("buttons.colvisRestore", "Restore visibility"),

			init: (dt, button, conf) => {
				conf._visOriginal = dt
					.columns()
					.indexes()
					.map((idx) => dt.column(idx).visible())
					.toArray();
			},

			action: (e, dt, button, conf) => {
				dt.columns().every(function (i) {
					// Take into account that ColReorder might have disrupted our
					// indexes
					var idx =
						dt.colReorder && dt.colReorder.transpose
							? dt.colReorder.transpose(i, "toOriginal")
							: i;

					this.visible(conf._visOriginal[idx]);
				});
			},
		},

		colvisGroup: {
			className: "buttons-colvisGroup",

			action: (e, dt, button, conf) => {
				dt.columns(conf.show).visible(true, false);
				dt.columns(conf.hide).visible(false, false);

				dt.columns.adjust();
			},

			show: [],

			hide: [],
		},
	});

	return DataTable.Buttons;
});
