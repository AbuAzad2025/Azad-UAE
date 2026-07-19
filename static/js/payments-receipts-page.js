(() => {
	function bindArchiveButtons() {
		document.querySelectorAll(".js-archive-payment").forEach((btn) => {
			btn.addEventListener("click", () => {
				const type = btn.getAttribute("data-item-type") || "payment";
				const id = btn.getAttribute("data-item-id");
				const number = btn.getAttribute("data-item-number") || "";
				if (!id || !window.ActionHelpers) return;
				window.ActionHelpers.archivePaymentItem(type, id, number);
			});
		});
	}

	function initTableAndSmartPrint() {
		if (!window.jQuery?.fn.DataTable) return;
		const $ = window.jQuery;
		const $tableEl = $("#receiptsTable");
		if (!$tableEl.length) return;

		const languageUrl = $tableEl.data("langUrl") || "/static/datatables/Arabic.json";
		const printOptions = {
			title: "جميع المدفوعات",
			headerColor: "#198754",
		};

		let table;
		if ($.fn.DataTable.isDataTable($tableEl)) {
			table = $tableEl.DataTable();
		} else {
			table = $tableEl.DataTable({
				language: { url: languageUrl },
				order: [[2, "desc"]],
				pageLength: 25,
				dom: "Bfrtip",
				buttons: window.SmartPrint ? window.SmartPrint.buildButtons(printOptions) : [],
			});
		}

		if (!$tableEl.data("smartPrintInit") && window.SmartPrint) {
			window.SmartPrint.attachTrigger(table, "#printReceiptsBtn", printOptions);
			$tableEl.data("smartPrintInit", true);
		}
	}

	function init() {
		bindArchiveButtons();
		initTableAndSmartPrint();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
