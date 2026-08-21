import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../../static/js/pos/offline-sync.js";

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

  const ids = ["productSearch", "productResults", "cartBody", "cartCount", "posAlert", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency"];
  for (const id of ids) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }

  for (const id of ["currency", "warehouseId"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }

  for (const id of ["exchangeRate", "taxRate", "shippingCost", "discountAmount"]) {
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
  buildDom();
  mockFetch({});
  window.t = (k) => k;
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
  window.posOfflineCatalog = { hydrateCatalog: vi.fn(), lookupLocalProduct: vi.fn() };
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
});

async function loadModule() {
  const core = await import("../../../static/js/pos/core.js");
  const sync = await import(MOD_PATH);
  return { ...sync, state: core.state };
}

describe("pos/offline-sync.js — handleScannedCode", () => {
  it("fetches product online", async () => {
    mockFetch({
      "/pos/api/product?code=abc": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 1, name: "Apple", price: 5 }) }),
    });
    const { state, handleScannedCode } = await loadModule();
    await handleScannedCode("abc");
    expect(state.cart).toHaveLength(1);
    expect(state.cart[0].name).toBe("Apple");
  });

  it("falls back to offline catalog", async () => {
    mockFetch({
      "/pos/api/product?code=abc": () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) }),
    });
    window.posOfflineCatalog = {
      lookupLocalProduct: vi.fn(() => Promise.resolve({ id: 2, name: "Offline", price: 10 })),
    };
    const { state, handleScannedCode } = await loadModule();
    await handleScannedCode("abc");
    expect(window.posOfflineCatalog.lookupLocalProduct).toHaveBeenCalledWith("abc");
    expect(state.cart).toHaveLength(1);
    expect(state.cart[0].name).toBe("Offline");
  });

  it("shows inactive warning", async () => {
    mockFetch({
      "/pos/api/product?code=abc": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 1, name: "Apple", price: 5, is_inactive: true, warning: "\u0645\u0646\u062a\u062c \u0645\u0639\u0637\u0644" }),
        }),
    });
    const { handleScannedCode } = await loadModule();
    await handleScannedCode("abc");
    expect(document.getElementById("posAlert").textContent).toContain("\u0645\u0646\u062a\u062c \u0645\u0639\u0637\u0644");
  });

  it("uses state.scaleWeightKg for weight products", async () => {
    mockFetch({
      "/pos/api/product?code=abc": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 1, name: "Apple", price: 5, is_weight_product: true }) }),
    });
    const { state, handleScannedCode } = await loadModule();
    state.scaleWeightKg = 2.5;
    await handleScannedCode("abc");
    expect(state.cart[0].qty).toBe(2.5);
  });

  it("shows success alert", async () => {
    mockFetch({
      "/pos/api/product?code=abc": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 1, name: "Apple", price: 5 }) }),
    });
    const { handleScannedCode } = await loadModule();
    await handleScannedCode("abc");
    expect(document.getElementById("posAlert").textContent).toContain("\u062a\u0645\u062a \u0625\u0636\u0627\u0641\u0629");
  });
});

describe("pos/offline-sync.js — setupDevices", () => {
  it("starts BarcodeScanner", async () => {
    const start = vi.fn();
    window.BarcodeScanner = vi.fn(function () { this.start = start; this.stop = vi.fn(); });
    const { setupDevices } = await loadModule();
    setupDevices();
    expect(window.BarcodeScanner).toHaveBeenCalled();
    expect(start).toHaveBeenCalled();
  });

  it("wires camera scan UI", async () => {
    window.BarcodeScanner = vi.fn(function () { this.start = vi.fn(); this.stop = vi.fn(); });
    window.setupCameraScanUI = vi.fn();
    const cameraBtn = document.createElement("button");
    cameraBtn.id = "cameraScanBtn";
    document.body.appendChild(cameraBtn);
    const { setupDevices } = await loadModule();
    setupDevices();
    expect(window.setupCameraScanUI).toHaveBeenCalled();
    const args = window.setupCameraScanUI.mock.calls[0][0];
    expect(args.button).toBe(cameraBtn);
  });

  it("wires scale UI", async () => {
    window.BarcodeScanner = vi.fn(function () { this.start = vi.fn(); this.stop = vi.fn(); });
    const onStableWeight = vi.fn();
    window.PosScaleSerial = vi.fn(function (opts) { this.connect = vi.fn(); onStableWeight.push = opts.onStableWeight; });
    window.setupPosScaleUI = vi.fn();
    const scaleBtn = document.createElement("button");
    scaleBtn.id = "scaleConnectBtn";
    document.body.appendChild(scaleBtn);
    const { setupDevices } = await loadModule();
    setupDevices();
    expect(window.setupPosScaleUI).toHaveBeenCalled();
  });

  it("hydrates offline catalog and registers online listener", async () => {
    window.BarcodeScanner = vi.fn(function () { this.start = vi.fn(); this.stop = vi.fn(); });
    const hydrate = vi.fn();
    window.posOfflineCatalog = { hydrateCatalog: hydrate };
    const addListener = vi.spyOn(window, "addEventListener");
    const { setupDevices } = await loadModule();
    setupDevices();
    expect(hydrate).toHaveBeenCalled();
    expect(addListener).toHaveBeenCalledWith("online", expect.any(Function));
  });

  it("does not register online listener when offline catalog missing", async () => {
    window.BarcodeScanner = vi.fn(function () { this.start = vi.fn(); this.stop = vi.fn(); });
    delete window.posOfflineCatalog;
    const addListener = vi.spyOn(window, "addEventListener");
    const { setupDevices } = await loadModule();
    setupDevices();
    const onlineCalls = addListener.mock.calls.filter(([name]) => name === "online");
    expect(onlineCalls).toHaveLength(0);
  });
});
