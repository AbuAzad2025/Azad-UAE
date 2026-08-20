import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/pos/index.js";

function buildDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = "";

  const metaCsrf = document.createElement("meta");
  metaCsrf.name = "csrf-token";
  metaCsrf.content = "tok-test";
  document.head.appendChild(metaCsrf);

  const metaBase = document.createElement("meta");
  metaBase.name = "pos-base-currency";
  metaBase.content = "USD";
  document.head.appendChild(metaBase);

  const metaVat = document.createElement("meta");
  metaVat.name = "pos-prices-include-vat";
  metaVat.content = "false";
  document.head.appendChild(metaVat);

  const metaSym = document.createElement("meta");
  metaSym.name = "pos-currency-symbol";
  metaSym.content = "$";
  document.head.appendChild(metaSym);

  const ids = [
    "cartBody", "cartCount", "cartEmptyRow",
    "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency",
    "productResults", "productLoading", "productSearch",
    "customerSearch", "customerResults", "customerSelectedHint",
    "posAlert", "posPinModal", "posPinError", "posPinInput",
    "upsellBar", "doneSaleNumber", "doneViewBtn", "donePrintBtn", "doneUpsellList",
    "openSessionModal", "closeSessionModal", "openSessionAlert", "closeSessionAlert",
    "tableField", "posTablesBtn", "posHoldBtn", "posTableSelected",
    "posFloors", "posTablesGrid", "posTableClear",
    "posCategories", "posProductGrid",
    "posSessionBar", "posSessionRequired", "sessionNumber", "sessionBalance", "sessionTotal", "sessionTime",
    "splitTenderBox", "splitTenderRows", "splitTenderSum",
    "closeOpening", "closeCashSales", "closeExpected", "closeExpectedBlock",
    "posCalc", "posPayMethod", "taxRow",
  ];
  for (const id of ids) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }

  const selectIds = [
    "orderType", "tableSelect", "paymentMethod", "warehouseId", "currency",
    "exchangeRate",
  ];
  for (const id of selectIds) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }

  const inputIds = [
    "taxRate", "shippingCost", "discountAmount", "paidAmount",
    "referenceNumber", "orderNote",
    "openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes",
  ];
  for (const id of inputIds) {
    const el = document.createElement("input");
    el.id = id;
    document.body.appendChild(el);
  }

  const btnIds = [
    "checkoutBtn", "checkoutPrintBtn", "clearCustomer", "walkinCustomer",
    "drawerOpenBtn", "splitTenderAdd", "posPinConfirm",
    "openSessionBtn", "openSessionConfirm", "closeSessionBtn", "closeSessionConfirm",
    "clearProductSearch", "cameraScanBtn", "scaleConnectBtn",
  ];
  for (const id of btnIds) {
    const el = document.createElement("button");
    el.id = id;
    el.type = "button";
    document.body.appendChild(el);
  }

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = "splitTenderToggle";
  document.body.appendChild(cb);
}

function mockFetch(map) {
  const spy = vi.fn((url, opts) => {
    const handler = map[url] || map[url.split("?")[0]];
    if (handler) return handler(url, opts);
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ success: true }),
    });
  });
  globalThis.fetch = spy;
  window.fetch = spy;
  return spy;
}

let fetchSpy;

beforeEach(() => {
  buildDom();
  fetchSpy = mockFetch({});

  window.t = (k) => k;
  globalThis.t = (k) => k;

  Object.defineProperty(globalThis, "crypto", {
    value: { randomUUID: () => "test-uuid-123" },
    configurable: true,
    writable: true,
  });

  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };

  const jqChain = () => ({
    show: vi.fn(), hide: vi.fn(), on: vi.fn(), modal: vi.fn(),
    focus: vi.fn(), val: vi.fn(), text: vi.fn(), html: vi.fn(),
    addClass: vi.fn(), removeClass: vi.fn(), click: vi.fn(),
  });
  window.$ = vi.fn((sel) => {
    const a = jqChain();
    if (typeof sel === "function") { sel(); return a; }
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

  vi.resetModules();
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  await new Promise((r) => setTimeout(r, 0));
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

async function loadModule() {
  delete window._posFmt;
  await import(MOD_PATH + String.fromCharCode(63) + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}

describe("module load", () => {
  delete window._posFmt;
  await import(MOD_PATH + "?" + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}

describe("module load", () => {
  delete window._posFmt;
  await import(MOD_PATH + "?" + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}
  await import(MOD_PATH + String.fromCharCode(63) + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}

describe("module load", () => {
  it("loads without throwing", async () => {
    await loadModule();
  });

  it("exposes helpers on window", async () => {
    await loadModule();
    expect(typeof window._posFmt).toBe("function");
    expect(typeof window._posToNum).toBe("function");
    expect(typeof window._posEsc).toBe("function");
    expect(typeof window._posPriceForCurrency).toBe("function");
    expect(typeof window._posCurrencySymbolFor).toBe("function");
    expect(typeof window._posAddToCart).toBe("function");
    expect(typeof window._posRenderCart).toBe("function");
    expect(typeof window._posRecalc).toBe("function");
    expect(typeof window._posShowAlert).toBe("function");
    expect(typeof window._posState).toBe("object");
  });
});

describe("fmt()", () => {
  it("formats to 2 decimals", async () => {
    await loadModule();
    expect(window._posFmt(5)).toBe("5.00");
    expect(window._posFmt(5.5)).toBe("5.50");
    expect(window._posFmt(5.556)).toBe("5.56");
    expect(window._posFmt(0)).toBe("0.00");
    expect(window._posFmt(null)).toBe("0.00");
    expect(window._posFmt(undefined)).toBe("0.00");
  });
});

describe("toNum()", () => {
  it("converts valid input", async () => {
    await loadModule();
    expect(window._posToNum("5")).toBe(5);
    expect(window._posToNum(5.5)).toBe(5.5);
    expect(window._posToNum("3.14")).toBe(3.14);
  });

  it("returns 0 for invalid", async () => {
    await loadModule();
    expect(window._posToNum("abc")).toBe(0);
    expect(window._posToNum(NaN)).toBe(0);
    expect(window._posToNum("")).toBe(0);
  });
});

describe("esc()", () => {
  it("escapes HTML", async () => {
    await loadModule();
    expect(window._posEsc("<script>")).toBe("&lt;script&gt;");
    expect(window._posEsc('"hello"')).toBe("&quot;hello&quot;");
    expect(window._posEsc("A&B")).toBe("A&amp;B");
  });

  it("returns empty for null/undefined", async () => {
    await loadModule();
    expect(window._posEsc(null)).toBe("");
    expect(window._posEsc(undefined)).toBe("");
  });
});

describe("priceForCurrency()", () => {
  it("returns base price for same currency", async () => {
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="USD">USD</option>';
    sel.value = "USD";
    document.getElementById("exchangeRate").value = "1";
    expect(window._posPriceForCurrency(100)).toBe(100);
  });

  it("divides by rate for different currency", async () => {
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    document.getElementById("exchangeRate").value = "3.67";
    expect(window._posPriceForCurrency(100)).toBeCloseTo(27.25, 1);
  });
});

describe("currencySymbolFor()", () => {
  it("returns symbols", async () => {
    await loadModule();
    expect(window._posCurrencySymbolFor("USD")).toBe("$");
    expect(window._posCurrencySymbolFor("EUR")).toBe("€");
    expect(window._posCurrencySymbolFor("ILS")).toBe("₪");
  });

  it("returns code for unknown", async () => {
    await loadModule();
    expect(window._posCurrencySymbolFor("XYZ")).toBe("XYZ");
  });
});

describe("showAlert / showModalAlert / hideModalAlert", () => {
  it("shows and auto-hides alert", async () => {
    await loadModule();
    vi.useFakeTimers();
    window._posShowAlert("Test", "success");
    const el = document.getElementById("posAlert");
    expect(el.textContent).toBe("Test");
    expect(el.classList.contains("d-none")).toBe(false);
    await vi.advanceTimersByTimeAsync(6000);
    expect(el.classList.contains("d-none")).toBe(true);
  });

  it("shows modal alert", async () => {
    await loadModule();
    vi.useFakeTimers();
    const modalAlert = document.createElement("div");
    modalAlert.id = "testModalAlert";
    document.body.appendChild(modalAlert);
    window._posShowModalAlert("testModal", "Error", "warning");
    expect(modalAlert.textContent).toBe("Error");
    await vi.advanceTimersByTimeAsync(7000);
    expect(modalAlert.classList.contains("d-none")).toBe(true);
  });

  it("hides modal alert", async () => {
    await loadModule();
    const modalAlert = document.createElement("div");
    modalAlert.id = "hideModalAlert";
    modalAlert.classList.remove("d-none");
    document.body.appendChild(modalAlert);
    window._posHideModalAlert("hideModal");
    expect(modalAlert.classList.contains("d-none")).toBe(true);
  });
});

describe("customerHint()", () => {
  it("shows customer name", async () => {
    await loadModule();
    window._posState.customer = { id: 1, text: "John" };
    window._posCustomerHint();
    const el = document.getElementById("customerSelectedHint");
    expect(el.textContent).toContain("John");
    expect(el.classList.contains("text-success")).toBe(true);
  });

  it("shows default without customer", async () => {
    await loadModule();
    window._posState.customer = null;
    window._posCustomerHint();
    const el = document.getElementById("customerSelectedHint");
    expect(el.classList.contains("text-muted")).toBe(true);
  });
});

describe("addToCart / renderCart", () => {
  it("adds product", async () => {
    await loadModule();
    await window._posAddToCart({ id: 1, name: "A", price: 10 });
    expect(window._posState.cart.length).toBe(1);
    expect(window._posState.cart[0].name).toBe("A");
    expect(window._posState.cart[0].qty).toBe(1);
  });

  it("increments duplicate", async () => {
    await loadModule();
    await window._posAddToCart({ id: 1, name: "A", price: 10 });
    await window._posAddToCart({ id: 1, name: "A", price: 10 });
    expect(window._posState.cart.length).toBe(1);
    expect(window._posState.cart[0].qty).toBe(2);
  });

  it("adds with custom qty", async () => {
    await loadModule();
    await window._posAddToCart({ id: 2, name: "B", price: 5 }, 3);
    expect(window._posState.cart[0].qty).toBe(3);
  });

  it("renders empty cart", async () => {
    await loadModule();
    window._posState.cart = [];
    await window._posRenderCart();
    expect(document.getElementById("cartBody").innerHTML).toContain("السلة فارغة");
  });

  it("renders items", async () => {
    await loadModule();
    window._posState.cart = [
      { id: 1, name: "Item", sku: "S1", barcode: "B1", qty: 2, price: 10, discountPercent: 0, basePrice: 10 },
    ];
    await window._posRenderCart();
    const body = document.getElementById("cartBody");
    expect(body.querySelectorAll("tr").length).toBe(1);
    expect(body.textContent).toContain("Item");
  });
});

describe("recalc()", () => {
  it("empty cart", async () => {
    await loadModule();
    window._posState.cart = [];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(0);
    expect(totals.total).toBe(0);
  });

  it("with items", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true, subtotal: 20, tax_amount: 0, discount: 0, total: 20 }),
        }),
    });
    await loadModule();
    window._posState.cart = [{ id: 1, qty: 2, price: 10, discountPercent: 0 }];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(20);
  });
});

describe("renderProductResults", () => {
  it("renders list", async () => {
    await loadModule();
    window._posRenderProductResults([
      { id: 1, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false },
    ]);
    const box = document.getElementById("productResults");
    expect(box.querySelectorAll("button").length).toBe(1);
    expect(box.textContent).toContain("Apple");
  });

  it("shows out of stock", async () => {
    await loadModule();
    window._posRenderProductResults([
      { id: 1, text: "Banana", price: 3, stock: 0, is_out_of_stock: true, is_inactive: false },
    ]);
    expect(document.getElementById("productResults").innerHTML).toContain("نفد");
  });
});

describe("runProductSearch", () => {
  it("clears on empty", async () => {
    await loadModule();
    await window._posRunProductSearch("");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);
  });

  it("fetches products", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, text: "Apple", price: 5, stock: 10 }]),
        }),
    });
    await loadModule();
    await window._posRunProductSearch("app");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(false);
  });
});

describe("addFirstOrLookup", () => {
  it("does nothing on empty", async () => {
    await loadModule();
    await window._posAddFirstOrLookup("");
    expect(window._posState.cart.length).toBe(0);
  });
});

describe("updateCartPrices / loadRateForCurrency", () => {
  it("updates prices with rate", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, basePrice: 100, price: 100 }];
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    await window._posUpdateCartPrices();
    expect(window._posState.cart[0].price).toBe(50);
  });

  it("sets rate to 1 for base", async () => {
    mockFetch({});
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="USD">USD</option>';
    sel.value = "USD";
    document.getElementById("exchangeRate").value = "2";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("1");
  });

  it("fetches rate for diff currency", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true, rate: 0.85 }),
        }),
    });
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("0.850000");
  });
});

describe("split tender", () => {
  it("splitEnabled false", async () => {
    await loadModule();
    expect(window._posSplitEnabled()).toBe(false);
  });

  it("adds row", async () => {
    await loadModule();
    window._posAddSplitRow(50, "cash");
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(1);
    expect(document.getElementById("splitTenderSum").textContent).toBe("50.00");
  });

  it("reads payments", async () => {
    await loadModule();
    window._posAddSplitRow(30, "cash");
    window._posAddSplitRow(20, "card");
    const payments = window._posReadSplitPayments();
    expect(payments).toHaveLength(2);
    expect(payments[0].amount).toBe(30);
    expect(payments[1].payment_method).toBe("card");
  });

  it("returns null for invalid", async () => {
    await loadModule();
    window._posAddSplitRow(0, "cash");
    expect(window._posReadSplitPayments()).toBeNull();
  });

  it("splitSumRefresh", async () => {
    await loadModule();
    window._posAddSplitRow(10, "cash");
    window._posAddSplitRow(20, "card");
    window._posSplitSumRefresh();
    expect(document.getElementById("splitTenderSum").textContent).toBe("30.00");
  });
});

describe("resetAfterSale", () => {
  it("clears cart", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, name: "A", qty: 1, price: 10 }];
    await window._posResetAfterSale();
    expect(window._posState.cart.length).toBe(0);
    expect(document.getElementById("paidAmount").value).toBe("0");
  });
});

describe("checkout", () => {
  it("warns no customer", async () => {
    await loadModule();
    vi.useFakeTimers();
    window._posState.customer = null;
    await window._posCheckout(false);
    const alert = document.getElementById("posAlert");
    expect(alert.textContent).toBeTruthy();
    expect(alert.classList.contains("d-none")).toBe(false);
  });

  it("warns empty cart", async () => {
    await loadModule();
    vi.useFakeTimers();
    window._posState.customer = { id: 1 };
    window._posState.cart = [];
    await window._posCheckout(false);
    expect(document.getElementById("posAlert").textContent).toBeTruthy();
  });
});

describe("handleScannedCode", () => {
  it("returns early for empty/null", async () => {
    await loadModule();
    await window._posHandleScannedCode("");
    expect(window._posState.cart.length).toBe(0);
    await window._posHandleScannedCode(null);
    expect(window._posState.cart.length).toBe(0);
  });
});

describe("newCartKey", () => {
  it("generates key", async () => {
    await loadModule();
    const key = window._posNewCartKey();
    expect(typeof key).toBe("string");
    expect(key.length).toBeGreaterThan(0);
  });
});

describe("fetchJson", () => {
  it("returns ok data", async () => {
    mockFetch({
      "/test": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ data: "hello" }),
        }),
    });
    await loadModule();
    const res = await window._posFetchJson("/test");
    expect(res.ok).toBe(true);
    expect(res.data).toEqual({ data: "hello" });
  });

  it("returns error on 404", async () => {
    mockFetch({
      "/test": () =>
        Promise.resolve({
          ok: false, status: 404,
          json: () => Promise.resolve({ error: "not found" }),
        }),
    });
    await loadModule();
    const res = await window._posFetchJson("/test");
    expect(res.ok).toBe(false);
    expect(res.error).toBe("not found");
  });
});

describe("warehouseParam", () => {
  it("empty when no warehouse", async () => {
    await loadModule();
    document.getElementById("warehouseId").value = "";
    expect(window._posWarehouseParam()).toBe("");
  });

  it("returns param", async () => {
    await loadModule();
    const wh = document.getElementById("warehouseId");
    wh.innerHTML = '<option value="5">W5</option>';
    wh.value = "5";
    expect(window._posWarehouseParam()).toBe("&warehouse_id=5");
  });

  it("custom separator", async () => {
    await loadModule();
    const wh = document.getElementById("warehouseId");
    wh.innerHTML = '<option value="5">W5</option>';
    wh.value = "5";
    expect(window._posWarehouseParam("?")).toBe("?warehouse_id=5");
  });
});

describe("needsOverride", () => {
  it("true for 403 with تفويض", async () => {
    await loadModule();
    expect(window._posNeedsOverride({ status: 403 }, { error: "يتطلب تفويض" })).toBe(true);
  });

  it("false for other", async () => {
    await loadModule();
    expect(window._posNeedsOverride({ status: 200 }, { error: "" })).toBe(false);
  });
});

describe("postWithOverride", () => {
  it("returns first if not 403", async () => {
    mockFetch({
      "/test": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true }),
        }),
    });
    await loadModule();
    const result = await window._posPostWithOverride("/test", {}, "action");
    expect(result.r.ok).toBe(true);
  });
});

describe("upsell", () => {
  it("hides for empty", async () => {
    await loadModule();
    const bar = document.getElementById("upsellBar");
    window._posRenderUpsellMessages(bar, []);
    expect(bar.classList.contains("d-none")).toBe(true);
  });

  it("shows prompts", async () => {
    await loadModule();
    const bar = document.getElementById("upsellBar");
    window._posRenderUpsellMessages(bar, [{ message: "Buy" }]);
    expect(bar.classList.contains("d-none")).toBe(false);
    expect(bar.textContent).toContain("Buy");
  });

  it("schedule sets timeout", async () => {
    await loadModule();
    vi.useFakeTimers();
    window._posScheduleUpsellEval();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
  });
});

describe("toggleTableField", () => {
  it("shows for dine-in", async () => {
    await loadModule();
    const sel = document.getElementById("orderType");
    sel.innerHTML = '<option value="dine_in">Dine</option>';
    sel.value = "dine_in";
    window._posToggleTableField();
    expect(document.getElementById("tableField").classList.contains("d-none")).toBe(false);
  });

  it("hides for takeaway", async () => {
    await loadModule();
    const sel = document.getElementById("orderType");
    sel.innerHTML = '<option value="takeaway">Takeaway</option>';
    sel.value = "takeaway";
    window._posToggleTableField();
    expect(document.getElementById("tableField").classList.contains("d-none")).toBe(true);
  });
});

describe("heldCount", () => {
  it("0 when empty", async () => {
    await loadModule();
    localStorage.setItem("pos_held_carts", "[]");
    expect(window._posHeldCount()).toBe(0);
  });

  it("returns count", async () => {
    await loadModule();
    localStorage.setItem("pos_held_carts", JSON.stringify([{ cart: [] }, { cart: [] }]));
    expect(window._posHeldCount()).toBe(2);
  });

  it("0 for invalid json", async () => {
    await loadModule();
    localStorage.setItem("pos_held_carts", "bad");
    expect(window._posHeldCount()).toBe(0);
  });
});

describe("loadCategories", () => {
  it("renders categories", async () => {
    mockFetch({
      "/pos/api/categories": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, name: "Food", name_ar: "طعام" }]),
        }),
    });
    await loadModule();
    await window._posLoadCategories();
    expect(document.getElementById("posCategories").textContent).toContain("طعام");
  });
});

describe("loadProducts", () => {
  it("renders grid", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([
            { id: 1, name: "Burger", name_ar: "برجر", price: 25, stock: 10, is_out_of_stock: false, is_inactive: false },
          ]),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("برجر");
  });

  it("empty state", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([]),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("لا توجد منتجات");
  });
});

describe("loadFloors / loadTables", () => {
  it("renders floors", async () => {
    mockFetch({
      "/pos/api/floors": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, name: "Ground", name_ar: "أرضي" }]),
        }),
    });
    await loadModule();
    await window._posLoadFloors();
    expect(document.getElementById("posFloors").textContent).toContain("أرضي");
  });

  it("renders tables", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, label: "T1", status: "free" }]),
        }),
    });
    await loadModule();
    await window._posLoadTables("1");
    expect(document.getElementById("posTablesGrid").textContent).toContain("T1");
  });
});
