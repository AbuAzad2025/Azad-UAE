import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/pos/index.js";

function buildDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  const meta = document.createElement("meta");
  meta.name = "csrf-token";
  meta.content = "tok";
  document.head.appendChild(meta);
  const base = document.createElement("meta");
  base.name = "pos-base-currency";
  base.content = "USD";
  document.head.appendChild(base);
  const ids = [
    "cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency",
    "productResults", "productLoading", "productSearch", "customerSearch", "customerResults",
    "customerSelectedHint", "posAlert", "posPinModal", "posPinError", "posPinInput",
    "upsellBar", "doneSaleNumber", "doneViewBtn", "donePrintBtn", "doneUpsellList",
    "openSessionModal", "closeSessionModal", "openSessionAlert", "closeSessionAlert",
    "tableField", "posTablesBtn", "posHoldBtn", "posTableSelected", "posFloors",
    "posTablesGrid", "posTableClear", "posCategories", "posProductGrid", "posSessionBar",
    "posSessionRequired", "sessionNumber", "sessionBalance", "sessionTotal", "sessionTime",
    "splitTenderBox", "splitTenderRows", "splitTenderSum", "closeOpening", "closeCashSales",
    "closeExpected", "closeExpectedBlock", "posCalc", "posPayMethod", "taxRow", "refField",
    "pushTerminalBtn", "cameraScanBtn", "scaleConnectBtn",
  ];
  for (const id of ids) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }
  for (const id of ["orderType", "tableSelect", "warehouseId", "currency"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }
  const pmSel = document.createElement("select");
  pmSel.id = "paymentMethod";
  pmSel.innerHTML = '<option value="cash">Cash</option><option value="card">Card</option>';
  document.body.appendChild(pmSel);
  for (const id of [
    "taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber",
    "orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance",
    "closeSessionNotes", "exchangeRate",
  ]) {
    const el = document.createElement("input");
    el.id = id;
    document.body.appendChild(el);
  }
  for (const id of [
    "checkoutBtn", "checkoutPrintBtn", "clearCustomer", "walkinCustomer", "drawerOpenBtn",
    "splitTenderAdd", "posPinConfirm", "openSessionBtn", "openSessionConfirm",
    "closeSessionBtn", "closeSessionConfirm", "clearProductSearch", "cameraScanBtn",
    "scaleConnectBtn",
  ]) {
    const el = document.createElement("button");
    el.id = id;
    el.type = "button";
    document.body.appendChild(el);
  }
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = "splitTenderToggle";
  document.body.appendChild(cb);
  // Payment method chips
  const payMethod = document.getElementById("posPayMethod");
  for (const m of ["cash", "card"]) {
    const pm = document.createElement("span");
    pm.className = "pm";
    pm.setAttribute("data-method", m);
    payMethod.appendChild(pm);
  }
  // Calculator buttons
  const calc = document.getElementById("posCalc");
  const acts = [
    { act: "digit", val: "5" }, { act: "digit", val: "0" },
    { act: "dot" }, { act: "back" }, { act: "clear" }, { act: "add", val: "10" },
  ];
  for (const a of acts) {
    const b = document.createElement("button");
    b.setAttribute("data-act", a.act);
    if (a.val !== undefined) b.setAttribute("data-val", a.val);
    calc.appendChild(b);
  }
}

function mockFetch(map) {
  const existing = globalThis.fetch?._map || {};
  const merged = { ...existing, ...map };
  const spy = vi.fn((url) => {
    const handler = merged[url] || merged[url.split("?")[0]];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  spy._map = merged;
  globalThis.fetch = spy;
  window.fetch = spy;
  return spy;
}

let modalCallbacks = {};

beforeEach(() => {
  buildDom();
  modalCallbacks = {};
  mockFetch({
    "/pos/api/session/current": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/order-types": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/categories": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    "/pos/api/products": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
  });
  window.t = (k) => k;
  Object.defineProperty(globalThis, "crypto", {
    value: { randomUUID: () => "uuid" },
    configurable: true,
    writable: true,
  });
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
  const jq = () => ({
    show: vi.fn(),
    hide: vi.fn(),
    on: vi.fn((event, handler) => {
      modalCallbacks[event] = handler;
      return jq();
    }),
    modal: vi.fn((action) => {
      if (action === "hide" && modalCallbacks["hidden.bs.modal"]) {
        modalCallbacks["hidden.bs.modal"]();
      }
      return jq();
    }),
    focus: vi.fn(),
    val: vi.fn(),
    text: vi.fn(),
    html: vi.fn(),
    addClass: vi.fn(),
    removeClass: vi.fn(),
    click: vi.fn(),
  });
  window.$ = vi.fn((sel) => {
    const a = jq();
    if (typeof sel === "function") {
      sel();
      return a;
    }
    return a;
  });
  globalThis.$ = window.$;
  window.BarcodeScanner = vi.fn(function (opts) {
    this.start = vi.fn();
    this.stop = vi.fn();
    this.onScan = opts?.onScan;
  });
  window.printSaleTickets = vi.fn();
  window.printQueuedCartReceipt = vi.fn();
  window.POS_CONFIG = { enable_tables: true, enable_hold: true };
  window.posOfflineCatalog = {
    lookupLocalProduct: vi.fn(() => null),
    hydrateCatalog: vi.fn(),
  };
  window.PosScaleSerial = vi.fn(function (opts) {
    this.onStableWeight = opts?.onStableWeight;
    this.onError = opts?.onError;
  });
  window.setupPosScaleUI = vi.fn();
  window.setupCameraScanUI = vi.fn();
  window.setupTerminalButton = vi.fn();
  vi.resetModules();
});

afterEach(async () => {
  vi.useRealTimers();
  vi.clearAllTimers();
  vi.restoreAllMocks();
  await new Promise((r) => setTimeout(r, 0));
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  localStorage.clear();
});

async function loadModule() {
  delete window._posFmt;
  await import(MOD_PATH + String.fromCharCode(63) + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}

function dispatchKeyOnBody(key, opts = {}) {
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, ...opts });
  Object.defineProperty(ev, "target", { value: document.body, writable: false });
  document.body.dispatchEvent(ev);
}

describe("pos/index extended", () => {
  it("updateCartPrices converts prices", async () => {
    await loadModule();
    const cur = document.getElementById("currency");
    cur.innerHTML = '<option value="EUR">EUR</option>';
    cur.value = "EUR";
    document.getElementById("exchangeRate").value = "4";
    window._posState.cart = [{ id: 1, name: "A", basePrice: 100, price: 100, qty: 1, discountPercent: 0 }];
    await window._posUpdateCartPrices();
    expect(window._posState.cart[0].price).toBe(25);
  });

  it("loadRateForCurrency sets rate=1 for base currency", async () => {
    await loadModule();
    const cur = document.getElementById("currency");
    cur.innerHTML = '<option value="USD">USD</option>';
    cur.value = "USD";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("1");
  });

  it("loadRateForCurrency fetches rate for foreign currency", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, rate: 3.67 }) }),
    });
    await loadModule();
    const cur = document.getElementById("currency");
    cur.innerHTML = '<option value="EUR">EUR</option>';
    cur.value = "EUR";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("3.670000");
  });

  it("evaluateUpsell renders prompts", async () => {
    mockFetch({
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, upsell_prompts: [{ message: "Add fries" }] }) }),
    });
    await loadModule();
    window._posState.cart = [{ id: 1, qty: 1, price: 10, discountPercent: 0 }];
    await window._posEvaluateUpsell();
    expect(document.getElementById("upsellBar").classList.contains("d-none")).toBe(false);
  });

  it("scheduleUpsellEval triggers evaluate after delay", async () => {
    mockFetch({
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
    });
    await loadModule();
    window._posState.cart = [{ id: 1, qty: 1, price: 10, discountPercent: 0 }];
    window._posScheduleUpsellEval();
    await new Promise((r) => setTimeout(r, 600));
  });

  it("confirmPin success hides modal and settles", async () => {
    mockFetch({
      "/pos/api/authorize-override": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, override_token: "tok123" }) }),
    });
    await loadModule();
    document.getElementById("posPinInput").value = "1234";
    const promise = window._posRequestOverrideToken("test_action");
    await window._posConfirmPin();
    const resolved = await promise;
    expect(resolved).toBe("tok123");
  });

  it("confirmPin failure shows error", async () => {
    mockFetch({
      "/pos/api/authorize-override": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false, error: "bad pin" }) }),
    });
    await loadModule();
    document.getElementById("posPinInput").value = "0000";
    await window._posConfirmPin();
    expect(document.getElementById("posPinError").textContent).toBe("bad pin");
  });

  it("postWithOverride retries on 403", async () => {
    let calls = 0;
    mockFetch({
      "/test-ov": () => {
        calls++;
        if (calls === 1) {
          return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ error: "needs تفويض" }) });
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
      },
      "/pos/api/authorize-override": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, override_token: "ov_tok" }) }),
    });
    await loadModule();
    const promise = window._posPostWithOverride("/test-ov", { foo: 1 }, "test_action");
    await new Promise((r) => setTimeout(r, 50));
    document.getElementById("posPinInput").value = "1234";
    await window._posConfirmPin();
    const r = await promise;
    expect(r.r.ok).toBe(true);
    expect(calls).toBe(2);
  });

  it("checkout success with autoPrint", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, subtotal: 10, discount: 0, total: 10, tax_amount: 0, prices_include_vat: false }) }),
      "/pos/api/checkout": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, sale_number: "S001", view_url: "/v", print_url: "/p", sale_id: 99 }) }),
    });
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posState.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await window._posCheckout(true);
    expect(document.getElementById("doneSaleNumber").textContent).toBe("S001");
  });

  it("checkout 202 queued", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, subtotal: 10, discount: 0, total: 10, tax_amount: 0, prices_include_vat: false }) }),
      "/pos/api/checkout": () =>
        Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ queued: true, message: "queued" }) }),
    });
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posState.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await window._posCheckout(false);
    expect(window._posState.cart.length).toBe(0);
  });

  it("checkout error response", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, subtotal: 10, discount: 0, total: 10, tax_amount: 0, prices_include_vat: false }) }),
      "/pos/api/checkout": () =>
        Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ error: "server error" }) }),
    });
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posState.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await window._posCheckout(false);
    expect(document.getElementById("posAlert").textContent).toContain("server error");
  });

  it("handleScannedCode finds product online", async () => {
    mockFetch({
      "/pos/api/product": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 2, name: "Scanned", price: 15, is_inactive: false }) }),
    });
    await loadModule();
    await window._posHandleScannedCode("123456");
    expect(window._posState.cart.length).toBe(1);
    expect(window._posState.cart[0].name).toBe("Scanned");
  });

  it("handleScannedCode falls back to offline catalog", async () => {
    mockFetch({
      "/pos/api/product": () =>
        Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "not found" }) }),
    });
    window.posOfflineCatalog.lookupLocalProduct = vi.fn(() => ({ id: 3, name: "Offline", price: 20, is_inactive: false }));
    await loadModule();
    await window._posHandleScannedCode("999");
    expect(window._posState.cart.length).toBe(1);
    expect(window._posState.cart[0].name).toBe("Offline");
  });

  it("handleScannedCode with scale weight", async () => {
    mockFetch({
      "/pos/api/product": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 4, name: "Apples", price: 5, is_inactive: false, is_weight_product: true, scale_weight_kg: 1 }) }),
    });
    await loadModule();
    window._posState.scaleWeightKg = 2.5;
    await window._posHandleScannedCode("111");
    expect(window._posState.cart[0].qty).toBe(2.5);
  });

  it("calculator digit", async () => {
    await loadModule();
    const btn = document.querySelector('#posCalc button[data-act="digit"][data-val="5"]');
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById("paidAmount").value).toBe("5");
  });

  it("calculator dot prevents double", async () => {
    await loadModule();
    const paid = document.getElementById("paidAmount");
    paid.value = "5";
    const dotBtn = document.querySelector('#posCalc button[data-act="dot"]');
    dotBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(paid.value).toBe("5.");
    dotBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(paid.value).toBe("5.");
  });

  it("calculator back", async () => {
    await loadModule();
    const paid = document.getElementById("paidAmount");
    paid.value = "50";
    const backBtn = document.querySelector('#posCalc button[data-act="back"]');
    backBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(paid.value).toBe("5");
  });

  it("calculator clear", async () => {
    await loadModule();
    const paid = document.getElementById("paidAmount");
    paid.value = "123";
    const clearBtn = document.querySelector('#posCalc button[data-act="clear"]');
    clearBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(paid.value).toBe("0");
  });

  it("calculator add", async () => {
    await loadModule();
    const paid = document.getElementById("paidAmount");
    paid.value = "5";
    const addBtn = document.querySelector('#posCalc button[data-act="add"]');
    addBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(paid.value).toBe("15");
  });

  it("syncPay sets active class on matching chip", async () => {
    await loadModule();
    const pm = document.querySelector('#posPayMethod .pm[data-method="card"]');
    document.getElementById("paymentMethod").value = "card";
    window._posSyncPay();
    expect(pm.classList.contains("active")).toBe(true);
  });

  it("Ctrl+K focuses product search", async () => {
    await loadModule();
    const search = document.getElementById("productSearch");
    search.focus = vi.fn();
    dispatchKeyOnBody("k", { ctrlKey: true });
    expect(search.focus).toHaveBeenCalled();
  });

  it("F2 focuses product search", async () => {
    await loadModule();
    const search = document.getElementById("productSearch");
    search.focus = vi.fn();
    dispatchKeyOnBody("F2");
    expect(search.focus).toHaveBeenCalled();
  });

  it("F4 focuses customer search", async () => {
    await loadModule();
    const search = document.getElementById("customerSearch");
    search.focus = vi.fn();
    dispatchKeyOnBody("F4");
    expect(search.focus).toHaveBeenCalled();
  });

  it("Escape clears product search", async () => {
    await loadModule();
    const search = document.getElementById("productSearch");
    search.value = "abc";
    dispatchKeyOnBody("Escape");
    expect(search.value).toBe("");
  });

  it("cart input price updates basePrice with currency conversion", async () => {
    await loadModule();
    const cur = document.getElementById("currency");
    cur.innerHTML = '<option value="EUR">EUR</option>';
    cur.value = "EUR";
    document.getElementById("exchangeRate").value = "4";
    window._posState.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await window._posRenderCart();
    const inp = document.querySelector('input[data-k="price"]');
    inp.value = "20";
    inp.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart[0].price).toBe(20);
    expect(window._posState.cart[0].basePrice).toBe(80);
  });

  it("cart click inc increments qty", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await window._posRenderCart();
    const btn = document.querySelector('button[data-act="inc"]');
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart[0].qty).toBe(2);
  });

  it("cart click dec decrements qty", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 2, discountPercent: 0 }];
    await window._posRenderCart();
    const btn = document.querySelector('button[data-act="dec"]');
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart[0].qty).toBe(1);
  });

  it("loadOrderTypes populates select", async () => {
    mockFetch({
      "/pos/api/order-types": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, order_types: [{ code: "dine_in", display_name: "Dine In" }], default_code: "dine_in" }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 100));
    expect(document.getElementById("orderType").value).toBe("dine_in");
  });

  it("loadTableOptions populates select", async () => {
    mockFetch({
      "/pos/api/tables": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, label: "T1", floor_name: "F1" }]) }),
    });
    await loadModule();
    await window._posLoadTableOptions();
    expect(document.getElementById("tableSelect").children.length).toBeGreaterThan(0);
  });

  it("openSessionBtn click shows modal", async () => {
    await loadModule();
    document.getElementById("openSessionBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(modalCallbacks["hidden.bs.modal"]).toBeDefined();
  });

  it("closeSessionBtn click loads report", async () => {
    mockFetch({
      "/pos/api/session/report": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, session: { opening_balance: 100, total_cash_sales: 200, expected_balance: 300 } }) }),
    });
    await loadModule();
    document.getElementById("closeSessionBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 100));
    expect(document.getElementById("closeOpening").textContent).toBe("100.00");
  });

  it("hold cart saves to localStorage", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    window._posState.customer = { id: 1, text: "John" };
    document.getElementById("posHoldBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    const held = JSON.parse(localStorage.getItem("pos_held_carts") || "[]");
    expect(held.length).toBe(1);
  });

  it("resume held cart restores state", async () => {
    await loadModule();
    localStorage.setItem("pos_held_carts", JSON.stringify([{ cart: [{ id: 2, name: "B", price: 20, qty: 1, discountPercent: 0 }], customer: { id: 2, text: "Jane" }, table: null, note: "", ts: Date.now() }]));
    window._posState.cart = [];
    document.getElementById("posHoldBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart.length).toBe(1);
    expect(window._posState.cart[0].name).toBe("B");
  });

  it("drawerOpenBtn success", async () => {
    mockFetch({
      "/pos/api/drawer/open": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }),
    });
    await loadModule();
    document.getElementById("drawerOpenBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(document.getElementById("posAlert").textContent).toBe("تم فتح الدرج");
  });

  it("push terminal button wired", async () => {
    await loadModule();
    expect(window.setupTerminalButton).toHaveBeenCalled();
  });

  it("camera scan UI wired", async () => {
    await loadModule();
    expect(window.setupCameraScanUI).toHaveBeenCalled();
  });

  it("scale serial UI wired", async () => {
    await loadModule();
    expect(window.setupPosScaleUI).toHaveBeenCalled();
  });

  it("offline catalog hydrate on load", async () => {
    await loadModule();
    expect(window.posOfflineCatalog.hydrateCatalog).toHaveBeenCalled();
  });

  it("recalc uses backend when cart has items", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, subtotal: 90, discount: 10, total: 80, tax_amount: 0, prices_include_vat: false }) }),
    });
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 10 }];
    const totals = await window._posRecalc();
    expect(totals.total).toBe(80);
  });

  it("split tender toggle adds row", async () => {
    await loadModule();
    const toggle = document.getElementById("splitTenderToggle");
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change", { bubbles: true }));
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(1);
  });

  it("readSplitPayments validates zero amount", async () => {
    await loadModule();
    window._posAddSplitRow(0, "cash");
    const p = window._posReadSplitPayments();
    expect(p).toBeNull();
  });

  it("walkin customer loads and sets", async () => {
    mockFetch({
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 99, text: "Walkin", name: "Walkin" }) }),
    });
    await loadModule();
    document.getElementById("walkinCustomer").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.customer?.text).toBe("Walkin");
  });

  it("clear customer resets", async () => {
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    document.getElementById("clearCustomer").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(window._posState.customer).toBeNull();
  });

  it("product search input triggers search", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false }]) }),
    });
    await loadModule();
    const search = document.getElementById("productSearch");
    search.value = "app";
    search.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 300));
    expect(document.getElementById("productResults").textContent).toContain("Apple");
  });

  it("warehouse change re-runs search", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    });
    await loadModule();
    const search = document.getElementById("productSearch");
    search.value = "x";
    document.getElementById("warehouseId").dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 300));
  });

  it("addFirstOrLookup with barcode match adds first result", async () => {
    await loadModule();
    window._posState.lastProductResults = [{ id: 1, name: "A", price: 10, barcode: "123", sku: "", is_inactive: false }];
    await window._posAddFirstOrLookup("123");
    expect(window._posState.cart.length).toBe(1);
  });

  it("addFirstOrLookup lookup failure falls back to first result", async () => {
    mockFetch({
      "/pos/api/product": () =>
        Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "not found" }) }),
    });
    await loadModule();
    window._posState.lastProductResults = [{ id: 1, name: "A", price: 10, barcode: "", sku: "", is_inactive: false }];
    await window._posAddFirstOrLookup("999");
    expect(window._posState.cart.length).toBe(1);
  });

  it("renderProductResults shows inactive warning", async () => {
    await loadModule();
    window._posRenderProductResults([{ id: 1, text: "Inactive", price: 10, stock: 0, is_out_of_stock: false, is_inactive: true }]);
    expect(document.getElementById("productResults").innerHTML).toContain("غير نشط");
  });

  it("showModalAlert falls back to showAlert when modal alert missing", async () => {
    await loadModule();
    document.getElementById("openSessionAlert").remove();
    window._posShowModalAlert("openSession", "msg", "warning");
    expect(document.getElementById("posAlert").textContent).toBe("msg");
  });

  it("hideModalAlert hides alert", async () => {
    await loadModule();
    const el = document.getElementById("openSessionAlert");
    el.classList.remove("d-none");
    window._posHideModalAlert("openSession");
    expect(el.classList.contains("d-none")).toBe(true);
  });

  it("loadProducts error shows error message", async () => {
    mockFetch({
      "/pos/api/products": () => Promise.reject(new Error("network")),
    });
    await loadModule();
    await window._posLoadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("تعذر تحميل المنتجات");
  });

  it("loadTables error shows error", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    });
    await loadModule();
    await window._posLoadTables("1");
    expect(document.getElementById("posTablesGrid").textContent).toContain("تعذر التحميل");
  });

  it("loadFloors empty shows empty message", async () => {
    mockFetch({
      "/pos/api/floors": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    });
    await loadModule();
    await window._posLoadFloors();
    expect(document.getElementById("posFloors").textContent).toContain("لا توجد أرضيات");
  });

  it("loadSession shows session bar", async () => {
    mockFetch({
      "/pos/api/session/current": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, session: { id: 1, number: "S1", opening_balance: 100, total_sales: 200, duration_minutes: 30 } }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 100));
    expect(document.getElementById("posSessionBar").classList.contains("d-none")).toBe(false);
  });

  it("closeSessionConfirm validates NaN", async () => {
    await loadModule();
    document.getElementById("closeSessionBalance").value = "abc";
    document.getElementById("closeSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(document.getElementById("closeSessionAlert").textContent).toContain("إدخال رصيد");
  });

  it("closeSessionConfirm success with diff", async () => {
    mockFetch({
      "/pos/api/session/close": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, session: { difference: 5.5 } }) }),
    });
    await loadModule();
    document.getElementById("closeSessionBalance").value = "100";
    document.getElementById("closeSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 100));
    expect(document.getElementById("posAlert").textContent).toContain("فرق الرصيد");
  });

  it("closeSessionConfirm success without diff", async () => {
    mockFetch({
      "/pos/api/session/close": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, session: { difference: 0 } }) }),
    });
    await loadModule();
    document.getElementById("closeSessionBalance").value = "100";
    document.getElementById("closeSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 100));
    expect(document.getElementById("posAlert").textContent).toContain("مطابق");
  });

  it("checkout with split payments", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, subtotal: 100, discount: 0, total: 100, tax_amount: 0, prices_include_vat: false }) }),
      "/pos/api/checkout": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, sale_number: "S003", view_url: "/v", print_url: "/p" }) }),
    });
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posState.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    window._posAddSplitRow(60, "cash");
    window._posAddSplitRow(40, "card");
    document.getElementById("splitTenderToggle").checked = true;
    await window._posCheckout(false);
    expect(document.getElementById("doneSaleNumber").textContent).toBe("S003");
  });

  it("checkout with split payments null returns early", async () => {
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posState.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    document.getElementById("splitTenderToggle").checked = true;
    const result = await window._posCheckout(false);
    expect(result).toBeUndefined();
  });

  it("toggleTableField non-dine hides table", async () => {
    await loadModule();
    const sel = document.getElementById("orderType");
    sel.innerHTML = '<option value="takeaway">T</option>';
    sel.value = "takeaway";
    window._posToggleTableField();
    expect(document.getElementById("tableField").classList.contains("d-none")).toBe(true);
  });

  it("renderUpsellMessages with non-array", async () => {
    await loadModule();
    const bar = document.getElementById("upsellBar");
    window._posRenderUpsellMessages(bar, null);
    expect(bar.classList.contains("d-none")).toBe(true);
  });

  it("cart input disc clamps to 100", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await window._posRenderCart();
    const inp = document.querySelector('input[data-k="disc"]');
    inp.value = "150";
    inp.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart[0].discountPercent).toBe(100);
  });

  it("cart input qty minimum 0.001", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await window._posRenderCart();
    const inp = document.querySelector('input[data-k="qty"]');
    inp.value = "0";
    inp.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 50));
    expect(window._posState.cart[0].qty).toBe(0.001);
  });
});
