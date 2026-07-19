/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/pt", [], () => ({
		errorLoading: () => "Os resultados não puderam ser carregados.",
		inputTooLong: (e) => {
			var r = e.input.length - e.maximum,
				n = "Por favor apague " + r + " ";
			return (n += 1 != r ? "caracteres" : "caractere");
		},
		inputTooShort: (e) =>
			"Introduza " + (e.minimum - e.input.length) + " ou mais caracteres",
		loadingMore: () => "A carregar mais resultados…",
		maximumSelected: (e) => {
			var r = "Apenas pode seleccionar " + e.maximum + " ";
			return (r += 1 != e.maximum ? "itens" : "item");
		},
		noResults: () => "Sem resultados",
		searching: () => "A procurar…",
		removeAllItems: () => "Remover todos os itens",
	})),
		e.define,
		e.require;
})();
