import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../../static/js/pos/payments.js";

function buildDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = "";

  const meta = document.createElement("meta");
  meta.name = "csrf-token";
  meta.content = "tok";
  document.head.appendChild(meta);

  const ids = [
    "posPinModal", "posPinInput", "posPinError", "splitTenderRows", "splitTenderSum",
    "posPayMethod", "refField", "posAlert",
  ];
  for (const id of ids) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }

  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.id = "splitTenderToggle";
  document.body.appendChild(toggle);

  for (const id of ["currency"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }

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

  const pinInput = document.getElementById("posPinInput");
  pinInput.value = "";
  pinInput.focus = vi.fn();
}

function createJQueryMock() {
  const cache = new Map();
  const jq = vi.fn((sel) => {
    if (typeof sel === "function") { sel(); return jq(""); }
    if (!cache.has(sel)) {
      cache.set(sel, {
        modal: vi.fn(),
        on: vi.fn(),
        val: vi.fn((v) => { if (v !== undefined && sel && document.querySelector(sel)) document.querySelector(sel).value = v; return document.querySelector(sel)?.value || ""; }),
        text: vi.fn(),
        html: vi.fn(),
        focus: vi.fn(),
        addClass: vi.fn(),
        removeClass: vi.fn(),
      });
    }
    return cache.get(sel);
  });
  return jq;
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

beforeEach(() => {
  vi.useFakeTimers();
  buildDom();
  mockFetch({});
  window.t = (k) => k;
  window.$ = createJQueryMock();
  Object.defineProperty(globalThis, "crypto", { value: { randomUUID: () => "uuid" }, configurable: true, writable: true });
  vi.resetModules();
});

afterEach(async () => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.clearAllTimers();
  vi.restoreAllMocks();
  await new Promise((r) => setTimeout(r, 0));
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

async function loadModule() {
  return import(MOD_PATH + "?" + Date.now());
}

describe("pos/payments.js — settlePin + requestOverrideToken", () => {
  it("shows modal and resolves with token", async () => {
    const { settlePin, requestOverrideToken } = await loadModule();
    const promise = requestOverrideToken("discount_override");
    vi.runOnlyPendingTimers();
    settlePin("token-123");
    await expect(promise).resolves.toBe("token-123");
    expect(window.$("#posPinModal").modal).toHaveBeenCalledWith("show");
  });

  it("returns null when modal missing", async () => {
    document.getElementById("posPinModal").remove();
    const { requestOverrideToken } = await loadModule();
    await expect(requestOverrideToken("x")).resolves.toBeNull();
  });
});

describe("pos/payments.js — confirmPin", () => {
  it("success hides modal and resolves", async () => {
    mockFetch({
      "/pos/api/authorize-override": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, override_token: "tok-ok" }) }),
    });
    const { confirmPin, requestOverrideToken } = await loadModule();
    document.getElementById("posPinInput").value = "1234";
    const promise = requestOverrideToken("discount_override");
    await confirmPin();
    await expect(promise).resolves.toBe("tok-ok");
    expect(window.$("#posPinModal").modal).toHaveBeenCalledWith("hide");
  });

  it("failure shows error", async () => {
    mockFetch({
      "/pos/api/authorize-override": () =>
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({ error: "bad pin" }) }),
    });
    const { confirmPin } = await loadModule();
    document.getElementById("posPinInput").value = "0000";
    await confirmPin();
    const err = document.getElementById("posPinError");
    expect(err.textContent).toBe("bad pin");
    expect(err.classList.contains("d-none")).toBe(false);
  });

  it("network error shows error", async () => {
    mockFetch({
      "/pos/api/authorize-override": () => Promise.reject(new Error("offline")),
    });
    const { confirmPin } = await loadModule();
    document.getElementById("posPinInput").value = "0000";
    await confirmPin();
    const err = document.getElementById("posPinError");
    expect(err.classList.contains("d-none")).toBe(false);
  });
});

describe("pos/payments.js — postWithOverride", () => {
  it("sends body", async () => {
    const captured = [];
    mockFetch({
      "/test": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) }),
    });
    globalThis.fetch = vi.fn((url, opts) => {
      captured.push({ url, body: JSON.parse(opts.body) });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    });
    const { postWithOverride } = await loadModule();
    const result = await postWithOverride("/test", { amount: 10 }, "x");
    expect(result.r.ok).toBe(true);
    expect(captured[0].body).toEqual({ amount: 10 });
  });

  it("retries with override token on 403", async () => {
    let calls = 0;
    const captured = [];
    globalThis.fetch = vi.fn((url, opts) => {
      calls++;
      captured.push({ url, body: JSON.parse(opts.body) });
      if (calls === 1) {
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ error: "\u062a\u0641\u0648\u064a\u0636" }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
    });
    const { postWithOverride, settlePin } = await loadModule();
    const promise = postWithOverride("/test", { amount: 10 }, "x");
    await vi.advanceTimersByTimeAsync(0);
    settlePin("override-tok");
    const result = await promise;
    expect(result.r.ok).toBe(true);
    expect(captured[1].body.override_token).toBe("override-tok");
  });

  it("returns first response when no token", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ error: "\u062a\u0641\u0648\u064a\u0636" }) })
    );
    const { postWithOverride } = await loadModule();
    document.getElementById("posPinModal").remove();
    const result = await postWithOverride("/test", { amount: 10 }, "x");
    expect(result.r.status).toBe(403);
  });
});

describe("pos/payments.js — needsOverride", () => {
  it("is true only when 403 and error contains authorization word", async () => {
    const { needsOverride } = await loadModule();
    expect(needsOverride({ status: 403 }, { error: "\u062a\u0641\u0648\u064a\u0636 \u0645\u0637\u0644\u0648\u0628" })).toBe(true);
    expect(needsOverride({ status: 401 }, { error: "\u062a\u0641\u0648\u064a\u0636" })).toBe(false);
    expect(needsOverride({ status: 403 }, { error: "forbidden" })).toBe(false);
    expect(needsOverride({ status: 403 }, {})).toBe(false);
  });
});

describe("pos/payments.js — addSplitRow", () => {
  it("creates amount input, method select and remove button with cash default", async () => {
    const { addSplitRow } = await loadModule();
    addSplitRow(50, "");
    const row = document.querySelector("#splitTenderRows .split-row");
    expect(row).not.toBeNull();
    expect(row.querySelector("input.split-amount")).not.toBeNull();
    expect(row.querySelector("select.split-method")).not.toBeNull();
    expect(row.querySelector("button.split-remove")).not.toBeNull();
    expect(row.querySelector("select.split-method").value).toBe("cash");
    expect(row.querySelector("input.split-amount").value).toBe("50");
  });
});

describe("pos/payments.js — readSplitPayments", () => {
  it("returns chunks for valid rows", async () => {
    const { addSplitRow, readSplitPayments } = await loadModule();
    document.getElementById("currency").innerHTML = '<option value="USD" selected>USD</option>';
    addSplitRow(30, "cash");
    addSplitRow(20, "card");
    const chunks = readSplitPayments();
    expect(chunks).toHaveLength(2);
    expect(chunks[0].amount).toBe(30);
    expect(chunks[1].payment_method).toBe("card");
  });

  it("warns and returns null when no rows", async () => {
    const { readSplitPayments } = await loadModule();
    expect(readSplitPayments()).toBeNull();
    expect(document.getElementById("posAlert").textContent).toContain("\u0623\u0636\u0641 \u062f\u0641\u0639\u0629");
  });

  it("warns and returns null when amount is zero", async () => {
    const { addSplitRow, readSplitPayments } = await loadModule();
    addSplitRow(0, "cash");
    expect(readSplitPayments()).toBeNull();
    expect(document.getElementById("posAlert").textContent).toContain("\u0643\u0644 \u062f\u0641\u0639\u0629");
  });
});

describe("pos/payments.js — splitSumRefresh", () => {
  it("sums split-amount inputs", async () => {
    const { addSplitRow, splitSumRefresh } = await loadModule();
    addSplitRow(10, "cash");
    addSplitRow(20.5, "card");
    document.querySelectorAll(".split-amount")[1].value = "15";
    splitSumRefresh();
    expect(document.getElementById("splitTenderSum").textContent).toBe("25.00");
  });
});
