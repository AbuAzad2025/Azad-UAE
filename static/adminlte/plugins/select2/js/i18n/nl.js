/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/nl", [], () => ({
		errorLoading: () => "De resultaten konden niet worden geladen.",
		inputTooLong: (e) =>
			"Gelieve " + (e.input.length - e.maximum) + " karakters te verwijderen",
		inputTooShort: (e) =>
			"Gelieve " +
			(e.minimum - e.input.length) +
			" of meer karakters in te voeren",
		loadingMore: () => "Meer resultaten laden…",
		maximumSelected: (e) => {
			var n = 1 == e.maximum ? "kan" : "kunnen",
				r = "Er " + n + " maar " + e.maximum + " item";
			return 1 != e.maximum && (r += "s"), (r += " worden geselecteerd");
		},
		noResults: () => "Geen resultaten gevonden…",
		searching: () => "Zoeken…",
		removeAllItems: () => "Verwijder alle items",
	})),
		e.define,
		e.require;
})();
