/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/ar", [], () => ({
		errorLoading: () => "لا يمكن تحميل النتائج",
		inputTooLong: (n) =>
			"الرجاء حذف " + (n.input.length - n.maximum) + " عناصر",
		inputTooShort: (n) =>
			"الرجاء إضافة " + (n.minimum - n.input.length) + " عناصر",
		loadingMore: () => "جاري تحميل نتائج إضافية...",
		maximumSelected: (n) => "تستطيع إختيار " + n.maximum + " بنود فقط",
		noResults: () => "لم يتم العثور على أي نتائج",
		searching: () => "جاري البحث…",
		removeAllItems: () => "قم بإزالة كل العناصر",
	})),
		n.define,
		n.require;
})();
