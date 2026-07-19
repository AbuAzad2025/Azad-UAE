/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/sr", [], () => {
		function n(n, e, r, t) {
			return n % 10 == 1 && n % 100 != 11
				? e
				: n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)
					? r
					: t;
		}
		return {
			errorLoading: () => "Preuzimanje nije uspelo.",
			inputTooLong: (e) => {
				var r = e.input.length - e.maximum,
					t = "Obrišite " + r + " simbol";
				return (t += n(r, "", "a", "a"));
			},
			inputTooShort: (e) => {
				var r = e.minimum - e.input.length,
					t = "Ukucajte bar još " + r + " simbol";
				return (t += n(r, "", "a", "a"));
			},
			loadingMore: () => "Preuzimanje još rezultata…",
			maximumSelected: (e) => {
				var r = "Možete izabrati samo " + e.maximum + " stavk";
				return (r += n(e.maximum, "u", "e", "i"));
			},
			noResults: () => "Ništa nije pronađeno",
			searching: () => "Pretraga…",
			removeAllItems: () => "Уклоните све ставке",
		};
	}),
		n.define,
		n.require;
})();
