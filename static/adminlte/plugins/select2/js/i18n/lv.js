/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/lv", [], () => {
		function e(e, n, u, i) {
			return 11 === e ? n : e % 10 == 1 ? u : i;
		}
		return {
			inputTooLong: (n) => {
				var u = n.input.length - n.maximum,
					i = "Lūdzu ievadiet par  " + u;
				return (i += " simbol" + e(u, "iem", "u", "iem")) + " mazāk";
			},
			inputTooShort: (n) => {
				var u = n.minimum - n.input.length,
					i = "Lūdzu ievadiet vēl " + u;
				return (i += " simbol" + e(u, "us", "u", "us"));
			},
			loadingMore: () => "Datu ielāde…",
			maximumSelected: (n) => {
				var u = "Jūs varat izvēlēties ne vairāk kā " + n.maximum;
				return (u += " element" + e(n.maximum, "us", "u", "us"));
			},
			noResults: () => "Sakritību nav",
			searching: () => "Meklēšana…",
			removeAllItems: () => "Noņemt visus vienumus",
		};
	}),
		e.define,
		e.require;
})();
