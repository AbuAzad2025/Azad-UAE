/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/ps", [], () => ({
		errorLoading: () => "پايلي نه سي ترلاسه کېدای",
		inputTooLong: (n) => {
			var e = n.input.length - n.maximum,
				r = "د مهربانۍ لمخي " + e + " توری ړنګ کړئ";
			return 1 != e && (r = r.replace("توری", "توري")), r;
		},
		inputTooShort: (n) =>
			"لږ تر لږه " + (n.minimum - n.input.length) + " يا ډېر توري وليکئ",
		loadingMore: () => "نوري پايلي ترلاسه کيږي...",
		maximumSelected: (n) => {
			var e = "تاسو يوازي " + n.maximum + " قلم په نښه کولای سی";
			return 1 != n.maximum && (e = e.replace("قلم", "قلمونه")), e;
		},
		noResults: () => "پايلي و نه موندل سوې",
		searching: () => "لټول کيږي...",
		removeAllItems: () => "ټول توکي لرې کړئ",
	})),
		n.define,
		n.require;
})();
