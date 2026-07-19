(() => {
	var m = document.querySelector('meta[name="pos-config"]');
	if (m) {
		try {
			window.POS_CONFIG = JSON.parse(m.getAttribute("content"));
		} catch (_e) {}
	}
	window.POS_CONFIG = window.POS_CONFIG || {
		enable_tables: false,
		enable_hold: true,
	};
})();
