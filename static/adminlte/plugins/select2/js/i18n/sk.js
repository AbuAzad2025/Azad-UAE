/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var e = jQuery.fn.select2.amd;
	e.define("select2/i18n/sk", [], () => {
		var e = { 2: (e) => (e ? "dva" : "dve"), 3: () => "tri", 4: () => "štyri" };
		return {
			errorLoading: () => "Výsledky sa nepodarilo načítať.",
			inputTooLong: (n) => {
				var t = n.input.length - n.maximum;
				return 1 == t
					? "Prosím, zadajte o jeden znak menej"
					: t >= 2 && t <= 4
						? "Prosím, zadajte o " + e[t](!0) + " znaky menej"
						: "Prosím, zadajte o " + t + " znakov menej";
			},
			inputTooShort: (n) => {
				var t = n.minimum - n.input.length;
				return 1 == t
					? "Prosím, zadajte ešte jeden znak"
					: t <= 4
						? "Prosím, zadajte ešte ďalšie " + e[t](!0) + " znaky"
						: "Prosím, zadajte ešte ďalších " + t + " znakov";
			},
			loadingMore: () => "Načítanie ďalších výsledkov…",
			maximumSelected: (n) =>
				1 == n.maximum
					? "Môžete zvoliť len jednu položku"
					: n.maximum >= 2 && n.maximum <= 4
						? "Môžete zvoliť najviac " + e[n.maximum](!1) + " položky"
						: "Môžete zvoliť najviac " + n.maximum + " položiek",
			noResults: () => "Nenašli sa žiadne položky",
			searching: () => "Vyhľadávanie…",
			removeAllItems: () => "Odstráňte všetky položky",
		};
	}),
		e.define,
		e.require;
})();
