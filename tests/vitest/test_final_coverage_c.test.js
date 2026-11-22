import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// cart.js is a side-effectful dependency (it renders the cart and fires network
// requests). Stubbing addToCart lets these tests assert that ui/offline-sync
// actually call it without dragging the whole cart render pipeline in.
vi.mock("../../static/js/pos/cart.js", () => ({
  addToCart: vi.fn(async () => true),
}));

const UI = "../../static/js/pos/ui.js";
const CORE = "../../static/js/pos/core.js";
const TERMINAL = "../../static/js/pos/terminal.js";
const OFFLINE = "../../static/js/pos/offline-sync.js";

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: () => Promise.resolve(body) };
}
function flush(ms = 0) {
  return new Promise((r) => setTimeout(r, ms));
}
function setFetch(spy) {
  global.fetch = spy;
  window.fetch = spy;
  return spy;
}
function routeFetch(map) {
  return setFetch(
    vi.fn((url) => {
      const u = String(url);
      const key = Object.keys(map).find((k) => u.includes(k));
      return key ? map[key](u) : Promise.resolve(jsonResponse({}));
    }),
  );
}
function keydown(key) {
  return new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
}
function addEl(tag, id, props = {}) {
  const el = document.createElement(tag);
  el.id = id;
  for (const [k, v] of Object.entries(props)) el[k] = v;
  document.body.appendChild(el);
  return el;
}

/* ================================================================== *
 *  static/js/pos/ui.js
 * ================================================================== */
describe("pos/ui.js — final coverage", () => {
  let addToCart;

  function buildDom() {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    const meta = (name, content) => {
      const m = document.createElement("meta");
      m.name = name;
      m.content = content;
      document.head.appendChild(m);
    };
    meta("csrf-token", "tok");
    meta("pos-base-currency", "ILS");
    meta("pos-prices-include-vat", "false");

    const currency = addEl("select", "currency");
    currency.innerHTML = '<option value="ILS">ILS</option>';
    currency.value = "ILS";
    addEl("input", "exchangeRate", { value: "1" });
    addEl("input", "warehouseId", { value: "" });
    addEl("input", "productSearch");
    addEl("div", "productResults");
    addEl("div", "productLoading");
    addEl("div", "posAlert");
    addEl("div", "customerSelectedHint");
    const orderType = addEl("select", "orderType");
    orderType.innerHTML =
      '<option value="dine_in">dine_in</option><option value="table_12">table_12</option><option value="takeaway">takeaway</option>';
    addEl("div", "tableField");
    addEl("select", "tableSelect");
    addEl("div", "posCategories");
    addEl("div", "posProductGrid");
    addEl("div", "posFloors");
    addEl("div", "posTablesGrid");
    addEl("div", "posTableSelected");
    addEl("div", "posTablesBtn");
    addEl("div", "barcodeSecondary");
  }

  beforeEach(async () => {
    vi.resetModules();
    buildDom();
    setFetch(vi.fn(() => Promise.resolve(jsonResponse({}))));
    const cart = await import("../../static/js/pos/cart.js");
    addToCart = cart.addToCart;
    addToCart.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllTimers();
    document.head.innerHTML = "";
    document.body.innerHTML = "";
  });

  async function load() {
    const ui = await import(UI);
    const core = await import(CORE);
    return { ...ui, state: core.state };
  }

  it("showAlert: role/class/level and timer callback; pos:alert event", async () => {
    vi.useFakeTimers();
    const { showAlert } = await load();
    const el = document.getElementById("posAlert");

    showAlert("boom", "danger");
    expect(el.textContent).toBe("boom");
    expect(el.className).toBe("alert alert-danger");
    expect(el.getAttribute("role")).toBe("alert");
    await vi.advanceTimersByTimeAsync(15000);
    expect(el.classList.contains("d-none")).toBe(true);

    showAlert("yay", "success");
    expect(el.getAttribute("role")).toBe("status");
    await vi.advanceTimersByTimeAsync(4000);

    showAlert("info", "info");
    await vi.advanceTimersByTimeAsync(5000);

    window.dispatchEvent(
      new CustomEvent("pos:alert", { detail: { msg: "evt", level: "warning" } }),
    );
    expect(el.textContent).toBe("evt");
    expect(el.className).toBe("alert alert-warning");
    vi.useRealTimers();
  });

  it("showModalAlert/hideModalAlert: element, fallback and timer", async () => {
    vi.useFakeTimers();
    const { showModalAlert, hideModalAlert } = await load();
    const modalAlert = addEl("div", "demoAlert");

    showModalAlert("demo", "msg", "warning");
    expect(modalAlert.textContent).toBe("msg");
    expect(modalAlert.className).toBe("alert alert-warning mb-3");
    hideModalAlert("demo");
    expect(modalAlert.classList.contains("d-none")).toBe(true);
    await vi.advanceTimersByTimeAsync(6000);

    showModalAlert("absent", "fallback", "danger");
    expect(document.getElementById("posAlert").textContent).toBe("fallback");
    hideModalAlert("absent");
    vi.useRealTimers();
  });

  it("customerHint: selected, unselected and missing element", async () => {
    const { customerHint, state } = await load();
    const hint = document.getElementById("customerSelectedHint");
    customerHint();
    expect(hint.textContent).toContain("لم يتم اختيار عميل بعد");
    expect(hint.className).toBe("text-muted mt-2 small");

    state.customer = { text: "Acme" };
    customerHint();
    expect(hint.textContent).toContain("Acme");
    expect(hint.className).toBe("text-success mt-2");

    hint.remove();
    expect(() => customerHint()).not.toThrow();
  });

  it("loadOrderTypes: default_code, first-type fallback, success=false, missing select, throw", async () => {
    routeFetch({
      "/pos/api/order-types": () =>
        Promise.resolve(
          jsonResponse({
            success: true,
            data: {
              order_types: [
                { code: "dine_in", display_name: "Dine In" },
                { code: "takeaway", name_ar: "سفري" },
              ],
              default_code: "takeaway",
            },
          }),
        ),
      "/pos/api/tables": () =>
        Promise.resolve(jsonResponse({ data: [{ id: 7, label: "T7", floor_name: "Ground" }] })),
    });
    const { loadOrderTypes } = await load();
    await loadOrderTypes();
    const sel = document.getElementById("orderType");
    expect(sel.options).toHaveLength(2);
    expect(sel.options[0].textContent).toBe("Dine In");
    expect(sel.options[1].textContent).toBe("سفري");
    expect(sel.value).toBe("takeaway");
    expect(document.getElementById("tableField").classList.contains("d-none")).toBe(true);

    // no default_code -> first option selected; "dine" -> table field visible
    routeFetch({
      "/pos/api/order-types": () =>
        Promise.resolve(
          jsonResponse({
            success: true,
            order_types: [{ code: "dine_in", name_ar: "داخل" }],
          }),
        ),
      "/pos/api/tables": () => Promise.resolve(jsonResponse([{ id: 9, label: "T9" }])),
    });
    await loadOrderTypes();
    await flush(); // toggleTableField -> loadTableOptions is fire-and-forget
    expect(sel.value).toBe("dine_in");
    expect(document.getElementById("tableField").classList.contains("d-none")).toBe(false);
    expect(document.getElementById("tableSelect").options).toHaveLength(1);

    // envelope.success === false returns early
    routeFetch({
      "/pos/api/order-types": () => Promise.resolve(jsonResponse({ success: false })),
    });
    await loadOrderTypes();

    // r.json() rejecting is swallowed by the .catch(() => ({}))
    setFetch(
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error("bad json")) }),
      ),
    );
    await loadOrderTypes();

    // missing select returns early
    sel.remove();
    await loadOrderTypes();

    // fetch rejects -> swallow
    setFetch(vi.fn(() => Promise.reject(new Error("offline"))));
    await expect(loadOrderTypes()).resolves.toBeUndefined();
  });

  it("toggleTableField: missing nodes, table/dine codes and plain codes", async () => {
    const { toggleTableField } = await load();
    const sel = document.getElementById("orderType");
    const tableField = document.getElementById("tableField");

    sel.value = "dine_in";
    routeFetch({ "/pos/api/tables": () => Promise.resolve(jsonResponse([])) });
    toggleTableField();
    expect(tableField.classList.contains("d-none")).toBe(false);

    sel.value = "table_12";
    toggleTableField();
    expect(tableField.classList.contains("d-none")).toBe(false);

    sel.value = "takeaway";
    toggleTableField();
    expect(tableField.classList.contains("d-none")).toBe(true);

    tableField.remove();
    expect(() => toggleTableField()).not.toThrow();
  });

  it("loadTableOptions: already-loaded guard and floor labels", async () => {
    const sel = document.getElementById("tableSelect");
    const { loadTableOptions } = await load();
    routeFetch({
      "/pos/api/tables": () =>
        Promise.resolve(
          jsonResponse({ tables: [{ id: 1, label: "A", floor_name: "1st" }, { id: 2, label: "B" }] }),
        ),
    });
    await loadTableOptions();
    expect(sel.options).toHaveLength(2);
    expect(sel.options[0].textContent).toBe("A — 1st");
    expect(sel.options[1].textContent).toBe("B");
    expect(sel.dataset.loaded).toBe("1");

    const fetchSpy = global.fetch;
    await loadTableOptions();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // a rejected r.json() is swallowed and leaves the select untouched
    delete sel.dataset.loaded;
    setFetch(
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error("bad json")) }),
      ),
    );
    await loadTableOptions();

    sel.remove();
    await expect(loadTableOptions()).resolves.toBeUndefined();
  });

  it("renderProductResults: badges, inactive click and active click", async () => {
    const { renderProductResults, state } = await load();
    const box = document.getElementById("productResults");
    const products = [
      { id: 1, text: "Out", price: 5, stock: 0, is_out_of_stock: true, is_inactive: false },
      { id: 2, text: "Old", price: 5, stock: 3, is_out_of_stock: false, is_inactive: true },
      { id: 3, text: "Apple", price: 5, stock: 10, is_out_of_stock: false, is_inactive: false },
    ];
    renderProductResults(products);
    expect(state.lastProductResults).toBe(products);
    expect(box.querySelectorAll("button")).toHaveLength(3);
    expect(box.innerHTML).toContain("نفد");

    const buttons = box.querySelectorAll("button");
    // The result handler only blocks inactive products; an out-of-stock
    // result is still passed to addToCart (which validates availability).
    buttons[0].click();
    await flush();
    expect(addToCart).toHaveBeenCalledWith(products[0]);

    buttons[1].click();
    await flush();
    expect(document.getElementById("posAlert").textContent).toContain("المنتج غير نشط");
    expect(addToCart).toHaveBeenCalledTimes(1);

    document.getElementById("productSearch").value = "typed";
    buttons[2].click();
    await flush();
    expect(addToCart).toHaveBeenCalledWith(products[2]);
    expect(document.getElementById("productSearch").value).toBe("");
    expect(box.classList.contains("d-none")).toBe(true);

    renderProductResults(null);
    expect(box.classList.contains("d-none")).toBe(true);
  });

  it("addFirstOrLookup: empty q, first-result match and lookup miss", async () => {
    const { addFirstOrLookup, state } = await load();
    await expect(addFirstOrLookup("")).resolves.toBeUndefined();

    const first = { id: 1, text: "Apple", barcode: "123", price: 5 };
    state.lastProductResults = [first];
    await addFirstOrLookup("123");
    expect(addToCart).toHaveBeenCalledWith(first);
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);

    addToCart.mockClear();
    state.lastProductResults = [];
    routeFetch({ "/pos/api/product": () => Promise.resolve(jsonResponse({ success: false, message: "missing" })) });
    await addFirstOrLookup("zzz");
    expect(document.getElementById("posAlert").textContent).toContain("missing");
    expect(addToCart).not.toHaveBeenCalled();
  });

  it("addFirstOrLookup: failed lookup falls back to last result", async () => {
    const { addFirstOrLookup, state } = await load();
    const fallback = { id: 2, text: "Fallback", price: 5 };
    state.lastProductResults = [fallback];
    routeFetch({ "/pos/api/product": () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) }) });
    await addFirstOrLookup("unknown");
    expect(addToCart).toHaveBeenCalledWith(fallback);
    expect(document.getElementById("productSearch").value).toBe("");
  });

  it("addFirstOrLookup: inactive, warning, normal and missing id", async () => {
    const { addFirstOrLookup } = await load();
    const product = (extra) => ({ id: 3, text: "X", price: 5, ...extra });
    const respond = (data) =>
      setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: true, data }))));

    respond(product({ is_inactive: true, warning: "disabled!" }));
    await addFirstOrLookup("X");
    expect(document.getElementById("posAlert").textContent).toBe("disabled!");
    expect(addToCart).not.toHaveBeenCalled();

    respond(product({ warning: "low stock" }));
    await addFirstOrLookup("X");
    expect(document.getElementById("posAlert").textContent).toBe("low stock");
    expect(addToCart).toHaveBeenCalledTimes(1);

    addToCart.mockClear();
    respond(product({}));
    await addFirstOrLookup("X");
    expect(addToCart).toHaveBeenCalledTimes(1);
    expect(document.getElementById("productSearch").value).toBe("");

    respond({ error: "not found" });
    await addFirstOrLookup("X");
    expect(document.getElementById("posAlert").textContent).toBe("لم يُعثر على المنتج");
  });

  it("runProductSearch: empty query, busy guard, success and error", async () => {
    const { runProductSearch } = await load();
    await runProductSearch("");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);

    let resolveFirst;
    const pending = setFetch(vi.fn(() => new Promise((r) => { resolveFirst = r; })));
    const p1 = runProductSearch("foo");
    await flush();
    expect(pending).toHaveBeenCalledTimes(1);
    await runProductSearch("foo"); // blocked by productBusy
    expect(pending).toHaveBeenCalledTimes(1);
    resolveFirst(jsonResponse([{ id: 1, text: "Foo", price: 5, stock: 2, is_out_of_stock: false, is_inactive: false }]));
    await p1;
    expect(document.getElementById("productResults").textContent).toContain("Foo");
    expect(document.getElementById("productLoading").classList.contains("d-none")).toBe(true);

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false, message: "search failed" }))));
    await runProductSearch("bar");
    expect(document.getElementById("posAlert").textContent).toBe("search failed");
  });

  it("loadCategories: missing box, error, empty and chips click", async () => {
    const { loadCategories } = await load();
    document.getElementById("posCategories").remove();
    await expect(loadCategories()).resolves.toBeUndefined();

    const box = addEl("div", "posCategories");
    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false, message: "nope" }))));
    await loadCategories();
    expect(box.textContent).toContain("تعذر تحميل التصنيفات");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ categories: [] }))));
    await loadCategories();
    expect(box.textContent).toContain("الكل");

    routeFetch({ "/pos/api/products": () => Promise.resolve(jsonResponse([{ id: 1, name: "burger" }])) });
    setFetch(
      vi.fn((url) => {
        if (String(url).includes("/pos/api/products")) {
          return Promise.resolve(jsonResponse([{ id: 1, name: "burger", price: 5, stock: 2 }]));
        }
        return Promise.resolve(jsonResponse({ categories: [{ id: 4, name: "Meals" }] }));
      }),
    );
    await loadCategories();
    const chips = box.querySelectorAll(".pos-cat");
    expect(chips).toHaveLength(2);
    chips[1].click();
    await flush();
    expect(chips[0].classList.contains("active")).toBe(false);
    expect(chips[1].classList.contains("active")).toBe(true);
    expect(document.getElementById("posProductGrid").textContent).toContain("burger");
  });

  it("loadProducts: missing grid, HTTP error + retry, empty and catch + retry", async () => {
    const { loadProducts } = await load();
    document.getElementById("posProductGrid").remove();
    await expect(loadProducts("")).resolves.toBeUndefined();

    const grid = addEl("div", "posProductGrid");
    const errFetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ success: false, message: "HTTP 500" }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: [{ id: 1, name: "Recovered", price: 5, stock: 2 }] }));
    setFetch(errFetch);
    await loadProducts("");
    expect(grid.textContent).toContain("تعذر تحميل المنتجات");
    expect(grid.textContent).toContain("HTTP 500");
    grid.querySelector("[data-retry-products]").click();
    await flush();
    expect(grid.textContent).toContain("Recovered");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse([]))));
    await loadProducts("");
    expect(grid.textContent).toContain("لا توجد منتجات في هذه الفئة");

    const netFetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("net"))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: [{ id: 2, name: "RetryOK", price: 5, stock: 2 }] }));
    setFetch(netFetch);
    await loadProducts("");
    expect(grid.textContent).toContain("تحقّق من الاتصال");
    grid.querySelector("[data-retry-products]").click();
    await flush();
    expect(grid.textContent).toContain("RetryOK");
  });

  it("loadProducts: image error, unavailable reasons, click, keydown and category URL", async () => {
    const { loadProducts } = await load();
    const grid = document.getElementById("posProductGrid");
    setFetch(
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            products: [
              { id: 1, name: "Img", name_ar: "صورة", price: 5, stock: 2, image_url: "/x.png" },
              { id: 2, name: "Out", price: 5, stock: 0, is_out_of_stock: true },
              { id: 3, name: "Inactive", price: 5, stock: 2, is_inactive: true },
              { id: 4, name: "Fine", price: 5, stock: 2 },
            ],
          }),
        ),
      ),
    );
    await loadProducts("cat-9");
    expect(global.fetch.mock.calls[0][0]).toContain("category_id=cat-9");

    const cards = grid.querySelectorAll(".pos-card");
    expect(cards).toHaveLength(4);
    expect(cards[0].classList.contains("has-img")).toBe(true);
    const img = cards[0].querySelector(".card-img");
    img.dispatchEvent(new Event("error"));
    expect(cards[0].classList.contains("has-img")).toBe(false);
    expect(cards[0].querySelector(".card-img")).toBeNull();

    const alert = document.getElementById("posAlert");
    cards[1].click();
    await flush();
    expect(alert.textContent).toContain("نفد من المخزون");
    cards[2].dispatchEvent(keydown(" "));
    await flush();
    expect(alert.textContent).toContain("غير نشط");

    cards[3].dispatchEvent(keydown("Enter"));
    await flush();
    expect(addToCart).toHaveBeenCalledTimes(1);
    cards[0].dispatchEvent(keydown("Escape"));
    await flush();
    cards[0].dispatchEvent(keydown("Enter"));
    await flush();
    expect(addToCart).toHaveBeenCalledTimes(2);
  });

  it("loadFloors: missing box, error, empty, chips click and first-floor auto-select", async () => {
    const { loadFloors } = await load();
    document.getElementById("posFloors").remove();
    await expect(loadFloors()).resolves.toBeUndefined();
    const box = addEl("div", "posFloors");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false, message: "floor err" }))));
    await loadFloors();
    expect(box.textContent).toContain("floor err");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ floors: [] }))));
    await loadFloors();
    expect(box.textContent).toContain("لا توجد أرضيات");

    setFetch(
      vi.fn((url) => {
        if (String(url).includes("/pos/api/floors/")) {
          return Promise.resolve(jsonResponse({ tables: [{ id: 1, label: "T", status: "free" }] }));
        }
        return Promise.resolve(jsonResponse({ floors: [{ id: 5, name: "Ground" }, { id: 6, name: "First" }] }));
      }),
    );
    await loadFloors();
    const chips = box.querySelectorAll(".pos-cat");
    expect(chips).toHaveLength(2);
    expect(chips[0].classList.contains("active")).toBe(true);
    await flush(); // auto-select of the first floor calls loadTables asynchronously
    expect(document.getElementById("posTablesGrid").textContent).toContain("T");
    chips[1].click();
    await flush();
    expect(chips[1].classList.contains("active")).toBe(true);
    expect(chips[0].classList.contains("active")).toBe(false);
  });

  it("loadTables: missing grid, no floor, error, empty, occupied/free, click and keydown", async () => {
    const { loadTables, state } = await load();
    document.getElementById("posTablesGrid").remove();
    await expect(loadTables("1")).resolves.toBeUndefined();
    const grid = addEl("div", "posTablesGrid");

    await loadTables("");
    expect(grid.textContent).toContain("اختر طابقاً");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false, message: "table err" }))));
    await loadTables("1");
    expect(grid.textContent).toContain("table err");

    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ tables: [] }))));
    await loadTables("1");
    expect(grid.textContent).toContain("لا توجد طاولات");

    setFetch(
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            tables: [
              { id: 1, label: "Busy", status: "occupied" },
              { id: 2, label: "Held", status: "reserved" },
              { id: 3, label: "Other", status: "dirty" },
              { id: 4, label: "Free", status: "free" },
            ],
          }),
        ),
      ),
    );
    await loadTables("1");
    const cards = grid.querySelectorAll(".pos-card");
    expect(cards).toHaveLength(4);
    expect(cards[0].querySelector(".price").textContent).toContain("occupied");
    expect(cards[1].querySelector(".price").textContent).toContain("reserved");
    expect(cards[2].querySelector(".price").textContent).toContain("dirty");
    expect(cards[0].hasAttribute("role")).toBe(false);
    expect(cards[3].getAttribute("role")).toBe("button");

    cards[3].click();
    expect(state.selectedTable).toEqual({ id: 4, label: "Free" });
    expect(document.getElementById("posTableSelected").textContent).toContain("Free");
    expect(document.getElementById("posTablesBtn").classList.contains("has-selection")).toBe(true);

    state.selectedTable = null;
    cards[3].dispatchEvent(keydown("Enter"));
    expect(state.selectedTable).toEqual({ id: 4, label: "Free" });

    // the modal is hidden through jQuery when both globals are available
    const origJQuery = window.jQuery;
    const origDollar = window.$;
    const modal = vi.fn();
    window.jQuery = window.$ = vi.fn(() => ({ modal }));
    cards[3].click();
    expect(modal).toHaveBeenCalledWith("hide");
    window.jQuery = origJQuery;
    window.$ = origDollar;
  });
});

/* ================================================================== *
 *  static/js/pos/terminal.js
 * ================================================================== */
describe("pos/terminal.js — final coverage", () => {
  const SDK_URL = "https://js.stripe.com/terminal/v1/";

  function terminalMock() {
    return {
      discoverReaders: vi.fn(() => Promise.resolve({ discoveredReaders: [{ id: "r1" }] })),
      connectReader: vi.fn(() => Promise.resolve({ reader: { id: "r1" } })),
      collectPaymentMethod: vi.fn(() => Promise.resolve({ paymentIntent: { id: "pi_1" } })),
      processPayment: vi.fn(() => Promise.resolve({ paymentIntent: { id: "pi_1", status: "succeeded" } })),
    };
  }
  function intentFetch() {
    return setFetch(
      vi.fn((url) => {
        const u = String(url);
        if (u.endsWith("/pos/api/terminal/status")) {
          return Promise.resolve(jsonResponse({ success: true, configured: true }));
        }
        if (u.endsWith("/pos/api/terminal/connection_token")) {
          return Promise.resolve(jsonResponse({ success: true, secret: "tok_1" }));
        }
        return Promise.resolve(
          jsonResponse({ success: true, id: "pi_intent", amount_minor: 1250, client_secret: "cs_1" }),
        );
      }),
    );
  }

  beforeEach(() => {
    vi.resetModules();
    document.head.innerHTML = "";
    localStorage.clear();
    delete window.StripeTerminal;
    delete window.PosTerminal;
    delete window.setupTerminalButton;
    delete window._FX_FALLBACK_BASE;
    intentFetch();
  });
  afterEach(() => {
    document.head.innerHTML = "";
    localStorage.clear();
    delete window.StripeTerminal;
    delete window.PosTerminal;
    delete window.setupTerminalButton;
    delete global.fetch;
    vi.restoreAllMocks();
  });

  it("lazily injects the SDK script and resolves on onload", async () => {
    await import(TERMINAL);
    const term = terminalMock();
    const create = vi.fn(() => term);
    const pos = new window.PosTerminal();

    const pending = pos._getTerminal();
    const scripts = document.querySelectorAll(`script[src="${SDK_URL}"]`);
    expect(scripts).toHaveLength(1);
    window.StripeTerminal = { create };
    scripts[0].onload();
    await expect(pending).resolves.toBe(term);
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("SDK onerror rejects with a safe message and clears the cached promise for retry", async () => {
    await import(TERMINAL);
    const pos = new window.PosTerminal();

    const first = pos._getTerminal();
    const firstScript = document.querySelector(`script[src="${SDK_URL}"]`);
    firstScript.onerror();
    await expect(first).rejects.toThrow("تعذر تحميل مكتبة الدفع الطرفي");

    // Retry creates a fresh script because _sdkPromise was reset to null.
    // StripeTerminal must stay unset until the script loads, otherwise
    // _loadTerminalSdk short-circuits on the window global.
    const second = pos._getTerminal();
    const allScripts = document.querySelectorAll(`script[src="${SDK_URL}"]`);
    expect(allScripts).toHaveLength(2);
    const term = terminalMock();
    window.StripeTerminal = { create: vi.fn(() => term) };
    allScripts[1].onload();
    await expect(second).resolves.toBe(term);
  });

  it("caches a single in-flight SDK load and reuses the terminal instance", async () => {
    await import(TERMINAL);
    const term = terminalMock();
    const pos = new window.PosTerminal();

    const a = pos._getTerminal();
    const b = pos._getTerminal();
    expect(document.querySelectorAll(`script[src="${SDK_URL}"]`)).toHaveLength(1);
    window.StripeTerminal = { create: vi.fn(() => term) };
    document.querySelector(`script[src="${SDK_URL}"]`).onload();
    await Promise.all([a, b]);
    await expect(pos._getTerminal()).resolves.toBe(term);
    expect(window.StripeTerminal.create).toHaveBeenCalledTimes(2);
  });

  it("_connectReader returns the cached reader without discovering", async () => {
    await import(TERMINAL);
    const pos = new window.PosTerminal();
    const cached = { id: "cached" };
    pos._reader = cached;
    const term = { discoverReaders: vi.fn() };
    await expect(pos._connectReader(term)).resolves.toBe(cached);
    expect(term.discoverReaders).not.toHaveBeenCalled();
  });

  it("pushPayment falls back to the intent id and accepts default arguments", async () => {
    window.StripeTerminal = { create: vi.fn(() => {
      const term = terminalMock();
      term.processPayment.mockResolvedValue({ paymentIntent: { status: "succeeded" } });
      return term;
    }) };
    await import(TERMINAL);
    const pos = new window.PosTerminal();
    const result = await pos.pushPayment({ amount: 7 });
    expect(result).toEqual({ intentId: "pi_intent", amountMinor: 1250 });
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body).toEqual({ amount: "7", currency: "ILS", sale_reference: "" });
  });

  it("_postJson throws the safe default error when the server omits a message", async () => {
    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false }, { ok: false, status: 500 }))));
    await import(TERMINAL);
    const pos = new window.PosTerminal();
    await expect(pos.pushPayment({ amount: 1 })).rejects.toThrow("فشلت عملية الدفع الطرفي.");
  });

  it("setupTerminalButton surfaces errors without a message and re-enables the button", async () => {
    window.StripeTerminal = { create: vi.fn(() => {
      const term = terminalMock();
      term.collectPaymentMethod.mockResolvedValue({ error: "cancelled" });
      return term;
    }) };
    await import(TERMINAL);
    const button = addEl("button", "payBtn");
    const onError = vi.fn();
    await window.setupTerminalButton({ button, getAmount: () => 10, onError });
    button.click();
    await flush();
    await flush();
    expect(onError).toHaveBeenCalledWith("ألغيت العملية أو تعذرت قراءة البطاقة.");
    expect(button.disabled).toBe(false);
  });

  it("checkStatus returns false when json parsing fails or the request rejects", async () => {
    await import(TERMINAL);
    const pos = new window.PosTerminal();
    setFetch(
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error("bad json")) }),
      ),
    );
    await expect(pos.checkStatus()).resolves.toBe(false);
    setFetch(vi.fn(() => Promise.reject(new Error("down"))));
    await expect(pos.checkStatus()).resolves.toBe(false);
  });

  it("wires connection-token and disconnect callbacks, including a bad-json token response", async () => {
    await import(TERMINAL);
    const term = terminalMock();
    const pos = new window.PosTerminal();
    let createOpts;
    const pending = pos._getTerminal();
    const script = document.querySelector(`script[src="${SDK_URL}"]`);
    window.StripeTerminal = {
      create: vi.fn((opts) => {
        createOpts = opts;
        return term;
      }),
    };
    script.onload();
    await pending;

    await expect(createOpts.onFetchConnectionToken()).resolves.toBe("tok_1");
    pos._reader = { id: "r1" };
    createOpts.onUnexpectedReaderDisconnect();
    expect(pos._reader).toBeNull();

    setFetch(
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error("bad json")) }),
      ),
    );
    await expect(createOpts.onFetchConnectionToken()).resolves.toBeUndefined();
  });

  it("_connectReader surfaces discovery, empty-list and connect errors", async () => {
    await import(TERMINAL);
    const pos = new window.PosTerminal();
    const term = terminalMock();

    term.discoverReaders.mockResolvedValueOnce({ error: "x" });
    await expect(pos._connectReader(term)).rejects.toThrow("تعذر البحث عن قارئ البطاقات.");
    term.discoverReaders.mockResolvedValueOnce({ discoveredReaders: [] });
    await expect(pos._connectReader(term)).rejects.toThrow("لا يوجد قارئ بطاقات");
    term.connectReader.mockResolvedValueOnce({ error: "x" });
    await expect(pos._connectReader(term)).rejects.toThrow("تعذر الاتصال بقارئ البطاقات.");

    // discoveredReaders omitted -> treated as an empty list
    term.discoverReaders.mockResolvedValueOnce({});
    await expect(new window.PosTerminal()._connectReader(term)).rejects.toThrow(
      "لا يوجد قارئ بطاقات",
    );
  });

  it("_connectReader stores an empty reader id when the reader has no id", async () => {
    await import(TERMINAL);
    const term = terminalMock();
    term.connectReader.mockResolvedValueOnce({ reader: {} });
    const pos = new window.PosTerminal();
    const reader = await pos._connectReader(term);
    expect(reader).toEqual({});
    expect(localStorage.getItem("pos.terminal.reader_id")).toBe("");
  });

  it("pushPayment surfaces collection, issuer-decline and non-succeeded errors", async () => {
    const cases = [
      { tweak: (t) => t.collectPaymentMethod.mockResolvedValue({ error: "x" }), msg: "ألغيت العملية" },
      { tweak: (t) => t.processPayment.mockResolvedValue({ error: "x" }), msg: "رفضت جهة الإصدار" },
      {
        tweak: (t) => t.processPayment.mockResolvedValue({ paymentIntent: { status: "pending" } }),
        msg: "لم تكتمل عملية الدفع",
      },
    ];
    for (const c of cases) {
      const term = terminalMock();
      c.tweak(term);
      window.StripeTerminal = { create: vi.fn(() => term) };
      await import(TERMINAL);
      const pos = new window.PosTerminal();
      await expect(pos.pushPayment({ amount: 5 })).rejects.toThrow(c.msg);
    }
  });

  it("setupTerminalButton: null button, unconfigured provider, zero amount and approval", async () => {
    await import(TERMINAL);
    await expect(window.setupTerminalButton({ button: null })).resolves.toBeNull();

    setFetch(
      vi.fn(() =>
        Promise.resolve(jsonResponse({ success: false, configured: false }, { ok: false })),
      ),
    );
    const hidden = addEl("button", "hiddenBtn");
    await expect(window.setupTerminalButton({ button: hidden })).resolves.toBeNull();

    intentFetch();
    const zeroBtn = addEl("button", "zeroBtn");
    const onError = vi.fn();
    await window.setupTerminalButton({ button: zeroBtn, getAmount: () => 0, onError });
    zeroBtn.click();
    expect(onError).toHaveBeenCalledWith("أضف أصنافاً إلى السلة أولاً.");

    window.StripeTerminal = { create: vi.fn(() => terminalMock()) };
    const okBtn = addEl("button", "okBtn");
    const onApproved = vi.fn();
    await window.setupTerminalButton({ button: okBtn, getAmount: () => 50, onApproved, onError });
    okBtn.click();
    await flush();
    await flush();
    expect(onApproved).toHaveBeenCalledWith({ intentId: "pi_1", amountMinor: 1250 });
    expect(okBtn.disabled).toBe(false);

    // a rejection without a message falls back to the Arabic safe error
    vi.spyOn(window.PosTerminal.prototype, "pushPayment").mockRejectedValueOnce({});
    const noMsgBtn = addEl("button", "noMsgBtn");
    const fallbackError = vi.fn();
    await window.setupTerminalButton({ button: noMsgBtn, getAmount: () => 10, onError: fallbackError });
    noMsgBtn.click();
    await flush();
    await flush();
    expect(fallbackError).toHaveBeenCalledWith("فشلت عملية الدفع الطرفي.");
  });
});

/* ================================================================== *
 *  static/js/pos/offline-sync.js
 * ================================================================== */
describe("pos/offline-sync.js — final coverage", () => {
  function buildDom() {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    const meta = (name, content) => {
      const m = document.createElement("meta");
      m.name = name;
      m.content = content;
      document.head.appendChild(m);
    };
    meta("csrf-token", "tok");
    meta("pos-base-currency", "ILS");
    addEl("input", "productSearch");
    addEl("div", "productResults");
    addEl("div", "posAlert");
    addEl("div", "barcodeSecondary");
    addEl("button", "cameraScanBtn");
    addEl("button", "scaleConnectBtn");
  }

  beforeEach(async () => {
    vi.resetModules();
    buildDom();
    setFetch(vi.fn(() => Promise.resolve(jsonResponse({}))));
    const cart = await import("../../static/js/pos/cart.js");
    cart.addToCart.mockClear();
  });
  afterEach(() => {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    delete window.BarcodeScanner;
    delete window.setupCameraScanUI;
    delete window.PosScaleSerial;
    delete window.setupPosScaleUI;
    delete window.posOfflineCatalog;
  });

  async function load() {
    const sync = await import(OFFLINE);
    const core = await import(CORE);
    return { ...sync, state: core.state, addToCart: (await import("../../static/js/pos/cart.js")).addToCart };
  }
  function productResponse(extra = {}) {
    return setFetch(
      vi.fn(() => Promise.resolve(jsonResponse({ id: 1, name: "Apple", price: 5, ...extra }))),
    );
  }

  it("handleScannedCode: empty code, secondary barcode present and success alert", async () => {
    const { handleScannedCode } = await load();
    await expect(handleScannedCode("   ")).resolves.toBeUndefined();
    expect(global.fetch).not.toHaveBeenCalled();

    productResponse();
    const secondary = document.getElementById("barcodeSecondary");
    secondary.value = "old-code";
    document.getElementById("productSearch").value = "abc";
    await handleScannedCode("abc");
    expect(secondary.value).toBe("");
    expect(document.getElementById("productSearch").value).toBe("");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);
    expect(document.getElementById("posAlert").textContent).toContain("تمت إضافة");
  });

  it("handleScannedCode: works when #barcodeSecondary is absent", async () => {
    document.getElementById("barcodeSecondary").remove();
    const { handleScannedCode } = await load();
    productResponse();
    await expect(handleScannedCode("abc")).resolves.toBeUndefined();
    expect(document.getElementById("posAlert").textContent).toContain("تمت إضافة");
  });

  it("handleScannedCode: offline catalog fallback and weight product quantity", async () => {
    const { handleScannedCode, state, addToCart } = await load();
    setFetch(vi.fn(() => Promise.reject(new Error("network"))));
    window.posOfflineCatalog = {
      lookupLocalProduct: vi.fn(() =>
        Promise.resolve({ id: 9, name: "Local", price: 5, is_weight_product: true }),
      ),
    };
    state.scaleWeightKg = 2.75;
    await handleScannedCode("code");
    expect(window.posOfflineCatalog.lookupLocalProduct).toHaveBeenCalledWith("code");
    // cart.addToCart is stubbed in this file, so assert the forwarded quantity.
    expect(addToCart).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }), 2.75);
  });

  it("handleScannedCode: inactive offline product and unfound product", async () => {
    const { handleScannedCode, addToCart } = await load();
    setFetch(vi.fn(() => Promise.resolve(jsonResponse({ success: false, message: "offline" }))));
    window.posOfflineCatalog = {
      lookupLocalProduct: vi.fn(() =>
        Promise.resolve({ id: 3, name: "Old", is_inactive: true, warning: "disabled" }),
      ),
    };
    await handleScannedCode("x");
    expect(document.getElementById("posAlert").textContent).toBe("disabled");
    expect(addToCart).not.toHaveBeenCalled();

    // no warning supplied -> the Arabic default is used
    window.posOfflineCatalog.lookupLocalProduct.mockResolvedValueOnce({
      id: 4,
      name: "Old2",
      is_inactive: true,
    });
    await handleScannedCode("y");
    expect(document.getElementById("posAlert").textContent).toBe("المنتج غير نشط.");

    delete window.posOfflineCatalog;
    await expect(handleScannedCode("nope")).resolves.toBeUndefined();
    expect(addToCart).not.toHaveBeenCalled();
  });

  it("setupDevices: wires every callback and forwards them to the right handler", async () => {
    productResponse();
    const start = vi.fn();
    window.BarcodeScanner = vi.fn(function () {
      this.start = start;
    });
    let cameraOpts;
    window.setupCameraScanUI = vi.fn((opts) => { cameraOpts = opts; });
    let scaleOpts;
    window.PosScaleSerial = vi.fn(function (opts) {
      scaleOpts = opts;
    });
    let scaleUiOpts;
    window.setupPosScaleUI = vi.fn((opts) => { scaleUiOpts = opts; });
    const hydrate = vi.fn(() => Promise.resolve(0));
    window.posOfflineCatalog = { hydrateCatalog: hydrate };

    const { setupDevices, state, addToCart } = await load();
    setupDevices();
    expect(start).toHaveBeenCalled();
    expect(cameraOpts.button).toBe(document.getElementById("cameraScanBtn"));
    expect(scaleOpts).toBeDefined();
    expect(scaleUiOpts.scale).toBe(state.posScale);
    expect(hydrate).toHaveBeenCalledTimes(1);

    cameraOpts.onScan("scanned");
    await flush();
    expect(addToCart).toHaveBeenCalledTimes(1);

    cameraOpts.onError("camera failed");
    expect(document.getElementById("posAlert").textContent).toBe("camera failed");

    scaleOpts.onStableWeight(1.234);
    expect(state.scaleWeightKg).toBe(1.234);
    expect(document.getElementById("scaleConnectBtn").dataset.liveWeight).toBe("1.234");
    scaleOpts.onError("scale failed");
    expect(document.getElementById("posAlert").textContent).toBe("scale failed");

    window.dispatchEvent(new Event("online"));
    expect(hydrate).toHaveBeenCalledTimes(2);
  });

  it("setupDevices: no scale button still records the weight without throwing", async () => {
    document.getElementById("scaleConnectBtn").remove();
    window.BarcodeScanner = vi.fn(function () { this.start = vi.fn(); });
    let scaleOpts;
    window.PosScaleSerial = vi.fn(function (opts) { scaleOpts = opts; });
    window.setupPosScaleUI = vi.fn();
    const { setupDevices, state } = await load();
    setupDevices();
    expect(() => scaleOpts.onStableWeight(3.5)).not.toThrow();
    expect(state.scaleWeightKg).toBe(3.5);
  });

  it("setupDevices: no optional globals only starts the scanner", async () => {
    const start = vi.fn();
    window.BarcodeScanner = vi.fn(function () { this.start = start; });
    const addListener = vi.spyOn(window, "addEventListener");
    const { setupDevices } = await load();
    setupDevices();
    expect(start).toHaveBeenCalledTimes(1);
    expect(addListener.mock.calls.filter(([n]) => n === "online")).toHaveLength(0);
  });
});
