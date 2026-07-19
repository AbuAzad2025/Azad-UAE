/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/af", [], () => ({
		errorLoading: () => "Die resultate kon nie gelaai word nie.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				r = "Verwyders asseblief " + n + " character";
			return 1 != n && (r += "s"), r;
		},
		inputTooShort: (e) =>
			"Voer asseblief " + (e.minimum - e.input.length) + " of meer karakters",
		loadingMore: () => "Meer resultate word gelaai…",
		maximumSelected: (e) => {
			var n = "Kies asseblief net " + e.maximum + " item";
			return 1 != e.maximum && (n += "s"), n;
		},
		noResults: () => "Geen resultate gevind",
		searching: () => "Besig…",
		removeAllItems: () => "Verwyder alle items",
	})),
		e.define,
		e.require;
})();
