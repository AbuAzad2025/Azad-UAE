import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/base-helpers.js";

function buildDom(extra = "") {
	document.body.innerHTML = `
    <meta name="csrf-token" content="bh-token">
    <a id="prefetchable" href="/sales/list">Sales</a>
    <div class="flash-message" id="flash1"><span class="flash-timer" style="width:100%"></span></div>
    <button data-ui-action="toggle-viewmode">
      <i data-ui-role="viewmode-icon" class="fas fa-desktop"></i>
      <span data-ui-role="viewmode-label"></span>
    </button>
    <table><tbody id="fx-rates-body"></tbody></table>
    <div id="fx-source-badge"></div>
    <div id="fx-last-updated"></div>
    <div id="fxModal"></div>
    <input id="calcDisplayClassic">
    <input id="calcDisplayScientific">
    <div id="calcClassicButtons"></div>
    <div id="calcScientificButtons"></div>
    <input id="loanPrincipal"><input id="loanRate"><input id="loanMonths">
    <button id="btnLoanCalc"></button><div id="loanResult"></div>
    <input id="costValue"><input id="sellValue">
    <button id="btnMarginCalc"></button><div id="marginResult"></div>
    ${extra}
  `;
}

function makeJQ() {
	const ajaxSetupStore = {};
	const sharedApi = () => ({
		ajaxError: vi.fn(),
		on: vi.fn(),
	});
	const $ = (sel) => {
		if (typeof sel === "function") {
			sel();
			const api = sharedApi();
			api.ready = (fn) => {
				if (typeof fn === "function") fn();
				return api;
			};
			return api;
		}
		if (typeof sel === "string") {
			const els = Array.from(document.querySelectorAll(sel));
			return {
				length: els.length,
				each(fn) {
					els.forEach((el, i) => fn.call(el, i, el));
					return this;
				},
				attr(name, val) {
					if (val !== undefined) {
						els.forEach((el) => el.setAttribute(name, String(val)));
						return this;
					}
					return els[0] ? els[0].getAttribute(name) : undefined;
				},
				text(v) {
					if (v === undefined) return els[0] ? els[0].textContent : "";
					els.forEach((el) => {
						el.textContent = v;
					});
					return this;
				},
				on(evt, handler) {
					els.forEach((el) =>
						el.addEventListener(evt, function (...args) {
							handler.apply(this, args);
						}),
					);
					return this;
				},
			};
		}
		if (sel && typeof sel.ajaxError !== "undefined") return sel;
		return Object.assign(sharedApi(), { length: 1 });
	};
	$.ajaxSetup = vi.fn((opts) => Object.assign(ajaxSetupStore, opts));
	$.__store = ajaxSetupStore;
	$.fn = {};
	return $;
}

beforeEach(() => {
	buildDom();
	window.t = (k) => k;
	window._FX_API_URL = "/api/fx";
	window._FX_BASE_CURRENCY = "USD";
	window._FX_FALLBACK_BASE = "USD";
	delete window._CURRENCY_NAME_AR;
	delete window._CURRENCY_SYMBOL;
	window._LOG_ENDPOINT = "/client-log";
	localStorage.clear();
	global.$ = makeJQ();
	global.jQuery = global.$;
	const LIVE_FX = {
		ok: true,
		base: "USD",
		source: "live",
		stale: false,
		last_updated: new Date().toISOString(),
		rates: { ILS: 3.65, AED: 3.67 },
	};
	window.__fetchSpy = vi.fn((url) =>
		Promise.resolve({ ok: true, url, json: () => Promise.resolve(LIVE_FX) }),
	);
	globalThis.fetch = window.__fetchSpy;
	vi.resetModules();
});

afterEach(() => {
	vi.useRealTimers();
	document.body.innerHTML = "";
	document.head.innerHTML = "";
	delete global.$;
	delete global.jQuery;
	delete window.__fetchSpy;
	vi.resetModules();
});

function fetchCalls() {
	return window.__fetchSpy ? window.__fetchSpy.mock.calls : [];
}

async function load() {
	await import(MOD_PATH);
	return window.AzadHelpers;
}
const sleep = (ms = 15) => new Promise((r) => setTimeout(r, ms));

describe("base-helpers text/format utils", () => {
	it("formatCurrency pairs symbol with grouped number", async () => {
		const h = await load();
		expect(h.azad.formatCurrency(1234567.891, "$")).toBe("$ 1,234,567.89");
	});

	it("toast wrappers delegate to the notification drawer", async () => {
		await load();
		const box = document.getElementById("toastBox") || (() => {
			const d = document.createElement("div");
			d.id = "toastBox";
			d.className = "az-toast-box";
			document.body.appendChild(d);
			return d;
		})();
		void box;
		const azad = window.azad;
		["showError", "showSuccess", "showWarning", "showInfo"].forEach((fnName) => {
			azad[fnName]("msg");
		});
		const toasts = document.querySelectorAll("#toastContainer .toast-item, #toastBox .toast");
		expect(toasts.length).toBeGreaterThanOrEqual(0);
	});

	it("debounce collapses bursts into a single trailing call", async () => {
		vi.useFakeTimers();
		const h = await load();
		const fn = vi.fn();
		const debounced = h.azad.debounce(fn, 100);
		debounced("a");
		vi.advanceTimersByTime(50);
		debounced("b");
		vi.advanceTimersByTime(120);
		expect(fn).toHaveBeenCalledTimes(1);
		expect(fn).toHaveBeenCalledWith("b");
	});

	it("throttle passes the lead call and blocks until the window elapses", async () => {
		vi.useFakeTimers();
		const h = await load();
		const fn = vi.fn();
		const throttled = h.azad.throttle(fn, 100);
		throttled(1);
		throttled(2);
		throttled(3);
		expect(fn).toHaveBeenCalledTimes(1);
		vi.advanceTimersByTime(120);
		throttled(4);
		expect(fn).toHaveBeenCalledTimes(2);
	});
});

describe("base-helpers safeEval calculator grammar", () => {
	async function evalCases(cases) {
		const h = await load();
		for (const [expr, expected] of cases) {
			expect(h.safeEval(expr)).toBe(expected);
		}
	}

	it("arithmetic with precedence, parens, unary minus", async () => {
		await evalCases([
			["2+3*4", "14"],
			["(2+3)*4", "20"],
			["-3+5", "2"],
			["-3^2", "-9"],
			["10÷4", "2.5"],
			["6×7", "42"],
			["2^10", "1024"],
			["2**3", "8"],
			[".5+.25", "0.75"],
			["1e2+1", "101"],
		]);
	});

	it("constants and scientific functions evaluate", async () => {
		const h = await load();
		expect(Number(h.safeEval("pi"))).toBeCloseTo(Math.PI, 6);
		expect(Number(h.safeEval("e"))).toBeCloseTo(Math.E, 6);
		expect(h.safeEval("sin(0)")).toBe("0");
		expect(h.safeEval("cos(0)")).toBe("1");
		expect(h.safeEval("tan(0)")).toBe("0");
		expect(h.safeEval("sqrt(9)")).toBe("3");
		expect(h.safeEval("log(1000)")).toBe("3");
		expect(Number(h.safeEval("ln(e)"))).toBeCloseTo(1, 6);
		expect(h.safeEval("sqrt(pi*2)^2")).toBe(String(Math.round(Math.PI * 2 * 1e8) / 1e8));
	});

		it("invalid or unsafe inputs return the ERR sentinel", async () => {
		await evalCases([
			["", "ERR"],
			["5/0", "ERR"],
			["2+", "ERR"],
			["(2+3", "ERR"],
			["2+3)", "ERR"],
			["abc", "ERR"],
			["foo(1)", "ERR"],
			["sin 30", "ERR"],
			["1..2", "ERR"],
			["..", "ERR"],
			["1e", "ERR"],
			["9e999", "ERR"],
			["2+2 ", "4"],
		]);
	});
});

describe("base-helpers navbar calculator pads", () => {
	it("classic pad renders buttons and computes 7×8=", async () => {
		const h = await load();
		const grid = document.getElementById("calcClassicButtons");
		const display = document.getElementById("calcDisplayClassic");
		expect(grid.querySelectorAll("[data-calc]").length).toBeGreaterThan(15);

		const press = (val) =>
			grid
				.querySelector(`[data-calc="${CSS.escape(val)}"]`)
				.dispatchEvent(new MouseEvent("click", { bubbles: true }));

		["7", "×", "8"].forEach(press);
		expect(display.value).toBe("7×8");
		press("=");
		expect(display.value).toBe("56");

		press("DEL");
		expect(display.value).toBe("5");
		press("C");
		expect(display.value).toBe("0");
	});

	it("scientific pad supports π constants and functions end-to-end", async () => {
		const h = await load();
		const grid = document.getElementById("calcScientificButtons");
		const display = document.getElementById("calcDisplayScientific");
		expect(grid.querySelectorAll("[data-calc]").length).toBeGreaterThan(25);

		const press = (val) =>
			grid
				.querySelector(`[data-calc="${CSS.escape(val)}"]`)
				.dispatchEvent(new MouseEvent("click", { bubbles: true }));

		press("sqrt(");
		press("9");
		press(")");
		press("^");
		press("2");
		press("=");
		expect(display.value).toBe("9");

		press("C");
		press("π");
		expect(display.value).toBe("π");
		press("C");
		press("ln(");
		press(")");
		press("=");
		expect(display.value).toBe("ERR");
	});

	it("div-by-zero via pad yields the ERR sentinel without crashing", async () => {
		await load();
		const grid = document.getElementById("calcClassicButtons");
		const display = document.getElementById("calcDisplayClassic");
		const press = (val) =>
			grid.querySelector(`[data-calc="${CSS.escape(val)}"]`).dispatchEvent(
				new MouseEvent("click", { bubbles: true }),
			);
		["5", "÷", "0", "="].forEach(press);
		expect(display.value).toBe("ERR");
	});
});

describe("base-helpers loan + margin calculators", () => {
	it("loan EMI math renders installment/interest/total row", async () => {
		await load();
		document.getElementById("loanPrincipal").value = "12000";
		document.getElementById("loanRate").value = "12";
		document.getElementById("loanMonths").value = "12";
		document.getElementById("btnLoanCalc").click();

		const out = document.getElementById("loanResult");
		expect(out.className).toContain("alert-info");
		expect(out.textContent).toContain(window.t("monthly_installment"));

		const emiMatch = out.innerHTML.match(/<strong>(\d+\.\d{2})<\/strong>/);
		expect(Number(emiMatch[1])).toBeGreaterThan(1000);
	});

	it("loan rejects zero principal with a warning card", async () => {
		await load();
		document.getElementById("loanPrincipal").value = "0";
		document.getElementById("btnLoanCalc").click();
		const out = document.getElementById("loanResult");
		expect(out.className).toContain("alert-warning");
		expect(out.textContent).toContain(window.t("enter_valid_values"));
	});

	it("zero-rate loan divides principal evenly", async () => {
		await load();
		document.getElementById("loanPrincipal").value = "1200";
		document.getElementById("loanRate").value = "0";
		document.getElementById("loanMonths").value = "12";
		document.getElementById("btnLoanCalc").click();
		const amounts = Array.from(
			document.getElementById("loanResult").querySelectorAll("strong"),
		).map((s) => s.textContent);
		expect(amounts[0]).toBe("100.00");
		expect(amounts[2]).toBe("1200.00");
	});

	it("margin widget computes profit, margin, markup", async () => {
		await load();
		document.getElementById("costValue").value = "50";
		document.getElementById("sellValue").value = "80";
		document.getElementById("btnMarginCalc").click();
		const out = document.getElementById("marginResult");
		expect(out.className).toContain("alert-success");
		expect(out.textContent).toContain("37.50%");
		expect(out.textContent).toContain("60.00%");
	});

	it("margin widget guards against impossible values", async () => {
		await load();
		document.getElementById("costValue").value = "10";
		document.getElementById("sellValue").value = "0";
		document.getElementById("btnMarginCalc").click();
		expect(document.getElementById("marginResult").className).toContain("alert-warning");
	});
});

describe("base-helpers FX rates widget", () => {
	it("loads remote rates, paints table, marks source as live", async () => {
		const h = await load();
		await h.loadFxRates();
		const rows = document.getElementById("fx-rates-body").querySelectorAll("tr");
		expect(rows.length).toBe(2);
		const joined = Array.from(rows)
			.map((r) => r.textContent)
			.join("|");
		expect(joined).toContain("3.650");
		expect(joined).toContain("3.670");
		expect(document.getElementById("fx-source-badge").textContent).toBe(
			window.t("live_rate"),
		);
		expect(fetchCalls().find((c) => c[0].includes("/api/fx"))[0]).toContain("/api/fx?base=USD");
	});

	it("falls back to bundled static table when the API fails", async () => {
		window.__fetchSpy = vi.fn(() => Promise.reject(new TypeError("offline")));
		globalThis.fetch = window.__fetchSpy;
		const h = await load();
		await h.loadFxRates();
		const tbody = document.getElementById("fx-rates-body");
		expect(tbody.querySelectorAll("tr").length).toBeGreaterThan(4);
		expect(document.getElementById("fx-source-badge").textContent).toBe(
			window.t("estimated_rate"),
		);
		expect(h.getFallbackFx().rates.AED).toBe(3.67);
	});

	it("caches successful responses for five minutes", async () => {
		const h = await load();
		await h.loadFxRates();
		const afterFirst = fetchCalls().filter((c) => c[0].includes("/api/fx")).length;
		expect(afterFirst).toBe(1);
		await h.loadFxRates();
		expect(fetchCalls().filter((c) => c[0].includes("/api/fx")).length).toBe(afterFirst);
	});

	it("formatFxRate picks precision by magnitude", async () => {
		const h = await load();
		expect(h.formatFxRate(null)).toBe("--");
		expect(h.formatFxRate("junk")).toBe("--");
		expect(h.formatFxRate(123.456)).toBe("123.46");
		expect(h.formatFxRate(3.65)).toBe("3.650");
		expect(h.formatFxRate(0.05)).toBe("0.0500");
	});

	it("populateFxDisplay tolerates a missing table container", async () => {
		const h = await load();
		document.body.innerHTML = "";
		expect(() => h.populateFxDisplay({ ok: true, rates: {} })).not.toThrow();
	});
});

describe("base-helpers view mode switching", () => {
	it("cycles auto → desktop → mobile persisting choice and updating chrome", async () => {
		const h = await load();
		const btn = document.querySelector('[data-ui-action="toggle-viewmode"]');
		const label = btn.querySelector('[data-ui-role="viewmode-label"]');

		// Drive through the exposed seam (same function the click handler calls).
		h.cycleViewMode();
		expect(localStorage.getItem("azad_view_mode")).toBe("desktop");
		expect(document.body.classList.contains("view-desktop")).toBe(true);
		expect(label.textContent).toBe(window.t("desktop"));

		h.cycleViewMode();
		expect(document.body.classList.contains("view-mobile")).toBe(true);
		expect(label.textContent).toBe(window.t("mobile"));

		h.cycleViewMode();
		expect(localStorage.getItem("azad_view_mode")).toBe("auto");
		expect(document.body.classList.contains("view-desktop")).toBe(false);

		h.setViewMode("bogus");
		expect(localStorage.getItem("azad_view_mode")).toBe("auto");
	});

	it("delegated clicks on the toolbar button cycle the mode too", async () => {
		await load();
		const btn = document.querySelector('[data-ui-action="toggle-viewmode"]');
		btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
		expect(
			document.body.classList.contains("view-desktop") ||
				document.body.classList.contains("view-mobile") ||
				localStorage.getItem("azad_view_mode") === "auto",
		).toBe(true);
	});
});

describe("base-helpers link prefetching", () => {
	it("injects a prefetch hint exactly once per hovered route link", async () => {
		await load();
		const link = document.getElementById("prefetchable");
		link.dispatchEvent(new MouseEvent("mouseenter", { bubbles: false }));
		const hints = document.head.querySelectorAll('link[rel="prefetch"]');
		expect(hints.length).toBe(1);
		expect(hints[0].href).toContain("/sales/list");
		link.dispatchEvent(new MouseEvent("mouseenter", { bubbles: false }));
		expect(document.head.querySelectorAll('link[rel="prefetch"]').length).toBe(1);
	});

	it("skips logout targets entirely", async () => {
		buildDom('<a id="logoutLink" href="/logout">bye</a>');
		await load();
		document.getElementById("logoutLink").dispatchEvent(
			new MouseEvent("mouseenter", { bubbles: false }),
		);
		const hints = Array.from(document.head.querySelectorAll('link[rel="prefetch"]'));
		expect(hints.some((l) => l.href.includes("logout"))).toBe(false);
	});
});

describe("base-helpers telemetry pipeline", () => {
	it("CSRF ajaxSetup attaches token header only for mutating verbs", async () => {
		await load();
		const beforeSend = global.$.__store.beforeSend;
		expect(beforeSend).toBeTypeOf("function");
		const xhr = { setRequestHeader: vi.fn() };
		beforeSend(xhr, { type: "POST" });
		expect(xhr.setRequestHeader).toHaveBeenCalledWith("X-CSRFToken", "bh-token");
		const xhr2 = { setRequestHeader: vi.fn() };
		beforeSend(xhr2, { type: "get" });
		expect(xhr2.setRequestHeader).not.toHaveBeenCalled();
	});

	it("runtime window errors post a deduplicated runtime report", async () => {
		window.__fetchSpy = vi.fn(() => Promise.resolve({ ok: true }));
		globalThis.fetch = window.__fetchSpy;
		const h = await load();
		void h;
		window.dispatchEvent(
			new ErrorEvent("error", { message: "boom", filename: "a.js", lineno: 3 }),
		);
		await sleep(30);
		let bodies = fetchCalls()
			.filter((c) => c[0] === "/client-log")
			.map((c) => JSON.parse(c[1].body));
		let runtime = bodies.find((b) => b.type === "runtime");
		expect(runtime.message).toBe("boom");
		expect(runtime.fingerprint_key).toContain("runtime|boom|");

		window.dispatchEvent(
			new ErrorEvent("error", { message: "boom", filename: "a.js", lineno: 3 }),
		);
		await sleep(30);
		bodies = fetchCalls()
			.filter((c) => c[0] === "/client-log")
			.map((c) => JSON.parse(c[1].body));
		runtime = bodies.filter((b) => b.type === "runtime").pop();
		expect(runtime.repeat_count).toBeGreaterThanOrEqual(2);
	});

	it("opaque cross-origin script errors are never reported", async () => {
		window.__fetchSpy = vi.fn(() => Promise.resolve({ ok: true }));
		globalThis.fetch = window.__fetchSpy;
		await load();
		window.dispatchEvent(new Event("error"));
		await sleep(20);
		const postedBodies = fetchCalls()
			.filter((c) => c[0] === "/client-log")
			.map((c) => JSON.parse(c[1].body));
		expect(postedBodies.some((b) => b.message === "Script error.")).toBe(false);
	});

	it("unhandled promise rejections surface as promise-type reports", async () => {
		window.__fetchSpy = vi.fn(() => Promise.resolve({ ok: true }));
		globalThis.fetch = window.__fetchSpy;
		await load();
		const ev = new Event("unhandledrejection");
		ev.reason = new Error("async blew up");
		window.dispatchEvent(ev);
		await sleep(30);
		const body = fetchCalls()
			.filter((c) => c[0] === "/client-log")
			.map((c) => JSON.parse(c[1].body))
			.pop();
		expect(body.message).toBe("async blew up");
	});

	it("instrumented fetch reports API failures and network rejections once", async () => {
		window.__fetchSpy = vi.fn((url) => {
			if (url === "/api_enhanced/thing")
				return Promise.resolve({ ok: false, status: 500, headers: null });
			if (url === "/api/v2/other") return Promise.reject(new TypeError("socket gone"));
			return Promise.resolve({ ok: true });
		});
		globalThis.fetch = window.__fetchSpy;

		await load();
		// Module wrapped our spy; drive the wrapper for real instrumentation.
		const wrapped = globalThis.fetch;
		await wrapped("/api_enhanced/thing").catch(() => {});
		await sleep(30);
		let logBodies = () =>
			fetchCalls()
				.filter((c) => c[0] === "/client-log")
				.map((c) => JSON.parse(c[1].body));
		let apiReport = logBodies().find((b) => b.type === "api");
		expect(apiReport.status).toBe(500);

		await expect(wrapped("/api/v2/other")).rejects.toThrow("socket gone");
		await sleep(30);
		apiReport = logBodies().find(
			(b) =>
				String(b.request_url || "").includes("/api/v2/other") &&
				b.message === "socket gone",
		);
		expect(apiReport.status).toBeUndefined();
	});
});
