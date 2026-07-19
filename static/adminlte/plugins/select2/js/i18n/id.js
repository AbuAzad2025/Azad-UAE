/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/id", [], () => ({
		errorLoading: () => "Data tidak boleh diambil.",
		inputTooLong: (n) => "Hapuskan " + (n.input.length - n.maximum) + " huruf",
		inputTooShort: (n) =>
			"Masukkan " + (n.minimum - n.input.length) + " huruf lagi",
		loadingMore: () => "Mengambil data…",
		maximumSelected: (n) =>
			"Anda hanya dapat memilih " + n.maximum + " pilihan",
		noResults: () => "Tidak ada data yang sesuai",
		searching: () => "Mencari…",
		removeAllItems: () => "Hapus semua item",
	})),
		n.define,
		n.require;
})();
