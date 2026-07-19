/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/vi", [], () => ({
		inputTooLong: (n) =>
			"Vui lòng xóa bớt " + (n.input.length - n.maximum) + " ký tự",
		inputTooShort: (n) =>
			"Vui lòng nhập thêm từ " +
			(n.minimum - n.input.length) +
			" ký tự trở lên",
		loadingMore: () => "Đang lấy thêm kết quả…",
		maximumSelected: (n) => "Chỉ có thể chọn được " + n.maximum + " lựa chọn",
		noResults: () => "Không tìm thấy kết quả",
		searching: () => "Đang tìm…",
		removeAllItems: () => "Xóa tất cả các mục",
	})),
		n.define,
		n.require;
})();
