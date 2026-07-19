/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/zh-TW", [], () => ({
		inputTooLong: (n) => "請刪掉" + (n.input.length - n.maximum) + "個字元",
		inputTooShort: (n) => "請再輸入" + (n.minimum - n.input.length) + "個字元",
		loadingMore: () => "載入中…",
		maximumSelected: (n) => "你只能選擇最多" + n.maximum + "項",
		noResults: () => "沒有找到相符的項目",
		searching: () => "搜尋中…",
		removeAllItems: () => "刪除所有項目",
	})),
		n.define,
		n.require;
})();
