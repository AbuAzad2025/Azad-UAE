/**
 * Draft Autosave Utility
 * Persists form state to localStorage and offers restore on page load.
 * Usage: DraftAutosave.init('form_key', '#form-selector')
 */
const DraftAutosave = (function () {
	const STORAGE_PREFIX = "azad_draft_";
	const AUTOSAVE_DELAY = 5000;
	const MAX_AGE_MS = 24 * 60 * 60 * 1000;

	function getKey(formId) {
		return STORAGE_PREFIX + formId;
	}

	function serializeForm(form) {
		const data = {};
		form.querySelectorAll("input, select, textarea").forEach((el) => {
			if (!el.name || el.disabled) return;
			if (el.type === "checkbox" || el.type === "radio") {
				if (el.checked) data[el.name] = el.value;
			} else if (el.type !== "password" && el.type !== "file" && el.type !== "hidden") {
				data[el.name] = el.value;
			}
		});
		return data;
	}

	function deserializeForm(form, data) {
		Object.entries(data).forEach(([name, value]) => {
			const el = form.querySelector(`[name="${name}"]`);
			if (!el || el.type === "password" || el.type === "file") return;
			if (el.type === "checkbox" || el.type === "radio") {
				el.checked = el.value === value;
			} else {
				el.value = value;
				el.dispatchEvent(new Event("change", { bubbles: true }));
			}
		});
	}

	function save(formId, form) {
		try {
			localStorage.setItem(
				getKey(formId),
				JSON.stringify({ data: serializeForm(form), timestamp: Date.now() }),
			);
		} catch (_) {}
	}

	function load(formId, form) {
		try {
			const stored = localStorage.getItem(getKey(formId));
			if (!stored) return false;
			const payload = JSON.parse(stored);
			if (Date.now() - payload.timestamp > MAX_AGE_MS) {
				clear(formId);
				return false;
			}
			deserializeForm(form, payload.data);
			return true;
		} catch (_) {
			return false;
		}
	}

	function clear(formId) {
		localStorage.removeItem(getKey(formId));
	}

	function hasDraft(formId) {
		try {
			const stored = localStorage.getItem(getKey(formId));
			if (!stored) return false;
			return Date.now() - JSON.parse(stored).timestamp <= MAX_AGE_MS;
		} catch (_) {
			return false;
		}
	}

	function init(formId, formSelector = "form") {
		const form =
			typeof formSelector === "string" ? document.querySelector(formSelector) : formSelector;
		if (!form) return;

		if (hasDraft(formId)) {
			const banner = document.createElement("div");
			banner.className = "alert alert-info alert-dismissible fade show";
			banner.setAttribute("role", "alert");
			const t = window.t || ((k) => k);
			banner.innerHTML = `
				<i class="fas fa-clock mr-2"></i>${t("Found_saved_draft")}
				<button type="button" class="btn btn-sm btn-outline-primary ml-2 js-draft-restore">${t("Restore")}</button>
				<button type="button" class="btn btn-sm btn-outline-secondary ml-2 js-draft-discard">${t("Discard")}</button>
				<button type="button" class="close" data-dismiss="alert" aria-label="${t("Close")}">&times;</button>
			`;
			form.prepend(banner);
			banner.querySelector(".js-draft-restore").addEventListener("click", () => {
				load(formId, form);
				banner.remove();
			});
			banner.querySelector(".js-draft-discard").addEventListener("click", () => {
				clear(formId);
				banner.remove();
			});
		}

		let timer;
		const scheduleSave = () => {
			clearTimeout(timer);
			timer = setTimeout(() => save(formId, form), AUTOSAVE_DELAY);
		};
		form.addEventListener("input", scheduleSave);
		form.addEventListener("change", scheduleSave);

		form.addEventListener("submit", () => clear(formId));

		window.addEventListener("beforeunload", () => save(formId, form));
	}

	return { init, save, load, clear, hasDraft };
})();

window.DraftAutosave = DraftAutosave;