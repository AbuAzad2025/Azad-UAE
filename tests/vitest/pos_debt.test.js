import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const ELEMENT_IDS = [
	"cameraScanBtn", "cartBody", "cartCount", "checkoutBtn", "checkoutPrintBtn",
	"clearCartBtn", "clearCustomer", "clearProductSearch", "closeCashSales", "closeExpected",
	"closeExpectedBlock", "closeOpening", "closeSessionBalance", "closeSessionBtn",
	"closeSessionConfirm", "closeSessionNotes", "currency", "customerResults",
	"customerSearch", "customerSelectedHint", "discountAmount", "donePrintBtn",
	"doneSaleNumber", "doneUpsellList", "doneViewBtn", "drawerOpenBtn",
	"exchangeRate", "kpiChange", "kpiCurrency", "kpiDiscount", "kpiSubtotal", "kpiTotal",
	"openSessionBalance", "openSessionBtn", "openSessionConfirm", "openSessionNotes",
	"orderNote", "orderType", "paidAmount", "paymentMethod", "posAlert",
	"posCalc", "posCategories", "posFloors", "posHoldBtn", "posPayMethod", "posPinConfirm",
	"posPinError", "posPinInput", "posPinModal", "posProductGrid", "posSessionBar",
	"posSessionRequired", "posTableClear", "posTablesBtn", "posTableSelected",
	"posTablesGrid", "productLoading", "productResults", "productSearch",
	"pushTerminalBtn", "referenceNumber", "refField", "scaleConnectBtn",
	"sessionBalance", "sessionNumber", "sessionTime", "sessionTotal",
	"shippingCost", "splitTenderAdd", "splitTenderBox", "splitTenderRows",
	"splitTenderSum", "splitTenderToggle", "tableField", "tableSelect",
	"taxRate", "upsellBar", "walkinCustomer", "warehouseId",
];

let mockSession = null;
let checkoutBodies = [];
let closeCalls = 0;

const buildFetchMock = () =>
	vi.fn(async (url) => {
		const u = String(url);
		const json = async (obj) => obj;
		if (u.includes("/pos/api/session/current")) {
			return {
				ok: true,
				status: 200,
				json: async () =>
					mockSession ? { success: true, data: { session: mockSession } } : { success: false },
			};
		}
		if (u.includes("/pos/api/session/close")) {
			closeCalls += 1;
			return {
				ok: true,
				status: 200,
				json: async () => ({ success: true, data: { session: { difference: 0 } } }),
			};
		}
		if (u.includes("/pos/api/checkout")) {
			checkoutBodies.push(JSON.parse(arguments.length ? "{}" : "{}"));
			return { ok: true, status: 200 };
		}
		return { ok: true, status: 200, json: async () => ({ success: false }) };
	});

const buildJqMock = () => {
	const jq = vi.fn(() => ({
		on: vi.fn(),
		ready: vi.fn((cb) => cb()),
		modal: vi.fn(),
		val: vi.fn(() => ""),
	}));
	jq.fn = { select2: vi.fn(), DataTable: { isDataTable: vi.fn(() => false) } };
	return jq;
};

const INPUT_IDS = new Set([
	"paidAmount", "orderNote", "referenceNumber", "taxRate", "shippingCost",
	"discountAmount", "currency", "exchangeRate", "warehouseId",
	"openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes",
]);

const buildDom = () => {
	const meta = document.createElement("meta");
	meta.setAttribute("name", "csrf-token");
	meta.setAttribute("content", "test-csrf");
	document.head.appendChild(meta);
	for (const id of ELEMENT_IDS) {
		if (id === "paymentMethod") continue;
		const el = document.createElement(INPUT_IDS.has(id) ? "input" : "div");
		el.id = id;
		document.body.appendChild(el);
	}
	const pmSel = document.createElement("select");
	pmSel.id = "paymentMethod";
	const opt = document.createElement("option");
	opt.value = "cash";
	pmSel.appendChild(opt);
	pmSel.value = "cash";
	document.body.appendChild(pmSel);
	const calc = document.getElementById("posCalc");
	const totalBtn = document.createElement("button");
	totalBtn.setAttribute("data-act", "total");
	calc.appendChild(totalBtn);
	const wrap = document.getElementById("posPayMethod");
	["cash", "card"].forEach((m) => {
		const tile = document.createElement("div");
		tile.className = "pm";
		tile.setAttribute("data-method", m);
		wrap.appendChild(tile);
	});
};

const flush = async (ms = 20) => {
	if (vi.isFakeTimers()) {
		await vi.advanceTimersByTimeAsync(ms);
	} else {
		await new Promise((r) => setTimeout(r, ms));
	}
};

const bootModule = async () => {
	await import("../../static/js/pos/index.js");
	await flush();
};

describe("pos debt behaviors", () => {
	beforeEach(() => {
		vi.resetModules();
		document.body.innerHTML = "";
		document.head.innerHTML = "";
		localStorage.clear();
		sessionStorage.clear();
		mockSession = null;
		checkoutBodies = [];
		closeCalls = 0;
		buildDom();
		global.$ = global.jQuery = buildJqMock();
		const MockScanner = vi.fn(function () {
			return { start: vi.fn(), stop: vi.fn() };
		});
		global.BarcodeScanner = window.BarcodeScanner = MockScanner;
		window.t = window.t || ((k) => k);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
		document.body.innerHTML = "";
		document.head.innerHTML = "";
		delete global.$;
		delete global.jQuery;
		delete global.BarcodeScanner;
		delete window.BarcodeScanner;
		vi.resetModules();
	});

	it("numpad total copies lastTotals.total into paid amount", async () => {
		global.fetch = buildFetchMock();
		await bootModule();
		window._posState.lastTotals = { total: 123.45 };
		document.querySelector('#posCalc button[data-act="total"]').click();
		await new Promise((r) => setTimeout(r, 10));
		expect(document.getElementById("paidAmount").value).toBe("123.45");
	});

	it("decrement to zero removes row and rotates idempotency key", async () => {
		global.fetch = buildFetchMock();
		await bootModule();
		window._posState.cart.push({ id: 1, name: "A", qty: 1, price: 10, basePrice: 10, discountPercent: 0 });
		const oldKey = window._posState.idemKey;
		const dec = document.createElement("button");
		dec.setAttribute("data-act", "dec");
		dec.setAttribute("data-i", "0");
		document.getElementById("cartBody").appendChild(dec);
		dec.click();
		await new Promise((r) => setTimeout(r, 10));
		expect(window._posState.cart.length).toBe(0);
		expect(window._posState.idemKey).not.toBe(oldKey);
	});

	it("clearCartBtn requires confirmation and resets state", async () => {
		global.fetch = buildFetchMock();
		await bootModule();
		window._posState.cart.push({ id: 1, name: "A", qty: 1, price: 10, basePrice: 10, discountPercent: 0 });
		const oldKey = window._posState.idemKey;
		const confirmSpy = vi.fn(() => false);
		vi.stubGlobal("confirm", confirmSpy);
		document.getElementById("clearCartBtn").click();
		await new Promise((r) => setTimeout(r, 10));
		expect(confirmSpy).toHaveBeenCalledOnce();
		expect(window._posState.cart.length).toBe(1);
		confirmSpy.mockReturnValue(true);
		document.getElementById("clearCartBtn").click();
		await new Promise((r) => setTimeout(r, 10));
		expect(window._posState.cart.length).toBe(0);
		expect(window._posState.idemKey).not.toBe(oldKey);
	});

	it("hold badge reflects parked carts at init", async () => {
		localStorage.setItem("pos_held_carts", JSON.stringify([{ id: "h1" }, { id: "h2" }]));
		global.fetch = buildFetchMock();
		await bootModule();
		expect(document.getElementById("posHoldBtn").innerHTML).toContain('class="badge warn"');
		expect(document.getElementById("posHoldBtn").innerHTML).toContain(">2<");
	});

	it("hold badge renders without span when nothing parked", async () => {
		global.fetch = buildFetchMock();
		await bootModule();
		expect(document.getElementById("posHoldBtn").innerHTML).not.toContain("badge warn");
	});

	it("session timer ticks every minute and clears after close", async () => {
		vi.useFakeTimers();
		mockSession = {
			number: "POS-1",
			opening_balance: 0,
			total_sales: 0,
			duration_minutes: 1,
			opened_at: new Date(Date.now() - 60000).toISOString(),
		};
		const fetchMock = buildFetchMock();
		global.fetch = fetchMock;
		await bootModule();
		await vi.advanceTimersByTimeAsync(0);
		expect(document.getElementById("sessionTime").textContent).toContain("1");
		await vi.advanceTimersByTimeAsync(60000);
		expect(document.getElementById("sessionTime").textContent).toContain("2");
		expect(window.__sesTimer).toBeTruthy();
		mockSession = null;
		document.getElementById("closeSessionBalance").value = "0";
		document.getElementById("closeSessionConfirm").click();
		await vi.advanceTimersByTimeAsync(50);
		expect(closeCalls).toBe(1);
		expect(window.__sesTimer).toBeNull();
	});

	it("serialized product prompts once, forces qty 1, stores serial", async () => {
		global.fetch = buildFetchMock();
		const promptSpy = vi.fn(() => "SN-77");
		vi.stubGlobal("prompt", promptSpy);
		await bootModule();
		const ok = await window._posAddToCart({ id: 9, name: "Serial X", price: 100, has_serial_number: true });
		expect(ok).toBe(true);
		expect(promptSpy).toHaveBeenCalledOnce();
		expect(window._posState.cart.length).toBe(1);
		expect(window._posState.cart[0].qty).toBe(1);
		expect(window._posState.cart[0].serial).toBe("SN-77");
	});

	it("serialized add cancelled without serial leaves cart untouched", async () => {
		global.fetch = buildFetchMock();
		vi.stubGlobal("prompt", vi.fn(() => ""));
		await bootModule();
		const ok = await window._posAddToCart({ id: 9, name: "Serial X", price: 100, has_serial_number: true });
		expect(ok).toBe(false);
		expect(window._posState.cart.length).toBe(0);
	});

	it("re-adding serialized product creates separate rows per serial", async () => {
		global.fetch = buildFetchMock();
		const promptSpy = vi.fn().mockReturnValueOnce("SN-A").mockReturnValueOnce("SN-B");
		vi.stubGlobal("prompt", promptSpy);
		await bootModule();
		const p = { id: 9, name: "Serial X", price: 100, has_serial_number: true };
		await window._posAddToCart(p);
		await window._posAddToCart(p);
		expect(window._posState.cart.length).toBe(2);
		expect(window._posState.cart.map((i) => i.serial)).toEqual(["SN-A", "SN-B"]);
	});

	it("increment is blocked on serialized lines", async () => {
		global.fetch = buildFetchMock();
		await bootModule();
		window._posState.cart.push({ id: 9, name: "X", qty: 1, price: 10, basePrice: 10, discountPercent: 0, serial: "SN-9" });
		const inc = document.createElement("button");
		inc.setAttribute("data-act", "inc");
		inc.setAttribute("data-i", "0");
		document.getElementById("cartBody").appendChild(inc);
		inc.click();
		await new Promise((r) => setTimeout(r, 10));
		expect(window._posState.cart[0].qty).toBe(1);
		expect(document.getElementById("posAlert").textContent).toContain("المتسلسل");
	});

	it("checkout payload carries serials map keyed by product id", async () => {
		let capturedBody = null;
		global.fetch = vi.fn(async (url, opts) => {
			const u = String(url);
			if (u.includes("/pos/api/checkout")) {
				capturedBody = JSON.parse(opts.body);
				return {
					ok: true,
					status: 200,
					json: async () => ({
						success: true,
						data: { sale_number: "S-1", upsell_prompts: [], view_url: "#", print_url: "#" },
					}),
				};
			}
			if (u.includes("/pos/api/session/current")) {
				return { ok: true, status: 200, json: async () => ({ success: false }) };
			}
			return { ok: true, status: 200, json: async () => ({ success: false }) };
		});
		await bootModule();
		window._posState.customer = { id: 5, is_walkin: false };
		window._posState.cart.push(
			{ id: 9, name: "X", qty: 1, price: 10, basePrice: 10, discountPercent: 0, serial: "SN-9" },
			{ id: 3, name: "Y", qty: 2, price: 5, basePrice: 5, discountPercent: 0 },
		);
		await window._posCheckout(false);
		expect(capturedBody).not.toBeNull();
		expect(capturedBody.serials).toEqual({ 9: ["SN-9"] });
		expect(capturedBody.lines.length).toBe(2);
	});
});
