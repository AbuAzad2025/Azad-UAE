/**
 * 🌍 JavaScript Internationalization — Minimal runtime language helper
 *
 * Uses server-injected translations from utils/i18n.py TRANSLATIONS dict.
 * The server injects `window.I18N_TRANSLATIONS` and current language.
 */

function getCurrentLanguage() {
	return window.I18N_LANG || document.documentElement.lang || "ar";
}

// Translation function — uses server-injected TRANSLATIONS dict
window.t = (key) => {
	const lang = getCurrentLanguage();
	if (window.I18N_TRANSLATIONS && key in window.I18N_TRANSLATIONS) {
		return window.I18N_TRANSLATIONS[key][lang] ?? window.I18N_TRANSLATIONS[key].en ?? key;
	}
	return key;
};

window.getCurrentLanguage = getCurrentLanguage;
