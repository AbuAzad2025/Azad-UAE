/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/ka", [], () => ({
		errorLoading: () => "მონაცემების ჩატვირთვა შეუძლებელია.",
		inputTooLong: (n) =>
			"გთხოვთ აკრიფეთ " + (n.input.length - n.maximum) + " სიმბოლოთი ნაკლები",
		inputTooShort: (n) =>
			"გთხოვთ აკრიფეთ " + (n.minimum - n.input.length) + " სიმბოლო ან მეტი",
		loadingMore: () => "მონაცემების ჩატვირთვა…",
		maximumSelected: (n) =>
			"თქვენ შეგიძლიათ აირჩიოთ არაუმეტეს " + n.maximum + " ელემენტი",
		noResults: () => "რეზულტატი არ მოიძებნა",
		searching: () => "ძიება…",
		removeAllItems: () => "ამოიღე ყველა ელემენტი",
	})),
		n.define,
		n.require;
})();
