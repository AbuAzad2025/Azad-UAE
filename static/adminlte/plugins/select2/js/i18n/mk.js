/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/mk", [], () => ({
		inputTooLong: (n) => {
			var e =
				(n.input.length,
				n.maximum,
				"Ве молиме внесете " + n.maximum + " помалку карактер");
			return 1 !== n.maximum && (e += "и"), e;
		},
		inputTooShort: (n) => {
			var e =
				(n.minimum,
				n.input.length,
				"Ве молиме внесете уште " + n.maximum + " карактер");
			return 1 !== n.maximum && (e += "и"), e;
		},
		loadingMore: () => "Вчитување резултати…",
		maximumSelected: (n) => {
			var e = "Можете да изберете само " + n.maximum + " ставк";
			return 1 === n.maximum ? (e += "а") : (e += "и"), e;
		},
		noResults: () => "Нема пронајдено совпаѓања",
		searching: () => "Пребарување…",
		removeAllItems: () => "Отстрани ги сите предмети",
	})),
		n.define,
		n.require;
})();
