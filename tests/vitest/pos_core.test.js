import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/pos/core.js";

function buildDom({ baseCurrency = "USD", symbol = "$" } = {}) {
  document.head.innerHTML = "";
  document.body.innerHTML = "";

  const csrf = document.createElement("meta");
  csrf.name = "csrf-token";
  csrf.content = "test-csrf";
  document.head.appendChild(csrf);

  const base = document.createElement("meta");
  base.name = "pos-base-currency";
  base.content = baseCurrency;
  document.head.appendChild(base);

  const vat = document.createElement("meta");
  vat.name = "pos-prices-include-vat";
  vat.content = "false";
  document.head.appendChild(vat);

  const sym = document.createElement("meta");
  sym.name = "pos-currency-symbol";
  sym.content = symbol;
  document.head.appendChild(sym);

  const currency = document.createElement("select");
  currency.id = "currency";
  document.body.appendChild(currency);

  const rate = document.createElement("input");
  rate.id = "exchangeRate";
  rate.type = "number";
  rate.value = "1";
  document.body.appendChild(rate);

  const warehouse = document.createElement("select");
  warehouse.id = "warehouseId";
  document.body.appendChild(warehouse);

  const fixture = document.createElement("div");
  fixture.id = "fixture";
  fixture.innerHTML = '<span class="item">a</span><span class="item">b</span>';
  document.body.appendChild(fixture);

  window.t = (k) => k;
}

beforeEach(() => {
  buildDom();
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
  document.head.innerHTML = "";
  document.body.innerHTML = "";
});

async function loadModule() {
  return import(MOD_PATH + "?" + Date.now());
}

describe("pos/core.js — formatting helpers", () => {
  it("fmt returns a fixed 2-decimal string", async () => {
    const { fmt } = await loadModule();
    expect(fmt(1)).toBe("1.00");
    expect(fmt(1.5)).toBe("1.50");
    expect(fmt("3.555")).toBe("3.56");
    expect(fmt(null)).toBe("0.00");
    expect(fmt(undefined)).toBe("0.00");
  });

  it("toNum coerces values to finite numbers", async () => {
    const { toNum } = await loadModule();
    expect(toNum("2.5")).toBe(2.5);
    expect(toNum(42)).toBe(42);
    expect(toNum("not-a-number")).toBe(0);
    expect(toNum(null)).toBe(0);
    expect(toNum(undefined)).toBe(0);
    expect(toNum(Infinity)).toBe(0);
  });

  it("esc escapes HTML entities", async () => {
    const { esc } = await loadModule();
    expect(esc('<script>alert("x")</script>')).toBe(
      "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    );
    expect(esc(null)).toBe("");
    expect(esc(undefined)).toBe("");
  });
});

describe("pos/core.js — currency helpers", () => {
  it("exports the currency symbol map", async () => {
    const { CURRENCY_SYMBOLS } = await loadModule();
    expect(CURRENCY_SYMBOLS.USD).toBe("$");
    expect(CURRENCY_SYMBOLS.ILS).toBe("₪");
  });

  it("currencySymbolFor returns the symbol or falls back to code", async () => {
    const { currencySymbolFor } = await loadModule();
    expect(currencySymbolFor("USD")).toBe("$");
    expect(currencySymbolFor("EUR")).toBe("€");
    expect(currencySymbolFor("UNKNOWN")).toBe("UNKNOWN");
  });

  it("reads base currency from meta tag", async () => {
    const { baseCurrency } = await loadModule();
    expect(baseCurrency).toBe("USD");
  });

  it("reads base currency from fallback global", async () => {
    document.head.innerHTML = "";
    window._FX_FALLBACK_BASE = "AED";
    const { baseCurrency } = await loadModule();
    expect(baseCurrency).toBe("AED");
    delete window._FX_FALLBACK_BASE;
  });

  it("selectedCurrency returns the currency input value or baseCurrency", async () => {
    const { selectedCurrency } = await loadModule();
    expect(selectedCurrency()).toBe("USD");
    document.getElementById("currency").innerHTML = '<option value="EUR" selected>EUR</option>';
    expect(selectedCurrency()).toBe("EUR");
  });

  it("currentRate returns the exchange rate input as a number", async () => {
    const { currentRate } = await loadModule();
    expect(currentRate()).toBe(1);
    document.getElementById("exchangeRate").value = "3.67";
    expect(currentRate()).toBe(3.67);
  });

  it("priceForCurrency converts when currency differs", async () => {
    const { priceForCurrency } = await loadModule();
    document.getElementById("currency").innerHTML = '<option value="EUR" selected>EUR</option>';
    document.getElementById("exchangeRate").value = "2";
    expect(priceForCurrency(100)).toBe(50);
  });

  it("priceForCurrency returns base price when currency matches", async () => {
    const { priceForCurrency } = await loadModule();
    expect(priceForCurrency(100)).toBe(100);
  });

  it("tenant pos symbol overrides the base currency symbol", async () => {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    const base = document.createElement("meta");
    base.name = "pos-base-currency";
    base.content = "USD";
    document.head.appendChild(base);
    const sym = document.createElement("meta");
    sym.name = "pos-currency-symbol";
    sym.content = "US$";
    document.head.appendChild(sym);
    window.t = (k) => k;
    const { currencySymbolFor } = await import(MOD_PATH + "?" + Date.now());
    expect(currencySymbolFor("USD")).toBe("US$");
  });
});

describe("pos/core.js — DOM helpers", () => {
  it("qs wraps querySelector", async () => {
    const { qs } = await loadModule();
    expect(qs("#fixture")).toBe(document.getElementById("fixture"));
    expect(qs(".missing")).toBeNull();
  });

  it("qsa returns an array of matched elements", async () => {
    const { qsa } = await loadModule();
    const items = qsa(".item", document.getElementById("fixture"));
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("a");
  });

  it("warehouseParam returns an empty string when no warehouse is selected", async () => {
    const { warehouseParam } = await loadModule();
    expect(warehouseParam()).toBe("");
    expect(warehouseParam("?")).toBe("");
  });

  it("warehouseParam returns a query segment when a warehouse is selected", async () => {
    const { warehouseParam } = await loadModule();
    document.getElementById("warehouseId").innerHTML = '<option value="7" selected>7</option>';
    expect(warehouseParam()).toBe("&warehouse_id=7");
    expect(warehouseParam("?")).toBe("?warehouse_id=7");
  });

  it("csrf reads the meta tag value", async () => {
    const { csrf } = await loadModule();
    expect(csrf).toBe("test-csrf");
  });
});

describe("pos/core.js — state and ids", () => {
  it("exports a shared state object", async () => {
    const { state } = await loadModule();
    expect(Array.isArray(state.cart)).toBe(true);
    expect(state.customer).toBeNull();
    expect(typeof state.idemKey).toBe("string");
  });

  it("newCartKey uses crypto.randomUUID when available", async () => {
    Object.defineProperty(globalThis, "crypto", {
      value: { randomUUID: () => "uuid-123" },
      configurable: true,
      writable: true,
    });
    const { newCartKey } = await loadModule();
    expect(newCartKey()).toBe("uuid-123");
  });

  it("newCartKey falls back when randomUUID is unavailable", async () => {
    Object.defineProperty(globalThis, "crypto", {
      value: {},
      configurable: true,
      writable: true,
    });
    const { newCartKey } = await loadModule();
    const key = newCartKey();
    expect(key.startsWith("k-")).toBe(true);
  });
});

describe("pos/core.js — fetchJson", () => {
  it("returns ok:true with JSON data on success", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) })
    );
    const { fetchJson } = await loadModule();
    const result = await fetchJson("/api/test");
    expect(result.ok).toBe(true);
    expect(result.data).toEqual({ items: [] });
  });

  it("returns a friendly error on 404", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ error: "missing" }),
      })
    );
    const { fetchJson } = await loadModule();
    const result = await fetchJson("/api/missing");
    expect(result.ok).toBe(false);
    expect(result.error).toBe("missing");
  });

  it("returns HTTP status when error body is empty", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );
    const { fetchJson } = await loadModule();
    const result = await fetchJson("/api/fail");
    expect(result.ok).toBe(false);
    expect(result.error).toBe("HTTP 500");
  });
});
