/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/nb", [], () => ({
		errorLoading: () => "Kunne ikke hente resultater.",
		inputTooLong: (e) =>
			"Vennligst fjern " + (e.input.length - e.maximum) + " tegn",
		inputTooShort: (e) =>
			"Vennligst skriv inn " + (e.minimum - e.input.length) + " tegn til",
		loadingMore: () => "Laster flere resultater…",
		maximumSelected: (e) => "Du kan velge maks " + e.maximum + " elementer",
		noResults: () => "Ingen treff",
		searching: () => "Søker…",
		removeAllItems: () => "Fjern alle elementer",
	})),
		e.define,
		e.require;
})();
