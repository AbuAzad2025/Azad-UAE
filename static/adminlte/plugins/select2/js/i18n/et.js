/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/et", [], () => ({
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				t = "Sisesta " + n + " täht";
			return 1 != n && (t += "e"), (t += " vähem");
		},
		inputTooShort: (e) => {
			var n = e.minimum - e.input.length,
				t = "Sisesta " + n + " täht";
			return 1 != n && (t += "e"), (t += " rohkem");
		},
		loadingMore: () => "Laen tulemusi…",
		maximumSelected: (e) => {
			var n = "Saad vaid " + e.maximum + " tulemus";
			return 1 == e.maximum ? (n += "e") : (n += "t"), (n += " valida");
		},
		noResults: () => "Tulemused puuduvad",
		searching: () => "Otsin…",
		removeAllItems: () => "Eemalda kõik esemed",
	})),
		e.define,
		e.require;
})();
