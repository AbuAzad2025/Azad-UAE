/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/sq", [], () => ({
		errorLoading: () => "Rezultatet nuk mund të ngarkoheshin.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				t = "Të lutem fshi " + n + " karakter";
			return 1 != n && (t += "e"), t;
		},
		inputTooShort: (e) =>
			"Të lutem shkruaj " +
			(e.minimum - e.input.length) +
			" ose më shumë karaktere",
		loadingMore: () => "Duke ngarkuar më shumë rezultate…",
		maximumSelected: (e) => {
			var n = "Mund të zgjedhësh vetëm " + e.maximum + " element";
			return 1 != e.maximum && (n += "e"), n;
		},
		noResults: () => "Nuk u gjet asnjë rezultat",
		searching: () => "Duke kërkuar…",
		removeAllItems: () => "Hiq të gjitha sendet",
	})),
		e.define,
		e.require;
})();
