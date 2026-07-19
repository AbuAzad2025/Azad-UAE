/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/he", [], () => ({
		errorLoading: () => "שגיאה בטעינת התוצאות",
		inputTooLong: (n) => {
			var e = n.input.length - n.maximum,
				r = "נא למחוק ";
			return (r += 1 === e ? "תו אחד" : e + " תווים");
		},
		inputTooShort: (n) => {
			var e = n.minimum - n.input.length,
				r = "נא להכניס ";
			return (r += 1 === e ? "תו אחד" : e + " תווים"), (r += " או יותר");
		},
		loadingMore: () => "טוען תוצאות נוספות…",
		maximumSelected: (n) => {
			var e = "באפשרותך לבחור עד ";
			return (
				1 === n.maximum ? (e += "פריט אחד") : (e += n.maximum + " פריטים"), e
			);
		},
		noResults: () => "לא נמצאו תוצאות",
		searching: () => "מחפש…",
		removeAllItems: () => "הסר את כל הפריטים",
	})),
		n.define,
		n.require;
})();
