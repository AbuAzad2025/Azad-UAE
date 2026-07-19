/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/km", [], () => ({
		errorLoading: () => "មិនអាចទាញយកទិន្នន័យ",
		inputTooLong: (n) => "សូមលុបចេញ  " + (n.input.length - n.maximum) + " អក្សរ",
		inputTooShort: (n) =>
			"សូមបញ្ចូល" + (n.minimum - n.input.length) + " អក្សរ រឺ ច្រើនជាងនេះ",
		loadingMore: () => "កំពុងទាញយកទិន្នន័យបន្ថែម...",
		maximumSelected: (n) => "អ្នកអាចជ្រើសរើសបានតែ " + n.maximum + " ជម្រើសប៉ុណ្ណោះ",
		noResults: () => "មិនមានលទ្ធផល",
		searching: () => "កំពុងស្វែងរក...",
		removeAllItems: () => "លុបធាតុទាំងអស់",
	})),
		n.define,
		n.require;
})();
