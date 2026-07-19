/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/ro", [], () => ({
		errorLoading: () => "Rezultatele nu au putut fi incărcate.",
		inputTooLong: (e) => {
			var t = e.input.length - e.maximum,
				n = "Vă rugăm să ștergeți" + t + " caracter";
			return 1 !== t && (n += "e"), n;
		},
		inputTooShort: (e) =>
			"Vă rugăm să introduceți " +
			(e.minimum - e.input.length) +
			" sau mai multe caractere",
		loadingMore: () => "Se încarcă mai multe rezultate…",
		maximumSelected: (e) => {
			var t = "Aveți voie să selectați cel mult " + e.maximum;
			return (t += " element"), 1 !== e.maximum && (t += "e"), t;
		},
		noResults: () => "Nu au fost găsite rezultate",
		searching: () => "Căutare…",
		removeAllItems: () => "Eliminați toate elementele",
	})),
		e.define,
		e.require;
})();
