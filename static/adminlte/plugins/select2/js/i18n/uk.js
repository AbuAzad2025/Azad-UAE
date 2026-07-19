/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/uk", [], () => {
		function n(n, e, u, r) {
			return n % 100 > 10 && n % 100 < 15
				? r
				: n % 10 == 1
					? e
					: n % 10 > 1 && n % 10 < 5
						? u
						: r;
		}
		return {
			errorLoading: () => "Неможливо завантажити результати",
			inputTooLong: (e) =>
				"Будь ласка, видаліть " +
				(e.input.length - e.maximum) +
				" " +
				n(e.maximum, "літеру", "літери", "літер"),
			inputTooShort: (n) =>
				"Будь ласка, введіть " +
				(n.minimum - n.input.length) +
				" або більше літер",
			loadingMore: () => "Завантаження інших результатів…",
			maximumSelected: (e) =>
				"Ви можете вибрати лише " +
				e.maximum +
				" " +
				n(e.maximum, "пункт", "пункти", "пунктів"),
			noResults: () => "Нічого не знайдено",
			searching: () => "Пошук…",
			removeAllItems: () => "Видалити всі елементи",
		};
	}),
		n.define,
		n.require;
})();
