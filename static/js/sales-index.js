$(document).ready(() => {
	const $tableEl = $("#salesTable");
	const printOptions = {
		title: window.t("sales_register"),
		headerColor: "#007A3D",
	};
	let table;
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
				const total = api
					.column(3, { page: "current" })
					.data()
					.reduce((a, b) => a + firstNumber(b), 0);
				const paid = api
					.column(4, { page: "current" })
					.data()
					.reduce((a, b) => a + firstNumber(b), 0);
				const info = `${window.t("page_total")}: ${total.toFixed(2)} | ${window.t("paid_status")}: ${paid.toFixed(2)}`;
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
			table.search("").draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterPaid")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			table.column(8).search(window.t("paid_status")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterPartial")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			table.column(8).search(window.t("partial")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
	$("#filterUnpaid")
		.off("click.smartPrint")
		.on("click.smartPrint", function () {
			table.column(8).search(window.t("unpaid_status")).draw();
			$(".btn-group .btn").removeClass("active");
			$(this).addClass("active");
		});
});
