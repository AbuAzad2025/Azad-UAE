/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/sv", [], () => ({
		errorLoading: () => "Resultat kunde inte laddas.",
		inputTooLong: (n) =>
			"Vänligen sudda ut " + (n.input.length - n.maximum) + " tecken",
		inputTooShort: (n) =>
			"Vänligen skriv in " +
			(n.minimum - n.input.length) +
			" eller fler tecken",
		loadingMore: () => "Laddar fler resultat…",
		maximumSelected: (n) => "Du kan max välja " + n.maximum + " element",
		noResults: () => "Inga träffar",
		searching: () => "Söker…",
		removeAllItems: () => "Ta bort alla objekt",
	})),
		n.define,
		n.require;
})();
