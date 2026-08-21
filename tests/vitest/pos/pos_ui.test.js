import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../../static/js/pos/ui.js";

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

  const vat = document.createElement("meta");
  vat.name = "pos-prices-include-vat";
  vat.content = "false";
  document.head.appendChild(vat);

  const ids = [
    "posAlert", "posCategories", "posProductGrid", "posFloors", "posTablesGrid",
    "productResults", "productLoading", "productSearch", "customerSelectedHint",
  ];
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

  for (const id of ["exchangeRate"]) {
    const el = document.createElement("input");
    el.id = id;
    el.type = "number";
    el.value = "1";
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
  return import(MOD_PATH + "?" + Date.now());
}

describe("pos/ui.js — showAlert", () => {
  it("sets text, level class and auto-hides after timeout", async () => {
    const { showAlert } = await loadModule();
    vi.useFakeTimers();
    const el = document.getElementById("posAlert");
    showAlert("\u062a\u0645", "success");
    expect(el.textContent).toBe("\u062a\u0645");
    expect(el.classList.contains("alert-success")).toBe(true);
    expect(el.classList.contains("d-none")).toBe(false);
    await vi.advanceTimersByTimeAsync(5000);
    expect(el.classList.contains("d-none")).toBe(true);
  });
});

describe("pos/ui.js — showModalAlert", () => {
  it("writes to modal alert element", async () => {
    const modalAlert = document.createElement("div");
    modalAlert.id = "posPinAlert";
    document.body.appendChild(modalAlert);
    const { showModalAlert } = await loadModule();
    showModalAlert("posPin", "\u062e\u0637\u0623", "warning");
    expect(modalAlert.textContent).toBe("\u062e\u0637\u0623");
    expect(modalAlert.classList.contains("alert-warning")).toBe(true);
  });

  it("falls back to showAlert when modal element missing", async () => {
    const { showModalAlert } = await loadModule();
    showModalAlert("missing", "\u0646\u0635", "danger");
    const el = document.getElementById("posAlert");
    expect(el.textContent).toBe("\u0646\u0635");
    expect(el.classList.contains("alert-danger")).toBe(true);
  });
});

describe("pos/ui.js — loadCategories", () => {
  it("fetches categories and renders chips including All", async () => {
    mockFetch({
      "/pos/api/categories": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "Food", name_ar: "\u0637\u0639\u0627\u0645" }]) }),
    });
    const { loadCategories } = await loadModule();
    await loadCategories();
    const box = document.getElementById("posCategories");
    expect(box.textContent).toContain("\u0627\u0644\u0643\u0644");
    expect(box.textContent).toContain("\u0637\u0639\u0627\u0645");
  });
});

describe("pos/ui.js — loadProducts", () => {
  it("renders product cards", async () => {
    mockFetch({
      "/pos/api/products?per_page=60": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "Burger", name_ar: "\u0628\u0631\u062c\u0631", price: 25, stock: 10, is_out_of_stock: false, is_inactive: false }]) }),
    });
    const { loadProducts } = await loadModule();
    await loadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("Burger");
  });

  it("shows empty state", async () => {
    mockFetch({
      "/pos/api/products?per_page=60": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    });
    const { loadProducts } = await loadModule();
    await loadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("\u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u0646\u062a\u062c\u0627\u062a");
  });

  it("shows loading state initially", async () => {
    mockFetch({
      "/pos/api/products?per_page=60": () => new Promise(() => {}),
    });
    const { loadProducts } = await loadModule();
    const promise = loadProducts("");
    expect(document.getElementById("posProductGrid").textContent).toContain("\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u062d\u0645\u064a\u0644");
    await Promise.race([promise, new Promise((r) => setTimeout(r, 10))]);
  });

  it("renders out-of-stock and inactive badges", async () => {
    mockFetch({
      "/pos/api/products?per_page=60": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([
            { id: 1, name: "A", price: 10, stock: 0, is_out_of_stock: true, is_inactive: false },
            { id: 2, name: "B", price: 10, stock: 5, is_out_of_stock: false, is_inactive: true },
          ]),
        }),
    });
    const { loadProducts } = await loadModule();
    await loadProducts("");
    const grid = document.getElementById("posProductGrid").innerHTML;
    expect(grid).toContain("\u0646\u0641\u062f");
    expect(grid).toContain("\u063a\u064a\u0631 \u0646\u0634\u0637");
  });
});

describe("pos/ui.js — loadFloors", () => {
  it("renders floors", async () => {
    mockFetch({
      "/pos/api/floors": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, name: "Ground", name_ar: "\u0623\u0631\u0636\u064a" }]) }),
    });
    const { loadFloors } = await loadModule();
    await loadFloors();
    expect(document.getElementById("posFloors").textContent).toContain("\u0623\u0631\u0636\u064a");
  });

  it("shows empty state", async () => {
    mockFetch({
      "/pos/api/floors": () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    });
    const { loadFloors } = await loadModule();
    await loadFloors();
    expect(document.getElementById("posFloors").textContent).toContain("\u0644\u0627 \u062a\u0648\u062c\u062f \u0623\u0631\u0636\u064a\u0627\u062a");
  });
});

describe("pos/ui.js — loadTables", () => {
  it("renders tables with status", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, label: "T1", status: "occupied" }]) }),
    });
    const { loadTables } = await loadModule();
    await loadTables("1");
    const grid = document.getElementById("posTablesGrid").innerHTML;
    expect(grid).toContain("T1");
    expect(grid).toContain("occupied");
  });

  it("shows error state on fetch failure", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    });
    const { loadTables } = await loadModule();
    await loadTables("1");
    expect(document.getElementById("posTablesGrid").textContent).toContain("\u062a\u0639\u0630\u0631 \u0627\u0644\u062a\u062d\u0645\u064a\u0644");
  });
});

describe("pos/ui.js — runProductSearch", () => {
  it("fetches products with warehouse param", async () => {
    const warehouse = document.createElement("select");
    warehouse.id = "warehouseId";
    warehouse.innerHTML = '<option value="3">W3</option>';
    warehouse.value = "3";
    document.body.appendChild(warehouse);

    globalThis.fetch = vi.fn((url) => {
      if (url.includes("/pos/api/products?q=foo")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: 1, text: "Foo", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false }]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
    });
    const { runProductSearch } = await loadModule();
    await runProductSearch("foo");
    expect(document.getElementById("productResults").textContent).toContain("Foo");
  });

  it("hides results when query empty", async () => {
    const { runProductSearch } = await loadModule();
    document.getElementById("productResults").classList.remove("d-none");
    await runProductSearch("");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);
  });
});

describe("pos/ui.js — renderProductResults", () => {
  it("renders result buttons with price and stock", async () => {
    const { renderProductResults } = await loadModule();
    renderProductResults([{ id: 1, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false }]);
    const box = document.getElementById("productResults").innerHTML;
    expect(box).toContain("Apple");
    expect(box).toContain("5.00");
    expect(box).toContain("10.00");
  });

  it("shows inactive warning", async () => {
    const { renderProductResults } = await loadModule();
    renderProductResults([{ id: 1, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: true }]);
    const box = document.getElementById("productResults").innerHTML;
    expect(box).toContain("\u063a\u064a\u0631 \u0646\u0634\u0637");
  });
});
