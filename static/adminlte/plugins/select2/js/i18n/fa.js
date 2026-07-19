/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/fa", [], () => ({
		errorLoading: () => "امکان بارگذاری نتایج وجود ندارد.",
		inputTooLong: (n) =>
			"لطفاً " + (n.input.length - n.maximum) + " کاراکتر را حذف نمایید",
		inputTooShort: (n) =>
			"لطفاً تعداد " +
			(n.minimum - n.input.length) +
			" کاراکتر یا بیشتر وارد نمایید",
		loadingMore: () => "در حال بارگذاری نتایج بیشتر...",
		maximumSelected: (n) =>
			"شما تنها می‌توانید " + n.maximum + " آیتم را انتخاب نمایید",
		noResults: () => "هیچ نتیجه‌ای یافت نشد",
		searching: () => "در حال جستجو...",
		removeAllItems: () => "همه موارد را حذف کنید",
	})),
		n.define,
		n.require;
})();
