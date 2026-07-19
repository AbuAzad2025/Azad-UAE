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
	$("#fxModal").on("show.bs.modal", loadFxRates);
	updateDateTime();
	setInterval(updateDateTime, 1000);
	initNavbarCalculator();
});

document.querySelectorAll('a[href^="/"]').forEach((link) => {
	link.addEventListener(
		"mouseenter",
		function () {
			const url = this.getAttribute("href");
			if (url && !this.dataset.prefetched) {
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

document.querySelectorAll(".flash-message").forEach((alert) => {
	if (
		!alert.classList.contains("alert-permanent") &&
		!alert.classList.contains("alert-danger")
	) {
		const progressBar = alert.querySelector(".flash-timer");
		setTimeout(() => {
			if (progressBar) progressBar.style.width = "0%";
		}, 100);
		setTimeout(() => {
			alert.style.transition = "all 0.5s ease-out";
			alert.style.transform = "translateX(100%)";
			alert.style.opacity = "0";
			setTimeout(() => alert.remove(), 500);
		}, 40000);
	}
});

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
		tbody.textContent = "";
		const tr = document.createElement("tr");
		const td = document.createElement("td");
		td.colSpan = 3;
		const span = document.createElement("span");
		span.className = "spinner-border spinner-border-sm text-muted";
		td.appendChild(span);
		td.appendChild(document.createTextNode(" جارٍ التحميل..."));
		tr.appendChild(td);
		tbody.appendChild(tr);
	}
	try {
		const res = await fetch(window._FX_API_URL, { cache: "no-store" });
		if (!res.ok) {
			populateFxDisplay(getFallbackFx());
			return;
		}
		const data = await res.json();
		if (!data.ok) {
			populateFxDisplay(getFallbackFx());
			return;
		}
		fxDisplayCache = data;
		fxDisplayCacheTime = now;
		populateFxDisplay(data);
	} catch (e) {
		populateFxDisplay(getFallbackFx());
	}
}

function getFallbackFx() {
	return {
		ok: false,
		base: window._FX_FALLBACK_BASE,
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
	const base = data.base || "USD";
	const stale = data.stale || false;
	const source = data.source || "unknown";
	const labels = {
		USD: { ar: "دولار أمريكي", sym: "$" },
		ILS: { ar: "شيقل إسرائيلي", sym: "₪" },
		JOD: { ar: "دينار أردني", sym: "JD" },
		EUR: { ar: "يورو", sym: "€" },
		AED: { ar: window._CURRENCY_NAME_AR, sym: window._CURRENCY_SYMBOL },
		SAR: { ar: "ريال سعودي", sym: "ر.س" },
		EGP: { ar: "جنيه مصري", sym: "ج.م" },
		GBP: { ar: "جنيه إسترليني", sym: "£" },
	};
	const tbody = document.getElementById("fx-rates-body");
	if (!tbody) return;
	let html = "";
	for (const [code, rate] of Object.entries(rates)) {
		const lbl = labels[code] || { ar: code, sym: code };
		html += `<tr>
      <td class="text-right"><strong>${lbl.sym}</strong> <small class="text-muted">${lbl.ar}</small></td>
      <td class="font-weight-bold">${formatFxRate(rate)}</td>
      <td class="text-muted small">1 ${base} = ${formatFxRate(rate)} ${code}</td>
    </tr>`;
	}
	tbody.innerHTML = html;
	const badge = document.getElementById("fx-source-badge");
	if (badge) {
		badge.style.display = "inline-block";
		if (stale || source === "fallback_static") {
			badge.className = "badge badge-warning ml-1";
			badge.textContent = "آخر سعر محفوظ";
		} else {
			badge.className = "badge badge-success ml-1";
			badge.textContent = "مباشر";
		}
	}
	const updatedEl = document.getElementById("fx-last-updated");
	if (updatedEl && data.last_updated) {
		const d = new Date(data.last_updated);
		const timeStr = isNaN(d.getTime())
			? "--"
			: d.toLocaleTimeString("ar-AE", { hour: "2-digit", minute: "2-digit" });
		updatedEl.innerHTML =
			'<i class="fas fa-clock mr-1"></i>آخر تحديث: ' + timeStr;
	}
}

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

function safeEval(expr) {
	const normalized = String(expr || "")
		.replace(/Ã·/g, "/")
		.replace(/Ã—/g, "*")
		.replace(/\^/g, "**")
		.replace(/Ï€/g, "Math.PI")
		.replace(/\be\b/g, "Math.E")
		.replace(/sin\(/g, "Math.sin(")
		.replace(/cos\(/g, "Math.cos(")
		.replace(/tan\(/g, "Math.tan(")
		.replace(/log\(/g, "Math.log10(")
		.replace(/ln\(/g, "Math.log(")
		.replace(/sqrt\(/g, "Math.sqrt(");
	if (!/^[0-9+\-*/().,\sA-Za-z_]*$/.test(normalized)) return "ERR";
	try {
		const val = Function(`"use strict"; return (${normalized});`)();
		if (!Number.isFinite(val)) return "ERR";
		return String(Math.round((val + Number.EPSILON) * 100000000) / 100000000);
	} catch (e) {
		return "ERR";
	}
}

function wirePad(container, display, buttons) {
	if (!container || !display) return;
	container.innerHTML = buttons
		.map(
			(b) =>
				`<button type="button" class="btn btn-outline-secondary m-1" data-calc="${b}">${b}</button>`,
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
			display.value =
				display.value.length > 1 ? display.value.slice(0, -1) : "0";
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
		"Ã·",
		"4",
		"5",
		"6",
		"Ã—",
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
		"Ï€",
		"e",
		"7",
		"8",
		"9",
		"Ã·",
		"4",
		"5",
		"6",
		"Ã—",
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
			const p = parseFloat(
				document.getElementById("loanPrincipal").value || "0",
			);
			const annual = parseFloat(
				document.getElementById("loanRate").value || "0",
			);
			const months = parseInt(
				document.getElementById("loanMonths").value || "0",
				10,
			);
			const out = document.getElementById("loanResult");
			if (!(p > 0) || !(months > 0)) {
				out.textContent = "أدخل قيم صحيحة.";
				return;
			}
			const r = annual / 100 / 12;
			const emi =
				r > 0
					? (p * r * (1 + r) ** months) / ((1 + r) ** months - 1)
					: p / months;
			out.textContent = `القسط الشهري: ${emi.toFixed(2)}`;
		});
	}
	if (btnMarginCalc) {
		btnMarginCalc.addEventListener("click", () => {
			const cost = parseFloat(
				document.getElementById("costValue").value || "0",
			);
			const sell = parseFloat(
				document.getElementById("sellValue").value || "0",
			);
			const out = document.getElementById("marginResult");
			if (!(cost >= 0) || !(sell > 0)) {
				out.textContent = "أدخل قيم صحيحة.";
				return;
			}
			const profit = sell - cost;
			const margin = (profit / sell) * 100;
			const markup = cost > 0 ? (profit / cost) * 100 : 0;
			out.textContent = `الربح: ${profit.toFixed(2)} | Margin: ${margin.toFixed(2)}% | Markup: ${markup.toFixed(2)}%`;
		});
	}
}

const VIEW_MODES = ["auto", "desktop", "mobile"];
const VIEW_MODE_LABELS = { auto: "تلقائي", desktop: "كمبيوتر", mobile: "جوال" };
const VIEW_MODE_ICONS = {
	auto: "fa-desktop",
	desktop: "fa-desktop",
	mobile: "fa-mobile-alt",
};

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
		window.innerWidth + "x" + window.innerHeight,
	);
setViewMode(currentMode);

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
				parsed.pathname.indexOf("/api/") === 0 ||
				parsed.pathname.indexOf("/api_enhanced/") === 0
			);
		} catch (_) {
			return false;
		}
	}
	function getClientContext() {
		const root = document.documentElement;
		return {
			viewport: window.innerWidth + "x" + window.innerHeight,
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
				variableMetricTypes.indexOf(typeForKey) === -1
					? payload.message || ""
					: "",
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
					"X-CSRFToken":
						document.querySelector('meta[name="csrf-token"]')?.content || "",
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
				const resourceUrl =
					target.src || target.href || target.currentSrc || "";
				sendError({
					type: "resource",
					message: "Resource load failed: " + target.tagName,
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
				stack: ev.error && ev.error.stack ? ev.error.stack : null,
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
		} else if (reason && reason.message) {
			msg = reason.message;
			stack = reason.stack || null;
		}
		sendError({
			type: "promise",
			message: msg,
			source: "unhandledrejection",
			lineno: 0,
			colno: 0,
			stack: stack,
			url: window.location.href,
		});
	});

	if (window.fetch) {
		const originalFetch = window.fetch;
		window.fetch = function (input, init) {
			const requestUrl = typeof input === "string" ? input : input && input.url;
			const method = (init && init.method) || (input && input.method) || "GET";
			const absoluteUrl = toAbsoluteUrl(requestUrl);
			const requestIsApi = isApiRequest(absoluteUrl);
			const startedAt =
				window.performance && performance.now ? performance.now() : Date.now();
			activeRequests += 1;
			if (
				activeRequests >= CONCURRENCY_WARN_AT &&
				!shouldSkipRequest(absoluteUrl)
			) {
				const now = Date.now();
				if (now - concurrencyNoticeAt > DUPLICATE_WINDOW_MS) {
					concurrencyNoticeAt = now;
					sendError({
						type: "concurrency",
						message: "High concurrent browser requests: " + activeRequests,
						source: "fetch.concurrency",
						request_url: absoluteUrl,
						method: method,
						url: window.location.href,
					});
				}
			}
			return originalFetch
				.apply(this, arguments)
				.then((response) => {
					const duration = Math.round(
						(window.performance && performance.now
							? performance.now()
							: Date.now()) - startedAt,
					);
					if (response && !response.ok && !shouldSkipRequest(requestUrl)) {
						sendError({
							type: requestIsApi ? "api" : "fetch",
							message:
								(requestIsApi ? "API failed: HTTP " : "Fetch failed: HTTP ") +
								response.status,
							source: requestIsApi ? "fetch.api" : "fetch",
							request_url: absoluteUrl,
							method: method,
							status: response.status,
							duration_ms: duration,
							active_requests: activeRequests,
							request_id:
								response.headers && response.headers.get
									? response.headers.get("X-Request-Id")
									: "",
							url: window.location.href,
						});
					} else if (
						response &&
						duration >= SLOW_REQUEST_MS &&
						!shouldSkipRequest(requestUrl)
					) {
						sendError({
							type: requestIsApi ? "api_slow" : "fetch_slow",
							message:
								(requestIsApi ? "Slow API request" : "Slow fetch request") +
								": " +
								duration +
								"ms",
							source: requestIsApi ? "fetch.api.slow" : "fetch.slow",
							request_url: absoluteUrl,
							method: method,
							status: response.status,
							duration_ms: duration,
							active_requests: activeRequests,
							request_id:
								response.headers && response.headers.get
									? response.headers.get("X-Request-Id")
									: "",
							url: window.location.href,
						});
					}
					activeRequests = Math.max(0, activeRequests - 1);
					return response;
				})
				.catch((err) => {
					if (!shouldSkipRequest(requestUrl)) {
						const duration = Math.round(
							(window.performance && performance.now
								? performance.now()
								: Date.now()) - startedAt,
						);
						sendError({
							type: requestIsApi ? "api" : "fetch",
							message:
								(err && err.message) ||
								(requestIsApi ? "API network error" : "Fetch network error"),
							source: requestIsApi ? "fetch.api" : "fetch",
							request_url: absoluteUrl,
							method: method,
							duration_ms: duration,
							active_requests: activeRequests,
							stack: err && err.stack ? err.stack : null,
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
			const requestUrl = settings && settings.url;
			if (shouldSkipRequest(requestUrl)) return;
			const absoluteUrl = toAbsoluteUrl(requestUrl);
			const requestIsApi = isApiRequest(absoluteUrl);
			sendError({
				type: requestIsApi ? "api" : "ajax",
				message:
					thrownError ||
					(requestIsApi ? "API AJAX failed: HTTP " : "AJAX failed: HTTP ") +
						(xhr && xhr.status),
				source: requestIsApi ? "jquery.ajax.api" : "jquery.ajax",
				request_url: absoluteUrl,
				method: settings && settings.type,
				status: xhr && xhr.status,
				response_size: xhr && xhr.responseText ? xhr.responseText.length : 0,
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
							message:
								"Main thread long task: " + Math.round(entry.duration) + "ms",
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
					if (
						!layoutNoticeSent &&
						cumulativeLayoutShift >= LAYOUT_SHIFT_WARN_AT
					) {
						layoutNoticeSent = true;
						sendError({
							type: "layout",
							message:
								"High cumulative layout shift: " +
								cumulativeLayoutShift.toFixed(3),
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
			if (
				VALID_THEME_MODES.indexOf(mode) === -1 ||
				VALID_THEME_VARIANTS.indexOf(variant) === -1
			) {
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
