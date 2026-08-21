import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../../static/js/pos/cart.js";

function buildDom({ pricesIncludeVat = "false" } = {}) {
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

  const vat = document.createElement("meta");
  vat.name = "pos-prices-include-vat";
  vat.content = pricesIncludeVat;
  document.head.appendChild(vat);

  const ids = [
    "cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency", "upsellBar",
  ];
  for (const id of ids) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }

  for (const id of ["currency"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }

  for (const id of ["taxRate", "shippingCost", "discountAmount", "exchangeRate"]) {
    const el = document.createElement("input");
    el.id = id;
    el.type = "number";
    el.value = "0";
    document.body.appendChild(el);
  }
}

function mockFetch(map) {
  const existing = globalThis.fetch?._map || {};
  const merged = { ...existing, ...map };
  const spy = vi.fn((url) => {
    const u = new URL(url, "http://localhost");
    const path = u.pathname + u.search;
    const handler = merged[path] || merged[u.pathname];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  spy._map = merged;
  globalThis.fetch = spy;
  window.fetch = spy;
  return spy;
}

beforeEach(() => {
  buildDom();
  mockFetch({});
  window.t = (k) => k;
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
  Object.defineProperty(globalThis, "crypto", { value: { randomUUID: () => "uuid" }, configurable: true, writable: true });
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
  const core = await import("../../../static/js/pos/core.js");
  const cart = await import(MOD_PATH);
  return { ...cart, state: core.state };
}

describe("pos/cart.js — updateCartPrices", () => {
  it("converts cart item prices using current rate", async () => {
    const { state, updateCartPrices } = await loadModule();
    const currency = document.getElementById("currency");
    currency.innerHTML = '<option value="EUR">EUR</option>';
    currency.value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    state.cart = [{ id: 1, name: "A", price: 50, basePrice: 100, qty: 1, discountPercent: 0 }];
    await updateCartPrices();
    expect(state.cart[0].price).toBe(50);
    expect(state.cart[0].basePrice).toBe(100);
  });
});

describe("pos/cart.js — loadRateForCurrency", () => {
  it("sets rate to 1 for base currency and updates prices", async () => {
    const { state, loadRateForCurrency } = await loadModule();
    const currency = document.getElementById("currency");
    currency.innerHTML = '<option value="USD">USD</option>';
    currency.value = "USD";
    state.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await loadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("1");
    expect(state.cart[0].price).toBe(10);
  });

  it("fetches and applies rate for foreign currency", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, rate: 4 }) }),
    });
    const { state, loadRateForCurrency } = await loadModule();
    const currency = document.getElementById("currency");
    currency.innerHTML = '<option value="EUR">EUR</option>';
    currency.value = "EUR";
    state.cart = [{ id: 1, name: "A", price: 100, basePrice: 100, qty: 1, discountPercent: 0 }];
    await loadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("4.000000");
    expect(state.cart[0].price).toBe(25);
  });

  it("ignores fetch failure and still updates prices", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () => Promise.reject(new Error("offline")),
    });
    const { state, loadRateForCurrency } = await loadModule();
    const currency = document.getElementById("currency");
    currency.innerHTML = '<option value="EUR">EUR</option>';
    currency.value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    state.cart = [{ id: 1, name: "A", price: 50, basePrice: 100, qty: 1, discountPercent: 0 }];
    await loadRateForCurrency();
    expect(state.cart[0].price).toBe(50);
  });
});

describe("pos/cart.js — recalc", () => {
  it("returns quick totals with empty cart", async () => {
    const { state, recalc } = await loadModule();
    state.cart = [];
    const totals = await recalc();
    expect(totals.subtotal).toBe(0);
    expect(totals.total).toBe(0);
  });

  it("backend success path updates KPIs", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, subtotal: 90, discount: 5, total: 100, tax_amount: 15, prices_include_vat: false }),
        }),
    });
    const { state, recalc } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    document.getElementById("taxRate").value = "10";
    const totals = await recalc();
    expect(document.getElementById("kpiSubtotal").textContent).toBe("90.00");
    expect(document.getElementById("kpiTotal").textContent).toBe("100.00");
    expect(totals.subtotal).toBe(90);
    expect(totals.total).toBe(100);
  });

  it("backend failure falls back to quick totals", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    });
    const { state, recalc } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    document.getElementById("taxRate").value = "10";
    const totals = await recalc();
    expect(totals.subtotal).toBe(100);
    expect(totals.total).toBe(110);
  });

  it("handles VAT-inclusive meta with zero quick tax", async () => {
    buildDom({ pricesIncludeVat: "true" });
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.reject(new Error("offline")),
    });
    const { state, recalc } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    document.getElementById("taxRate").value = "10";
    const totals = await recalc();
    expect(totals.tax).toBe(0);
    expect(totals.prices_include_vat).toBe(true);
  });
});

describe("pos/cart.js — renderUpsellMessages", () => {
  it("renders prompt messages", async () => {
    const { renderUpsellMessages } = await loadModule();
    const bar = document.getElementById("upsellBar");
    renderUpsellMessages(bar, [{ message: "\u0623\u0636\u0641 \u0645\u0634\u0631\u0648\u0628" }]);
    expect(bar.textContent).toContain("\u0623\u0636\u0641 \u0645\u0634\u0631\u0648\u0628");
    expect(bar.classList.contains("d-none")).toBe(false);
  });

  it("treats non-array as empty", async () => {
    const { renderUpsellMessages } = await loadModule();
    const bar = document.getElementById("upsellBar");
    renderUpsellMessages(bar, "bad");
    expect(bar.innerHTML).toBe("");
    expect(bar.classList.contains("d-none")).toBe(true);
  });

  it("hides container when prompts empty", async () => {
    const { renderUpsellMessages } = await loadModule();
    const bar = document.getElementById("upsellBar");
    renderUpsellMessages(bar, []);
    expect(bar.classList.contains("d-none")).toBe(true);
  });
});

describe("pos/cart.js — evaluateUpsell", () => {
  it("fetches promotions and renders prompts", async () => {
    mockFetch({
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, upsell_prompts: [{ message: "\u0639\u0631\u0636" }] }),
        }),
    });
    const { state, evaluateUpsell } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await evaluateUpsell();
    expect(document.getElementById("upsellBar").textContent).toContain("\u0639\u0631\u0636");
  });

  it("clears bar when cart empty", async () => {
    const { state, evaluateUpsell } = await loadModule();
    const bar = document.getElementById("upsellBar");
    bar.innerHTML = "<div>old</div>";
    bar.classList.remove("d-none");
    state.cart = [];
    await evaluateUpsell();
    expect(bar.classList.contains("d-none")).toBe(true);
    expect(bar.innerHTML).toBe("");
  });

  it("handles network error", async () => {
    mockFetch({
      "/pos/api/promotions/evaluate": () => Promise.reject(new Error("offline")),
    });
    const { state, evaluateUpsell } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await expect(evaluateUpsell()).resolves.toBeUndefined();
    expect(document.getElementById("upsellBar").classList.contains("d-none")).toBe(true);
  });
});

describe("pos/cart.js — addToCart", () => {
  it("increments existing item quantity", async () => {
    const { state, addToCart } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 10, basePrice: 10, qty: 1, discountPercent: 0 }];
    await addToCart({ id: 1, name: "A", price: 10 }, 2);
    expect(state.cart[0].qty).toBe(3);
  });

  it("adds new item with priceForCurrency", async () => {
    const { state, addToCart } = await loadModule();
    const currency = document.getElementById("currency");
    currency.innerHTML = '<option value="EUR">EUR</option>';
    currency.value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    await addToCart({ id: 2, name: "B", price: 100 }, 1);
    expect(state.cart).toHaveLength(1);
    expect(state.cart[0].basePrice).toBe(100);
    expect(state.cart[0].price).toBe(50);
  });
});

describe("pos/cart.js — heldCount", () => {
  it("reads localStorage HOLD_KEY count", async () => {
    const { heldCount } = await loadModule();
    localStorage.setItem("pos_held_carts", JSON.stringify([{ cart: [] }, { cart: [] }]));
    expect(heldCount()).toBe(2);
  });

  it("returns 0 on bad JSON", async () => {
    const { heldCount } = await loadModule();
    localStorage.setItem("pos_held_carts", "not-json");
    expect(heldCount()).toBe(0);
  });
});
