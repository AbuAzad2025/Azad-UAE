/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/el", [], () => ({
		errorLoading: () => "Τα αποτελέσματα δεν μπόρεσαν να φορτώσουν.",
		inputTooLong: (n) => {
			var e = n.input.length - n.maximum,
				u = "Παρακαλώ διαγράψτε " + e + " χαρακτήρ";
			return 1 == e && (u += "α"), 1 != e && (u += "ες"), u;
		},
		inputTooShort: (n) =>
			"Παρακαλώ συμπληρώστε " +
			(n.minimum - n.input.length) +
			" ή περισσότερους χαρακτήρες",
		loadingMore: () => "Φόρτωση περισσότερων αποτελεσμάτων…",
		maximumSelected: (n) => {
			var e = "Μπορείτε να επιλέξετε μόνο " + n.maximum + " επιλογ";
			return 1 == n.maximum && (e += "ή"), 1 != n.maximum && (e += "ές"), e;
		},
		noResults: () => "Δεν βρέθηκαν αποτελέσματα",
		searching: () => "Αναζήτηση…",
		removeAllItems: () => "Καταργήστε όλα τα στοιχεία",
	})),
		n.define,
		n.require;
})();
