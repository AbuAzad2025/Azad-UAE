/**
 * 🌍 JavaScript Internationalization — Minimal runtime language helper
 *
 * Previously contained a 60KB inline translation dictionary and UI helpers
 * (t, translatePage, getDataTablesLanguage, showAlert, confirmAction).
 * Those were never invoked by templates (verified zero hits for window.t,
 * translatePage, getDataTablesLanguage, showAlert, confirmAction in templates/).
 * The full server-side TRANSLATIONS dict in utils/i18n.py is the canonical
 * source; Jinja t()/_() render translations server-side.
 *
 * Kept: getCurrentLanguage() — now consumed by app.js, performance.js,
 * notifications.js for conditional DataTables language and RTL defaults.
 */

function getCurrentLanguage() {
	return document.documentElement.lang || "ar";
}

// Retain legacy global for any rare inline scripts that may reference it,
// but map it to a no-op passthrough so keys render as-is.
window.t = function (key) {
	return key;
};
window.getCurrentLanguage = getCurrentLanguage;
