/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/ru", [], () => {
		function n(n, e, r, u) {
			return (n % 10 < 5 && n % 10 > 0 && n % 100 < 5) || n % 100 > 20
				? n % 10 > 1
					? r
					: e
				: u;
		}
		return {
			errorLoading: () => "Невозможно загрузить результаты",
			inputTooLong: (e) => {
				var r = e.input.length - e.maximum,
					u = "Пожалуйста, введите на " + r + " символ";
				return (u += n(r, "", "a", "ов")), (u += " меньше");
			},
			inputTooShort: (e) => {
				var r = e.minimum - e.input.length,
					u = "Пожалуйста, введите ещё хотя бы " + r + " символ";
				return (u += n(r, "", "a", "ов"));
			},
			loadingMore: () => "Загрузка данных…",
			maximumSelected: (e) => {
				var r = "Вы можете выбрать не более " + e.maximum + " элемент";
				return (r += n(e.maximum, "", "a", "ов"));
			},
			noResults: () => "Совпадений не найдено",
			searching: () => "Поиск…",
			removeAllItems: () => "Удалить все элементы",
		};
	}),
		n.define,
		n.require;
})();
