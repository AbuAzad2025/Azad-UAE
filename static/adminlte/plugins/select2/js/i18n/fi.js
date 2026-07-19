/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/fi", [], () => ({
		errorLoading: () => "Tuloksia ei saatu ladattua.",
		inputTooLong: (n) =>
			"Ole hyvä ja anna " + (n.input.length - n.maximum) + " merkkiä vähemmän",
		inputTooShort: (n) =>
			"Ole hyvä ja anna " + (n.minimum - n.input.length) + " merkkiä lisää",
		loadingMore: () => "Ladataan lisää tuloksia…",
		maximumSelected: (n) => "Voit valita ainoastaan " + n.maximum + " kpl",
		noResults: () => "Ei tuloksia",
		searching: () => "Haetaan…",
		removeAllItems: () => "Poista kaikki kohteet",
	})),
		n.define,
		n.require;
})();
