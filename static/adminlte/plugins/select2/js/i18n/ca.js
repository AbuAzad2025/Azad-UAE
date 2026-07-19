/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/ca", [], () => ({
		errorLoading: () => "La càrrega ha fallat",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				r = "Si us plau, elimina " + n + " car";
			return (r += 1 == n ? "àcter" : "àcters");
		},
		inputTooShort: (e) => {
			var n = e.minimum - e.input.length,
				r = "Si us plau, introdueix " + n + " car";
			return (r += 1 == n ? "àcter" : "àcters");
		},
		loadingMore: () => "Carregant més resultats…",
		maximumSelected: (e) => {
			var n = "Només es pot seleccionar " + e.maximum + " element";
			return 1 != e.maximum && (n += "s"), n;
		},
		noResults: () => "No s'han trobat resultats",
		searching: () => "Cercant…",
		removeAllItems: () => "Treu tots els elements",
	})),
		e.define,
		e.require;
})();
