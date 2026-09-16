import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
	createGapJQuery,
	findHandlers,
	installGapGlobals,
	resetGapState,
	loadApp,
	ensureCsrfMeta,
} from "./app_gap_harness.js";

const RICH_DOM = `
<img id="lz1" data-src="/lazy.png" class="lazy" />
<img id="lz2" data-src="/lazy2.png" class="lazy" />
<input id="sq" data-search="products" value="wid" />
<div data-search-target="products" id="sr"></div>
<form id="af" data-autosave="1"><input name="name" value="test" /><input type="password" name="pw" value="s" /></form>
<table class="datatable" id="tb"><thead><tr><th>A</th></tr></thead></table>
<input class="datepicker" id="dp" />
<select class="select2" id="sl"><option value="1">A</option></select>
`;

function mockSocket() {
	const sockHandlers = {};
	const emitted = [];
	globalThis.io = () => ({
		on: (evt, fn) => {
			sockHandlers[evt] = fn;
		},
		emit: (evt, data) => emitted.push([evt, data]),
	});
	return { sockHandlers, emitted };
}

function mockIntersectionObserver() {
	const observed = [];
	const unobserved = [];
	let cb = null;
	class MockIO {
		constructor(fn) {
			cb = fn;
		}
		observe(el) {
			observed.push(el);
		}
		unobserve(el) {
			unobserved.push(el);
		}
		disconnect() {}
	}
	window.IntersectionObserver = MockIO;
	globalThis.IntersectionObserver = MockIO;
	return {
		observed,
		unobserved,
		fire: (entries) => cb(entries, {}),
	};
}

describe("app.js gap100b — perf, search, notify, print, api, safety nets", () => {
	beforeEach(() => {
		resetGapState();
		ensureCsrfMeta();
	});

	afterEach(() => {
		resetGapState();
		vi.useRealTimers();
		vi.restoreAllMocks();
		delete window.IntersectionObserver;
		delete globalThis.IntersectionObserver;
		delete window.print;
		delete window.open;
		delete window.confirm;
	});

	it("boots without IntersectionObserver or socket.io", async () => {
		delete window.IntersectionObserver;
		delete globalThis.IntersectionObserver;
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = '<img data-src="/a.png" class="lazy" id="lz" />';
		await loadApp();
		expect(window.apiFetch).toBeDefined();
		expect(document.getElementById("lz").getAttribute("src")).toBeNull();
	});

	it("lazy images load on intersection and detach", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		const io = mockIntersectionObserver();
		document.body.innerHTML = RICH_DOM;
		await loadApp();

		expect(io.observed).toContain(document.getElementById("lz1"));
		expect(io.observed).toContain(document.getElementById("lz2"));
		io.fire([
			{ isIntersecting: true, target: document.getElementById("lz1") },
			{ isIntersecting: false, target: document.getElementById("lz2") },
		]);
		const lz1 = document.getElementById("lz1");
		expect(lz1.getAttribute("src")).toBe("/lazy.png");
		expect(lz1.classList.contains("lazy")).toBe(false);
		expect(io.unobserved).toContain(lz1);
		expect(document.getElementById("lz2").getAttribute("src")).toBeNull();
	});

	it("debounced search input triggers performSearch after 300ms", async () => {
		const seen = [];
		const $ = createGapJQuery({
			getImpl: (url, params) => {
				seen.push([url, params]);
				return { done: (cb) => ({ fail: () => ({}) }) };
			},
		});
		installGapGlobals($, "ar");
		mockIntersectionObserver();
		document.body.innerHTML = RICH_DOM;
		await loadApp();

		const sq = document.getElementById("sq");
		sq.value = "widget";
		const rec = $._storeOf(sq)["on:input.erpSearch"][0];
		vi.useFakeTimers();
		rec.handler.call(sq);
		// rapid retype resets the timer
		rec.handler.call(sq);
		expect(seen.length).toBe(0);
		vi.advanceTimersByTime(300);
		expect(seen).toEqual([["/api/search", { type: "products", q: "widget" }]]);
	});

	it("autosave input persists the form after debounce", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		mockIntersectionObserver();
		document.body.innerHTML = RICH_DOM;
		await loadApp();

		const form = document.getElementById("af");
		const rec = $._storeOf(form)["on:input change.erpAutoSave"][0];
		vi.useFakeTimers();
		rec.handler.call(form);
		vi.advanceTimersByTime(1000);
		expect(document.getElementById("notification-container")).not.toBeNull();
	});

	it("performSearch renders html, results, empty, and failure states", async () => {
		let mode = "html";
		const $ = createGapJQuery({
			getImpl: () => ({
				done: (cb) => {
					if (mode === "html") cb({ html: '<div class="res">Item</div>' });
					if (mode === "results")
						cb({ results: [{ text: "A", phone: "123" }, { name: "B" }] });
					if (mode === "empty") cb({ results: [] });
					if (mode === "bare") cb({});
					return {
						fail: (fcb) => {
							if (mode === "fail") fcb();
							return {};
						},
					};
				},
			}),
		});
		installGapGlobals($, "ar");
		document.body.innerHTML = RICH_DOM;
		await loadApp();

		const sr = () => document.querySelector('[data-search-target="products"]');
		const before = $._calls.datatable.length;
		expect(before).toBeGreaterThanOrEqual(0);

		window.performSearch("x", "products");
		expect(sr().innerHTML).toBe("");

		mode = "html";
		window.performSearch("ab", "products");
		expect(sr().querySelector(".res")).not.toBeNull();

		mode = "results";
		window.performSearch("ab", "products");
		expect(sr().querySelectorAll(".list-group-item").length).toBe(2);
		expect(sr().innerHTML).toContain("123");

		mode = "empty";
		window.performSearch("ab", "products");
		expect(sr().textContent).toContain("لا توجد نتائج");

		mode = "bare";
		window.performSearch("ab", "products");
		expect(sr().textContent).toContain("لا توجد نتائج");

		mode = "fail";
		window.performSearch("ab", "products");
		expect(sr().querySelector(".alert-danger")).not.toBeNull();
	});

	it("saveFormData stores public fields and toasts", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML =
			'<form id="sf1"><input name="name" value="test" /><input type="password" name="pw" value="secret" /><input type="hidden" name="csrf" value="t" /><input name="api_key" value="k" /><textarea name="notes">hi</textarea></form>';
		await loadApp();

		window.saveFormData($(document.getElementById("sf1")));
		const stored = localStorage.getItem("form_sf1");
		expect(stored).toContain("name=test");
		expect(stored).toContain("notes=hi");
		expect(stored).not.toContain("pw=");
		expect(stored).not.toContain("secret");
		expect(stored).not.toContain("csrf");
		expect(stored).not.toContain("api_key");
		expect(document.getElementById("notification-container").textContent).toContain(
			"تم الحفظ محلياً",
		);
	});

	it("socket.io events fan out to toasts and system alerts", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		const { sockHandlers, emitted } = mockSocket();
		mockIntersectionObserver();
		document.body.innerHTML = RICH_DOM;
		await loadApp();

		expect(emitted).toEqual([["subscribe_notifications", {}]]);
		sockHandlers.notification({ message: "hello", type: "success" });
		expect(document.getElementById("notification-container").textContent).toContain("hello");
		sockHandlers.broadcast_notification({ message: "all", type: "info" });
		expect(document.getElementById("notification-container").textContent).toContain("all");
		sockHandlers.system_alert({ message: "storm", severity: "critical" });
		expect(document.getElementById("system-alert-container").textContent).toContain("storm");
	});

	it("showNotification covers every type and auto-dismisses", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();
		vi.useFakeTimers();

		window.showNotification("T1", "M1", "success");
		let box = document.getElementById("notification-container");
		expect(box.querySelector(".alert-success")).not.toBeNull();
		expect(box.textContent).toContain("T1");
		expect(box.innerHTML).toContain("fa-check-circle");

		window.showNotification("T2", "M2", "error");
		window.showNotification("T3", "M3", "warning");
		window.showNotification("T4", "M4", "info");
		window.showNotification("T5", "M5", "mystery");
		box = document.getElementById("notification-container");
		expect(box.querySelectorAll(".alert").length).toBe(5);
		expect(box.querySelector(".alert-danger")).not.toBeNull();
		expect(box.querySelector(".alert-warning")).not.toBeNull();
		expect(box.querySelectorAll(".alert-info").length).toBe(2);

		const closes = $._calls.alert.length;
		vi.advanceTimersByTime(5000);
		expect($._calls.alert.length).toBeGreaterThan(closes);
	});

	it("showSystemAlert covers severities, defaults, and auto-dismiss", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();
		vi.useFakeTimers();

		window.showSystemAlert("down", "critical");
		let box = document.getElementById("system-alert-container");
		expect(box.querySelector(".alert-danger")).not.toBeNull();
		expect(box.textContent).toContain("down");

		window.showSystemAlert("watch", "warning");
		window.showSystemAlert("note", "info");
		window.showSystemAlert("odd", "mystery");
		window.showSystemAlert("plain");
		box = document.getElementById("system-alert-container");
		expect(box.querySelectorAll(".alert").length).toBe(5);
		expect(box.querySelector(".alert-info")).not.toBeNull();
		expect(box.querySelectorAll(".alert-warning").length).toBe(3);

		const closes = $._calls.alert.length;
		vi.advanceTimersByTime(10000);
		expect($._calls.alert.length).toBeGreaterThan(closes);
	});

	it("printPageReport toggles body class around window.print", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		window.print = vi.fn();
		await loadApp();
		vi.useFakeTimers();

		window.AzadPrint.printPageReport();
		expect(document.body.classList.contains("is-printing-report")).toBe(true);
		vi.advanceTimersByTime(100);
		expect(window.print).toHaveBeenCalled();
		vi.advanceTimersByTime(500);
		expect(document.body.classList.contains("is-printing-report")).toBe(false);
	});

	it("printElement guards missing nodes and popups, prints otherwise", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = '<div id="rpt"><table><tr><td>x</td></tr></table></div>';
		window.open = vi.fn();
		await loadApp();
		vi.useFakeTimers();

		window.AzadPrint.printElement("#nope");
		expect(window.open).not.toHaveBeenCalled();

		window.open = vi.fn(() => null);
		window.AzadPrint.printElement("#rpt");
		expect(window.open).toHaveBeenCalledTimes(1);

		const printWin = {
			document: { open: vi.fn(), write: vi.fn(), close: vi.fn() },
			print: vi.fn(),
			close: vi.fn(),
		};
		window.open = vi.fn(() => printWin);
		window.AzadPrint.printElement("#rpt", { title: "Ledger", headerColor: "#123456" });
		const written = printWin.document.write.mock.calls.map((c) => String(c[0])).join("\n");
		expect(written).toContain("Ledger");
		expect(written).toContain("#123456");
		expect(written).toContain("<td>x</td>");
		vi.advanceTimersByTime(500);
		expect(printWin.print).toHaveBeenCalled();
		expect(printWin.close).toHaveBeenCalled();

		printWin.document.write.mockClear();
		window.AzadPrint.printElement("#rpt");
		const fallback = printWin.document.write.mock.calls.map((c) => String(c[0])).join("\n");
		expect(fallback).toContain("طباعة");
		expect(fallback).toContain("#0d6efd");
		vi.advanceTimersByTime(500);
		expect(printWin.print).toHaveBeenCalledTimes(2);
	});

	it("applyDataTablePrintStyles guards and injects", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();

		expect(() => window.applyDataTablePrintStyles(null)).not.toThrow();
		expect(() => window.applyDataTablePrintStyles({})).not.toThrow();
		expect(() => window.applyDataTablePrintStyles({ document: null })).not.toThrow();

		const creek = document.implementation.createHTMLDocument("print");
		window.applyDataTablePrintStyles({ document: creek });
		const styles = Array.from(creek.querySelectorAll("style"));
		expect(styles.some((s) => s.textContent.includes("A4 landscape"))).toBe(true);
		expect(styles.some((s) => s.textContent.includes("table th, table td"))).toBe(true);
	});

	it("apiFetch sends csrf/json headers and returns data", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();

		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 5 }) }),
		);
		const data = await window.apiFetch("/api/x");
		expect(data).toEqual({ id: 5 });
		const [, opts] = global.fetch.mock.calls[0];
		expect(opts.credentials).toBe("same-origin");
		expect(opts.headers.Accept).toBe("application/json");
		expect(opts.headers["X-CSRFToken"]).toBe("test-csrf");
		expect(opts.headers["Content-Type"]).toBeUndefined();

		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
		);
		await window.apiFetch("/api/x", {
			method: "POST",
			body: JSON.stringify({ a: 1 }),
			headers: { "X-Custom": "yes" },
		});
		const [, post] = global.fetch.mock.calls[0];
		expect(post.headers["Content-Type"]).toBe("application/json");
		expect(post.headers["X-Custom"]).toBe("yes");

		document.querySelector('meta[name="csrf-token"]').remove();
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
		);
		await window.apiFetch("/api/x");
		expect(global.fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("");
		ensureCsrfMeta();

		global.fetch = vi.fn(() => Promise.reject(new TypeError("down")));
		await expect(window.apiFetch("/api/x")).rejects.toThrow("تعذر الاتصال");

		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error("bad")) }),
		);
		await expect(window.apiFetch("/api/x")).resolves.toEqual({});
	});

	it("apiFetch maps server errors and status fallbacks", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();
		const errFetch = (status, payload) => {
			global.fetch = vi.fn(() =>
				Promise.resolve({ ok: false, status, json: () => Promise.resolve(payload) }),
			);
		};

		errFetch(400, { error: "E1" });
		await expect(window.apiFetch("/api/x")).rejects.toThrow("E1");
		errFetch(400, { message: "M1" });
		await expect(window.apiFetch("/api/x")).rejects.toThrow("M1");
		errFetch(400, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("طلب غير صالح");
		errFetch(401, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("انتهت الجلسة");
		errFetch(403, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("ليس لديك صلاحية");
		errFetch(404, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("not_found");
		errFetch(409, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("تعارض");
		errFetch(419, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("انتهت صلاحية النموذج");
		errFetch(429, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("طلبات كثيرة");
		errFetch(500, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("خطأ في الخادم");
		errFetch(418, {});
		await expect(window.apiFetch("/api/x")).rejects.toThrow("(418)");
	});

	it("unhandled rejections toast via notify, Swal, or silently", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = "";
		await loadApp();
		vi.spyOn(console, "error").mockImplementation(() => {});
		const fire = (reason) => {
			const promise = Promise.reject(reason instanceof Error ? reason : new Error("wrap"));
			promise.catch(() => {});
			window.dispatchEvent(
				new PromiseRejectionEvent("unhandledrejection", { promise, reason }),
			);
		};
		const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

		window.notify = { show: vi.fn() };
		fire(new TypeError("net down"));
		await flush();
		expect(window.notify.show).toHaveBeenCalledWith(
			expect.objectContaining({ type: "error", message: expect.stringContaining("تعذر") }),
		);

		window.notify.show.mockClear();
		fire(new Error("kablam"));
		await flush();
		expect(window.notify.show).toHaveBeenCalledWith(
			expect.objectContaining({ type: "error", message: "kablam" }),
		);

		delete window.notify;
		globalThis.Swal = { fire: vi.fn() };
		fire(new Error("swal-mapped"));
		await flush();
		expect(globalThis.Swal.fire).toHaveBeenCalledWith(
			expect.objectContaining({ toast: true, icon: "error", text: "swal-mapped" }),
		);

		delete globalThis.Swal;
		fire("plain-string");
		await flush();
		fire(undefined);
		await flush();
	});

	it("empty plugin registry skips all enhancements but keeps forms alive", async () => {
		const $ = createGapJQuery({ plugins: "empty" });
		installGapGlobals($, "ar");
		document.body.innerHTML = `
		<a id="open1" data-bs-toggle="modal" data-bs-target="#m1" href="#m1">open</a>
		<button class="btn-close" id="bc"></button>
		<table class="datatable" id="tb"><thead><tr><th>A</th></tr></thead></table>
		<input class="datepicker" id="dp" />
		<select class="select2" id="sl"><option value="1">A</option></select>
		<a id="tip" data-toggle="tooltip" title="t">x</a>
		<form id="cf1" data-confirm="Sure?"><input name="x" value="1" /></form>
		<button class="btn-loading" id="btn">Go</button>`;
		await loadApp();

		expect($._calls.datatable.length).toBe(0);
		expect($._calls.tooltip.length).toBe(0);
		expect($._calls.select2.length).toBe(0);
		expect($._calls.datepicker.length).toBe(0);
		expect(document.getElementById("open1").getAttribute("data-toggle")).toBe("modal");
		expect(document.getElementById("bc").classList.contains("close")).toBe(true);
		expect(window.bootstrap).toEqual({});
		expect(window.__bootstrapCompatDelegatesBound).toBe(true);
		expect(document.getElementById("cf1").dataset.confirmBound).toBe("1");
		expect(document.getElementById("btn").dataset.loadingBound).toBe("1");
		expect(typeof window.apiFetch).toBe("function");
	});
});
