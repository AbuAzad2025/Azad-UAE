/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/az", [], () => ({
		inputTooLong: (n) => n.input.length - n.maximum + " simvol silin",
		inputTooShort: (n) => n.minimum - n.input.length + " simvol daxil edin",
		loadingMore: () => "Daha çox nəticə yüklənir…",
		maximumSelected: (n) => "Sadəcə " + n.maximum + " element seçə bilərsiniz",
		noResults: () => "Nəticə tapılmadı",
		searching: () => "Axtarılır…",
		removeAllItems: () => "Bütün elementləri sil",
	})),
		n.define,
		n.require;
})();
