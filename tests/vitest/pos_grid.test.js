import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Ensure jsdom document is available before any module imports
if (typeof document === "undefined") {
  globalThis.document = {
    createElement: () => ({ querySelector: () => null, querySelectorAll: () => [], innerHTML: "", appendChild: () => {}, setAttribute: () => {}, addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true }),
    createElementNS: () => ({ querySelector: () => null, querySelectorAll: () => [], innerHTML: "", appendChild: () => {}, setAttribute: () => {}, addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true }),
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    body: { innerHTML: "", appendChild: () => {}, querySelector: () => null, querySelectorAll: () => [], createElement: () => ({}), createElementNS: () => ({}), removeChild: () => {} },
    head: { innerHTML: "", appendChild: () => {}, querySelector: () => null, querySelectorAll: () => [], createElement: () => ({}), createElementNS: () => ({}), removeChild: () => {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  };
  globalThis.window = globalThis.document.defaultView = globalThis.document;
}

let fetchSpy;
const _dclHandlers = [];

async function loadModule() {
  for (const { fn, target } of _dclHandlers) {
    try { target.removeEventListener("DOMContentLoaded", fn); } catch (_) {}
  }
  _dclHandlers.length = 0;

  const origAdd = document.addEventListener;
  document.addEventListener = function (type, fn, opts) {
    if (type === "DOMContentLoaded") {
      _dclHandlers.push({ fn, target: this });
    }
    return origAdd.call(this, type, fn, opts);
  };

  await import("../../static/js/pos/grid.js");
  document.addEventListener = origAdd;

  document.dispatchEvent(new Event("DOMContentLoaded"));
  await new Promise((r) => setTimeout(r, 20));
}

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

  const divIds = [
    "cartItems", "cartEmpty",
    "kpiSubtotal", "kpiTax", "kpiDiscount", "kpiShipping", "kpiTotal", "kpiCurrency",
    "productGrid", "productLoading", "productResults",
    "categoryList",
    "posSessionBar", "posSessionRequired", "sessionNumber", "sessionBalance", "sessionTotal",
    "customerSelectedHint", "customerResults",
    "posAlert", "upsellBar",
    "posPinModal", "posPinError",
    "splitTenderBox", "splitTenderRows", "splitTenderSum",
    "openSessionModal", "closeSessionModal",
    "closeOpening", "closeCashSales", "closeExpected", "closeExpectedBlock",
    "doneSaleNumber", "doneViewBtn", "donePrintBtn", "doneUpsellList",
    "taxRow",
  ];
  for (const id of divIds) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }
  document.getElementById("upsellBar").classList.add("d-none");
  document.getElementById("cartItems").classList.add("d-none");

  const selectIds = [
    "orderType", "tableSelect", "paymentMethod", "warehouseId", "currency",
  ];
  for (const id of selectIds) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }

  const inputIds = [
    "taxRate", "shippingCost", "discountAmount", "paidAmount", "exchangeRate",
    "productSearch", "posPinInput", "customerSearch", "tableField",
    "openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes",
    "referenceNumber",
  ];
  for (const id of inputIds) {
    const el = document.createElement("input");
    el.id = id;
    document.body.appendChild(el);
  }

  const btnIds = [
    "checkoutBtn", "clearCartBtn", "openSessionBtn", "openSessionConfirm",
    "closeSessionBtn", "closeSessionConfirm",
    "walkinCustomer", "clearCustomer", "drawerOpenBtn",
    "splitTenderAdd", "posPinConfirm", "checkoutPrintBtn",
    "cameraScanBtn", "scaleConnectBtn",
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

  const cartPanel = document.createElement("div");
  cartPanel.className = "pos-cart-panel";
  document.body.appendChild(cartPanel);

  const numpad = document.createElement("div");
  numpad.className = "pos-numpad";
  for (const key of ["1","2","3","4","5","6","7","8","9","0",".","del","Enter","qty","disc","price"]) {
    const b = document.createElement("button");
    b.dataset.key = key;
    b.textContent = key;
    numpad.appendChild(b);
  }
  document.body.appendChild(numpad);
}

function mockFetch(map) {
  fetchSpy = vi.fn((url, opts) => {
    const handler = map[url] || map[url.split("?")[0]];
    if (handler) return handler(url, opts);
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true }),
    });
  });
  globalThis.fetch = fetchSpy;
  window.fetch = fetchSpy;
}

beforeEach(() => {
  buildDom();
  mockFetch({});

  window.t = (k) => k;
  globalThis.t = (k) => k;

  window.open = vi.fn();
  if (typeof window.crypto.randomUUID !== "function") {
    Object.defineProperty(window.crypto, "randomUUID", {
      value: () => "rand-" + Math.random(),
      configurable: true,
      writable: true,
    });
  }
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };

  const jqChain = () => {
    const api = { show: vi.fn(), hide: vi.fn(), on: vi.fn(), val: vi.fn(""), modal: vi.fn(), focus: vi.fn(), text: vi.fn(), html: vi.fn(), addClass: vi.fn(), removeClass: vi.fn() };
    return api;
  };
  window.$ = vi.fn((sel) => {
    const a = jqChain();
    if (typeof sel === "function") { sel(); return a; }
    return a;
  });
  globalThis.$ = window.$;

  vi.resetModules();
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  await new Promise((r) => setTimeout(r, 0));
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});



describe("pos/grid.js module load", () => {
  it("loads without throwing", async () => {
    await loadModule();
  });

  it("fires DOMContentLoaded and calls fetch for session", async () => {
    let sessionHit = false;
    mockFetch({
      "/pos/api/session/current": () => {
        sessionHit = true;
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true, session: { id: 1, number: "S1", opening_balance: 100, total_sales: 50 } }),
        });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    expect(sessionHit).toBe(true);
  });

  it("calls loadCategories endpoint", async () => {
    let catHit = false;
    mockFetch({
      "/pos/api/categories": () => {
        catHit = true;
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, name: "Food", name_ar: "طعام" }]),
        });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    expect(catHit).toBe(true);
    const catItems = document.querySelectorAll(".cat-item");
    expect(catItems.length).toBe(1);
    expect(catItems[0].textContent).toContain("طعام");
  });

  it("calls loadProducts endpoint", async () => {
    let prodHit = false;
    mockFetch({
      "/pos/api/products": () => {
        prodHit = true;
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 1, name: "Burger", name_ar: "برجر", price: 25, stock: 10, stock_label: "10" }]),
        });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    expect(prodHit).toBe(true);
    const cards = document.querySelectorAll(".pos-product-card");
    expect(cards.length).toBe(1);
    expect(cards[0].dataset.id).toBe("1");
  });

  it("calls loadOrderTypes endpoint", async () => {
    let otHit = false;
    mockFetch({
      "/pos/api/order-types": () => {
        otHit = true;
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true, order_types: [{ code: "dine_in", display_name: "Dine In" }], default_code: "dine_in" }),
        });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    expect(otHit).toBe(true);
    const sel = document.getElementById("orderType");
    expect(sel.options.length).toBe(1);
    expect(sel.options[0].value).toBe("dine_in");
  });
});

describe("esc() HTML escaping", () => {
  it("escapes ampersand and angle brackets", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve([{ id: 10, name: "A&B <C> D", price: 5, stock: 1, stock_label: "" }]),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const nameEl = document.querySelector(".prod-name");
    const escapedText = nameEl?.innerHTML || "";
    expect(escapedText).toContain("&amp;");
    expect(escapedText).toContain("&lt;");
    expect(escapedText).toContain("&gt;");
  });

  it("returns empty string for null/undefined", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));
    const container = document.getElementById("cartItems");
    expect(container?.innerHTML || "").toBe("");
  });
});

describe("fmt() number formatting", () => {
  it("formats numbers to 2 decimals via recalc", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 5, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 1.5, discount: 0, total: 11.5 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 50));
    const subtotalEl = document.getElementById("kpiSubtotal");
    expect(subtotalEl.textContent).toMatch(/^\d+\.\d{2}$/);
  });
});

describe("currencySymbolFor() symbol lookup", () => {
  it("returns correct symbol for known currency", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 5, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 50));
    const kpiCur = document.getElementById("kpiCurrency");
    expect(kpiCur.textContent).toBe("$");
  });
});

describe("showAlert()", () => {
  it("displays alert message and auto-hides", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false, error: "no walkin" }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    vi.useFakeTimers();
    document.getElementById("checkoutBtn").click();
    await vi.advanceTimersByTimeAsync(50);
    const alert = document.getElementById("posAlert");
    expect(alert.textContent).toBeTruthy();
    expect(alert.classList.contains("d-none")).toBe(false);

    await vi.advanceTimersByTimeAsync(6000);
    expect(alert.classList.contains("d-none")).toBe(true);
  });
});

describe("addToCart / renderCart / recalc", () => {
  it("adds a product when card is clicked", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([{ id: 42, name: "Fries", name_ar: "بطاطا", price: 10, stock: 5, stock_label: "5" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 1.5, discount: 0, total: 11.5 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    const card = document.querySelector(".pos-product-card");
    expect(card).toBeTruthy();
    card.click();
    await new Promise((r) => setTimeout(r, 50));

    const items = document.querySelectorAll(".pos-cart-item");
    expect(items.length).toBe(1);
    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });

  it("increments quantity for duplicate product", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 5, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    const card = document.querySelector(".pos-product-card");
    card.click();
    await new Promise((r) => setTimeout(r, 30));
    card.click();
    await new Promise((r) => setTimeout(r, 30));

    const items = document.querySelectorAll(".pos-cart-item");
    expect(items.length).toBe(1);
    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });

  it("clear cart resets state", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "X", price: 5, stock: 5, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 0, tax_amount: 0, discount: 0, total: 0 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(1);

    document.getElementById("clearCartBtn").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(0);
    expect(document.getElementById("kpiTotal").textContent).toBe("0.00");
  });
});

describe("handleNumpad()", () => {
  it("shows warning when no line selected for qty mode", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 5, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 0, tax_amount: 0, discount: 0, total: 0 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    vi.useFakeTimers();
    document.querySelector('[data-key="qty"]').click();
    await vi.advanceTimersByTimeAsync(10);
    expect(document.getElementById("posAlert").classList.contains("d-none")).toBe(false);
  });

  it("updates quantity when a line is selected", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 50, tax_amount: 0, discount: 0, total: 50 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));

    const cartItem = document.querySelector(".pos-cart-item");
    expect(cartItem).toBeTruthy();
    cartItem.click();
    await new Promise((r) => setTimeout(r, 10));

    document.querySelector('[data-key="qty"]').click();
    await new Promise((r) => setTimeout(r, 10));
    document.querySelector('[data-key="5"]').click();
    document.querySelector('[data-key="Enter"]').click();
    await new Promise((r) => setTimeout(r, 30));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("50.00");
  });

  it("del key removes last digit from buffer", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    document.querySelector(".pos-cart-item").click();
    await new Promise((r) => setTimeout(r, 10));

    document.querySelector('[data-key="qty"]').click();
    document.querySelector('[data-key="1"]').click();
    document.querySelector('[data-key="0"]').click();
    document.querySelector('[data-key="del"]').click();
    document.querySelector('[data-key="Enter"]').click();
    await new Promise((r) => setTimeout(r, 30));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });

  it("Escape key resets numpad buffer and mode", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 10, stock: 5, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    document.querySelector(".pos-cart-item").click();
    await new Promise((r) => setTimeout(r, 10));

    document.querySelector('[data-key="qty"]').click();
    document.querySelector('[data-key="5"]').click();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    document.querySelector('[data-key="Enter"]').click();
    await new Promise((r) => setTimeout(r, 30));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });
});

describe("numpad discount mode", () => {
  it("sets discount percent on selected line", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Item", price: 100, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 90, tax_amount: 0, discount: 10, total: 90 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    document.querySelector(".pos-cart-item").click();
    await new Promise((r) => setTimeout(r, 10));

    document.querySelector('[data-key="disc"]').click();
    document.querySelector('[data-key="1"]').click();
    document.querySelector('[data-key="0"]').click();
    document.querySelector('[data-key="Enter"]').click();
    await new Promise((r) => setTimeout(r, 30));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("90.00");
  });
});

describe("split tender", () => {
  it("splitEnabled returns false when toggle unchecked", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.getElementById("splitTenderToggle").checked).toBe(false);
  });

  it("adds split rows when toggled", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    const toggle = document.getElementById("splitTenderToggle");
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 10));

    const rows = document.querySelectorAll("#splitTenderRows .split-row");
    expect(rows.length).toBe(1);
    expect(rows[0].querySelector(".split-amount")).toBeTruthy();
    expect(rows[0].querySelector(".split-method")).toBeTruthy();
  });

  it("add button creates new rows", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("splitTenderAdd").click();
    await new Promise((r) => setTimeout(r, 10));
    document.getElementById("splitTenderAdd").click();
    await new Promise((r) => setTimeout(r, 10));
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(2);
  });

  it("removing a row updates sum", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("splitTenderAdd").click();
    document.getElementById("splitTenderAdd").click();
    await new Promise((r) => setTimeout(r, 10));

    const removeBtn = document.querySelector(".split-remove");
    removeBtn.click();
    await new Promise((r) => setTimeout(r, 10));
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(1);
  });
});

describe("toggleTableField", () => {
  it("shows table field for dine-in order type", async () => {
    mockFetch({
      "/pos/api/order-types": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, order_types: [{ code: "dine_in", display_name: "Dine In" }], default_code: "dine_in" }),
        }),
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/tables": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 1, label: "Table 1", floor_name: "Ground" }]) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const tableField = document.getElementById("tableField");
    expect(tableField.classList.contains("d-none")).toBe(false);
  });

  it("hides table field for takeaway order type", async () => {
    mockFetch({
      "/pos/api/order-types": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, order_types: [{ code: "takeaway", display_name: "Takeaway" }], default_code: "takeaway" }),
        }),
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const tableField = document.getElementById("tableField");
    expect(tableField.classList.contains("d-none")).toBe(true);
  });
});

describe("customer search", () => {
  it("search populates customer results", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/customers": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, text: "John Doe" }]),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    const custSearch = document.getElementById("customerSearch");
    custSearch.value = "John";
    custSearch.dispatchEvent(new Event("input"));
    await new Promise((r) => setTimeout(r, 300));

    const results = document.getElementById("customerResults");
    expect(results.classList.contains("d-none")).toBe(false);
    expect(results.children.length).toBe(1);
    expect(results.children[0].textContent).toBe("John Doe");
  });
});

describe("walk-in customer", () => {
  it("sets walk-in customer on click", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, id: 99, text: "Walk-in" }),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("walkinCustomer").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.getElementById("customerSelectedHint").textContent).toBe("Walk-in");
  });

  it("clears customer on clearCustomer click", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, id: 99, text: "Walk-in" }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("walkinCustomer").click();
    await new Promise((r) => setTimeout(r, 30));
    document.getElementById("clearCustomer").click();
    await new Promise((r) => setTimeout(r, 10));
    expect(document.getElementById("customerSelectedHint").textContent).not.toBe("Walk-in");
  });
});

describe("checkout", () => {
  it("shows warning on empty cart", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    vi.useFakeTimers();
    document.getElementById("checkoutBtn").click();
    await vi.advanceTimersByTimeAsync(50);
    expect(document.getElementById("posAlert").textContent).toBeTruthy();
  });

  it("successful checkout clears cart", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, id: 1 }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
      "/pos/api/checkout": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, sale_number: "SA-001", view_url: "/view", print_url: "/print" }),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("checkoutBtn").click();
    await new Promise((r) => setTimeout(r, 80));

    expect(document.querySelectorAll(".pos-cart-item").length).toBe(0);
  });
});

describe("session management", () => {
  it("open session sends balance to server", async () => {
    let openHit = false;
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/open": (url, opts) => {
        openHit = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.getElementById("openSessionBalance").value = "500";
    document.getElementById("openSessionConfirm").click();
    await new Promise((r) => setTimeout(r, 50));
    expect(openHit).toBe(true);
  });

  it("close session sends balance to server", async () => {
    let closeHit = false;
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, session: { id: 1, number: "S1", opening_balance: 100, total_sales: 50 } }) }),
      "/pos/api/session/report": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, session: { opening_balance: 100, total_cash_sales: 200, expected_balance: 300 } }) }),
      "/pos/api/session/close": (url, opts) => {
        closeHit = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.getElementById("closeSessionBalance").value = "300";
    document.getElementById("closeSessionConfirm").click();
    await new Promise((r) => setTimeout(r, 50));
    expect(closeHit).toBe(true);
  });
});

describe("401 session expiry", () => {
  it("hits 401 handler", async () => {
    mockFetch({
      "/pos/api/session/current": () =>
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
      "/pos/api/categories": () =>
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
      "/pos/api/products": () =>
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
      "/pos/api/order-types": () =>
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchSpy).toHaveBeenCalled();
  });
});

describe("keyboard shortcuts", () => {
  it("F2 focuses product search", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    const focusSpy = vi.fn();
    document.getElementById("productSearch").focus = focusSpy;
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "F2", bubbles: true }));
    expect(focusSpy).toHaveBeenCalled();
  });

  it("F8 triggers checkout print", async () => {
    let checkoutHit = false;
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, id: 1 }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
      "/pos/api/checkout": () => {
        checkoutHit = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, sale_number: "S2", view_url: "/v", print_url: "/p" }) });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "F8", bubbles: true }));
    await new Promise((r) => setTimeout(r, 80));
    expect(checkoutHit).toBe(true);
  });
});

describe("product search", () => {
  it("debounced search calls loadProducts", async () => {
    let searchParam = "";
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": (url) => {
        if (url.includes("q=")) searchParam = url;
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      },
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    const input = document.getElementById("productSearch");
    input.value = "burger";
    input.dispatchEvent(new Event("input"));
    await new Promise((r) => setTimeout(r, 300));
    expect(searchParam).toContain("q=burger");
  });
});

describe("empty products", () => {
  it("shows 'no products' message when API returns empty", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    const grid = document.getElementById("productGrid");
    expect(grid.innerHTML).toContain("لا توجد منتجات");
  });
});

describe("product grid rendering", () => {
  it("renders product with image URL", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 5, stock: 5, stock_label: "", image_url: "/img/a.png" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const img = document.querySelector(".pos-product-card .prod-img");
    expect(img.tagName).toBe("IMG");
  });

  it("renders product without image as icon fallback", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "B", price: 8, stock: 3, stock_label: "3" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const fallback = document.querySelector(".pos-product-card .prod-img");
    expect(fallback.querySelector("i")).toBeTruthy();
  });

  it("out-of-stock card does not get click listener", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "X", price: 5, stock: 0, stock_label: "0", is_out_of_stock: true }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    const card = document.querySelector(".pos-product-card.out-of-stock");
    expect(card).toBeTruthy();
    card.click();
    await new Promise((r) => setTimeout(r, 10));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(0);
  });
});

describe("qty minus removes item", () => {
  it("removes item when minus clicked at qty 1", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 0, tax_amount: 0, discount: 0, total: 0 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(1);

    const minusBtn = document.querySelector(".qty-minus");
    minusBtn.click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(0);
  });

  it("decrements qty when above 1", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": (_url, opts) => {
        const body = JSON.parse(opts.body);
        const sub = body.lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: sub, tax_amount: 0, discount: 0, total: sub }) });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 20));
    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 20));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("20.00");
    const minusBtn = document.querySelector(".qty-minus");
    minusBtn.click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });
});

describe("item remove button", () => {
  it("removes item from cart", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 0, tax_amount: 0, discount: 0, total: 0 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(1);

    document.querySelector(".item-remove").click();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelectorAll(".pos-cart-item").length).toBe(0);
  });
});

describe("currency change", () => {
  it("loads rate for selected currency", async () => {
    let rateHit = false;
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/api/currency-rate/EUR/USD": () => {
        rateHit = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, rate: 0.92 }) });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 30));

    const cur = document.getElementById("currency");
    const opt = document.createElement("option");
    opt.value = "EUR";
    opt.textContent = "EUR";
    cur.appendChild(opt);
    cur.value = "EUR";
    cur.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));
    expect(rateHit).toBe(true);
    expect(document.getElementById("exchangeRate").value).toBe("0.920000");
  });
});

describe("upsell evaluation", () => {
  it("renders upsell messages from server", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              upsell_prompts: [{ message: "Add fries for $3!" }],
            }),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 500));

    const upsell = document.getElementById("upsellBar");
    expect(upsell.classList.contains("d-none")).toBe(false);
    expect(upsell.textContent).toContain("Add fries");
  });

  it("hides upsell bar when cart is empty", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));
    const upsell = document.getElementById("upsellBar");
    expect(upsell.classList.contains("d-none")).toBe(true);
  });
});

describe("readSplitPayments", () => {
  it("checkout with split enabled and valid rows proceeds", async () => {
    let checkoutHit = false;
    let bodyCaptured = null;
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 100, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, id: 1 }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 100, tax_amount: 0, discount: 0, total: 100 }) }),
      "/pos/api/checkout": (url, opts) => {
        checkoutHit = true;
        bodyCaptured = JSON.parse(opts.body);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, sale_number: "S3", view_url: "/v", print_url: "/p" }),
        });
      },
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));

    const toggle = document.getElementById("splitTenderToggle");
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 10));

    const amountInput = document.querySelector("#splitTenderRows .split-amount");
    amountInput.value = "100";

    document.getElementById("checkoutBtn").click();
    await new Promise((r) => setTimeout(r, 80));

    expect(checkoutHit).toBe(true);
    expect(bodyCaptured.payments).toBeDefined();
    expect(bodyCaptured.payments.length).toBe(1);
    expect(bodyCaptured.payments[0].amount).toBe(100);
  });
});

describe("session init with active session", () => {
  it("shows session bar when session is active", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, session: { id: 42, number: "POS-42", opening_balance: 500, total_sales: 1200 } }),
        }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    expect(document.getElementById("posSessionBar").classList.contains("d-none")).toBe(false);
    expect(document.getElementById("posSessionRequired").classList.contains("d-none")).toBe(true);
    expect(document.getElementById("sessionNumber").textContent).toBe("POS-42");
    expect(document.getElementById("sessionBalance").textContent).toBe("500.00");
    expect(document.getElementById("sessionTotal").textContent).toBe("1200.00");
  });
});

describe("numpad Enter with no buffer", () => {
  it("Enter with no buffer is a no-op", async () => {
    mockFetch({
      "/pos/api/categories": () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "A", price: 10, stock: 10, stock_label: "" }]),
        }),
      "/pos/api/order-types": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/session/current": () => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, upsell_prompts: [] }) }),
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, subtotal: 10, tax_amount: 0, discount: 0, total: 10 }) }),
    });
    await loadModule();
    await new Promise((r) => setTimeout(r, 50));

    document.querySelector(".pos-product-card").click();
    await new Promise((r) => setTimeout(r, 30));
    document.querySelector(".pos-cart-item").click();
    await new Promise((r) => setTimeout(r, 10));

    document.querySelector('[data-key="qty"]').click();
    document.querySelector('[data-key="Enter"]').click();
    await new Promise((r) => setTimeout(r, 30));

    expect(document.getElementById("kpiSubtotal").textContent).toBe("10.00");
  });
});
