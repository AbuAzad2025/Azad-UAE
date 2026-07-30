(() => {
	document.addEventListener("click", (e) => {
		const btn = e.target.closest('[data-action="window-print"]');
		if (btn) {
			e.preventDefault();
			window.print();
		}
		const closeBtn = e.target.closest('[data-action="window-close"]');
		if (closeBtn) {
			e.preventDefault();
			window.close();
		}
		const backBtn = e.target.closest('[data-action="history-back"]');
		if (backBtn) {
			e.preventDefault();
			// Standalone print documents are often opened in a popup/tab:
			// go back when possible, otherwise close the window safely.
			if (window.history.length > 1) {
				window.history.back();
			} else {
				window.close();
			}
		}
	});
	if (new URLSearchParams(window.location.search).get("auto_print") === "true") {
		window.addEventListener("DOMContentLoaded", () => {
			setTimeout(() => {
				window.print();
			}, 300);
		});
	}
})();
