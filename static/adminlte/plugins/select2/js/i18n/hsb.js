/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/hsb", [], () => {
		var n = ["znamješko", "znamješce", "znamješka", "znamješkow"],
			e = ["zapisk", "zapiskaj", "zapiski", "zapiskow"],
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
			errorLoading: () => "Wuslědki njedachu so začitać.",
			inputTooLong: (e) => {
				var a = e.input.length - e.maximum;
				return "Prošu zhašej " + a + " " + u(a, n);
			},
			inputTooShort: (e) => {
				var a = e.minimum - e.input.length;
				return "Prošu zapodaj znajmjeńša " + a + " " + u(a, n);
			},
			loadingMore: () => "Dalše wuslědki so začitaja…",
			maximumSelected: (n) =>
				"Móžeš jenož " + n.maximum + " " + u(n.maximum, e) + "wubrać",
			noResults: () => "Žane wuslědki namakane",
			searching: () => "Pyta so…",
			removeAllItems: () => "Remove all items",
		};
	}),
		n.define,
		n.require;
})();
