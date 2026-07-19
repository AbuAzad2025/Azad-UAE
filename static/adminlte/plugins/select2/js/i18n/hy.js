/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/hy", [], () => ({
		errorLoading: () => "Արդյունքները հնարավոր չէ բեռնել։",
		inputTooLong: (n) =>
			"Խնդրում ենք հեռացնել " + (n.input.length - n.maximum) + " նշան",
		inputTooShort: (n) =>
			"Խնդրում ենք մուտքագրել " +
			(n.minimum - n.input.length) +
			" կամ ավել նշաններ",
		loadingMore: () => "Բեռնվում են նոր արդյունքներ․․․",
		maximumSelected: (n) =>
			"Դուք կարող եք ընտրել առավելագույնը " + n.maximum + " կետ",
		noResults: () => "Արդյունքներ չեն գտնվել",
		searching: () => "Որոնում․․․",
		removeAllItems: () => "Հեռացնել բոլոր տարրերը",
	})),
		n.define,
		n.require;
})();
