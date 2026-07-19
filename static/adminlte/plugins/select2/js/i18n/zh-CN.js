/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/zh-CN", [], () => ({
		errorLoading: () => "无法载入结果。",
		inputTooLong: (n) => "请删除" + (n.input.length - n.maximum) + "个字符",
		inputTooShort: (n) =>
			"请再输入至少" + (n.minimum - n.input.length) + "个字符",
		loadingMore: () => "载入更多结果…",
		maximumSelected: (n) => "最多只能选择" + n.maximum + "个项目",
		noResults: () => "未找到结果",
		searching: () => "搜索中…",
		removeAllItems: () => "删除所有项目",
	})),
		n.define,
		n.require;
})();
