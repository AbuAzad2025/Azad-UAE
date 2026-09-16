import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

function flush(ms = 10) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------- pos/core ----------

describe("pos/core.js gaps", () => {
  let origFetch;
  let savedT;
  let hadWindowT;
  let hadGlobalT;

  beforeEach(() => {
    origFetch = global.fetch;
    savedT = window.t;
    hadWindowT = "t" in window;
    hadGlobalT = "t" in globalThis;
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    if (hadWindowT) window.t = savedT;
    else delete window.t;
    if (hadGlobalT) globalThis.t = savedT;
    else delete globalThis.t;
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    vi.resetModules();
  });

  function baseDom() {
    const meta = document.createElement("meta");
    meta.name = "csrf-token";
    meta.content = "tok";
    document.head.appendChild(meta);
  }

  it("falls back to an identity translator without window.t", async () => {
    delete window.t;
    delete globalThis.t;
    baseDom();
    const core = await import("../../static/js/pos/core.js");
    expect(core.t("hello")).toBe("hello");
  });

  it("parses successful JSON envelopes in fetchJson", async () => {
    baseDom();
    global.fetch = vi.fn(() =>
      Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve({ success: true, data: [1] }) })
    );
    window.fetch = global.fetch;
    const core = await import("../../static/js/pos/core.js");
    await expect(core.fetchJson("/x")).resolves.toEqual({ ok: true, data: [1] });
  });
});

// ---------- pos/cart ----------

function buildCartDom({ pricesIncludeVat = "false" } = {}) {
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
  for (const id of ["cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency", "upsellBar"]) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }
  const currency = document.createElement("select");
  currency.id = "currency";
  currency.innerHTML = '<option value="USD">USD</option>';
  currency.value = "USD";
  document.body.appendChild(currency);
  for (const id of ["taxRate", "shippingCost", "discountAmount", "exchangeRate", "paidAmount"]) {
    const el = document.createElement("input");
    el.id = id;
    el.type = "number";
    el.value = "0";
    document.body.appendChild(el);
  }
  const change = document.createElement("div");
  change.id = "kpiChange";
  document.body.appendChild(change);
}

function mockFetch(map) {
  const spy = vi.fn((url) => {
    const u = new URL(url, "http://localhost");
    const handler = map[u.pathname] || map[u.pathname + u.search];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  global.fetch = spy;
  window.fetch = spy;
  return spy;
}

describe("pos/cart.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    buildCartDom();
    mockFetch({});
    window.t = (k) => k;
    window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
    Object.defineProperty(globalThis, "crypto", {
      value: { randomUUID: () => "uuid" },
      configurable: true,
      writable: true,
    });
    vi.resetModules();
  });

  afterEach(async () => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    vi.useRealTimers();
    vi.restoreAllMocks();
    await flush(0);
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    localStorage.clear();
    vi.resetModules();
  });

  async function loadModule() {
    const core = await import("../../static/js/pos/core.js");
    const cart = await import("../../static/js/pos/cart.js");
    return { ...cart, state: core.state };
  }

  it("backfills missing base prices before conversion", async () => {
    const { state, updateCartPrices } = await loadModule();
    document.getElementById("exchangeRate").value = "1";
    state.cart = [{ id: 1, name: "A", price: 20, qty: 1, discountPercent: 0 }];
    await updateCartPrices();
    expect(state.cart[0].basePrice).toBe(20);
  });

  it("updates the change KPI on backend success", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({ success: true, subtotal: 90, discount: 5, total: 100, tax_amount: 15, prices_include_vat: false }),
        }),
    });
    const { state, recalc } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 100, qty: 1, discountPercent: 0 }];
    document.getElementById("paidAmount").value = "150";
    const totals = await recalc();
    expect(totals.total).toBe(100);
    expect(document.getElementById("kpiChange").textContent).toBe("50.00");
  });

  it("evaluates upsell prompts and schedules evaluation", async () => {
    vi.useFakeTimers();
    mockFetch({
      "/pos/api/promotions/evaluate": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, upsell_prompts: [{ message: "deal" }] }),
        }),
    });
    const { state, evaluateUpsell, scheduleUpsellEval } = await loadModule();
    state.cart = [{ id: 1, name: "A", price: 10, qty: 1, discountPercent: 0 }];
    await evaluateUpsell();
    expect(document.getElementById("upsellBar").textContent).toContain("deal");
    scheduleUpsellEval();
    await vi.advanceTimersByTimeAsync(500);
  });
});

// ---------- pos/payments ----------

function buildPayDom(withRows = true) {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  const meta = document.createElement("meta");
  meta.name = "csrf-token";
  meta.content = "tok";
  document.head.appendChild(meta);
  for (const id of ["posPinModal", "posPinInput", "posPinError", "posPayMethod", "refField"]) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }
  if (withRows) {
    const rows = document.createElement("div");
    rows.id = "splitTenderRows";
    document.body.appendChild(rows);
  }
  const sum = document.createElement("div");
  sum.id = "splitTenderSum";
  document.body.appendChild(sum);
  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.id = "splitTenderToggle";
  document.body.appendChild(toggle);
  const currency = document.createElement("select");
  currency.id = "currency";
  document.body.appendChild(currency);
  for (const id of ["exchangeRate"]) {
    const el = document.createElement("input");
    el.id = id;
    el.type = "number";
    el.value = "1";
    document.body.appendChild(el);
  }
  const paySel = document.createElement("select");
  paySel.id = "paymentMethod";
  document.body.appendChild(paySel);
  document.getElementById("posPinInput").value = "";
}

function mockPayJQuery() {
  const jq = (sel) => {
    if (typeof sel === "function") {
      sel();
      return jq("");
    }
    return { modal: vi.fn(), on: vi.fn() };
  };
  window.$ = jq;
  return jq;
}

describe("pos/payments.js gaps", () => {
  let origFetch;
  let origDollar;

  beforeEach(() => {
    origFetch = global.fetch;
    origDollar = window.$;
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    window.$ = origDollar;
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it("shows server-side pin errors from confirmPin", async () => {
    buildPayDom();
    mockPayJQuery();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false, message: "bad pin" }) })
    );
    window.fetch = global.fetch;
    const mod = await import("../../static/js/pos/payments.js");
    document.getElementById("posPinInput").value = "0000";
    await mod.confirmPin();
    expect(document.getElementById("posPinError").textContent).toBe("bad pin");
  });

  it("posts directly when no override is required", async () => {
    buildPayDom();
    mockPayJQuery();
    const spy = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) })
    );
    global.fetch = spy;
    window.fetch = spy;
    const mod = await import("../../static/js/pos/payments.js");
    const { r } = await mod.postWithOverride("/pos/api/x", { a: 1 }, "void");
    expect(r.status).toBe(200);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("ignores split rows without a container", async () => {
    buildPayDom(false);
    mockPayJQuery();
    const mod = await import("../../static/js/pos/payments.js");
    expect(mod.splitEnabled()).toBe(false);
    mod.addSplitRow("5", "cash");
    expect(document.getElementById("splitTenderRows")).toBeNull();
  });

  it("removes split rows via the row button", async () => {
    buildPayDom(true);
    mockPayJQuery();
    const mod = await import("../../static/js/pos/payments.js");
    mod.addSplitRow("7", "cash");
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(1);
    document.querySelector(".split-remove").click();
    expect(document.querySelectorAll("#splitTenderRows .split-row").length).toBe(0);
    expect(document.getElementById("splitTenderSum").textContent).toBe("0.00");
  });
});

// ---------- pos/print-tickets ----------

describe("pos/print-tickets.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    delete window.printSaleTickets;
    delete window.printQueuedCartReceipt;
    delete window.escPosSafe;
    vi.resetModules();
  });

  it("prints an offline queued cart receipt through the agent", async () => {
    const spy = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
    global.fetch = spy;
    window.fetch = spy;
    await import("../../static/js/pos/print-tickets.js");
    const ok = await window.printQueuedCartReceipt(
      [{ qty: 2, name: "Tea", price: 5 }],
      { total: 10 },
      { sale_reference: "OFF-1" }
    );
    expect(ok).toBe(true);
    expect(spy).toHaveBeenCalledWith(
      "http://127.0.0.1:8567/print-receipt",
      expect.objectContaining({ method: "POST" })
    );
  });
});
