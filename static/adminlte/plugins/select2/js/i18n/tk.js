/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/tk", [], () => ({
		errorLoading: () => "Netije ýüklenmedi.",
		inputTooLong: (e) => e.input.length - e.maximum + " harp bozuň.",
		inputTooShort: (e) =>
			"Ýene-de iň az " + (e.minimum - e.input.length) + " harp ýazyň.",
		loadingMore: () => "Köpräk netije görkezilýär…",
		maximumSelected: (e) => "Diňe " + e.maximum + " sanysyny saýlaň.",
		noResults: () => "Netije tapylmady.",
		searching: () => "Gözlenýär…",
		removeAllItems: () => "Remove all items",
	})),
		e.define,
		e.require;
})();
