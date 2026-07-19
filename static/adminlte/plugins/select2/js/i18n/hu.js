/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/hu", [], () => ({
		errorLoading: () => "Az eredmények betöltése nem sikerült.",
		inputTooLong: (e) =>
			"Túl hosszú. " +
			(e.input.length - e.maximum) +
			" karakterrel több, mint kellene.",
		inputTooShort: (e) =>
			"Túl rövid. Még " + (e.minimum - e.input.length) + " karakter hiányzik.",
		loadingMore: () => "Töltés…",
		maximumSelected: (e) => "Csak " + e.maximum + " elemet lehet kiválasztani.",
		noResults: () => "Nincs találat.",
		searching: () => "Keresés…",
		removeAllItems: () => "Távolítson el minden elemet",
	})),
		e.define,
		e.require;
})();
