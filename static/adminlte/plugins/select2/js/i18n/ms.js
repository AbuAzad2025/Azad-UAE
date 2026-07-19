/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/ms", [], () => ({
		errorLoading: () => "Keputusan tidak berjaya dimuatkan.",
		inputTooLong: (n) =>
			"Sila hapuskan " + (n.input.length - n.maximum) + " aksara",
		inputTooShort: (n) =>
			"Sila masukkan " + (n.minimum - n.input.length) + " atau lebih aksara",
		loadingMore: () => "Sedang memuatkan keputusan…",
		maximumSelected: (n) =>
			"Anda hanya boleh memilih " + n.maximum + " pilihan",
		noResults: () => "Tiada padanan yang ditemui",
		searching: () => "Mencari…",
		removeAllItems: () => "Keluarkan semua item",
	})),
		n.define,
		n.require;
})();
