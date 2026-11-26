/* Standalone print pages do not extend base.html, so they need their own
 * CSP-safe listener for the shared [data-print] action. */
document.addEventListener("click", (event) => {
	const button = event.target.closest("[data-print]");
	if (!button) return;
	event.preventDefault();
	window.print();
});
