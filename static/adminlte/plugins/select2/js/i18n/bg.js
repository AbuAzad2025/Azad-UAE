/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/bg", [], () => ({
		inputTooLong: (n) => {
			var e = n.input.length - n.maximum,
				u = "Моля въведете с " + e + " по-малко символ";
			return e > 1 && (u += "a"), u;
		},
		inputTooShort: (n) => {
			var e = n.minimum - n.input.length,
				u = "Моля въведете още " + e + " символ";
			return e > 1 && (u += "a"), u;
		},
		loadingMore: () => "Зареждат се още…",
		maximumSelected: (n) => {
			var e = "Можете да направите до " + n.maximum + " ";
			return n.maximum > 1 ? (e += "избора") : (e += "избор"), e;
		},
		noResults: () => "Няма намерени съвпадения",
		searching: () => "Търсене…",
		removeAllItems: () => "Премахнете всички елементи",
	})),
		n.define,
		n.require;
})();
