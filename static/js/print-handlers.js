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
	});
	if (
		new URLSearchParams(window.location.search).get("auto_print") === "true"
	) {
		window.addEventListener("DOMContentLoaded", () => {
			setTimeout(() => {
				window.print();
			}, 300);
		});
	}
})();
