/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/pt-BR", [], () => ({
		errorLoading: () => "Os resultados não puderam ser carregados.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				r = "Apague " + n + " caracter";
			return 1 != n && (r += "es"), r;
		},
		inputTooShort: (e) =>
			"Digite " + (e.minimum - e.input.length) + " ou mais caracteres",
		loadingMore: () => "Carregando mais resultados…",
		maximumSelected: (e) => {
			var n = "Você só pode selecionar " + e.maximum + " ite";
			return 1 == e.maximum ? (n += "m") : (n += "ns"), n;
		},
		noResults: () => "Nenhum resultado encontrado",
		searching: () => "Buscando…",
		removeAllItems: () => "Remover todos os itens",
	})),
		e.define,
		e.require;
})();
