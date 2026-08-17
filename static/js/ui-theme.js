(() => {
	const STORAGE_MODE = "ui_mode";
	const STORAGE_VARIANT = "ui_variant";
	const STORAGE_SIDEBAR = "sidebarLayout";
	const STORAGE_SIDEBAR_DIR = "sidebarLayoutDir";

	function normalizeMode(v) {
		return v === "dark" ? "dark" : "light";
	}
	function normalizeVariant(v) {
		return v === "gulf" ? "gulf" : "palestinian";
	}
	function normalizeSidebarSide(v) {
		return v === "left" ? "left" : v === "right" ? "right" : null;
	}
	function getDefaultSidebarSide() {
		return document.documentElement.getAttribute("dir") === "rtl" ? "right" : "left";
	}

	function getInitialMode() {
		const stored = localStorage.getItem(STORAGE_MODE);
		if (stored) return normalizeMode(stored);
		try {
			return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
		} catch (_e) {
			return "light";
		}
	}

	function getInitialVariant() {
		const stored = localStorage.getItem(STORAGE_VARIANT);
		if (stored) return normalizeVariant(stored);
		return "palestinian";
	}

	function getInitialSidebarSide() {
		const stored = normalizeSidebarSide(localStorage.getItem(STORAGE_SIDEBAR));
		const storedDir = localStorage.getItem(STORAGE_SIDEBAR_DIR);
		const currentDir = document.documentElement.getAttribute("dir") || "rtl";
		if (!stored) return getDefaultSidebarSide();
		if (storedDir && storedDir !== currentDir) return getDefaultSidebarSide();
		return stored;
	}

	function applySidebarSide(side) {
		const body = document.body;
		const html = document.documentElement;
		if (!body) return;
		const normalized = normalizeSidebarSide(side) || getDefaultSidebarSide();
		body.dataset.sidebarSide = normalized;
		localStorage.setItem(STORAGE_SIDEBAR, normalized);
		localStorage.setItem(STORAGE_SIDEBAR_DIR, html.getAttribute("dir") || "rtl");

		const sidebar = document.querySelector(".main-sidebar");
		const content = document.querySelector(".content-wrapper");
		const header = document.querySelector(".main-header");
		const footer = document.querySelector(".main-footer");

		if (sidebar) {
			sidebar.style.transition = "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)";
			if (normalized === "right") {
				sidebar.style.left = "auto";
				sidebar.style.right = "0";
			} else {
				sidebar.style.left = "0";
				sidebar.style.right = "auto";
			}
		}

		const marginProp = normalized === "right" ? "margin-right" : "margin-left";
		const otherProp = normalized === "right" ? "margin-left" : "margin-right";
		const width =
			body.classList.contains("sidebar-mini") && body.classList.contains("sidebar-collapse")
				? "4.6rem"
				: "250px";

		[content, header, footer].forEach((el) => {
			if (!el) return;
			el.style.transition = "margin 0.35s cubic-bezier(0.4, 0, 0.2, 1)";
			el.style.setProperty(marginProp, width, "important");
			el.style.setProperty(otherProp, "0px", "important");
		});
	}

	function updateModeToggle(mode) {
		const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
		if (!toggle) return;
		toggle.setAttribute("data-ui-mode", mode);
		toggle.setAttribute("aria-pressed", mode === "dark" ? "true" : "false");
		toggle.setAttribute(
			"aria-label",
			mode === "dark" ? "التبديل إلى الوضع الفاتح" : "التبديل إلى الوضع الداكن",
		);
		toggle.setAttribute(
			"title",
			mode === "dark" ? "التبديل إلى الوضع الفاتح" : "التبديل إلى الوضع الداكن",
		);

		const label = toggle.querySelector('[data-ui-role="mode-label"]');
		if (label) label.textContent = mode === "dark" ? "داكن" : "فاتح";

		const icon = toggle.querySelector('[data-ui-role="mode-icon"]');
		if (icon) {
			icon.style.transition = "transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)";
			icon.style.transform = "rotate(180deg) scale(0.8)";
			setTimeout(() => {
				icon.className = mode === "dark" ? "fas fa-moon" : "fas fa-sun";
				icon.style.transform = "rotate(0deg) scale(1)";
			}, 200);
		}
	}

	function updateThemeSwitcher(variant) {
		const buttons = document.querySelectorAll(".erp-theme-switcher .erp-theme-option");
		buttons.forEach((btn) => {
			const btnVariant = btn.getAttribute("data-value");
			btn.classList.toggle("active", btnVariant === variant);
		});
	}

	function applyTheme(mode, variant) {
		mode = normalizeMode(mode);
		variant = normalizeVariant(variant);
		const el = document.documentElement;

		// Smooth transition
		el.style.transition = "background-color 0.4s ease, color 0.4s ease";
		el.dataset.uiMode = mode;
		el.dataset.uiVariant = variant;
		localStorage.setItem(STORAGE_MODE, mode);
		localStorage.setItem(STORAGE_VARIANT, variant);

		updateModeToggle(mode);
		updateThemeSwitcher(variant);

		// Dispatch custom event for other components
		window.dispatchEvent(new CustomEvent("azad-theme-change", { detail: { mode, variant } }));

		// Remove transition after animation
		setTimeout(() => {
			el.style.transition = "";
		}, 500);
	}

	function boot() {
		applyTheme(getInitialMode(), getInitialVariant());
		applySidebarSide(getInitialSidebarSide());

		// Mode toggle
		const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
		if (toggle) {
			toggle.addEventListener("click", (ev) => {
				ev.preventDefault();
				const current = normalizeMode(document.documentElement.dataset.uiMode || "light");
				const next = current === "dark" ? "light" : "dark";
				const variant = normalizeVariant(
					document.documentElement.dataset.uiVariant || "palestinian",
				);
				applyTheme(next, variant);
			});
		}

		// Variant buttons
		const variantButtons = document.querySelectorAll(
			'.erp-theme-switcher .erp-theme-option[data-ui-action="set-variant"]',
		);
		variantButtons.forEach((btn) => {
			btn.addEventListener("click", (ev) => {
				ev.preventDefault();
				const variant = normalizeVariant(btn.getAttribute("data-value"));
				const mode = normalizeMode(document.documentElement.dataset.uiMode || "light");
				applyTheme(mode, variant);
			});
		});

		// Sidebar direction toggle
		window.toggleSidebarDirection = () => {
			const body = document.body;
			if (!body) return;
			const current = body.dataset.sidebarSide === "left" ? "left" : "right";
			const next = current === "left" ? "right" : "left";
			applySidebarSide(next);
		};

		// Flash messages auto-dismiss with animation
		const flashes = document.querySelectorAll(".flash-message");
		flashes.forEach((el) => {
			const bar = el.querySelector(".flash-timer");
			if (bar) {
				requestAnimationFrame(() => {
					bar.style.width = "0%";
				});
			}
			window.setTimeout(() => {
				try {
					if (window.jQuery?.fn?.alert) {
						window.jQuery(el).alert("close");
					} else {
						el.style.transition = "all 0.5s ease";
						el.style.opacity = "0";
						el.style.transform = "translateX(100%)";
						setTimeout(() => el.remove(), 500);
					}
				} catch (_e) {}
			}, 20000);
		});

		// Listen for system dark mode changes
		try {
			const darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");
			darkModeQuery.addEventListener("change", (e) => {
				const stored = localStorage.getItem(STORAGE_MODE);
				if (!stored) {
					// Only auto-switch if user hasn't manually set
					const variant = normalizeVariant(
						document.documentElement.dataset.uiVariant || "palestinian",
					);
					applyTheme(e.matches ? "dark" : "light", variant);
				}
			});
		} catch (_) {}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", boot);
	} else {
		boot();
	}
})();
