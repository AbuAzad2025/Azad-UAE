import { describe, it, expect, vi, beforeEach } from "vitest";

const MOD_PATH = "../../static/js/pos/offline-catalog.js";

function computeChecksum(body12) {
  const digits = body12.split("").map(Number);
  const evens = digits.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0);
  const odds = digits.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0);
  return (10 - ((evens + 3 * odds) % 10)) % 10;
}

function makeValidCode(body12) {
  return body12 + computeChecksum(body12);
}

function makeMockIDB() {
  const storeMap = {};
  const mockStore = {
    clear: vi.fn(),
    put: vi.fn(),
    createIndex: vi.fn(),
    index: vi.fn((name) => {
      if (!storeMap[name]) {
        storeMap[name] = {
          get: vi.fn(() => {
            const req = { result: null };
            setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
            return req;
          }),
        };
      }
      return storeMap[name];
    }),
  };

  const mockTransaction = {
    objectStore: vi.fn(() => mockStore),
    oncomplete: null,
    onerror: null,
  };

  const mockDB = {
    transaction: vi.fn(() => {
      setTimeout(() => {
        if (mockTransaction.oncomplete) mockTransaction.oncomplete();
      }, 0);
      return mockTransaction;
    }),
  };

  const mockIDB = {
    open: vi.fn(() => {
      const req = {
        result: {
          createObjectStore: vi.fn(() => mockStore),
          transaction: mockDB.transaction,
        },
      };
      setTimeout(() => {
        if (req.onupgradeneeded) req.onupgradeneeded();
        if (req.onsuccess) req.onsuccess();
      }, 0);
      return req;
    }),
  };

  return { mockIDB, mockStore, storeMap, mockTransaction };
}

describe("parseScaleBarcodeLocal", () => {
  let parse;

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import(MOD_PATH);
    parse = mod.parseScaleBarcodeLocal;
  });

  it("returns null for empty or missing code", () => {
    expect(parse(null)).toBeNull();
    expect(parse(undefined)).toBeNull();
    expect(parse("")).toBeNull();
  });

  it("returns null for non-13-digit codes", () => {
    expect(parse("123456789012")).toBeNull();
    expect(parse("12345678901234")).toBeNull();
    expect(parse("12345")).toBeNull();
  });

  it("returns null for codes not starting with 20", () => {
    expect(parse("1012345678901")).toBeNull();
    expect(parse("3012345678901")).toBeNull();
    expect(parse("9912345678901")).toBeNull();
  });

  it("returns null for non-numeric codes", () => {
    expect(parse("20ABCDEFGHIJKL")).toBeNull();
    expect(parse("201234567890A")).toBeNull();
    expect(parse("2012345678901abc")).toBeNull();
  });

  it("returns null when checksum does not match", () => {
    const body = "201234567890";
    const valid = computeChecksum(body);
    for (let d = 0; d <= 9; d++) {
      const code = body + d;
      if (d === valid) {
        expect(parse(code)).not.toBeNull();
      } else {
        expect(parse(code)).toBeNull();
      }
    }
  });

  it("returns null for strings shorter than 13 that start with 20", () => {
    expect(parse("20")).toBeNull();
    expect(parse("2012345")).toBeNull();
  });

  it("returns valid result for all digits matching a correct checksum", () => {
    const body = "209876543210";
    const code = makeValidCode(body);
    expect(code).toHaveLength(13);
    const result = parse(code);
    expect(result).not.toBeNull();
    expect(result.itemCode).toBe(body.slice(2, 7));
  });

  it("returns correct itemCode and weightKg for a known valid code", () => {
    const body = "201234567890";
    const code = makeValidCode(body);
    const result = parse(code);
    expect(result).not.toBeNull();
    expect(result.itemCode).toBe("12345");
    expect(typeof result.weightKg).toBe("number");
    expect(result.weightKg).toBeGreaterThanOrEqual(0);
  });

  it("extracts weight from digits at positions 7-11 and divides by 1000", () => {
    const body = "200000000050";
    const code = makeValidCode(body);
    const result = parse(code);
    expect(result).not.toBeNull();
    expect(result.itemCode).toBe("00000");
    const grams = Number(code.slice(7, 12));
    expect(result.weightKg).toBe(Math.round(grams) / 1000);
  });

  it("rounds weightKg to the nearest gram", () => {
    const body = "201234500000";
    const code = makeValidCode(body);
    const result = parse(code);
    if (result) {
      expect(result.weightKg * 1000).toBe(Math.round(result.weightKg * 1000));
    }
  });

  it("handles leading whitespace in code", () => {
    const body = "201234567890";
    const code = makeValidCode(body);
    expect(parse("  " + code)).not.toBeNull();
  });

  it("handles code passed as a number", () => {
    const body = "201234567890";
    const code = makeValidCode(body);
    expect(parse(Number(code))).not.toBeNull();
  });

  it("returns null for all-invalid checksum endings", () => {
    const body = "301234567890";
    for (let d = 0; d <= 9; d++) {
      expect(parse(body + d)).toBeNull();
    }
  });
});

describe("window.posOfflineCatalog", () => {
  it("is exposed on window with expected methods", async () => {
    vi.resetModules();
    window.posOfflineCatalog = undefined;
    await import(MOD_PATH);
    expect(window.posOfflineCatalog).toBeDefined();
    expect(typeof window.posOfflineCatalog.parseScaleBarcodeLocal).toBe("function");
    expect(typeof window.posOfflineCatalog.lookupLocalProduct).toBe("function");
    expect(typeof window.posOfflineCatalog.hydrateCatalog).toBe("function");
  });
});

describe("module.exports", () => {
  it("exports parseScaleBarcodeLocal", async () => {
    vi.resetModules();
    const mod = await import(MOD_PATH);
    expect(typeof mod.parseScaleBarcodeLocal).toBe("function");
  });
});

describe("lookupLocalProduct", () => {
  let lookup;

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import(MOD_PATH);
    lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
  });

  it("returns null for empty code", async () => {
    expect(await lookup("")).toBeNull();
  });

  it("returns null for whitespace-only code", async () => {
    expect(await lookup("   ")).toBeNull();
  });

  it("returns null when indexedDB is not available", async () => {
    const origIDB = globalThis.indexedDB;
    globalThis.indexedDB = undefined;
    vi.resetModules();
    const mod = await import(MOD_PATH);
    const fn = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    expect(await fn("12345")).toBeNull();
    globalThis.indexedDB = origIDB;
  });
});

describe("lookupLocalProduct with mocked IndexedDB", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("returns null when no match found", async () => {
    const { mockIDB } = makeMockIDB();
    globalThis.indexedDB = mockIDB;

    const mod = await import(MOD_PATH);
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    expect(await lookup("9999999999999")).toBeNull();
    delete globalThis.indexedDB;
  });

  it("returns product with success flag when barcode matches", async () => {
    const { mockIDB, storeMap } = makeMockIDB();
    const mockProduct = { id: 42, name: "Matched", barcode: "abc123", sku: "S1" };
    storeMap.barcode_lc = {
      get: vi.fn(() => {
        const req = { result: mockProduct };
        setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
        return req;
      }),
    };
    globalThis.indexedDB = mockIDB;

    const mod = await import(MOD_PATH);
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    const result = await lookup("abc123");
    expect(result).not.toBeNull();
    expect(result.success).toBe(true);
    expect(result.name).toBe("Matched");
    expect(result.barcode_lc).toBeUndefined();
    expect(result.sku_lc).toBeUndefined();
    delete globalThis.indexedDB;
  });

  it("tries sku_lc index when barcode_lc misses", async () => {
    const { mockIDB, storeMap } = makeMockIDB();
    const mockProduct = { id: 50, name: "SkuMatch", barcode: "xyz", sku: "sku-99" };
    storeMap.barcode_lc = {
      get: vi.fn(() => {
        const req = { result: null };
        setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
        return req;
      }),
    };
    storeMap.sku_lc = {
      get: vi.fn(() => {
        const req = { result: mockProduct };
        setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
        return req;
      }),
    };
    globalThis.indexedDB = mockIDB;

    const mod = await import(MOD_PATH);
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    const result = await lookup("sku-99");
    expect(result).not.toBeNull();
    expect(result.success).toBe(true);
    expect(storeMap.barcode_lc.get).toHaveBeenCalled();
    expect(storeMap.sku_lc.get).toHaveBeenCalled();
    delete globalThis.indexedDB;
  });

  it("tries scale barcode lookup for prefix-20 codes", async () => {
    const body = "201234567890";
    const code = makeValidCode(body);
    const itemCode = code.slice(2, 7);
    const { mockIDB, storeMap } = makeMockIDB();
    const mockProduct = { id: 80, name: "ScaleItem", barcode: itemCode, sku: "" };

    let barcodeCallCount = 0;
    storeMap.barcode_lc = {
      get: vi.fn(() => {
        barcodeCallCount++;
        if (barcodeCallCount <= 2) {
          const req = { result: null };
          setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
          return req;
        }
        const req = { result: mockProduct };
        setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
        return req;
      }),
    };
    storeMap.sku_lc = {
      get: vi.fn(() => {
        const req = { result: null };
        setTimeout(() => { if (req.onsuccess) req.onsuccess(); }, 0);
        return req;
      }),
    };

    globalThis.indexedDB = mockIDB;

    const mod = await import(MOD_PATH);
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    const result = await lookup(code);
    expect(result).not.toBeNull();
    expect(result.is_scale_item).toBe(true);
    expect(result.scale_weight_kg).toBeGreaterThan(0);
    expect(result.success).toBe(true);
    delete globalThis.indexedDB;
  });
});

describe("hydrateCatalog", () => {
  let hydrate;

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import(MOD_PATH);
    hydrate = mod.hydrateCatalog || window.posOfflineCatalog.hydrateCatalog;
  });

  it("returns 0 when fetch fails", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("network error")));
    expect(await hydrate()).toBe(0);
    delete globalThis.fetch;
  });

  it("returns 0 when response is not ok", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );
    expect(await hydrate()).toBe(0);
    delete globalThis.fetch;
  });

  it("returns 0 when response success is false", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) })
    );
    expect(await hydrate()).toBe(0);
    delete globalThis.fetch;
  });

  it("returns 0 when products is not an array", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, products: "nope" }) })
    );
    expect(await hydrate()).toBe(0);
    delete globalThis.fetch;
  });

  it("returns 0 when JSON parsing fails", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.reject(new Error("bad json")) })
    );
    expect(await hydrate()).toBe(0);
    delete globalThis.fetch;
  });

  it("returns product count on success", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            products: [{ id: 1, name: "A" }, { id: 2, name: "B" }],
          }),
      })
    );
    const { mockIDB, mockStore } = makeMockIDB();
    globalThis.indexedDB = mockIDB;

    const count = await hydrate();
    expect(count).toBe(2);
    expect(mockStore.clear).toHaveBeenCalled();
    expect(mockStore.put).toHaveBeenCalledTimes(2);
    delete globalThis.fetch;
    delete globalThis.indexedDB;
  });

  it("passes warehouseParam to URL correctly", async () => {
    let calledUrl = "";
    globalThis.fetch = vi.fn((url) => {
      calledUrl = url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, products: [] }),
      });
    });
    const { mockIDB } = makeMockIDB();
    globalThis.indexedDB = mockIDB;

    await hydrate({ warehouseParam: "&warehouse_id=3" });
    expect(calledUrl).toContain("warehouse_id=3");
    delete globalThis.fetch;
    delete globalThis.indexedDB;
  });

  it("prepends ? when warehouseParam starts with &", async () => {
    let calledUrl = "";
    globalThis.fetch = vi.fn((url) => {
      calledUrl = url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, products: [] }),
      });
    });
    const { mockIDB } = makeMockIDB();
    globalThis.indexedDB = mockIDB;

    await hydrate({ warehouseParam: "&wh=5" });
    expect(calledUrl).toBe("/pos/api/catalog/snapshot?wh=5");
    delete globalThis.fetch;
    delete globalThis.indexedDB;
  });
});

describe("_normalize helper behavior", () => {
  it("adds lowercase barcode_lc and sku_lc fields", async () => {
    vi.resetModules();
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            products: [{ id: 1, name: "Apple", barcode: "ABC123", sku: "SKU-1" }],
          }),
      })
    );
    const { mockIDB, mockStore } = makeMockIDB();
    globalThis.indexedDB = mockIDB;

    const mod = await import(MOD_PATH);
    const hydrate = mod.hydrateCatalog || window.posOfflineCatalog.hydrateCatalog;
    const count = await hydrate();
    expect(count).toBe(1);
    const storedProduct = mockStore.put.mock.calls[0][0];
    expect(storedProduct.barcode_lc).toBe("abc123");
    expect(storedProduct.sku_lc).toBe("sku-1");
    expect(storedProduct.name).toBe("Apple");
    delete globalThis.fetch;
    delete globalThis.indexedDB;
  });
});
