/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/sl", [], () => ({
		errorLoading: () => "Zadetkov iskanja ni bilo mogoče naložiti.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				t = "Prosim zbrišite " + n + " znak";
			return 2 == n ? (t += "a") : 1 != n && (t += "e"), t;
		},
		inputTooShort: (e) => {
			var n = e.minimum - e.input.length,
				t = "Prosim vpišite še " + n + " znak";
			return 2 == n ? (t += "a") : 1 != n && (t += "e"), t;
		},
		loadingMore: () => "Nalagam več zadetkov…",
		maximumSelected: (e) => {
			var n = "Označite lahko največ " + e.maximum + " predmet";
			return 2 == e.maximum ? (n += "a") : 1 != e.maximum && (n += "e"), n;
		},
		noResults: () => "Ni zadetkov.",
		searching: () => "Iščem…",
		removeAllItems: () => "Odstranite vse elemente",
	})),
		e.define,
		e.require;
})();
