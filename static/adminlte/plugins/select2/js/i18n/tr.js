/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/tr", [], () => ({
		errorLoading: () => "Sonuç yüklenemedi",
		inputTooLong: (n) =>
			n.input.length - n.maximum + " karakter daha girmelisiniz",
		inputTooShort: (n) =>
			"En az " + (n.minimum - n.input.length) + " karakter daha girmelisiniz",
		loadingMore: () => "Daha fazla…",
		maximumSelected: (n) => "Sadece " + n.maximum + " seçim yapabilirsiniz",
		noResults: () => "Sonuç bulunamadı",
		searching: () => "Aranıyor…",
		removeAllItems: () => "Tüm öğeleri kaldır",
	})),
		n.define,
		n.require;
})();
