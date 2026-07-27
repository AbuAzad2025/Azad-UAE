/**
 * POS permission check.
 * Requires window.CURRENT_USER_PERMISSIONS to be set via inline
 * data injection before this script loads.
 */
window.hasPermission = (code) => {
	const perms = window.CURRENT_USER_PERMISSIONS || [];
	return Array.isArray(perms) && perms.includes(code);
};
