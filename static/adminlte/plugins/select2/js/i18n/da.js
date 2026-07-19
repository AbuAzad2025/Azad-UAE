/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/da", [], () => ({
		errorLoading: () => "Resultaterne kunne ikke indlæses.",
		inputTooLong: (e) =>
			"Angiv venligst " + (e.input.length - e.maximum) + " tegn mindre",
		inputTooShort: (e) =>
			"Angiv venligst " + (e.minimum - e.input.length) + " tegn mere",
		loadingMore: () => "Indlæser flere resultater…",
		maximumSelected: (e) => {
			var n = "Du kan kun vælge " + e.maximum + " emne";
			return 1 != e.maximum && (n += "r"), n;
		},
		noResults: () => "Ingen resultater fundet",
		searching: () => "Søger…",
		removeAllItems: () => "Fjern alle elementer",
	})),
		e.define,
		e.require;
})();
