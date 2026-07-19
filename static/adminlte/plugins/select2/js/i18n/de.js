/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/de", [], () => ({
		errorLoading: () => "Die Ergebnisse konnten nicht geladen werden.",
		inputTooLong: (e) =>
			"Bitte " + (e.input.length - e.maximum) + " Zeichen weniger eingeben",
		inputTooShort: (e) =>
			"Bitte " + (e.minimum - e.input.length) + " Zeichen mehr eingeben",
		loadingMore: () => "Lade mehr Ergebnisse…",
		maximumSelected: (e) => {
			var n = "Sie können nur " + e.maximum + " Element";
			return 1 != e.maximum && (n += "e"), (n += " auswählen");
		},
		noResults: () => "Keine Übereinstimmungen gefunden",
		searching: () => "Suche…",
		removeAllItems: () => "Entferne alle Elemente",
	})),
		e.define,
		e.require;
})();
