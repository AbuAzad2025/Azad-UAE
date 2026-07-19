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
		if (stored) {
			return normalizeMode(stored);
		}
		try {
			return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
		} catch (_e) {
			return "light";
		}
	}

	function getInitialVariant() {
		const stored = localStorage.getItem(STORAGE_VARIANT);
		if (stored) {
			return normalizeVariant(stored);
		}
		return "palestinian";
	}

	function getInitialSidebarSide() {
		const stored = normalizeSidebarSide(localStorage.getItem(STORAGE_SIDEBAR));
		const storedDir = localStorage.getItem(STORAGE_SIDEBAR_DIR);
		const currentDir = document.documentElement.getAttribute("dir") || "rtl";

		if (!stored) {
			return getDefaultSidebarSide();
		}

		if (storedDir && storedDir !== currentDir) {
			return getDefaultSidebarSide();
		}

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

		// Force inline styles so the switch actually moves elements regardless of CSS specificity
		const sidebar = document.querySelector(".main-sidebar");
		const content = document.querySelector(".content-wrapper");
		const header = document.querySelector(".main-header");
		const footer = document.querySelector(".main-footer");
		if (sidebar) {
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
			el.style.setProperty(marginProp, width, "important");
			el.style.setProperty(otherProp, "0px", "important");
		});
	}

	function updateModeToggle(mode) {
		const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
		if (!toggle) return;

		toggle.setAttribute("data-ui-mode", mode);
		toggle.setAttribute("aria-pressed", mode === "dark" ? "true" : "false");

		if (mode === "dark") {
			toggle.setAttribute("aria-label", "التبديل إلى الوضع الفاتح");
			toggle.setAttribute("title", "التبديل إلى الوضع الفاتح");
		} else {
			toggle.setAttribute("aria-label", "التبديل إلى الوضع الداكن");
			toggle.setAttribute("title", "التبديل إلى الوضع الداكن");
		}

		const label = toggle.querySelector('[data-ui-role="mode-label"]');
		if (label) {
			label.textContent = mode === "dark" ? "داكن" : "فاتح";
		}

		const icon = toggle.querySelector('[data-ui-role="mode-icon"]');
		if (icon) {
			icon.className = mode === "dark" ? "fas fa-moon" : "fas fa-sun";
		}
	}

	function updateThemeSwitcher(variant) {
		const buttons = document.querySelectorAll(".erp-theme-switcher .erp-theme-option");
		buttons.forEach((btn) => {
			const btnVariant = btn.getAttribute("data-value");
			if (btnVariant === variant) {
				btn.classList.add("active");
			} else {
				btn.classList.remove("active");
			}
		});
	}

	function applyTheme(mode, variant) {
		mode = normalizeMode(mode);
		variant = normalizeVariant(variant);

		const el = document.documentElement;
		el.dataset.uiMode = mode;
		el.dataset.uiVariant = variant;
		localStorage.setItem(STORAGE_MODE, mode);
		localStorage.setItem(STORAGE_VARIANT, variant);

		updateModeToggle(mode);
		updateThemeSwitcher(variant);
	}

	function boot() {
		applyTheme(getInitialMode(), getInitialVariant());
		applySidebarSide(getInitialSidebarSide());

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

		window.toggleSidebarDirection = () => {
			const body = document.body;
			if (!body) return;
			const current = body.dataset.sidebarSide === "left" ? "left" : "right";
			const next = current === "left" ? "right" : "left";
			applySidebarSide(next);
		};

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
						el.remove();
					}
				} catch (_e) {}
			}, 20000);
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", boot);
	} else {
		boot();
	}
})();
