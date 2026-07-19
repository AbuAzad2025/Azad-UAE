/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/eu", [], () => ({
		inputTooLong: (e) => {
			var t = e.input.length - e.maximum,
				n = "Idatzi ";
			return (
				(n += 1 == t ? "karaktere bat" : t + " karaktere"), (n += " gutxiago")
			);
		},
		inputTooShort: (e) => {
			var t = e.minimum - e.input.length,
				n = "Idatzi ";
			return (
				(n += 1 == t ? "karaktere bat" : t + " karaktere"), (n += " gehiago")
			);
		},
		loadingMore: () => "Emaitza gehiago kargatzen…",
		maximumSelected: (e) =>
			1 === e.maximum
				? "Elementu bakarra hauta dezakezu"
				: e.maximum + " elementu hauta ditzakezu soilik",
		noResults: () => "Ez da bat datorrenik aurkitu",
		searching: () => "Bilatzen…",
		removeAllItems: () => "Kendu elementu guztiak",
	})),
		e.define,
		e.require;
})();
