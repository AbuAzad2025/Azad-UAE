/**
 * Azad ERP — Base Helpers & Utilities
 * Fixed encoding issues, enhanced performance, added new utilities
 */

// ── 1. Azad UI Helper ──
(() => {
	let loadingCount = 0;

	function loadingOverlay() {
		let el = document.getElementById("azadLoadingOverlay");
		if (!el) {
			el = document.createElement("div");
			el.id = "azadLoadingOverlay";
			el.style.cssText =
				"position:fixed;inset:0;z-index:20000;background:rgba(255,255,255,0.65);display:flex;align-items:center;justify-content:center;backdrop-filter:blur(2px);transition:opacity 0.3s;";
			el.innerHTML =
				'<div class="azad-loader-ring"><div></div><div></div><div></div><div></div></div>';
			document.body.appendChild(el);
		}
		return el;
	}

	function azadToast(message, type) {
		if (window.toastr && typeof window.toastr[type] === "function") {
			window.toastr[type](message);
			return;
		}
		const colors = { success: "#28a745", error: "#dc3545", warning: "#D4AF37", info: "#17a2b8" };
		const icons = {
			success: "fa-check-circle",
			error: "fa-times-circle",
			warning: "fa-exclamation-triangle",
			info: "fa-info-circle",
		};

		const el = document.createElement("div");
		el.className = "azad-toast";
		el.innerHTML = `<i class="fas ${icons[type] || icons.info} azad-toast-icon"></i><span>${message}</span>`;
		el.style.cssText =
			"position:fixed;bottom:24px;right:24px;z-index:20001;background:" +
			(colors[type] || colors.info) +
			";color:#fff;padding:14px 22px;border-radius:12px;font-weight:600;font-size:0.92rem;box-shadow:0 8px 24px rgba(0,0,0,0.25);max-width:400px;direction:rtl;display:flex;align-items:center;gap:10px;opacity:0;transform:translateY(20px);transition:all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);";
		document.body.appendChild(el);

		requestAnimationFrame(() => {
			el.style.opacity = "1";
			el.style.transform = "translateY(0)";
		});

		setTimeout(() => {
			el.style.opacity = "0";
			el.style.transform = "translateY(20px)";
			setTimeout(() => el.remove(), 350);
		}, 5000);
	}

	window.azad = {
		showLoading() {
			loadingCount += 1;
			loadingOverlay().style.display = "flex";
			loadingOverlay().style.opacity = "1";
		},
		hideLoading() {
			loadingCount = Math.max(0, loadingCount - 1);
			if (loadingCount === 0) {
				const el = loadingOverlay();
				el.style.opacity = "0";
				setTimeout(() => {
					if (loadingCount === 0) el.style.display = "none";
				}, 300);
			}
		},
		formatNumber(value) {
			const n = Number(value);
			if (!Number.isFinite(n)) return "0.00";
			return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
		},
		formatCurrency(value, symbol = "") {
			return `${symbol} ${this.formatNumber(value)}`;
		},
		showError(msg) {
			azadToast(msg, "error");
		},
		showSuccess(msg) {
			azadToast(msg, "success");
		},
		showWarning(msg) {
			azadToast(msg, "warning");
		},
		showInfo(msg) {
			azadToast(msg, "info");
		},
		// Debounce utility
		debounce(fn, wait) {
			let timeout;
			return function (...args) {
				clearTimeout(timeout);
				timeout = setTimeout(() => fn.apply(this, args), wait);
			};
		},
		// Throttle utility
		throttle(fn, limit) {
			let inThrottle;
			return function (...args) {
				if (!inThrottle) {
					fn.apply(this, args);
					inThrottle = true;
					setTimeout(() => (inThrottle = false), limit);
				}
			};
		},
	};
})();

// ── 2. CSRF & AJAX Setup ──
$(() => {
	try {
		const csrfToken = $('meta[name="csrf-token"]').attr("content");
		if (csrfToken) {
			$.ajaxSetup({
				beforeSend: (xhr, settings) => {
					if (!/^GET|HEAD|OPTIONS|TRACE$/i.test(settings.type)) {
						xhr.setRequestHeader("X-CSRFToken", csrfToken);
					}
				},
			});
		}
	} catch (e) {
		console.warn("CSRF setup warning:", e);
	}

	// Initialize FX modal
	$("#fxModal").on("show.bs.modal", loadFxRates);

	// Initialize datetime
	updateDateTime();

	if (document.getElementById("time-display") || document.getElementById("date-display")) {
		setInterval(updateDateTime, 1000);
	}

	// Initialize calculator
	initNavbarCalculator();
});

// ── 3. Smart Link Prefetching ──
document
	.querySelectorAll('a[href^="/"]:not([href*="/logout"]):not([href^="//"])')
	.forEach((link) => {
		link.addEventListener(
			"mouseenter",
			function () {
				const url = this.getAttribute("href");
				if (url && !this.dataset.prefetched && url.length > 1) {
					const prefetch = document.createElement("link");
					prefetch.rel = "prefetch";
					prefetch.href = url;
					document.head.appendChild(prefetch);
					this.dataset.prefetched = "true";
				}
			},
			{ once: true, passive: true },
		);
	});

// ── 4. Flash Message Auto-Dismiss ──
document.querySelectorAll(".flash-message").forEach((alert) => {
	if (!alert.classList.contains("alert-permanent") && !alert.classList.contains("alert-danger")) {
		const progressBar = alert.querySelector(".flash-timer");
		setTimeout(() => {
			if (progressBar) progressBar.style.width = "0%";
		}, 100);
		setTimeout(() => {
			alert.style.transition = "all 0.5s cubic-bezier(0.4, 0, 0.2, 1)";
			alert.style.transform = "translateX(100%)";
			alert.style.opacity = "0";
			setTimeout(() => alert.remove(), 500);
		}, 40000);
	}
});

// ── 5. FX Rates ──
let fxDisplayCache = null;
let fxDisplayCacheTime = 0;
const FX_DISPLAY_CACHE_MS = 300000;

function formatFxRate(val) {
	if (val === null || val === undefined) return "--";
	const n = Number(val);
	if (!Number.isFinite(n)) return "--";
	if (n >= 100) return n.toFixed(2);
	if (n >= 1) return n.toFixed(3);
	return n.toFixed(4);
}

async function loadFxRates() {
	const now = Date.now();
	if (fxDisplayCache && now - fxDisplayCacheTime < FX_DISPLAY_CACHE_MS) {
		populateFxDisplay(fxDisplayCache);
		return;
	}

	const tbody = document.getElementById("fx-rates-body");
	if (tbody) {
		tbody.innerHTML =
			'<tr><td colspan="3" class="text-center py-4"><div class="spinner-border spinner-border-sm text-muted" role="status"></div><span class="mr-2"> جار�? التحميل...</span></td></tr>';
	}

	try {
		const baseCurrency =
			window._FX_BASE_CURRENCY || "{{ tenant_base_currency|default(\x27USD\x27) }}";
		const res = await fetch(`${window._FX_API_URL}?base=${encodeURIComponent(baseCurrency)}`, {
			cache: "no-store",
		});
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		const data = await res.json();
		if (!data.ok) throw new Error("API error");
		fxDisplayCache = data;
		fxDisplayCacheTime = now;
		populateFxDisplay(data);
	} catch (_e) {
		populateFxDisplay(getFallbackFx());
	}
}

function getFallbackFx() {
	return {
		ok: false,
		base: window._FX_FALLBACK_BASE || "USD",
		rates: {
			USD: 1.0,
			ILS: 3.65,
			JOD: 0.709,
			AED: 3.67,
			EUR: 0.92,
			SAR: 3.75,
			EGP: 50.5,
			GBP: 0.79,
		},
		source: "fallback_static",
		stale: true,
		last_updated: new Date().toISOString(),
	};
}

function populateFxDisplay(data) {
	const rates = data.rates || {};
	const base = data.tenant_base_currency || data.base || "USD";
	const stale = data.stale || false;
	const source = data.source || "unknown";

	const labels = {
		USD: { ar: "????? ??????", sym: "$" },
		ILS: { ar: "???? ????????", sym: "?" },
		JOD: { ar: "????? ?????", sym: "JD" },
		EUR: { ar: "????", sym: "�" },
		AED: { ar: "???? ???????", sym: "?.?" },
		SAR: { ar: "???? ?????", sym: "?.?" },
		EGP: { ar: "???? ????", sym: "?.?" },
		GBP: { ar: "???? ????????", sym: "�" },
	};
	labels[window._FX_FALLBACK_BASE || "USD"] = {
		ar: window._CURRENCY_NAME_AR,
		sym: window._CURRENCY_SYMBOL,
	};

	const tbody = document.getElementById("fx-rates-body");
	if (!tbody) return;

	let html = "";
	for (const [code, rate] of Object.entries(rates)) {
		const lbl = labels[code] || { ar: code, sym: code };
		html += `<tr class="az-enter" style="animation-delay:${Object.keys(rates).indexOf(code) * 0.03}s">
      <td class="text-right"><strong>${lbl.sym}</strong> <small class="text-muted">${lbl.ar}</small></td>
      <td class="font-weight-bold">${formatFxRate(rate)}</td>
      <td class="text-muted small">1 ${base} = ${formatFxRate(rate)} ${code}</td>
    </tr>`;
	}
	tbody.innerHTML = html;

	const badge = document.getElementById("fx-source-badge");
	if (badge) {
		badge.style.display = "inline-block";
		if (source === "fallback_static") {
			badge.className = "badge badge-warning ml-1";
			badge.textContent = "سعر تقديري";
		} else if (stale) {
			badge.className = "badge badge-warning ml-1";
			badge.textContent = "آخر سعر مح�?وظ";
		} else {
			badge.className = "badge badge-success ml-1";
			badge.textContent = "مباشر";
		}
	}

	const updatedEl = document.getElementById("fx-last-updated");
	if (updatedEl && data.last_updated) {
		const d = new Date(data.last_updated);
		const timeStr = Number.isNaN(d.getTime())
			? "--"
			: d.toLocaleTimeString("ar-AE", { hour: "2-digit", minute: "2-digit" });
		updatedEl.innerHTML = `<i class="fas fa-clock mr-1"></i>آخر تحديث: ${timeStr}`;
	}
}

// ── 6. DateTime Display ──
function updateDateTime() {
	const now = new Date();
	const timeString = now.toLocaleTimeString("ar-SA", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hour12: false,
	});
	const dateString = now.toLocaleDateString("ar-SA", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
	});
	const timeDisplay = document.getElementById("time-display");
	const dateDisplay = document.getElementById("date-display");
	if (timeDisplay) timeDisplay.textContent = timeString;
	if (dateDisplay) dateDisplay.textContent = dateString;
}

// ── 7. Safe Expression Evaluator ──
function safeEval(expr) {
	const src = String(expr || "")
		.replace(/[�]/g, "/")
		.replace(/[�]/g, "*")
		.replace(/[?]/g, "pi")
		.replace(/\^/g, "**");

	let pos = 0;
	const len = src.length;
	const isDigit = (c) => c >= "0" && c <= "9";
	const isIdent = (c) => (c >= "a" && c <= "z") || (c >= "A" && c <= "Z");
	const isWhite = (c) => c === " " || c === "\t" || c === "\n" || c === "\r";

	function error() {
		throw new Error("invalid expression");
	}
	function skipWs() {
		while (pos < len && isWhite(src[pos])) pos++;
	}
	function peek() {
		skipWs();
		return src[pos];
	}

	function parseExpression() {
		let value = parseTerm();
		for (;;) {
			const c = peek();
			if (c === "+") {
				pos++;
				value += parseTerm();
			} else if (c === "-") {
				pos++;
				value -= parseTerm();
			} else return value;
		}
	}

	function parseTerm() {
		let value = parseFactor();
		for (;;) {
			const c = peek();
			if (c === "*") {
				pos++;
				value *= parseFactor();
			} else if (c === "/") {
				pos++;
				const d = parseFactor();
				if (d === 0) error();
				value /= d;
			} else return value;
		}
	}

	function parseFactor() {
		skipWs();
		if (src[pos] === "-") {
			pos++;
			return -parseFactor();
		}
		const base = parsePrimary();
		if (peek() === "^" || (peek() === "*" && src[pos + 1] === "*")) {
			if (src[pos] === "^") pos++;
			else pos += 2;
			return base ** parseFactor();
		}
		return base;
	}

	function parseNumber() {
		skipWs();
		const start = pos;
		let hasDigit = false;
		while (pos < len && (isDigit(src[pos]) || src[pos] === ".")) {
			if (isDigit(src[pos])) hasDigit = true;
			pos++;
		}
		if (!hasDigit) error();
		if (pos < len && (src[pos] === "e" || src[pos] === "E")) {
			const save = pos;
			pos++;
			if (pos < len && (src[pos] === "+" || src[pos] === "-")) pos++;
			if (pos < len && isDigit(src[pos])) {
				while (pos < len && isDigit(src[pos])) pos++;
			} else {
				pos = save;
			}
		}
		const num = Number(src.slice(start, pos));
		if (!Number.isFinite(num)) error();
		return num;
	}

	function parseIdent() {
		skipWs();
		const start = pos;
		while (pos < len && isIdent(src[pos])) pos++;
		return src.slice(start, pos);
	}

	function parsePrimary() {
		skipWs();
		const c = src[pos];
		if (c === "(") {
			pos++;
			const v = parseExpression();
			if (peek() !== ")") error();
			pos++;
			return v;
		}
		if (isDigit(c) || c === ".") return parseNumber();
		if (isIdent(c)) {
			const name = parseIdent();
			if (name === "pi") return Math.PI;
			if (name === "e") return Math.E;
			const funcs = {
				sin: Math.sin,
				cos: Math.cos,
				tan: Math.tan,
				sqrt: Math.sqrt,
				log: Math.log10,
				ln: Math.log,
			};
			if (funcs[name]) {
				if (peek() !== "(") error();
				pos++;
				const arg = parseExpression();
				if (peek() !== ")") error();
				pos++;
				return funcs[name](arg);
			}
			error();
		}
		error();
	}

	try {
		const val = parseExpression();
		skipWs();
		if (pos !== len) error();
		if (!Number.isFinite(val)) return "ERR";
		return String(Math.round((val + Number.EPSILON) * 100000000) / 100000000);
	} catch (_e) {
		return "ERR";
	}
}

// ── 8. Calculator Pad Wiring ──
function wirePad(container, display, buttons) {
	if (!container || !display) return;
	container.innerHTML = buttons
		.map(
			(b) =>
				`<button type="button" class="btn btn-outline-secondary az-calc-btn" data-calc="${b}">${b}</button>`,
		)
		.join("");

	container.addEventListener("click", (e) => {
		const btn = e.target.closest("[data-calc]");
		if (!btn) return;
		const v = btn.getAttribute("data-calc");

		if (v === "C") {
			display.value = "0";
			return;
		}
		if (v === "=") {
			display.value = safeEval(display.value);
			return;
		}
		if (v === "DEL") {
			display.value = display.value.length > 1 ? display.value.slice(0, -1) : "0";
			return;
		}

		display.value = display.value === "0" ? v : display.value + v;
	});
}

function initNavbarCalculator() {
	const classicDisplay = document.getElementById("calcDisplayClassic");
	const scientificDisplay = document.getElementById("calcDisplayScientific");
	const classicContainer = document.getElementById("calcClassicButtons");
	const scientificContainer = document.getElementById("calcScientificButtons");

	wirePad(classicContainer, classicDisplay, [
		"7",
		"8",
		"9",
		"÷",
		"4",
		"5",
		"6",
		"×",
		"1",
		"2",
		"3",
		"-",
		"0",
		".",
		"=",
		"+",
		"(",
		")",
		"DEL",
		"C",
	]);
	wirePad(scientificContainer, scientificDisplay, [
		"sin(",
		"cos(",
		"tan(",
		"sqrt(",
		"log(",
		"ln(",
		"π",
		"e",
		"7",
		"8",
		"9",
		"÷",
		"4",
		"5",
		"6",
		"×",
		"1",
		"2",
		"3",
		"-",
		"0",
		".",
		"^",
		"+",
		"(",
		")",
		"DEL",
		"C",
		"=",
	]);

	const btnLoanCalc = document.getElementById("btnLoanCalc");
	const btnMarginCalc = document.getElementById("btnMarginCalc");

	if (btnLoanCalc) {
		btnLoanCalc.addEventListener("click", () => {
			const p = parseFloat(document.getElementById("loanPrincipal").value || "0");
			const annual = parseFloat(document.getElementById("loanRate").value || "0");
			const months = parseInt(document.getElementById("loanMonths").value || "0", 10);
			const out = document.getElementById("loanResult");

			if (!(p > 0) || !(months > 0)) {
				out.className = "alert alert-warning mt-2 mb-0";
				out.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i>أدخل قيم صحيحة.';
				return;
			}

			const r = annual / 100 / 12;
			const emi = r > 0 ? (p * r * (1 + r) ** months) / ((1 + r) ** months - 1) : p / months;
			const total = emi * months;
			const interest = total - p;

			out.className = "alert alert-info mt-2 mb-0";
			out.innerHTML = `
        <div class="d-flex justify-content-between flex-wrap">
          <span><i class="fas fa-hand-holding-usd mr-1"></i>القسط: <strong>${emi.toFixed(2)}</strong></span>
          <span><i class="fas fa-coins mr-1"></i>ال�?ائدة: <strong>${interest.toFixed(2)}</strong></span>
          <span><i class="fas fa-wallet mr-1"></i>الإجمالي: <strong>${total.toFixed(2)}</strong></span>
        </div>`;
		});
	}

	if (btnMarginCalc) {
		btnMarginCalc.addEventListener("click", () => {
			const cost = parseFloat(document.getElementById("costValue").value || "0");
			const sell = parseFloat(document.getElementById("sellValue").value || "0");
			const out = document.getElementById("marginResult");

			if (!(cost >= 0) || !(sell > 0)) {
				out.className = "alert alert-warning mt-2 mb-0";
				out.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i>أدخل قيم صحيحة.';
				return;
			}

			const profit = sell - cost;
			const margin = (profit / sell) * 100;
			const markup = cost > 0 ? (profit / cost) * 100 : 0;

			out.className = "alert alert-success mt-2 mb-0";
			out.innerHTML = `
        <div class="d-flex justify-content-between flex-wrap">
          <span><i class="fas fa-dollar-sign mr-1 text-success"></i>الربح: <strong>${profit.toFixed(2)}</strong></span>
          <span><i class="fas fa-percentage mr-1 text-info"></i>Margin: <strong>${margin.toFixed(2)}%</strong></span>
          <span><i class="fas fa-chart-line mr-1 text-warning"></i>Markup: <strong>${markup.toFixed(2)}%</strong></span>
        </div>`;
		});
	}
}

// ── 9. View Mode System ──
const VIEW_MODES = ["auto", "desktop", "mobile"];
const VIEW_MODE_LABELS = { auto: "تلقائي", desktop: "كمبيوتر", mobile: "جوال" };
const VIEW_MODE_ICONS = { auto: "fa-desktop", desktop: "fa-desktop", mobile: "fa-mobile-alt" };

function getSavedViewMode() {
	try {
		return localStorage.getItem("azad_view_mode") || "auto";
	} catch (_) {
		return "auto";
	}
}

function setViewMode(mode) {
	if (VIEW_MODES.indexOf(mode) === -1) mode = "auto";
	const body = document.body;
	body.classList.remove("view-desktop", "view-mobile");
	if (mode === "desktop") body.classList.add("view-desktop");
	if (mode === "mobile") body.classList.add("view-mobile");
	try {
		localStorage.setItem("azad_view_mode", mode);
	} catch (_) {}
	updateViewModeButton(mode);
}

function updateViewModeButton(mode) {
	const btn = document.querySelector('[data-ui-action="toggle-viewmode"]');
	if (!btn) return;
	const icon = btn.querySelector('[data-ui-role="viewmode-icon"]');
	const label = btn.querySelector('[data-ui-role="viewmode-label"]');
	if (icon) {
		icon.classList.remove("fa-desktop", "fa-mobile-alt");
		icon.classList.add(VIEW_MODE_ICONS[mode] || "fa-desktop");
	}
	if (label) label.textContent = VIEW_MODE_LABELS[mode] || "تلقائي";
}

function cycleViewMode() {
	const current = getSavedViewMode();
	const nextIdx = (VIEW_MODES.indexOf(current) + 1) % VIEW_MODES.length;
	setViewMode(VIEW_MODES[nextIdx]);
}

document.addEventListener("click", (e) => {
	const btn = e.target.closest('[data-ui-action="toggle-viewmode"]');
	if (btn) {
		e.preventDefault();
		cycleViewMode();
	}
});

const currentMode = getSavedViewMode();
if (window._DEBUG)
	console.log(
		"[Azad] View mode:",
		currentMode,
		"| Screen:",
		`${window.innerWidth}x${window.innerHeight}`,
	);
setViewMode(currentMode);

// ── 10. Telemetry & Error Reporting ──
(() => {
	const sentErrors = new Map();
	let sentWindow = [];
	let activeRequests = 0;
	let concurrencyNoticeAt = 0;
	const DUPLICATE_WINDOW_MS = 30000;
	const MAX_REPORTS_PER_MINUTE = 20;
	const CONCURRENCY_WARN_AT = 8;
	const SLOW_REQUEST_MS = 5000;
	const LONG_TASK_MS = 250;
	const LAYOUT_SHIFT_WARN_AT = 0.25;
	const VALID_THEME_MODES = ["light", "dark"];
	const VALID_THEME_VARIANTS = ["palestinian", "gulf"];

	function toAbsoluteUrl(value) {
		try {
			return new URL(value, window.location.href).toString();
		} catch (_) {
			return String(value || "");
		}
	}
	function shouldSkipRequest(url) {
		const absolute = toAbsoluteUrl(url);
		return !absolute || absolute.indexOf(window._LOG_ENDPOINT) !== -1;
	}
	function isApiRequest(url) {
		try {
			const parsed = new URL(url, window.location.href);
			return (
				parsed.pathname.indexOf("/api/") === 0 || parsed.pathname.indexOf("/api_enhanced/") === 0
			);
		} catch (_) {
			return false;
		}
	}
	function getClientContext() {
		const root = document.documentElement;
		return {
			viewport: `${window.innerWidth}x${window.innerHeight}`,
			pixel_ratio: window.devicePixelRatio || 1,
			online: navigator.onLine !== false,
			active_requests: activeRequests,
			ui_mode: root.dataset.uiMode || "",
			ui_variant: root.dataset.uiVariant || "",
			dir: root.getAttribute("dir") || "",
		};
	}

	function sendError(payload) {
		try {
			payload = payload || {};
			const isOpaqueScriptError =
				payload.message === "Script error." &&
				(!payload.source || payload.source === "unknown") &&
				!payload.lineno &&
				!payload.stack;
			if (isOpaqueScriptError) return;

			payload.url = payload.url || window.location.href;
			payload.route = window.location.pathname;
			payload.browser_time = new Date().toISOString();
			payload.client = getClientContext();

			const typeForKey = payload.type || "runtime";
			const variableMetricTypes = [
				"resource",
				"fetch",
				"fetch_slow",
				"ajax",
				"api",
				"api_slow",
				"concurrency",
				"longtask",
				"layout",
				"theme",
			];
			const key = [
				typeForKey,
				variableMetricTypes.indexOf(typeForKey) === -1 ? payload.message || "" : "",
				payload.source || "",
				payload.request_url || "",
				payload.status || "",
				payload.lineno || 0,
			].join("|");
			payload.fingerprint_key = key;

			const now = Date.now();
			const seen = sentErrors.get(key);
			if (seen && now - seen.lastSeen < DUPLICATE_WINDOW_MS) {
				seen.count += 1;
				seen.lastSeen = now;
				payload.repeat_count = seen.count;
				if ([2, 5, 10, 25, 50].indexOf(seen.count) === -1) return;
			} else {
				sentErrors.set(key, { count: 1, lastSeen: now });
				payload.repeat_count = 1;
			}

			if (sentErrors.size > 100) sentErrors.clear();
			sentWindow = sentWindow.filter((ts) => now - ts < 60000);
			if (sentWindow.length >= MAX_REPORTS_PER_MINUTE) return;
			sentWindow.push(now);

			fetch(window._LOG_ENDPOINT, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
				},
				body: JSON.stringify(payload),
				credentials: "same-origin",
				keepalive: true,
			}).catch(() => {});
		} catch (_) {}
	}

	window.addEventListener(
		"error",
		(ev) => {
			const target = ev.target;
			if (target && target !== window && target.tagName) {
				const resourceUrl = target.src || target.href || target.currentSrc || "";
				sendError({
					type: "resource",
					message: `Resource load failed: ${target.tagName}`,
					source: resourceUrl || target.tagName,
					request_url: resourceUrl,
					lineno: 0,
					colno: 0,
					stack: null,
					url: window.location.href,
				});
				return;
			}
			sendError({
				type: "runtime",
				message: ev.message || "Unknown error",
				source: ev.filename || "unknown",
				lineno: ev.lineno || 0,
				colno: ev.colno || 0,
				stack: ev.error?.stack ? ev.error.stack : null,
				url: window.location.href,
			});
		},
		true,
	);

	window.addEventListener("unhandledrejection", (ev) => {
		const reason = ev.reason;
		let msg = "Unhandled Promise Rejection";
		let stack = null;
		if (typeof reason === "string") {
			msg = reason;
		} else if (reason?.message) {
			msg = reason.message;
			stack = reason.stack || null;
		}
		sendError({
			type: "promise",
			message: msg,
			source: "unhandledrejection",
			lineno: 0,
			colno: 0,
			stack,
			url: window.location.href,
		});
	});

	if (window.fetch) {
		const originalFetch = window.fetch;
		window.fetch = function (input, init) {
			const requestUrl = typeof input === "string" ? input : input?.url;
			const method = init?.method || input?.method || "GET";
			const absoluteUrl = toAbsoluteUrl(requestUrl);
			const requestIsApi = isApiRequest(absoluteUrl);
			const startedAt = window.performance && performance.now ? performance.now() : Date.now();
			activeRequests += 1;

			if (activeRequests >= CONCURRENCY_WARN_AT && !shouldSkipRequest(absoluteUrl)) {
				const now = Date.now();
				if (now - concurrencyNoticeAt > DUPLICATE_WINDOW_MS) {
					concurrencyNoticeAt = now;
					sendError({
						type: "concurrency",
						message: `High concurrent browser requests: ${activeRequests}`,
						source: "fetch.concurrency",
						request_url: absoluteUrl,
						method,
						url: window.location.href,
					});
				}
			}

			return originalFetch
				.call(this, input, init)
				.then((response) => {
					const duration = Math.round(
						(window.performance && performance.now ? performance.now() : Date.now()) - startedAt,
					);
					if (response && !response.ok && !shouldSkipRequest(requestUrl)) {
						sendError({
							type: requestIsApi ? "api" : "fetch",
							message:
								(requestIsApi ? "API failed: HTTP " : "Fetch failed: HTTP ") + response.status,
							source: requestIsApi ? "fetch.api" : "fetch",
							request_url: absoluteUrl,
							method,
							status: response.status,
							duration_ms: duration,
							active_requests: activeRequests,
							request_id: response.headers?.get ? response.headers.get("X-Request-Id") : "",
							url: window.location.href,
						});
					} else if (response && duration >= SLOW_REQUEST_MS && !shouldSkipRequest(requestUrl)) {
						sendError({
							type: requestIsApi ? "api_slow" : "fetch_slow",
							message: `${requestIsApi ? "Slow API request" : "Slow fetch request"}: ${duration}ms`,
							source: requestIsApi ? "fetch.api.slow" : "fetch.slow",
							request_url: absoluteUrl,
							method,
							status: response.status,
							duration_ms: duration,
							active_requests: activeRequests,
							request_id: response.headers?.get ? response.headers.get("X-Request-Id") : "",
							url: window.location.href,
						});
					}
					activeRequests = Math.max(0, activeRequests - 1);
					return response;
				})
				.catch((err) => {
					if (!shouldSkipRequest(requestUrl)) {
						const duration = Math.round(
							(window.performance && performance.now ? performance.now() : Date.now()) - startedAt,
						);
						sendError({
							type: requestIsApi ? "api" : "fetch",
							message: err?.message || (requestIsApi ? "API network error" : "Fetch network error"),
							source: requestIsApi ? "fetch.api" : "fetch",
							request_url: absoluteUrl,
							method,
							duration_ms: duration,
							active_requests: activeRequests,
							stack: err?.stack ? err.stack : null,
							url: window.location.href,
						});
					}
					activeRequests = Math.max(0, activeRequests - 1);
					throw err;
				});
		};
	}

	if (window.jQuery) {
		window.jQuery(document).ajaxError((_event, xhr, settings, thrownError) => {
			const requestUrl = settings?.url;
			if (shouldSkipRequest(requestUrl)) return;
			const absoluteUrl = toAbsoluteUrl(requestUrl);
			const requestIsApi = isApiRequest(absoluteUrl);
			sendError({
				type: requestIsApi ? "api" : "ajax",
				message:
					thrownError ||
					(requestIsApi ? "API AJAX failed: HTTP " : "AJAX failed: HTTP ") + xhr?.status,
				source: requestIsApi ? "jquery.ajax.api" : "jquery.ajax",
				request_url: absoluteUrl,
				method: settings?.type,
				status: xhr?.status,
				response_size: xhr?.responseText ? xhr.responseText.length : 0,
				url: window.location.href,
			});
		});
	}

	try {
		if ("PerformanceObserver" in window) {
			new PerformanceObserver((list) => {
				list.getEntries().forEach((entry) => {
					if (entry.duration >= LONG_TASK_MS) {
						sendError({
							type: "longtask",
							message: `Main thread long task: ${Math.round(entry.duration)}ms`,
							source: "performance.longtask",
							duration_ms: Math.round(entry.duration),
							url: window.location.href,
						});
					}
				});
			}).observe({ entryTypes: ["longtask"] });
		}
	} catch (_) {}

	try {
		if ("PerformanceObserver" in window) {
			let cumulativeLayoutShift = 0;
			let layoutNoticeSent = false;
			new PerformanceObserver((list) => {
				list.getEntries().forEach((entry) => {
					if (entry.hadRecentInput) return;
					cumulativeLayoutShift += entry.value || 0;
					if (!layoutNoticeSent && cumulativeLayoutShift >= LAYOUT_SHIFT_WARN_AT) {
						layoutNoticeSent = true;
						sendError({
							type: "layout",
							message: `High cumulative layout shift: ${cumulativeLayoutShift.toFixed(3)}`,
							source: "performance.layout_shift",
							cls: Number(cumulativeLayoutShift.toFixed(3)),
							url: window.location.href,
						});
					}
				});
			}).observe({ type: "layout-shift", buffered: true });
		}
	} catch (_) {}

	function auditThemeState(reason) {
		try {
			const root = document.documentElement;
			const mode = root.dataset.uiMode || "";
			const variant = root.dataset.uiVariant || "";
			if (VALID_THEME_MODES.indexOf(mode) === -1 || VALID_THEME_VARIANTS.indexOf(variant) === -1) {
				sendError({
					type: "theme",
					message: "Invalid UI theme state",
					source: "ui.theme",
					reason: reason || "audit",
					ui_mode: mode,
					ui_variant: variant,
					url: window.location.href,
				});
			}
		} catch (_) {}
	}

	auditThemeState("boot");
	try {
		new MutationObserver((mutations) => {
			for (let i = 0; i < mutations.length; i += 1) {
				if (
					mutations[i].attributeName === "data-ui-mode" ||
					mutations[i].attributeName === "data-ui-variant"
				) {
					auditThemeState("mutation");
					break;
				}
			}
		}).observe(document.documentElement, {
			attributes: true,
			attributeFilter: ["data-ui-mode", "data-ui-variant"],
		});
	} catch (_) {}
})();

// ── 11. Expose Testable API ──
if (typeof window !== "undefined") {
	window.AzadHelpers = {
		azad: window.azad,
		formatFxRate,
		safeEval,
		updateDateTime,
		loadFxRates,
		getFallbackFx,
		populateFxDisplay,
		getSavedViewMode,
		setViewMode,
		cycleViewMode,
		initNavbarCalculator,
	};
}
