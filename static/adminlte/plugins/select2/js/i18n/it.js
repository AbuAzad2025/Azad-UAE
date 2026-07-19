/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/it", [], () => ({
		errorLoading: () => "I risultati non possono essere caricati.",
		inputTooLong: (e) => {
			var n = e.input.length - e.maximum,
				t = "Per favore cancella " + n + " caratter";
			return (t += 1 !== n ? "i" : "e");
		},
		inputTooShort: (e) =>
			"Per favore inserisci " +
			(e.minimum - e.input.length) +
			" o più caratteri",
		loadingMore: () => "Caricando più risultati…",
		maximumSelected: (e) => {
			var n = "Puoi selezionare solo " + e.maximum + " element";
			return 1 !== e.maximum ? (n += "i") : (n += "o"), n;
		},
		noResults: () => "Nessun risultato trovato",
		searching: () => "Sto cercando…",
		removeAllItems: () => "Rimuovi tutti gli oggetti",
	})),
		e.define,
		e.require;
})();
