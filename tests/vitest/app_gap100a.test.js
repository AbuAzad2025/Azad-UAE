import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
	createGapJQuery,
	findHandlers,
	installGapGlobals,
	resetGapState,
	loadApp,
	ensureCsrfMeta,
} from "./app_gap_harness.js";

const MAIN_DOM = `
<div id="wrap"><div id="m-wrap" class="modal"><div class="modal-dialog"><div class="modal-content"><button id="dis-in" data-bs-dismiss="modal">x</button></div></div></div></div>
<div id="m-body" class="modal show"><div class="modal-dialog"><div class="modal-content">b</div></div></div>
<div class="modal-backdrop"></div>
<div class="modal-backdrop"></div>
<button class="btn-close" id="bc-bare"></button>
<button class="btn-close close" id="bc-full" type="button" aria-label="Dismiss" data-dismiss="modal" data-bs-dismiss="modal"><span>x</span></button>
<button class="btn-close" id="bc-mid" data-bs-dismiss="alert">y</button>
<a id="open1" data-bs-toggle="modal" data-bs-target="#m-body" href="#m-body">open</a>
<a id="open2" data-bs-toggle="modal" href="#">empty</a>
<span id="pre" data-bs-toggle="modal" data-toggle="modal" data-bs-target="#m-body" data-target="#m-body">pre</span>
<button id="dis1" data-bs-dismiss="modal">close</button>
<span id="predis" data-bs-dismiss="modal" data-dismiss="modal">x</span>
<div class="alert" id="al1"><button id="albtn" data-bs-dismiss="alert">x</button></div>
<a id="tab1" data-bs-toggle="tab" href="#t1">t</a>
<a id="pill1" data-bs-toggle="pill" href="#t2">p</a>
<a id="tip1" data-toggle="tooltip" title="hover me">hover</a>
<a id="tip2" data-toggle="tooltip" title="preset">preset</a>
<table class="datatable" id="tbl1" data-page-length="25" data-order="2,desc"><thead><tr><th>Name</th><th class="dt-nosort">Code</th><th class="erp-col-actions"><i class="fa fa-cog"></i></th><th>Actions</th><th>إجراء</th><th>Qty</th><th>Stock <i class="fa fa-cog"></i></th></tr></thead><tbody><tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td><td>f</td><td>g</td></tr></tbody></table>
<table class="datatable" id="tbl2"><thead><tr><th>A</th><th>B</th></tr></thead></table>
<input class="datepicker" id="dp1" />
<select class="select2" id="sel1" placeholder="Pick one"><option value="1">A</option></select>
<select class="select2" id="sel2" data-allow-clear="true"><option value="2">B</option></select>
<select class="select2" id="sel4"><option value="4">D</option></select>
<div class="modal" id="m-sel"><select class="select2" id="sel3"><option value="3">C</option></select></div>
<select class="select2 ajax-select" id="ax1" data-url="/api/items" data-delay="100" data-limit="5" data-min-length="1" data-allow-clear="true"><option value="5">Five</option></select>
<select class="select2 ajax-select" id="ax2" data-url="/api/other"><option value="6">Six</option></select>
<select class="select2 ajax-select" id="ax3"><option value="7">Seven</option></select>
<select class="select2 ajax-select" id="ax4" data-url="/api/back" data-initial-text="Chosen"><option value="a\\b">Back</option></select>
<select class="select2 ajax-select" id="ax5" data-url="/api/empty"></select>
<div class="modal" id="m-ax"><select class="select2 ajax-select" id="ax6" data-url="/api/inmodal" data-endpoint="/api/ignored"><option value="8">Eight</option></select></div>
<form id="cf1" data-confirm="Sure?"><input name="x" value="1" /></form>
<button class="btn-loading" id="btn1">Go</button>
<form id="fbtn"><button class="btn-loading" id="btn2">Save</button></form>
<button class="btn-loading" id="btn3" disabled>Wait</button>
`;

function clearData($, el, key) {
	delete $._storeOf(el)[`data:${key}`];
	const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
	delete el.dataset[camel];
}

describe("app.js gap100a — init, modal, bootstrap, tables, pickers, forms", () => {
	beforeEach(() => {
		resetGapState();
		ensureCsrfMeta();
	});

	afterEach(() => {
		resetGapState();
		vi.useRealTimers();
		vi.restoreAllMocks();
		delete window.confirm;
		delete window.print;
	});

	it("bails out without jQuery", async () => {
		const savedDollar = global.$;
		const savedJQ = global.jQuery;
		global.$ = undefined;
		global.jQuery = undefined;
		await loadApp();
		expect(window.apiFetch).toBeUndefined();
		global.$ = savedDollar;
		global.jQuery = savedJQ;
		window.$ = savedDollar;
	});

	it("main import wires every init path", async () => {
		const $ = createGapJQuery();
		const mo = installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		$(document.getElementById("tip2")).data("bs.tooltip", { preset: true });
		$(document.getElementById("sel4")).data("allowClear", 1);
		await loadApp();

		expect(typeof window.apiFetch).toBe("function");
		expect(window.AzadPrint).toBeDefined();
		expect(typeof window.applyDataTablePrintStyles).toBe("function");
		expect(mo.observeArgs[0]).toBe(document.body);
		expect(mo.observeArgs[1]).toEqual({ childList: true, subtree: true });
		expect(document.querySelectorAll("#azad-modal-compat-style").length).toBe(1);
		// modal moved under body
		expect(document.getElementById("m-wrap").parentElement).toBe(document.body);
		// compat mappings
		expect(document.getElementById("open1").getAttribute("data-toggle")).toBe("modal");
		expect(document.getElementById("open1").getAttribute("data-target")).toBe("#m-body");
		expect(document.getElementById("dis1").getAttribute("data-dismiss")).toBe("modal");
		expect(document.getElementById("pre").getAttribute("data-toggle")).toBe("modal");
		// btn-close normalization
		const bare = document.getElementById("bc-bare");
		expect(bare.classList.contains("close")).toBe(true);
		expect(bare.getAttribute("type")).toBe("button");
		expect(bare.getAttribute("aria-label")).toBe("Close");
		expect(bare.innerHTML).toContain("×");
		expect(document.getElementById("bc-mid").getAttribute("data-dismiss")).toBe("alert");
		// bootstrap facades
		expect(typeof window.bootstrap.Modal).toBe("function");
		expect(typeof window.bootstrap.Tooltip).toBe("function");
		expect(typeof window.bootstrap.Tab).toBe("function");
		expect(typeof window.bootstrap.Alert).toBe("function");
		// tooltips: tip1 initialized, tip2 skipped (preset)
		expect($._calls.tooltip.some((c) => c.el.id === "tip1")).toBe(true);
		expect($._calls.tooltip.some((c) => c.el.id === "tip2")).toBe(false);
		// datatables
		const tbl1 = $._calls.datatable.find((c) => c.el.id === "tbl1");
		expect(tbl1.opts.pageLength).toBe(25);
		expect(tbl1.opts.order).toEqual([[2, "desc"]]);
		expect(tbl1.opts.dom).toBe("Bfrtip");
		expect(tbl1.opts.buttons.length).toBe(2);
		expect(tbl1.opts.language).toEqual({ url: "/static/datatables/Arabic.json" });
		expect(tbl1.opts.columnDefs).toEqual([
			{ orderable: false, targets: [0] },
			{ responsivePriority: 1, targets: [2, 3, 4, 6] },
		]);
		const tbl2 = $._calls.datatable.find((c) => c.el.id === "tbl2");
		expect(tbl2.opts.pageLength).toBe(10);
		expect(tbl2.opts.order).toEqual([]);
		expect(tbl2.opts.columnDefs).toEqual([]);
		// datepicker + select2
		expect($._storeOf(document.getElementById("dp1"))["datepicker:opts"].format).toBe(
			"yyyy-mm-dd",
		);
		const sel1 = $._calls.select2.find((c) => c.el.id === "sel1");
		expect(sel1.opts.dir).toBe("rtl");
		expect(sel1.opts.placeholder).toBe("Pick one");
		expect(sel1.opts.allowClear).toBe(false);
		expect(sel1.opts.dropdownParent[0]).toBe(document.body);
		const sel3 = $._calls.select2.find((c) => c.el.id === "sel3");
		expect(sel3.opts.dropdownParent[0]).toBe(document.getElementById("m-sel"));
		const sel4 = $._calls.select2.find((c) => c.el.id === "sel4");
		expect(sel4.opts.allowClear).toBe(true);
		// ajax selects
		const ax1 = $._calls.select2.find((c) => c.el.id === "ax1");
		expect(ax1.opts.ajax.url).toBe("/api/items");
		expect(ax1.opts.ajax.delay).toBe(100);
		expect(ax1.opts.minimumInputLength).toBe(1);
		expect(ax1.opts.allowClear).toBe(true);
		expect(ax1.opts.dropdownParent[0]).toBe(document.body);
		const ax6 = $._calls.select2.find((c) => c.el.id === "ax6");
		expect(ax6.opts.ajax.url).toBe("/api/inmodal");
		expect(ax6.opts.dropdownParent[0]).toBe(document.getElementById("m-ax"));
		const ax2 = $._calls.select2.find((c) => c.el.id === "ax2");
		expect(ax2.opts.ajax.delay).toBe(250);
		// ax3 has no url -> skipped
		expect($._calls.select2.find((c) => c.el.id === "ax3")).toBeUndefined();
		// ax4 backslash value matches nothing -> initial-text option appended
		const ax4 = document.getElementById("ax4");
		expect(ax4.querySelectorAll('option[value="Chosen"]').length).toBe(0);
		expect(ax4.innerHTML).toContain("Chosen");
		// forms + buttons bound
		expect(document.getElementById("cf1").dataset.confirmBound).toBe("1");
		expect(document.getElementById("btn1").dataset.loadingBound).toBe("1");
	});

	it("mutation observer callback re-runs initAll exactly once per flush", async () => {
		const $ = createGapJQuery();
		const mo = installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		const dtCalls = $._calls.datatable.length;

		vi.useFakeTimers();
		window._mutationPending = true;
		mo.cb();
		expect(window._mutationPending).toBe(true);
		expect($._calls.datatable.length).toBe(dtCalls);

		window._mutationPending = false;
		mo.cb();
		expect(window._mutationPending).toBe(true);
		vi.advanceTimersByTime(60);
		expect(window._mutationPending).toBe(false);
		// second initAll hits already-initialized guards -> no new DataTable calls
		expect($._calls.datatable.length).toBe(dtCalls);
	});

	it("document shown.bs.modal handler falls back to document", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		const recs = findHandlers($, "shown.bs.modal", null);
		expect(recs.length).toBe(1);
		const handler = recs[0].handler;

		const tbl2 = document.getElementById("tbl2");
		clearData($, tbl2, "dt-initialized");
		const before = $._calls.datatable.length;
		handler({ target: document });
		expect($._calls.datatable.length).toBe(before + 1);
		handler({});
		expect($._calls.datatable.length).toBe(before + 1);
	});

	it("modal stacking handlers normalize, layer, and clean up", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();

		const showH = findHandlers($, "show.bs.modal", ".modal")[0].handler;
		const shownH = findHandlers($, "shown.bs.modal", ".modal")[0].handler;
		const hiddenH = findHandlers($, "hidden.bs.modal", ".modal")[0].handler;

		// empty modal -> early return
		showH.call(null);
		// modal nested in wrapper moves to body + body flag
		const mWrap = document.getElementById("m-wrap");
		showH.call(mWrap);
		expect(mWrap.parentElement).toBe(document.body);
		expect(document.body.classList.contains("azad-modal-open")).toBe(true);

		shownH.call(mWrap);
		mWrap.classList.add("show");
		shownH.call(mWrap);
		const shows = Array.from(document.querySelectorAll(".modal.show"));
		expect(shows[0].style.zIndex).toBe("2050");
		expect(shows[1].style.zIndex).toBe("2070");
		const backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
		expect(backdrops[0].style.zIndex).toBe("2040");
		expect(backdrops[1].style.zIndex).toBe("2060");

		vi.useFakeTimers();
		hiddenH.call(mWrap);
		vi.advanceTimersByTime(0);
		// a modal is still shown -> backdrops kept
		expect(document.querySelectorAll(".modal-backdrop").length).toBe(2);

		document.querySelectorAll(".modal.show").forEach((m) => m.classList.remove("show"));
		hiddenH.call(mWrap);
		vi.advanceTimersByTime(0);
		expect(document.querySelectorAll(".modal-backdrop").length).toBe(0);
		expect(document.body.classList.contains("azad-modal-open")).toBe(false);
	});

	it("bootstrap delegated clicks drive modal/alert/tab facades", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();

		const modalToggle = findHandlers($, "click", '[data-bs-toggle="modal"]')[0].handler;
		const dismissed = findHandlers($, "click", '[data-bs-dismiss="modal"]')[0].handler;
		const alertDismiss = findHandlers($, "click", '[data-bs-dismiss="alert"]')[0].handler;
		const tabToggle = findHandlers($, "click", '[data-bs-toggle="tab"], [data-bs-toggle="pill"]')[0]
			.handler;

		const prevented = [];
		const evt = () => ({ preventDefault: () => prevented.push(true) });

		modalToggle.call(document.getElementById("open1"), evt());
		expect($._calls.modal.filter((c) => c.args[0] === "show").length).toBe(1);
		modalToggle.call(document.getElementById("open2"), evt());
		const bare = document.createElement("a");
		bare.setAttribute("data-bs-toggle", "modal");
		modalToggle.call(bare, evt());
		expect($._calls.modal.filter((c) => c.args[0] === "show").length).toBe(1);
		expect(prevented.length).toBe(1);

		dismissed.call(document.getElementById("dis-in"), evt());
		expect($._calls.modal.filter((c) => c.args[0] === "hide").length).toBe(1);

		alertDismiss.call(document.getElementById("albtn"), evt());
		expect($._calls.alert.filter((c) => c.args[0] === "close").length).toBe(1);

		tabToggle.call(document.getElementById("tab1"), evt());
		tabToggle.call(document.getElementById("pill1"), evt());
		expect($._calls.tab.filter((c) => c.args[0] === "show").length).toBe(2);
	});

	it("bootstrap facade classes and factories work", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();

		const mBody = document.getElementById("m-body");
		const modal = new window.bootstrap.Modal(mBody);
		modal.show();
		modal.hide();
		modal.toggle();
		modal.dispose();
		expect($._calls.modal.map((c) => c.args[0])).toEqual(["show", "hide", "toggle", "hide"]);
		expect(window.bootstrap.Modal.getInstance(document.createElement("div"))).toBeNull();
		$(mBody).data("bs.modal", { on: true });
		expect(window.bootstrap.Modal.getInstance(mBody)).not.toBeNull();
		expect(window.bootstrap.Modal.getOrCreateInstance(mBody).show).toBeDefined();

		const tipEl = document.createElement("div");
		const tip = new window.bootstrap.Tooltip(tipEl, { placement: "top" });
		tip.show();
		tip.hide();
		tip.toggle();
		tip.dispose();
		const tip2 = new window.bootstrap.Tooltip(document.createElement("div"));
		tip2.show();
		expect($._calls.tooltip.map((c) => c.args[0])).toContain("show");
		expect(window.bootstrap.Tooltip.getInstance(document.createElement("div"))).toBeNull();
		$(tipEl).data("bs.tooltip", { on: true });
		expect(window.bootstrap.Tooltip.getInstance(tipEl)).not.toBeNull();
		expect(window.bootstrap.Tooltip.getOrCreateInstance(tipEl).hide).toBeDefined();

		const tabEl = document.createElement("div");
		new window.bootstrap.Tab(tabEl).show();
		expect($._calls.tab.map((c) => c.args[0])).toContain("show");
		expect(window.bootstrap.Tab.getInstance(document.createElement("div"))).toBeNull();
		$(tabEl).data("bs.tab", { on: true });
		expect(window.bootstrap.Tab.getInstance(tabEl)).not.toBeNull();
		expect(window.bootstrap.Tab.getOrCreateInstance(tabEl).show).toBeDefined();

		const alertEl = document.createElement("div");
		new window.bootstrap.Alert(alertEl).close();
		expect($._calls.alert.map((c) => c.args[0])).toContain("close");
		expect(window.bootstrap.Alert.getInstance(document.createElement("div"))).toBeNull();
		$(alertEl).data("bs.alert", { on: true });
		expect(window.bootstrap.Alert.getInstance(alertEl)).not.toBeNull();
		expect(window.bootstrap.Alert.getOrCreateInstance(alertEl).close).toBeDefined();
	});

	it("second import reuses stacking, delegates, style, and bootstrap", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		expect(window.__azadModalStackingBound).toBe(true);
		expect(window.__bootstrapCompatDelegatesBound).toBe(true);

		global.$ = $;
		global.jQuery = $;
		window.$ = $;
		await loadApp();
		expect(window.__azadModalStackingBound).toBe(true);
		expect(window.__bootstrapCompatDelegatesBound).toBe(true);
		expect(document.querySelectorAll("#azad-modal-compat-style").length).toBe(1);
		expect(window.bootstrap.Modal).toBeDefined();
	});

	it("datatables without buttons in english use plain dom", async () => {
		const $ = createGapJQuery({ buttons: false });
		installGapGlobals($, "en");
		document.body.innerHTML =
			'<table class="datatable" id="tb"><thead><tr><th>A</th></tr></thead></table>';
		await loadApp();
		const rec = $._calls.datatable.find((c) => c.el.id === "tb");
		expect(rec.opts.dom).toBe("frtip");
		expect(rec.opts.buttons).toEqual([]);
		expect(rec.opts.language).toBeUndefined();
		expect(rec.opts.pageLength).toBe(10);
		expect(rec.opts.order).toEqual([]);
		expect(rec.opts.columnDefs).toEqual([]);
	});

	it("datatables skip tables already handled by native api", async () => {
		const $ = createGapJQuery({ isDataTable: () => true });
		installGapGlobals($, "ar");
		document.body.innerHTML =
			'<table class="datatable" id="tb"><thead><tr><th>A</th></tr></thead></table>';
		await loadApp();
		expect($._calls.datatable.length).toBe(0);
	});

	it("datatable print customize delegates to shared print styles", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		const tbl1 = $._calls.datatable.find((c) => c.el.id === "tbl1");
		const creek = document.implementation.createHTMLDocument("print");
		tbl1.opts.buttons[1].customize({ document: creek });
		const styles = Array.from(creek.querySelectorAll("style"));
		expect(styles.some((s) => s.textContent.includes("A4 landscape"))).toBe(true);
		expect(tbl1.opts.buttons[1].text).toContain("طباعة");
		expect(tbl1.opts.responsive).toBe(true);
		expect(tbl1.opts.autoWidth).toBe(false);
	});

	it("ajax select data/processResults callbacks normalize payloads", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		const ax1 = $._calls.select2.find((c) => c.el.id === "ax1");
		expect(ax1.opts.ajax.data({ term: "x" })).toEqual({ q: "x", limit: 5 });
		expect(ax1.opts.ajax.data({})).toEqual({ q: "", limit: 5 });
		expect(ax1.opts.ajax.dataType).toBe("json");
		expect(ax1.opts.ajax.cache).toBe(true);
		expect(
			ax1.opts.ajax.processResults([
				{ id: 1, text: "One" },
				{ id: 2, name: "Two" },
				{ id: 3 },
			]),
		).toEqual({
			results: [
				{ id: 1, text: "One" },
				{ id: 2, text: "Two" },
				{ id: 3, text: "3" },
			],
		});
		expect(ax1.opts.ajax.processResults({ results: [{ id: 9, text: "N" }] })).toEqual({
			results: [{ id: 9, text: "N" }],
		});
		expect(ax1.opts.ajax.processResults({ data: [{ id: 7, name: "D" }] })).toEqual({
			results: [{ id: 7, text: "D" }],
		});
	});

	it("confirm forms gate submit on dialog result", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		const form = document.getElementById("cf1");
		const handler = $._storeOf(form)["on:submit"][0].handler;
		const evt = () => ({ preventDefault: vi.fn(), stopImmediatePropagation: vi.fn() });

		window.confirm = vi.fn(() => true);
		const okEvt = evt();
		handler.call(form, okEvt);
		expect(window.confirm).toHaveBeenCalledWith("Sure?");
		expect(okEvt.preventDefault).not.toHaveBeenCalled();

		window.confirm = vi.fn(() => false);
		const noEvt = evt();
		handler.call(form, noEvt);
		expect(noEvt.preventDefault).toHaveBeenCalled();
		expect(noEvt.stopImmediatePropagation).toHaveBeenCalled();

		form.removeAttribute("data-confirm");
		const callsBefore = window.confirm.mock.calls.length;
		handler.call(form, evt());
		expect(window.confirm.mock.calls.length).toBe(callsBefore);
	});

	it("loading buttons spin, restore, or stay bound to forms", async () => {
		const $ = createGapJQuery();
		installGapGlobals($, "ar");
		document.body.innerHTML = MAIN_DOM;
		await loadApp();
		vi.useFakeTimers();

		const btn1 = document.getElementById("btn1");
		const btn2 = document.getElementById("btn2");
		const btn3 = document.getElementById("btn3");
		const original = btn1.innerHTML;
		const h1 = $._storeOf(btn1)["on:click"][0].handler;
		const h2 = $._storeOf(btn2)["on:click"][0].handler;
		const h3 = $._storeOf(btn3)["on:click"][0].handler;

		h3.call(btn3);
		expect(btn3.innerHTML).toBe("Wait");

		h1.call(btn1);
		expect(btn1.disabled).toBe(true);
		expect(btn1.getAttribute("aria-busy")).toBe("true");
		expect(btn1.innerHTML).toContain("spinner-border");
		vi.advanceTimersByTime(10000);
		expect(btn1.disabled).toBe(false);
		expect(btn1.getAttribute("aria-busy")).toBe("false");
		expect(btn1.innerHTML).toBe(original);

		h2.call(btn2);
		expect(btn2.disabled).toBe(true);
		vi.advanceTimersByTime(10000);
		expect(btn2.disabled).toBe(true);
	});
});
