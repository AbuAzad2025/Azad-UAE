(() => {
	function initTable() {
		if (!window.jQuery?.fn.DataTable) return;
		const $ = window.jQuery;
		const $table = $("#receiptsTable");
		if (!$table.length) return;
		const languageUrl = $table.data("langUrl") || "/static/datatables/Arabic.json";
		$table.DataTable({
			language: { url: languageUrl },
			order: [[2, "desc"]],
			pageLength: 25,
		});
	}

	function bindPrintButtons() {
		document.querySelectorAll(".js-print-receipt").forEach((btn) => {
			btn.addEventListener("click", () => {
				const printUrl = btn.getAttribute("data-print-url");
				if (window.ActionHelpers) {
					window.ActionHelpers.openPrintWindow(printUrl);
				} else if (printUrl) {
					window.open(printUrl, "_blank");
				}
			});
		});
	}

	function init() {
		initTable();
		bindPrintButtons();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
