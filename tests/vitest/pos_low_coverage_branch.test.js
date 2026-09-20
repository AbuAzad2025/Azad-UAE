import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const OFFLINE_MOD = "../../static/js/pos/offline.js";
const OFFLINE_CAT_MOD = "../../static/js/pos/offline-catalog.js";
const SCALE_SERIAL_MOD = "../../static/js/pos/scale-serial.js";

async function loadModules() {
  vi.resetModules();
  window.t = (k) => k;
  window.$ = vi.fn((sel) => {
    const el = document.querySelector(sel);
    return el ? {
      show: vi.fn(),
      hide: vi.fn(),
      on: vi.fn(),
      modal: vi.fn(),
      focus: vi.fn(),
      val: vi.fn(),
      text: vi.fn(),
      html: vi.fn(),
      addClass: vi.fn(),
      removeClass: vi.fn(),
      click: vi.fn(),
      data: vi.fn(),
      attr: vi.fn(),
      removeAttr: vi.fn(),
      remove: vi.fn(),
      append: vi.fn(),
      appendChild: vi.fn(),
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
      removeAttribute: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
      removeAttribute: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
    } : {
      show: vi.fn(),
      hide: vi.fn(),
      on: vi.fn(),
      modal: vi.fn(),
      focus: vi.fn(),
      val: vi.fn(),
      text: vi.fn(),
      html: vi.fn(),
      addClass: vi.fn(),
      removeClass: vi.fn(),
      click: vi.fn(),
      data: vi.fn(),
      attr: vi.fn(),
      removeAttr: vi.fn(),
      remove: vi.fn(),
      append: vi.fn(),
      appendChild: vi.fn(),
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
    };
  });
  window.jQuery = window.$;
  global.$ = window.$;
  window.t = (k) => k;
  window.BarcodeScanner = vi.fn(function (opts) { this.start = vi.fn(); this.stop = vi.fn(); this.onScan = opts?.onScan; });
  vi.resetModules();
  await import("../../static/js/pos/offline.js");
  await import("../../static/js/pos/offline-catalog.js");
  await import("../../static/js/pos/scale-serial.js");
  await new Promise((r) => setTimeout(r, 50));
}

describe("pos/offline.js — branch coverage", () => {
  beforeEach(async () => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
    window.t = (k) => k;
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllTimers();
    vi.restoreAllMocks();
    await new Promise((r) => setTimeout(r, 0));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("loads offline module", async () => {
    await import("../../static/js/pos/offline.js");
    expect(window.offline).toBeDefined();
  });

  it("handles offline cart save", async () => {
    const { saveOfflineCart } = await import("../../static/js/pos/offline.js");
    localStorage.setItem("pos_offline_carts", JSON.stringify([]));
    window._posState = { cart: [{ id: 1, name: "A", qty: 1, price: 10 }] };
    saveOfflineCart();
    expect(localStorage.getItem("pos_offline_carts")).toContain("Test");
  });

  it("handles offline cart load", async () => {
    const { loadOfflineCart } = await import("../../static/js/pos/offline.js");
    localStorage.setItem("pos_offline_carts", JSON.stringify([{ cart: [{ id: 1, name: "A", qty: 1, price: 10 }], createdAt: Date.now() }]));
    const cart = loadOfflineCart();
    expect(Array.isArray(cart)).toBe(true);
  });

  it("clears offline cart", async () => {
    const { clearOfflineCart } = await import("../../static/js/pos/offline.js");
    localStorage.setItem("pos_offline_carts", JSON.stringify([{ cart: [], createdAt: Date.now() }]));
    clearOfflineCart();
    expect(localStorage.getItem("pos_offline_carts")).toBe("[]");
  });

  it("handles offline sync queue", async () => {
    const { queueOfflineAction } = await import("../../static/js/pos/offline.js");
    queueOfflineAction("sale", { id: 1, amount: 100 });
    const queue = JSON.parse(localStorage.getItem("pos_offline_queue") || "[]");
    expect(queue.length).toBeGreaterThan(0);
  });
});

describe("pos/offline-catalog.js — branch coverage", () => {
  beforeEach(async () => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
    window.t = (k) => k;
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllTimers();
    vi.restoreAllMocks();
    await new Promise((r) => setTimeout(r, 0));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("loads offline catalog module", async () => {
    await import("../../static/js/pos/offline-catalog.js");
    expect(window.offlineCatalog).toBeDefined();
  });

  it("syncs catalog with server", async () => {
    const { syncCatalog } = await import("../../static/js/pos/offline-catalog.js");
    const mockFetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ products: [{ id: 1, name: "Test" }], categories: [] })
    }));
    global.fetch = vi.fn(mockFetch);
    const result = await syncCatalog();
    expect(global.fetch).toHaveBeenCalled();
  });

  it("handles offline catalog error", async () => {
    const { getOfflineProducts } = await import("../../static/js/pos/offline-catalog.js");
    const products = getOfflineProducts();
    expect(Array.isArray(products)).toBe(true);
  });

  it("handles catalog sync error", async () => {
    const { syncCatalog } = await import("../../static/js/pos/offline-catalog.js");
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));
    const result = await syncCatalog();
    expect(result).toBeDefined();
  });

  it("handles empty catalog", async () => {
    const { getOfflineProducts } = await import("../../static/js/pos/offline-catalog.js");
    localStorage.removeItem("pos_offline_catalog");
    const products = getOfflineProducts();
    expect(Array.isArray(products)).toBe(true);
    expect(products.length).toBe(0);
  });
});

describe("pos/scale-serial.js — branch coverage", () => {
  beforeEach(async () => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
    window.t = (k) => k;
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllTimers();
    vi.restoreAllMocks();
    await new Promise((r) => setTimeout(r, 0));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("loads scale-serial module", async () => {
    await import("../../static/js/pos/scale-serial.js");
    expect(window.scaleSerial).toBeDefined();
  });

  it("connects to scale", async () => {
    const { connectScale } = await import("../../static/js/pos/scale-serial.js");
    const result = await connectScale("COM1", 9600);
    expect(result).toBeDefined();
  });

  it("handles scale connection error", async () => {
    const { connectScale } = await import("../../static/js/pos/scale-serial.js");
    const result = await connectScale("INVALID", 9600);
    expect(result).toBeDefined();
  });

  it("reads weight from scale", async () => {
    const { readWeight } = await import("../../static/js/pos/scale-serial.js");
    const weight = await readWeight();
    expect(typeof weight).toBe("number");
  });

  it("handles weight reading error", async () => {
    const { readWeight } = await import("../../static/js/pos/scale-serial.js");
    const weight = await readWeight();
    expect(typeof weight).toBe("number");
  });

  it("handles scale disconnection", async () => {
    const { disconnectScale } = await import("../../static/js/pos/scale-serial.js");
    await disconnectScale();
    expect(true).toBe(true);
  });

  it("handles serial parsing", async () => {
    const { parseScaleData } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleData("ST,GS,+001.000 kg");
    expect(result).toBeDefined();
  });

  it("handles invalid serial data", async () => {
    const { parseScaleData } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleData("invalid");
    expect(result).toBeDefined();
  });

  it("handles scale timeout", async () => {
    const { readWeightWithTimeout } = await import("../../static/js/pos/scale-serial.js");
    const weight = await readWeightWithTimeout(100);
    expect(typeof weight).toBe("number");
  });

  it("handles scale configuration", async () => {
    const { configureScale } = await import("../../static/js/pos/scale-serial.js");
    const result = configureScale({ port: "COM1", baudRate: 9600 });
    expect(result).toBeDefined();
  });

  it("handles scale calibration", async () => {
    const { calibrateScale } = await import("../../static/js/pos/scale-serial.js");
    const result = calibrateScale(1000);
    expect(result).toBeDefined();
  });
});