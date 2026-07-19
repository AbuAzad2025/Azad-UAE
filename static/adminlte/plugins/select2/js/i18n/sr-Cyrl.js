/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/sr-Cyrl", [], () => {
		function n(n, e, r, u) {
			return n % 10 == 1 && n % 100 != 11
				? e
				: n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)
					? r
					: u;
		}
		return {
			errorLoading: () => "Преузимање није успело.",
			inputTooLong: (e) => {
				var r = e.input.length - e.maximum,
					u = "Обришите " + r + " симбол";
				return (u += n(r, "", "а", "а"));
			},
			inputTooShort: (e) => {
				var r = e.minimum - e.input.length,
					u = "Укуцајте бар још " + r + " симбол";
				return (u += n(r, "", "а", "а"));
			},
			loadingMore: () => "Преузимање још резултата…",
			maximumSelected: (e) => {
				var r = "Можете изабрати само " + e.maximum + " ставк";
				return (r += n(e.maximum, "у", "е", "и"));
			},
			noResults: () => "Ништа није пронађено",
			searching: () => "Претрага…",
			removeAllItems: () => "Уклоните све ставке",
		};
	}),
		n.define,
		n.require;
})();
