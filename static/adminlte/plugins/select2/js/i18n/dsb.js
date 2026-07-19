/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/dsb", [], () => {
		var n = ["znamuško", "znamušce", "znamuška", "znamuškow"],
			e = ["zapisk", "zapiska", "zapiski", "zapiskow"],
			u = (n, e) =>
				1 === n
					? e[0]
					: 2 === n
						? e[1]
						: n > 2 && n <= 4
							? e[2]
							: n >= 5
								? e[3]
								: void 0;
		return {
			errorLoading: () => "Wuslědki njejsu se dali zacytaś.",
			inputTooLong: (e) => {
				var a = e.input.length - e.maximum;
				return "Pšosym lašuj " + a + " " + u(a, n);
			},
			inputTooShort: (e) => {
				var a = e.minimum - e.input.length;
				return "Pšosym zapódaj nanejmjenjej " + a + " " + u(a, n);
			},
			loadingMore: () => "Dalšne wuslědki se zacytaju…",
			maximumSelected: (n) =>
				"Móžoš jano " + n.maximum + " " + u(n.maximum, e) + "wubraś.",
			noResults: () => "Žedne wuslědki namakane",
			searching: () => "Pyta se…",
			removeAllItems: () => "Remove all items",
		};
	}),
		n.define,
		n.require;
})();
