$(document).ready(() => {
	const $tableEl = $("#salesTable");
	if (!$tableEl.length) return;
	const _t = (k) => (typeof window.t === "function" ? window.t(k) : k);
	// Guard: DataTables may be lazy-loaded; wait if not ready
	if (typeof $.fn.DataTable === "undefined") {
		if (window.lazyLoad && typeof window.lazyLoad.datatables === "function") {
			window.lazyLoad.datatables().then(() => $(document).ready(() => $tableEl.DataTable && $tableEl.DataTable()));
		}
		return;
	}
	const printOptions = {
		title: _t("sales_register"),
		headerColor: "#007A3D",
	};
	let table;
	try {
		if ($.fn.DataTable.isDataTable($tableEl)) {
			table = $tableEl.DataTable();
		} else {
			table = $tableEl.DataTable({
				language: {
					url: window._DATATABLES_LANG_URL || "/static/datatables/Arabic.json",
				},
				order: [[2, "desc"]],
				pageLength: 25,
				responsive: true,
				dom: "Bfrtip",
				buttons: SmartPrint.buildButtons(printOptions),
				columnDefs: [{ responsivePriority: 1, targets: -1 }],
				// noinspection JSUnusedGlobalSymbols
				footerCallback: function () {
				const api = this.api();
				const firstNumber = (html) => {
					const m = String(html).match(/[\d,]*\.?\d+/);
					const val = m ? parseFloat(m[0].replace(/,/g, "")) : 0;
					return Number.isNaN(val) ? 0 : val;
				};
				const sumCents = (cells) =>
					cells.reduce((acc, raw) => acc + Math.round(firstNumber(raw) * 100), 0) / 100;
				const total = sumCents(api.column(3, { page: "current" }).data());
				const paid = sumCents(api.column(4, { page: "current" }).data());
				const info = `${_t("page_total")}: ${total.toFixed(2)} | ${_t("paid_status")}: ${paid.toFixed(2)}`;
				window.azad && typeof window.azad.showInfo === "function"
					? window.azad.showInfo(info)
					: console.info(info);
			},
		});
	}
	if (!$tableEl.data("smartPrintInit")) {
		SmartPrint.attachTrigger(table, "#printSalesBtn", printOptions);
		$tableEl.data("smartPrintInit", true);
	}
	$("#filterAll")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			if (!table) return;
			table.search("").draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterPaid")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			if (!table) return;
			table.column(8).search(_t("paid_status")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterPartial")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			if (!table) return;
			table.column(8).search(_t("partial")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterUnpaid")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			if (!table) return;
			table.column(8).search(_t("unpaid_status")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	} catch (e) {
		console.warn("DataTables init failed:", e.message);
	}
});
