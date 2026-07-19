/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/is", [], () => ({
		inputTooLong: (n) => {
			var t = n.input.length - n.maximum,
				e = "Vinsamlegast styttið texta um " + t + " staf";
			return t <= 1 ? e : e + "i";
		},
		inputTooShort: (n) => {
			var t = n.minimum - n.input.length,
				e = "Vinsamlegast skrifið " + t + " staf";
			return t > 1 && (e += "i"), (e += " í viðbót");
		},
		loadingMore: () => "Sæki fleiri niðurstöður…",
		maximumSelected: (n) => "Þú getur aðeins valið " + n.maximum + " atriði",
		noResults: () => "Ekkert fannst",
		searching: () => "Leita…",
		removeAllItems: () => "Fjarlægðu öll atriði",
	})),
		n.define,
		n.require;
})();
