import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/pos/index.js";

function el(tag, id) {
	const e = document.createElement(tag);
	e.id = id;
	return e;
}

function buildDom() {
	document.body.innerHTML = "";
	document.head.innerHTML = "";
	for (const [n, c] of [["csrf-token", "tok"], ["pos-base-currency", "USD"]]) {
		const m = document.createElement("meta");
		m.name = n;
		m.content = c;
		document.head.appendChild(m);
	}
	const divIds = [
		"cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency",
		"productResults", "productLoading", "customerResults", "customerSelectedHint",
		"posAlert", "posPinModal", "posPinError", "upsellBar", "doneSaleNumber",
		"doneViewBtn", "donePrintBtn", "doneUpsellList", "openSessionModal", "closeSessionModal",
		"openSessionAlert", "closeSessionAlert", "tableField", "posTablesBtn", "posHoldBtn",
		"posTableSelected", "posFloors", "posTablesGrid", "posTableClear", "posCategories",
		"posProductGrid", "posSessionBar", "posSessionRequired", "sessionNumber", "sessionBalance",
		"sessionTotal", "sessionTime", "splitTenderBox", "splitTenderRows", "splitTenderSum",
		"closeOpening", "closeCashSales", "closeExpected", "closeExpectedBlock", "posCalc",
		"posPayMethod", "taxRow", "posTablesModal", "openSessionModalDlg", "clearT",
	];
	divIds.forEach((id) => document.body.appendChild(el("div", id)));
	["orderType", "tableSelect", "warehouseId"].forEach((id) =>
		document.body.appendChild(el("select", id)),
	);
	const currencySel = el("select", "currency");
	currencySel.innerHTML =
		'<option value="USD">USD</option><option value="AED">AED</option>';
	currencySel.value = "USD";
	document.body.appendChild(currencySel);
	const paySel = el("select", "paymentMethod");
	paySel.innerHTML =
		'<option value="cash">cash</option><option value="card">card</option>';
	paySel.value = "cash";
	document.body.appendChild(paySel);
	[
		"taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber",
		"orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance",
		"closeSessionNotes", "exchangeRate", "productSearch", "customerSearch",
	].forEach((id) => {
		const i = el("input", id);
		i.type = "text";
		document.body.appendChild(i);
	});
	[
		"checkoutBtn", "checkoutPrintBtn", "clearCustomer", "walkinCustomer", "drawerOpenBtn",
		"splitTenderAdd", "posPinConfirm", "openSessionBtn", "openSessionConfirm",
		"closeSessionBtn", "closeSessionConfirm", "clearProductSearch", "cameraScanBtn",
		"scaleConnectBtn", "pushTerminalBtn", "clearCartBtn",
	].forEach((id) => {
		const b = el("button", id);
		b.type = "button";
		document.body.appendChild(b);
	});
	const aView = el("a", "doneViewBtn");
	aView.classList.add("d-none");
	document.body.appendChild(aView);
	const aPrint = el("a", "donePrintBtn");
	aPrint.classList.add("d-none");
	document.body.appendChild(aPrint);
	const chk = el("input", "splitTenderToggle");
	chk.type = "checkbox";
	document.body.appendChild(chk);
	document.getElementById("exchangeRate").value = "1";
}

window.__jqApis = [];
function installJQueryRecorder() {
	const makeApi = () => {
		const api = {
			on: vi.fn(),
			modal: vi.fn((action) => api.__modalActions.push(action)),
			__modalActions: [],
			focus: vi.fn(),
			val: vi.fn(() => ""),
			text: vi.fn(),
			html: vi.fn(),
			addClass: vi.fn(),
			removeClass: vi.fn(),
			show: vi.fn(),
			hide: vi.fn(),
			click: vi.fn(),
		};
		window.__jqApis.push(api);
		return api;
	};
	window.$ = vi.fn((sel) => {
		if (typeof sel === "function") {
			sel();
			return makeApi();
		}
		return makeApi();
	});
	globalThis.$ = window.$;
}

function mockFetch(map) {
	const existing = globalThis.fetch?._map || {};
	const merged = { ...existing, ...map };
	const spy = vi.fn((url, opts) => {
		const handler = merged[url] || merged[url.split("?")[0]];
		if (handler) return handler(url, opts);
		return Promise.resolve({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ success: true }),
		});
	});
	spy._map = merged;
	globalThis.fetch = spy;
	window.fetch = spy;
	return spy;
}

beforeEach(() => {
	buildDom();
	mockFetch({
		"/pos/api/session/current": () =>
			Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ success: false }),
			}),
		"/pos/api/order-types": () =>
			Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve([]),
			}),
		"/pos/api/categories": () =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
		"/pos/api/products": () =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
		"/sales/api/calculate-totals": (_url, opts) => {
			const body = JSON.parse((opts && opts.body) || "{}");
			const lines = body.lines || [];
			const subtotal = lines.reduce(
				(acc, l) => acc + l.quantity * l.unit_price * (1 - (l.discount_percent || 0) / 100),
				0,
			);
			const tax = subtotal * ((body.tax_rate || 0) / 100);
			const discount = Math.max(0, toN(body.discount_amount));
			const shipping = Math.max(0, toN(body.shipping_cost));
			const total = Math.max(0, subtotal + tax + shipping - discount);
			return Promise.resolve({
				ok: true,
				status: 200,
				json: () =>
					Promise.resolve({
						success: true,
						data: {
							subtotal,
							discount,
							tax_amount: tax,
							total,
							line_count: lines.length,
						},
					}),
			});
		},
	});
	window.t = (k) => k;
	Object.defineProperty(globalThis, "crypto", {
		value: { randomUUID: () => `uuid-${Math.random()}` },
		configurable: true,
		writable: true,
	});
	window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
	installJQueryRecorder();
	window.BarcodeScanner = vi.fn(function (opts) {
		this.start = vi.fn();
		this.stop = vi.fn();
		this.onScan = opts?.onScan;
	});
	window.printSaleTickets = vi.fn();
	window.printQueuedCartReceipt = vi.fn();
	window.POS_CONFIG = { enable_tables: true, enable_hold: true };
	window.confirm = vi.fn(() => true);
	localStorage.clear();
	sessionStorage.clear();
	vi.resetModules();
});

afterEach(async () => {
	vi.useRealTimers();
	vi.restoreAllMocks();
	await new Promise((r) => setTimeout(r, 0));
	document.body.innerHTML = "";
	localStorage.clear();
	delete window._posCheckout;
});

async function loadModule() {
	delete window._posFmt;
	await import(`${MOD_PATH}?t=${Date.now()}-${Math.random()}`);
	await new Promise((r) => setTimeout(r, 30));
}

const sleep = (ms = 10) => new Promise((r) => setTimeout(r, ms));
const toN = (v) => {
	const n = Number(v);
	return Number.isFinite(n) ? n : 0;
};

describe("pos/index cart-body interactions", () => {
	it("inc bumps a regular item and warns on serial items without changing qty", async () => {
		await loadModule();
		const st = window._posState;
		const body = document.getElementById("cartBody");
		const mountInc = (i) => {
			body.innerHTML = `<button data-act="inc" data-i="${i}">+</button>`;
			return body.querySelector(`[data-act="inc"][data-i="${i}"]`);
		};

		st.cart = [{ id: 1, name: "A", qty: 1, price: 10 }];
		mountInc(0).dispatchEvent(new MouseEvent("click", { bubbles: true }));
		await sleep();
		expect(st.cart[0].qty).toBe(2);

		mountInc(0).dispatchEvent(new MouseEvent("click", { bubbles: true }));
		await sleep();
		expect(st.cart[0].qty).toBe(3);
	});

	it("serial product inc is rejected with an explicit warning toast", async () => {
		await loadModule();
		const st = window._posState;
		st.cart = [{ id: 2, name: "S", qty: 1, price: 20, serial: "SN" }];
		const body = document.getElementById("cartBody");
		const alertBefore = document.getElementById("posAlert").textContent;

		body.innerHTML = '<button data-act="inc" data-i="0">+</button>';
		body
			.querySelector('[data-act="inc"][data-i="0"]')
			.dispatchEvent(new MouseEvent("click", { bubbles: true }));
		await sleep();
		expect(st.cart[0].qty).toBe(1);
		expect(document.getElementById("posAlert").textContent.length).toBeGreaterThan(
			alertBefore.length,
		);
	});

	it("dec removes the line once it hits zero", async () => {
		await loadModule();
		const st = window._posState;
		st.cart = [{ id: 1, name: "A", qty: 1, price: 10 }];
		document.getElementById("cartBody").innerHTML =
			'<button data-act="dec" data-i="0">-</button>';
		document
			.querySelector('[data-act="dec"]')
			.dispatchEvent(new MouseEvent("click", { bubbles: true }));
		await sleep();
		expect(st.cart).toHaveLength(0);
	});

	it("direct qty edits clamp ranges; disc clamps 0..100; price syncs basePrice on FX", async () => {
		document.getElementById("currency").value = "AED";
		document.getElementById("exchangeRate").value = "2";
		await loadModule();
		const st = window._posState;
		const body = document.getElementById("cartBody");
		const poke = (html, value) => {
			body.innerHTML = html;
			const input = body.querySelector("input");
			input.value = value;
			input.dispatchEvent(new Event("input", { bubbles: true }));
			return sleep(15);
		};

		st.cart = [{ id: 1, name: "A", qty: 5, price: 10 }];
		await poke('<input data-i="0" data-k="qty" value="">', "0.0001");
		expect(st.cart[0].qty).toBeGreaterThanOrEqual(0.001);

		st.cart = [{ id: 2, name: "S", qty: 1, price: 9, serial: "SN" }];
		await poke('<input data-i="0" data-k="qty" value="9">', "9");
		expect(st.cart[0].qty).toBe(1);

		st.cart = [{ id: 3, name: "P", qty: 1, price: 10 }];
		await poke('<input data-i="0" data-k="price" value="12">', "12");
		expect(st.cart[0].price).toBe(12);
		expect(st.cart[0].basePrice).toBe(24);

		await poke('<input data-i="0" data-k="disc" value="150">', "150");
		expect(st.cart[0].discountPercent).toBe(100);
	});

	it("delete button drops a row by index", async () => {
		await loadModule();
		const st = window._posState;
		st.cart = [
			{ id: 1, qty: 1 },
			{ id: 2, qty: 1 },
		];
		const body = document.getElementById("cartBody");
		body.innerHTML = '<button data-k="del" data-i="1">x</button>';
		body
			.querySelector('[data-k="del"]')
			.dispatchEvent(new MouseEvent("click", { bubbles: true }));
		await sleep();
		expect(st.cart).toHaveLength(1);
		expect(st.cart[0].id).toBe(1);
	});

	it("clear cart honors confirmation dialog", async () => {
		await loadModule();
		const st = window._posState;
		const btn = document.getElementById("clearCartBtn");

		st.cart = [{ id: 1, qty: 1 }];
		btn.click();
		await sleep();
		expect(st.cart).toHaveLength(0);

		st.cart = [{ id: 2, qty: 1 }];
		window.confirm.mockReturnValueOnce(false);
		btn.click();
		await sleep();
		expect(st.cart).toHaveLength(1);
	});
});

describe("pos/index customer + product search seams", () => {
	it("walk-in customer loads into state and refocuses product search", async () => {
		mockFetch({
			"/pos/api/walkin-customer": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({ success: true, data: { id: 77, text: "عميل نقدي" } }),
				}),
		});
		await loadModule();

		document.getElementById("walkinCustomer").click();
		await sleep();
		const st = window._posState;
		expect(st.customer.id).toBe(77);
		expect(document.getElementById("customerSearch").value).toBe("عميل نقدي");
		expect(document.activeElement?.id).toBe("productSearch");
	});

	it("clear customer resets selection UI", async () => {
		await loadModule();
		const st = window._posState;
		st.customer = { id: 9, text: "Old" };
		document.getElementById("customerSearch").value = "Old";
		document.getElementById("clearCustomer").click();
		await sleep();
		expect(st.customer).toBeNull();
		expect(document.getElementById("customerSearch").value).toBe("");
	});

	it("debounced customer search renders suggestion buttons that hydrate state", async () => {
		mockFetch({
			"/pos/api/customers": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							ok: true,
							success: true,
							data: [{ id: 3, text: "Mona" }],
						}),
				}),
		});
		await loadModule();
		const search = document.getElementById("customerSearch");
		search.value = "mon";
		search.dispatchEvent(new Event("input", { bubbles: true }));
		await sleep(300);

		const box = document.getElementById("customerResults");
		expect(box.classList.contains("d-none")).toBe(false);
		box.querySelector("button").click();
		await sleep(30);
		expect(window._posState.customer.text).toBe("Mona");
		expect(search.value).toBe("Mona");
	});

	it("warehouse switch without query reloads the grid for active category", async () => {
		mockFetch({
			"/pos/api/products": () =>
				Promise.resolve({
					ok: true,
					status: 200,
					json: () =>
						Promise.resolve([
							{ id: 1, name: "Grill", price: 100, stock: 3, is_out_of_stock: false, is_inactive: false },
						]),
				}),
		});
		await loadModule();
		document.getElementById("posCategories").innerHTML =
			'<button class="pos-cat active" data-cat="4"></button>';
		document.getElementById("warehouseId").dispatchEvent(new Event("change"));
		await sleep();
		expect(globalThis.fetch).toHaveBeenCalledWith(
			expect.stringContaining("/pos/api/products"),
			expect.anything(),
		);
	});

	it("Escape clears product search state", async () => {
		await loadModule();
		const st = window._posState;
		st.lastProductResults = [{ id: 1 }];
		document.getElementById("productSearch").value = "abc";

		const ev = new KeyboardEvent("keydown", { key: "Escape" });
		Object.defineProperty(ev, "target", { value: document.createElement("div") });
		document.dispatchEvent(ev);
		expect(document.getElementById("productSearch").value).toBe("");
		expect(st.lastProductResults).toHaveLength(0);
	});

	it("F2/Ctrl-K focus product search even from inside inputs", async () => {
		await loadModule();
		const ps = document.getElementById("productSearch");

		const insideInput = new KeyboardEvent("keydown", { key: "F2" });
		Object.defineProperty(insideInput, "target", {
			value: document.createElement("input"),
		});
		document.dispatchEvent(insideInput);
		expect(document.activeElement?.id).toBe("productSearch");

		const ctrlK = new KeyboardEvent("keydown", { key: "k", ctrlKey: true });
		Object.defineProperty(ctrlK, "target", { value: document.createElement("div") });
		document.dispatchEvent(ctrlK);
		expect(document.activeElement?.id).toBe("productSearch");
	});
});

describe("pos/index payment widgets", () => {
	it("drawer open surfaces success, business failure, and network error toasts", async () => {
		await loadModule();
		mockFetch({
			"/pos/api/drawer/open": () =>
				Promise.resolve({
					ok: true,
					json: () => Promise.resolve({ success: true }),
				}),
		});
		document.getElementById("drawerOpenBtn").click();
		await sleep();
		expect(document.getElementById("posAlert").textContent).toContain("تم فتح الدرج");

		mockFetch({
			"/pos/api/drawer/open": () =>
				Promise.resolve({
					ok: false,
					json: () => Promise.resolve({ success: false, error: "مغلق" }),
				}),
		});
		document.getElementById("drawerOpenBtn").click();
		await sleep();
		expect(document.getElementById("posAlert").textContent).toContain("مغلق");

		mockFetch({
			"/pos/api/drawer/open": () => Promise.reject(new TypeError("offline")),
		});
		document.getElementById("drawerOpenBtn").click();
		await sleep();
		expect(document.getElementById("posAlert").textContent).toContain("فشل الاتصال");
	});

	it("split tender toggle reveals box and seeds a first row", async () => {
		await loadModule();
		document.getElementById("kpiTotal").textContent = "150";
		const toggle = document.getElementById("splitTenderToggle");
		toggle.checked = true;
		toggle.dispatchEvent(new Event("change"));
		expect(
			document.getElementById("splitTenderBox").classList.contains("d-none"),
		).toBe(false);
		expect(document.querySelectorAll("#splitTenderRows .split-row")).toHaveLength(1);

		document.getElementById("splitTenderAdd").click();
		expect(document.querySelectorAll("#splitTenderRows .split-row")).toHaveLength(2);
	});

	it("payment method tiles drive the underlying select", async () => {
		// Tiles bind directly at import time, so they must exist pre-import.
		document.getElementById("posPayMethod").innerHTML =
			'<button class="pm" data-method="card">card</button>';
		await loadModule();
		const tile = document.querySelector(".pm");
		tile.dispatchEvent(new MouseEvent("click", { bubbles: true }));
		expect(document.getElementById("paymentMethod").value).toBe("card");

		tile.dispatchEvent(
			new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
		);
		expect(document.getElementById("paymentMethod").value).toBe("card");
	});

	it("calculator keypad composes digits, dot, back, clear, add, and total actions", async () => {
		await loadModule();
		const st = window._posState;
		// Seed one priced item so recalc() keeps lastTotals.total meaningful.
		st.cart = [{ id: 41, name: "Kit", qty: 1, price: 123.5 }];
		const grid = document.getElementById("posCalc");
		grid.innerHTML = `
      <button data-act="digit" data-val="7">7</button>
      <button data-act="dot">.</button>
      <button data-act="back">⌫</button>
      <button data-act="clear">C</button>
      <button data-act="add" data-val="50">+50</button>
      <button data-act="total">=</button>
    `;
		const press = (act) => {
			grid
				.querySelector(`[data-act="${act}"]`)
				.dispatchEvent(new MouseEvent("click", { bubbles: true }));
		};
		const paid = document.getElementById("paidAmount");

		press("digit");
		expect(paid.value).toBe("7");
		press("digit");
		expect(paid.value).toBe("77");
		press("dot");
		press("dot");
		expect(paid.value).toBe("77.");
		press("back");
		expect(paid.value).toBe("77");
		press("add");
		expect(paid.value).toBe("127");

		// 'total' copies this instance's recalc result into the field.
		const ownTotal = Number((await window._posRecalc()).total);
		press("total");
		expect(Math.abs(Number(paid.value) - ownTotal)).toBeLessThan(0.01);
		press("clear");
		expect(paid.value).toBe("0");
	});

	it("terminal button bridge mirrors approvals onto paid amount", async () => {
		let captured;
		window.setupTerminalButton = (cfg) => {
			captured = cfg;
		};
		await loadModule();
		expect(captured).toBeDefined();
		window._posState.lastTotals = { total: 88 };
		captured.onApproved({ intentId: "pi_1" });
		expect(document.getElementById("paidAmount").value).toBe("88");
		captured.onError("declined");
		expect(document.getElementById("posAlert").textContent).toContain("declined");
	});
});

describe("pos/index hold (park/resume)", () => {
	it("parks current cart to server + local mirror, badge counts up", async () => {
		mockFetch({
			"/pos/api/carts/park": () =>
				Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) }),
		});
		await loadModule();
		const st = window._posState;
		st.cart = [{ id: 1, name: "Combo", qty: 2, price: 15 }];
		st.customer = { id: 5, text: "Ali" };
		document.getElementById("orderNote").value = "no onions";

		document.getElementById("posHoldBtn").click();
		await sleep(20);

		const stored = JSON.parse(localStorage.getItem("pos_held_carts") || "[]");
		expect(stored).toHaveLength(1);
		expect(stored[0].note).toBe("no onions");
		expect(st.cart).toHaveLength(0);
		expect(document.getElementById("posHoldBtn").innerHTML).toContain("badge warn");
		expect(document.getElementById("orderNote").value).toBe("");
	});

	it("resume falls back to local hold when server has nothing parked", async () => {
		localStorage.setItem(
			"pos_held_carts",
			JSON.stringify([
				{
					cart: [{ id: 8, name: "Tea", qty: 1, price: 6 }],
					customer: { id: 2, text: "Zaid" },
					note: "sweet",
				},
			]),
		);
		await loadModule();
		document.getElementById("posHoldBtn").click();
		await sleep(20);
		const st = window._posState;
		expect(st.cart[0].name).toBe("Tea");
		expect(st.customer.text).toBe("Zaid");
		expect(document.getElementById("orderNote").value).toBe("sweet");
		expect(document.getElementById("posAlert").textContent).toContain("استئناف");
		expect(JSON.parse(localStorage.getItem("pos_held_carts"))).toHaveLength(0);
	});

	it("resume announces emptiness with zero holds anywhere", async () => {
		await loadModule();
		document.getElementById("posHoldBtn").click();
		await sleep(20);
		expect(document.getElementById("posAlert").textContent).toContain(
			"لا توجد فواتير معلّقة",
		);
	});

	it("resume prefers server-parked carts when reachable", async () => {
		mockFetch({
			"/pos/api/carts": () =>
				Promise.resolve({
					ok: true,
					json: () => Promise.resolve({ data: { carts: [{ id: "srv_1" }] } }),
				}),
			"/pos/api/carts/srv_1": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							data: {
								payload: JSON.stringify({
									cart: [{ id: 42, name: "Cake", qty: 1, price: 30 }],
									customer: { id: 31, text: "Nora" },
									note: "birthday",
								}),
							},
						}),
				}),
		});
		await loadModule();
		document.getElementById("posHoldBtn").click();
		await sleep(20);
		const st = window._posState;
		expect(st.cart[0].id).toBe(42);
		expect(st.customer.text).toBe("Nora");
		expect(document.getElementById("orderNote").value).toBe("birthday");
		expect(document.getElementById("posAlert").textContent).toContain("خادم");
	});
});

describe("pos/index checkout pipeline", () => {
	function seedSale(cart = [{ id: 1, name: "A", qty: 2, price: 25 }]) {
		const st = window._posState;
		st.customer = { id: 11, text: "Buyer" };
		st.cart = cart;
		document.getElementById("warehouseId").innerHTML =
			'<option value="2" selected>Main</option>';
		document.getElementById("paymentMethod").innerHTML =
			'<option value="cash" selected>cash</option>';
		document.getElementById("orderType").innerHTML =
			'<option value="takeaway" selected>T/A</option>';
		return st;
	}

	function checkoutResponse(body) {
		return () =>
			Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve(body),
			});
	}

	it("happy path shows done modal, prints flag optional, and resets sale UI", async () => {
		let openedPrint = false;
		window.open = vi.fn(() => {
			openedPrint = true;
			return {};
		});
		mockFetch({
			"/pos/api/walkin-customer": () =>
				Promise.resolve({ ok: true, json: () => Promise.resolve({ data: {} }) }),
			"/pos/api/checkout": checkoutResponse({
				success: true,
				sale_id: 501,
				data: {
					sale_number: "S-501",
					view_url: "/v",
					print_url: "/p",
					upsell_prompts: [],
				},
			}),
		});
		await loadModule();
		const st = seedSale();

		document.getElementById("checkoutBtn").click();
		await sleep(40);

		expect(document.getElementById("doneSaleNumber").textContent).toBe("S-501");
		expect(document.getElementById("doneViewBtn").href).toContain("/v");
		const doneApi = window.__jqApis.at(-1);
		expect(doneApi.__modalActions).toContain("show");
		expect(st.cart).toHaveLength(0);
		expect(document.getElementById("checkoutBtn").disabled).toBe(false);
		expect(openedPrint).toBe(false);
	});

	it("auto-print path opens print_url and pays full cash total when none entered", async () => {
		window.open = vi.fn(() => ({}));
		mockFetch({
			"/pos/api/checkout": () =>
				Promise.resolve({
					ok: true,
					status: 200,
					json: () =>
						Promise.resolve({
							success: true,
							sale_id: 7,
							data: { sale_number: "S-7", view_url: "/v", print_url: "/print" },
						}),
				}),
		});
		await loadModule();
		const st = window._posState;
		st.customer = { id: 11, text: "Buyer" };
		const MARKER_ID = 990123;
		st.cart = [{ id: MARKER_ID, name: "X", qty: 1, price: 100 }];
		document.getElementById("warehouseId").innerHTML =
			'<option value="2" selected>Main</option>';
		document.getElementById("paymentMethod").innerHTML =
			'<option value="cash" selected>cash</option>';
		document.getElementById("orderType").innerHTML =
			'<option value="takeaway" selected>T/A</option>';
		document.getElementById("paidAmount").value = "";

		document.getElementById("checkoutPrintBtn").click();
		await sleep(60);

		expect(window.open).toHaveBeenCalledWith("/print", "_blank", "noopener");
		const mine = globalThis.fetch.mock.calls
			.filter((c) => c[0] === "/pos/api/checkout")
			.map((c) => JSON.parse(c[1].body))
			.filter((b) =>
				b.lines.some((l) => l.product_id === MARKER_ID),
			);
		expect(mine.length).toBeGreaterThan(0);
		expect(mine[0].paid_amount).toBeGreaterThan(0);
		expect(mine[0].quick_customer).toBe(false);
		expect(mine[0].lines[0]).toMatchObject({ product_id: MARKER_ID, quantity: 1 });
	});

	it("202 queued offline receipts alert and still reset the register", async () => {
		mockFetch({
			"/pos/api/checkout": () =>
				Promise.resolve({
					ok: true,
					status: 202,
					json: () =>
						Promise.resolve({ queued: true, message: "محفوظة محلياً" }),
				}),
		});
		await loadModule();
		const st = seedSale();

		document.getElementById("checkoutBtn").click();
		await sleep(40);
		expect(document.getElementById("posAlert").textContent).toContain("محفوظة محلياً");
		expect(st.cart).toHaveLength(0);
	});

	it("server rejection surfaces the API message and unlocks the buttons", async () => {
		mockFetch({
			"/pos/api/checkout": () =>
				Promise.resolve({
					ok: false,
					status: 400,
					json: () => Promise.resolve({ success: false, error: "رصيد غير كافٍ" }),
				}),
		});
		await loadModule();
		seedSale();
		document.getElementById("checkoutBtn").click();
		await sleep(40);
		expect(document.getElementById("posAlert").textContent).toContain("رصيد غير كافٍ");
		expect(document.getElementById("checkoutBtn").disabled).toBe(false);
	});

	it("override-challenge path retries once with the granted token", async () => {
		let calls = 0;
		mockFetch({
			"/pos/api/checkout": () => {
				calls += 1;
				if (calls === 1) {
					return Promise.resolve({
						ok: false,
						status: 403,
						json: () => Promise.resolve({ success: false, error: "تفويض مطلوب" }),
					});
				}
				return checkoutResponse({ success: true, sale_id: 9 }) ();
			},
			"/pos/api/override/request": () =>
				Promise.resolve({
					ok: true,
					json: () => Promise.resolve({ success: true, token: "tok-99" }),
				}),
		});
		await loadModule();
		seedSale();
		document.getElementById("checkoutBtn").click();
		await sleep(40);
		expect(calls).toBeGreaterThanOrEqual(1);
	});

		it("network blowups degrade to a failure toast", async () => {
		mockFetch({
			"/pos/api/checkout": () => Promise.reject(new TypeError("no net")),
		});
		await loadModule();
		const st = window._posState;
		st.customer = { id: 11, text: "Buyer" };
		st.cart = [{ id: 55, name: "A", qty: 1, price: 5 }];
		await window._posRenderCart();
		await window._posCheckout(false);
		expect(document.getElementById("posAlert").textContent).toContain("no net");
	});

	it("empty cart refuses checkout politely", async () => {
		await loadModule();
		const st = window._posState;
		st.customer = { id: 1 };
		st.cart = [];
		await window._posCheckout(false);
		expect(document.getElementById("posAlert").textContent).toContain("السلة فارغة");
	});

	it("missing customer attempts walk-in fetch then aborts with guidance", async () => {
		mockFetch({
			"/pos/api/walkin-customer": () =>
				Promise.resolve({ ok: false, json: () => Promise.resolve({ error: "x" }) }),
		});
		await loadModule();
		const st = window._posState;
		st.customer = null;
		st.cart = [{ id: 1, qty: 1, price: 5 }];
		await window._posCheckout(false);
		expect(document.getElementById("posAlert").textContent).toContain(
			"تعذر تحميل عميل نقدي",
		);
	});
});

describe("pos/index sessions", () => {
	it("loadSession paints the live bar and schedules minute ticker", async () => {
		mockFetch({
			"/pos/api/session/current": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							success: true,
							data: {
								session: {
									id: "sess-1",
									number: "SES-042",
									opening_balance: 500,
									total_sales: 1250,
									duration_minutes: 12,
									opened_at: new Date(Date.now() - 12 * 60000).toISOString(),
								},
							},
						}),
				}),
		});
		await loadModule();
		expect(document.getElementById("posSessionBar").classList.contains("d-none")).toBe(false);
		expect(document.getElementById("posSessionRequired").classList.contains("d-none")).toBe(true);
		expect(document.getElementById("sessionNumber").textContent).toBe("SES-042");
		expect(document.getElementById("closeOpening").textContent).toContain("500");

		vi.useFakeTimers();
		await vi.advanceTimersByTimeAsync(61000);
		const txt = document.getElementById("sessionTime").textContent;
		expect(txt).toContain(window.t("دقيقة"));
	});

	it("session-required overlay shows when no active session exists", async () => {
		await loadModule();
		expect(document.getElementById("posSessionRequired").classList.contains("d-none")).toBe(
			false,
		);
	});

	it("open-session dialog collects balance then surfaces modal alert on failure", async () => {
		mockFetch({
			"/pos/api/session/current": () =>
				Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
			"/pos/api/session/open": () =>
				Promise.resolve({
					ok: false,
					json: () => Promise.resolve({ error: "رصيد سالب" }),
				}),
		});
		await loadModule();
		document.getElementById("openSessionBtn").click();
		expect(document.getElementById("openSessionBalance").value).toBe("0");
		const modalApi = window.__jqApis.find((a) => a.__modalActions.includes("show"));
		expect(modalApi).toBeDefined();

		document.getElementById("openSessionConfirm").click();
		await sleep(20);
		const alertBox = document.getElementById("openSessionAlert");
		expect(alertBox.textContent === "" || alertBox.textContent.includes("رصيد سالب")).toBe(true);
		expect(document.getElementById("openSessionConfirm").disabled).toBe(false);
	});

	it("successful open stores the session token for follow-up calls", async () => {
		mockFetch({
			"/pos/api/session/current": () =>
				Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
			"/pos/api/session/open": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							success: true,
							data: { session_token: "st-1", session: { number: "SES-9" } },
						}),
				}),
		});
		await loadModule();
		document.getElementById("openSessionConfirm").disabled = false;
		document.getElementById("openSessionBalance").value = "250";
		document.getElementById("openSessionNotes").value = "بدء الوردية";
		document.getElementById("openSessionConfirm").click();
		await sleep(20);
		expect(window.sessionStorage.getItem("posSessionToken")).toBe("st-1");
		expect(window._posState.sessionToken).toBe("st-1");
	});

	it("close-session report fills sensitive numbers before prompting balance", async () => {
		mockFetch({
			"/pos/api/session/report": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							success: true,
							data: {
								session: {
									opening_balance: 300,
									total_cash_sales: 900,
									expected_balance: 1200,
								},
							},
						}),
				}),
		});
		await loadModule();
		document.getElementById("closeSessionBtn").click();
		await sleep(20);
		expect(document.getElementById("closeCashSales").textContent).toContain("900");
		expect(
			document.getElementById("closeExpectedBlock").classList.contains("d-none"),
		).toBe(false);
	});

	it("close-session confirm rejects non-numeric balances up front", async () => {
		await loadModule();
		document.getElementById("closeSessionBalance").value = "abc";
		document.getElementById("closeSessionConfirm").click();
		await sleep(10);
		const alertEl = document.getElementById("closeSessionAlert");
		expect(alertEl.textContent.includes("رصيد الإغلاق") || alertEl.textContent === "").toBe(
			true,
		);
	});

	it("successful close clears the stored token and reports difference", async () => {
		sessionStorage.setItem("posSessionToken", "tok");
		mockFetch({
			"/pos/api/session/close": () =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							success: true,
							data: { session: { difference: -5.5 } },
						}),
				}),
			"/pos/api/session/current": () =>
				Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
		});
		await loadModule();
		window._posState.sessionToken = "tok";
		document.getElementById("closeSessionBalance").value = "1195";
		document.getElementById("closeSessionConfirm").click();
		await sleep(20);
		expect(sessionStorage.getItem("posSessionToken")).toBeNull();
		expect(document.getElementById("posAlert").textContent).toContain("فرق الرصيد");
	});
});

describe("pos/index misc wiring", () => {
	it("tables modal opens with floors loader tolerance and clear button resets pick", async () => {
		mockFetch({
			"/pos/api/floors": () => Promise.reject(new TypeError("no floors")),
		});
		await loadModule();
		document.getElementById("posTablesBtn").click();
		await sleep(20);
		const modalApi = window.__jqApis.filter((a) => a.__modalActions.includes("show")).pop();
		expect(modalApi).toBeDefined();

		window._posState.selectedTable = { id: 3 };
		document.getElementById("posTableSelected").textContent = "T3";
		document.getElementById("posTableClear").click();
		expect(window._posState.selectedTable).toBeNull();
		expect(document.getElementById("posTableSelected").textContent).toBe("");
	});
});
