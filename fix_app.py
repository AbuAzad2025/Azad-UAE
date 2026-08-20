with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

old = """// Systemic safety net: any async failure a caller forgot to catch becomes
// a localized toast instead of a silent console-only rejection.
window.addEventListener("unhandledrejection", (event) => {
	console.error("Unhandled async error:", event.reason);
	const message =
		event.reason instanceof TypeError
			? "تعذر الاتصال بالخادم — تحقق من اتصالك بالإنترنت"
			: event.reason?.message || "حدث خطأ غير متوقع — حاول مرة أخرى";
	if (window.notify?.show) {
		window.notify.show({ type: "error", message });
	} else if (typeof Swal !== "undefined") {
		Swal.fire({
			icon: "error",
			text: message,
			toast: true,
			position: "top-end",
			showConfirmButton: false,
			timer: 5000,
		});
	}
});
})(jQuery);"""

new = """// Systemic safety net: any async failure a caller forgot to catch becomes
// a localized toast instead of a silent console-only rejection.
window.addEventListener("unhandledrejection", (event) => {
	console.error("Unhandled async error:", event.reason);
	const message =
		event.reason instanceof TypeError
			? "تعذر الاتصال بالخادم — تحقق من اتصالك بالإنترنت"
			: event.reason?.message || "حدث خطأ غير متوقع — حاول مرة أخرى";
	if (window.notify?.show) {
		window.notify.show({ type: "error", message });
	} else if (typeof Swal !== "undefined") {
		Swal.fire({
			icon: "error",
			text: message,
			toast: true,
			position: "top-end",
			showConfirmButton: false,
			timer: 5000,
		});
	}
});

// Expose key functions for testability
window.showNotification = showNotification;
window.showSystemAlert = showSystemAlert;
window.saveFormData = saveFormData;
window.performSearch = performSearch;
})(jQuery);"""

if old not in content:
    print("Old not found")
    exit(1)

content = content.replace(old, new)

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
