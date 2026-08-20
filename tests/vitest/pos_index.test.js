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
  const ids = ["cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency", "productResults", "productLoading", "productSearch", "customerSearch", "customerResults", "customerSelectedHint", "posAlert", "posPinModal", "posPinError", "posPinInput", "upsellBar", "doneSaleNumber", "doneViewBtn", "donePrintBtn", "doneUpsellList", "openSessionModal", "closeSessionModal", "openSessionAlert", "closeSessionAlert", "tableField", "posTablesBtn", "posHoldBtn", "posTableSelected", "posFloors", "posTablesGrid", "posTableClear", "posCategories", "posProductGrid", "posSessionBar", "posSessionRequired", "sessionNumber", "sessionBalance", "sessionTotal", "sessionTime", "splitTenderBox", "splitTenderRows", "splitTenderSum", "closeOpening", "closeCashSales", "closeExpected", "closeExpectedBlock", "posCalc", "posPayMethod", "taxRow"];
  for (const id of ids) { const el = document.createElement("div"); el.id = id; document.body.appendChild(el); }
  for (const id of ["orderType", "tableSelect", "paymentMethod", "warehouseId", "currency"]) { const el = document.createElement("select"); el.id = id; document.body.appendChild(el); }
  for (const id of ["taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber", "orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes", "exchangeRate"]) { const el = document.createElement("input"); el.id = id; document.body.appendChild(el); }
  for (const id of ["checkoutBtn", "checkoutPrintBtn", "clearCustomer", "walkinCustomer", "drawerOpenBtn", "splitTenderAdd", "posPinConfirm", "openSessionBtn", "openSessionConfirm", "closeSessionBtn", "closeSessionConfirm", "clearProductSearch", "cameraScanBtn", "scaleConnectBtn"]) { const el = document.createElement("button"); el.id = id; el.type = "button"; document.body.appendChild(el); }
  const cb = document.createElement("input"); cb.type = "checkbox"; cb.id = "splitTenderToggle"; document.body.appendChild(cb);
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
  globalThis.fetch = spy; window.fetch = spy;
  return spy;
}

beforeEach(() => {
  buildDom();
  mockFetch({
    "/pos/api/session/current": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/order-types": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/categories": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    "/pos/api/products": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
  });
  window.t = (k) => k;
  Object.defineProperty(globalThis, "crypto", { value: { randomUUID: () => "uuid" }, configurable: true, writable: true });
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
  const jq = () => ({ show: vi.fn(), hide: vi.fn(), on: vi.fn(), modal: vi.fn(), focus: vi.fn(), val: vi.fn(), text: vi.fn(), html: vi.fn(), addClass: vi.fn(), removeClass: vi.fn(), click: vi.fn() });
  window.$ = vi.fn((sel) => { const a = jq(); if (typeof sel === "function") { sel(); return a; } return a; });
  globalThis.$ = window.$;
  window.BarcodeScanner = vi.fn(function (opts) { this.start = vi.fn(); this.stop = vi.fn(); this.onScan = opts?.onScan; });
  window.printSaleTickets = vi.fn();
  window.printQueuedCartReceipt = vi.fn();
  window.POS_CONFIG = { enable_tables: true, enable_hold: true };
  vi.resetModules();
});

afterEach(async () => { vi.useRealTimers(); vi.clearAllTimers(); vi.restoreAllMocks(); await new Promise((r) => setTimeout(r, 0)); document.body.innerHTML = ""; document.head.innerHTML = ""; });

async function loadModule() { delete window._posFmt; await import(MOD_PATH + String.fromCharCode(63) + Date.now()); await new Promise((r) => setTimeout(r, 50)); }

describe("pos/index basics", () => {
  it("loads", async () => { await loadModule(); });
  it("fmt", async () => { await loadModule(); expect(window._posFmt(5)).toBe("5.00"); expect(window._posFmt(5.556)).toBe("5.56"); });
  it("toNum", async () => { await loadModule(); expect(window._posToNum("5")).toBe(5); expect(window._posToNum("abc")).toBe(0); });
  it("esc", async () => { await loadModule(); expect(window._posEsc("<script>")).toBe("&lt;script&gt;"); });
  it("priceForCurrency same", async () => {
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="USD">USD</option>'; sel.value = "USD";
    document.getElementById("exchangeRate").value = "1";
    expect(window._posPriceForCurrency(100)).toBe(100);
  });
  it("priceForCurrency diff", async () => {
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>'; sel.value = "EUR";
    document.getElementById("exchangeRate").value = "4";
    expect(window._posPriceForCurrency(100)).toBe(25);
  });
  it("currencySymbol", async () => { await loadModule(); expect(window._posCurrencySymbolFor("USD")).toBe("$"); expect(window._posCurrencySymbolFor("XYZ")).toBe("XYZ"); });
  it("showAlert", async () => { await loadModule(); vi.useFakeTimers(); window._posShowAlert("Hi", "success"); expect(document.getElementById("posAlert").textContent).toBe("Hi"); await vi.advanceTimersByTimeAsync(6000); expect(document.getElementById("posAlert").classList.contains("d-none")).toBe(true); });
  it("customerHint", async () => { await loadModule(); window._posState.customer = { text: "John" }; window._posCustomerHint(); expect(document.getElementById("customerSelectedHint").textContent).toContain("John"); });
  it("addToCart", async () => { await loadModule(); await window._posAddToCart({ id: 1, name: "A", price: 10 }); expect(window._posState.cart.length).toBe(1); });
  it("renderCart empty", async () => { await loadModule(); window._posState.cart = []; await window._posRenderCart(); expect(document.getElementById("cartBody").innerHTML).toContain("السلة فارغة"); });
  it("recalc empty", async () => { await loadModule(); window._posState.cart = []; const t = await window._posRecalc(); expect(t.subtotal).toBe(0); });
  it("renderProductResults", async () => { await loadModule(); window._posRenderProductResults([{ id: 1, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false }]); expect(document.getElementById("productResults").textContent).toContain("Apple"); });
  it("splitEnabled", async () => { await loadModule(); expect(window._posSplitEnabled()).toBe(false); });
  it("addSplitRow", async () => { await loadModule(); window._posAddSplitRow(50, "cash"); expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(1); });
  it("readSplitPayments", async () => { await loadModule(); window._posAddSplitRow(30, "cash"); window._posAddSplitRow(20, "card"); const p = window._posReadSplitPayments(); expect(p).toHaveLength(2); });
  it("resetAfterSale", async () => { await loadModule(); window._posState.cart = [{ id: 1, name: "A", qty: 1, price: 10 }]; await window._posResetAfterSale(); expect(window._posState.cart.length).toBe(0); });
  it("checkout no customer", async () => { await loadModule(); vi.useFakeTimers(); window._posState.customer = null; await window._posCheckout(false); expect(document.getElementById("posAlert").textContent).toBeTruthy(); });
  it("handleScannedCode empty", async () => { await loadModule(); await window._posHandleScannedCode(""); expect(window._posState.cart.length).toBe(0); });
  it("newCartKey", async () => { await loadModule(); const k = window._posNewCartKey(); expect(typeof k).toBe("string"); });
  it("fetchJson ok", async () => { mockFetch({ "/test": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ data: "hello" }) }) }); await loadModule(); const r = await window._posFetchJson("/test"); expect(r.ok).toBe(true); expect(r.data).toEqual({ data: "hello" }); });
  it("fetchJson 404", async () => { mockFetch({ "/test": () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "nf" }) }) }); await loadModule(); const r = await window._posFetchJson("/test"); expect(r.ok).toBe(false); expect(r.error).toBe("nf"); });
  it("warehouseParam empty", async () => { await loadModule(); expect(window._posWarehouseParam()).toBe(""); });
  it("warehouseParam value", async () => { await loadModule(); const wh = document.getElementById("warehouseId"); wh.innerHTML = '<option value="5">W5</option>'; wh.value = "5"; expect(window._posWarehouseParam()).toBe("&warehouse_id=5"); });
  it("needsOverride", async () => { await loadModule(); expect(window._posNeedsOverride({ status: 403 }, { error: "تفويض" })).toBe(true); });
  it("postWithOverride", async () => { mockFetch({ "/test": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }) }); await loadModule(); const r = await window._posPostWithOverride("/test", {}, "a"); expect(r.r.ok).toBe(true); });
  it("upsell hide", async () => { await loadModule(); const bar = document.getElementById("upsellBar"); window._posRenderUpsellMessages(bar, []); expect(bar.classList.contains("d-none")).toBe(true); });
  it("toggleTableField dine", async () => { await loadModule(); const sel = document.getElementById("orderType"); sel.innerHTML = '<option value="dine_in">D</option>'; sel.value = "dine_in"; window._posToggleTableField(); expect(document.getElementById("tableField").classList.contains("d-none")).toBe(false); });
  it("heldCount", async () => { await loadModule(); localStorage.setItem("pos_held_carts", "[]"); expect(window._posHeldCount()).toBe(0); localStorage.setItem("pos_held_carts", JSON.stringify([{ cart: [] }])); expect(window._posHeldCount()).toBe(1); });
  it("loadCategories", async () => { mockFetch({ "/pos/api/categories": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "F", name_ar: "طعام" }]) }) }); await loadModule(); await window._posLoadCategories(); expect(document.getElementById("posCategories").textContent).toContain("طعام"); });
  it("loadProducts", async () => { mockFetch({ "/pos/api/products": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "Burger", name_ar: "برجر", price: 25, stock: 10, is_out_of_stock: false, is_inactive: false }]) }) }); await loadModule(); await window._posLoadProducts(""); expect(document.getElementById("posProductGrid").textContent).toContain("Burger"); });
  it("loadProducts empty", async () => { mockFetch({ "/pos/api/products": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }) }); await loadModule(); await window._posLoadProducts(""); expect(document.getElementById("posProductGrid").textContent).toContain("لا توجد منتجات"); });
  it("loadFloors", async () => { mockFetch({ "/pos/api/floors": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "G", name_ar: "أرضي" }]) }) }); await loadModule(); await window._posLoadFloors(); expect(document.getElementById("posFloors").textContent).toContain("أرضي"); });
  it("loadTables", async () => { mockFetch({ "/pos/api/floors/1/tables": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, label: "T1", status: "free" }]) }) }); await loadModule(); await window._posLoadTables("1"); expect(document.getElementById("posTablesGrid").textContent).toContain("T1"); });
});
