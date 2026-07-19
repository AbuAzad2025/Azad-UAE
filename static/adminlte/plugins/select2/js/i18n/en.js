/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/en", [], () => ({
		errorLoading: () => "The results could not be loaded.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				r = "Please delete " + n + " character";
			return 1 != n && (r += "s"), r;
		},
		inputTooShort: (e) =>
			"Please enter " + (e.minimum - e.input.length) + " or more characters",
		loadingMore: () => "Loading more results…",
		maximumSelected: (e) => {
			var n = "You can only select " + e.maximum + " item";
			return 1 != e.maximum && (n += "s"), n;
		},
		noResults: () => "No results found",
		searching: () => "Searching…",
		removeAllItems: () => "Remove all items",
	})),
		e.define,
		e.require;
})();
