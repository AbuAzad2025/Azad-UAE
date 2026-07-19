/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/fr", [], () => ({
		errorLoading: () => "Les résultats ne peuvent pas être chargés.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum;
			return "Supprimez " + n + " caractère" + (n > 1 ? "s" : "");
		},
		inputTooShort: (e) => {
			var n = e.minimum - e.input.length;
			return "Saisissez au moins " + n + " caractère" + (n > 1 ? "s" : "");
		},
		loadingMore: () => "Chargement de résultats supplémentaires…",
		maximumSelected: (e) =>
			"Vous pouvez seulement sélectionner " +
			e.maximum +
			" élément" +
			(e.maximum > 1 ? "s" : ""),
		noResults: () => "Aucun résultat trouvé",
		searching: () => "Recherche en cours…",
		removeAllItems: () => "Supprimer tous les éléments",
	})),
		e.define,
		e.require;
})();
