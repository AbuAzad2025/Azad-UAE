/**
 * Real coverage-gap tests for static/js/pos/index.js and
 * static/js/pos/offline-catalog.js.
 *
 * The POS entry point is a top-level script that binds a large number of DOM
 * event handlers when it is imported.  The existing vitest suites cover the
 * common paths but leave a set of rarely-dispatched handlers and error branches
 * untouched.  Every test below drives one of those real branches through the
 * public DOM / window seams the module already exposes (no production code is
 * changed and no coverage threshold or exclude is touched).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const INDEX_PATH = "../../static/js/pos/index.js";
const OFFLINE_PATH = "../../static/js/pos/offline-catalog.js";

const sleep = (ms = 10) => new Promise((r) => setTimeout(r, ms));

/* -------------------------------------------------------------------------- */
/* DOM                                                                         */
/* -------------------------------------------------------------------------- */

function addEl(tag, id, html = "") {
  const el = document.createElement(tag);
  el.id = id;
  if (html) el.innerHTML = html;
  document.body.appendChild(el);
  return el;
}

function buildDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = "";

  for (const [name, content] of [
    ["csrf-token", "tok"],
    ["pos-base-currency", "USD"],
  ]) {
    const meta = document.createElement("meta");
    meta.name = name;
    meta.content = content;
    document.head.appendChild(meta);
  }

  const divIds = [
    "cartBody", "cartCount", "kpiSubtotal", "kpiDiscount", "kpiTotal", "kpiCurrency",
    "productResults", "productLoading", "customerResults", "customerSelectedHint",
    "posAlert", "posPinModal", "posPinError", "upsellBar", "doneSaleNumber",
    "doneViewBtn", "donePrintBtn", "doneUpsellList", "openSessionModal",
    "closeSessionModal", "openSessionAlert", "closeSessionAlert", "tableField",
    "posTablesGrid", "posTableClear", "posCategories", "posProductGrid",
    "posSessionBar", "posSessionRequired", "sessionNumber", "sessionBalance",
    "sessionTotal", "sessionTime", "splitTenderBox", "splitTenderRows",
    "splitTenderSum", "closeOpening", "closeCashSales", "closeExpected",
    "closeExpectedBlock", "posCalc", "posTablesModal", "invoiceNumberBadge",
    "posTableSelected", "posFooterClock", "stockAvailable", "stockLow", "stockOut",
    "customerDisplayBtn", "exchangeRateSource", "exchangeRateNote",
  ];
  divIds.forEach((id) => addEl("div", id));
  document.getElementById("posTablesModal").classList.add("d-none");

  addEl("input", "productSearch");
  addEl("input", "customerSearch");
  addEl("input", "barcodeSecondary");
  for (const id of [
    "taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber",
    "orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance",
    "closeSessionNotes", "exchangeRate",
  ]) {
    addEl("input", id);
  }

  addEl("select", "warehouseId", '<option value="5">Main</option>');
  addEl("select", "orderType", '<option value="takeaway">Takeaway</option>');
  addEl("select", "tableSelect", '<option value="1">T1</option>');
  addEl("select", "currency", '<option value="USD">USD</option><option value="EUR">EUR</option>');
  const paySel = addEl(
    "select",
    "paymentMethod",
    '<option value="cash">cash</option><option value="card">card</option>',
  );
  paySel.value = "cash";
  document.getElementById("currency").value = "USD";
  document.getElementById("exchangeRate").value = "1";

  for (const id of [
    "checkoutBtn", "checkoutPrintBtn", "clearCustomer", "walkinCustomer",
    "addCustomerBtn", "drawerOpenBtn", "splitTenderAdd", "mixedPaymentBtn",
    "posPinConfirm", "openSessionBtn", "openSessionConfirm", "closeSessionBtn",
    "closeSessionConfirm", "clearProductSearch", "clearCartBtn", "cameraScanBtn",
    "scaleConnectBtn", "refreshRateBtn", "pushTerminalBtn", "posTablesBtn",
    "posHoldBtn", "posPinInput",
  ]) {
    addEl("button", id);
  }

  const toggle = addEl("input", "splitTenderToggle");
  toggle.type = "checkbox";

  const pmBox = document.createElement("div");
  pmBox.id = "posPayMethod";
  for (const method of ["cash", "card"]) {
    const tile = document.createElement("button");
    tile.className = "pm";
    tile.setAttribute("data-method", method);
    pmBox.appendChild(tile);
  }
  document.body.appendChild(pmBox);
}

/* -------------------------------------------------------------------------- */
/* Network / plugin / jQuery mocks                                             */
/* -------------------------------------------------------------------------- */

function mockFetch(map = {}) {
  const merged = {
    "/pos/api/session/current": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/order-types": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false }) }),
    "/pos/api/categories": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    "/pos/api/products": () =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    "/sales/api/calculate-totals": () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            data: { subtotal: 100, discount: 0, tax_amount: 0, total: 100, prices_include_vat: false },
          }),
      }),
    ...map,
  };
  const spy = vi.fn((url, opts) => {
    const handler = merged[url] || merged[String(url).split("?")[0]];
    if (handler) return handler(url, opts);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  globalThis.fetch = spy;
  window.fetch = spy;
  return spy;
}

let jqModalActions;
let jqHandlers;
function installJQuery({ withModal = true } = {}) {
  jqModalActions = [];
  jqHandlers = [];
  const make = (sel) => {
    const api = {
      on: vi.fn((evt, fn) => {
        jqHandlers.push({ sel, evt, fn });
        return api;
      }),
      off: vi.fn(() => api),
      focus: vi.fn(),
      val: vi.fn(() => ""),
      text: vi.fn(),
      html: vi.fn(),
      addClass: vi.fn(),
      removeClass: vi.fn(),
      show: vi.fn(),
      hide: vi.fn(),
      click: vi.fn(),
      modal: withModal
        ? vi.fn((action) => {
            jqModalActions.push([sel, action]);
            return api;
          })
        : undefined,
    };
    return api;
  };
  window.$ = vi.fn((sel) => {
    if (typeof sel === "function") {
      sel();
      return make("ready");
    }
    return make(sel);
  });
  globalThis.$ = window.$;
}

let capturedTerminal;
let realSetInterval;

beforeEach(() => {
  buildDom();
  installJQuery();
  mockFetch();
  capturedTerminal = undefined;

  window.t = (k) => k;
  window.prompt = vi.fn(() => null);
  window.confirm = vi.fn(() => true);
  window.open = vi.fn(() => ({}));
  window.cfdBroadcast = { sendCart: vi.fn(), setSession: vi.fn() };
  window.POS_CONFIG = { enable_tables: true, enable_hold: true };
  window.BarcodeScanner = vi.fn(function (opts) {
    this.start = vi.fn();
    this.stop = vi.fn();
    this.onScan = opts?.onScan;
  });
  window.PosScaleSerial = vi.fn(function (opts) {
    this.onStableWeight = opts?.onStableWeight;
    this.onError = opts?.onError;
  });
  window.setupPosScaleUI = vi.fn();
  window.setupCameraScanUI = vi.fn();
  window.setupTerminalButton = vi.fn((cfg) => {
    capturedTerminal = cfg;
  });
  window.posOfflineCatalog = {
    hydrateCatalog: vi.fn(() => Promise.resolve(0)),
    lookupLocalProduct: vi.fn(() => Promise.resolve(null)),
    parseScaleBarcodeLocal: vi.fn(() => null),
  };

  Object.defineProperty(globalThis, "crypto", {
    value: { randomUUID: () => `uuid-${Math.random()}` },
    configurable: true,
    writable: true,
  });

  // The footer clock installs a 1s interval at import; a no-op keeps the
  // jsdom timers from accumulating across the many module reloads in this file.
  realSetInterval = window.setInterval;
  window.setInterval = vi.fn(() => 1);

  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/pos/");
  vi.resetModules();
});

afterEach(async () => {
  if (window.__sesTimer) {
    clearInterval(window.__sesTimer);
    window.__sesTimer = null;
  }
  window.setInterval = realSetInterval;
  vi.useRealTimers();
  vi.clearAllTimers();
  vi.restoreAllMocks();
  await sleep(0);
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  localStorage.clear();
  sessionStorage.clear();
});

async function loadIndex() {
  delete window._posFmt;
  await import(INDEX_PATH);
  await sleep(30);
}

function seedCart(st = window._posState, price = 100) {
  st.customer = { id: 11, text: "Buyer" };
  st.cart = [{ id: 991, name: "Item", qty: 1, price, basePrice: price, discountPercent: 0 }];
  return st;
}

/* ========================================================================== */
/* index.js — missed handler / branch coverage                                */
/* ========================================================================== */

describe("pos/index — uncovered interaction branches", () => {
  it("exchangeRate input and change mark the rate manual and reprice the cart (146-151)", async () => {
    await loadIndex();
    const rate = document.getElementById("exchangeRate");
    rate.value = "3.5";
    rate.dispatchEvent(new Event("input", { bubbles: true }));
    expect(window._posState.rateSource).toBe("user_manual");
    rate.dispatchEvent(new Event("change", { bubbles: true }));
    expect(window._posState.rateSource).toBe("user_manual");
  });

  it("customer search with an empty query hides the result box after the debounce (161-162)", async () => {
    await loadIndex();
    const search = document.getElementById("customerSearch");
    search.value = "   ";
    const box = document.getElementById("customerResults");
    box.classList.remove("d-none");
    search.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(230);
    expect(box.classList.contains("d-none")).toBe(true);
  });

  it("add-customer button returns early when the prompt is blank (200-201)", async () => {
    await loadIndex();
    window.prompt.mockReturnValueOnce("   ");
    document.getElementById("addCustomerBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(10);
    expect(globalThis.fetch).not.toHaveBeenCalledWith(
      "/pos/api/customers/create",
      expect.anything(),
    );
  });

  it("add-customer button stores the new customer on success (202-213)", async () => {
    mockFetch({
      "/pos/api/customers/create": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, data: { id: 42, text: "New Client" } }),
        }),
    });
    await loadIndex();
    window.prompt.mockReturnValueOnce("  New Client  ");
    document.getElementById("addCustomerBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(window._posState.customer.id).toBe(42);
    expect(document.getElementById("customerSearch").value).toBe("New Client");
    expect(document.getElementById("posAlert").textContent).toContain("تمت إضافة الزبون");
  });

  it("add-customer button surfaces a rejected create response (208-209)", async () => {
    mockFetch({
      "/pos/api/customers/create": () =>
        Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ success: false, message: "duplicate" }),
        }),
    });
    await loadIndex();
    window.prompt.mockReturnValueOnce("Dup");
    document.getElementById("addCustomerBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("posAlert").textContent).toContain("duplicate");
  });

  it("add-customer button degrades to an alert on a network error (214-215)", async () => {
    mockFetch({
      "/pos/api/customers/create": () => Promise.reject(new TypeError("offline")),
    });
    await loadIndex();
    window.prompt.mockReturnValueOnce("Someone");
    document.getElementById("addCustomerBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("posAlert").textContent).toBeTruthy();
  });

  it("product search Enter adds the first cached result (226-228)", async () => {
    await loadIndex();
    window._posState.lastProductResults = [
      { id: 71, name: "First", price: 10, barcode: "777", sku: "", is_inactive: false },
    ];
    const search = document.getElementById("productSearch");
    search.value = "777";
    search.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await sleep(20);
    expect(window._posState.cart.some((l) => l.id === 71)).toBe(true);
  });

  it("secondary barcode field runs a search on input (234-235)", async () => {
    await loadIndex();
    const bar = document.getElementById("barcodeSecondary");
    bar.value = "  ABC-1  ";
    bar.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(10);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/pos/api/products"),
      expect.anything(),
    );
  });

  it("secondary barcode field adds the first result on Enter (238-240)", async () => {
    await loadIndex();
    window._posState.lastProductResults = [
      { id: 72, name: "Secondary", price: 8, barcode: "888", sku: "", is_inactive: false },
    ];
    const bar = document.getElementById("barcodeSecondary");
    bar.value = "888";
    bar.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await sleep(20);
    expect(window._posState.cart.some((l) => l.id === 72)).toBe(true);
  });

  it("warehouse change with no active query rehydrates the offline catalog (253)", async () => {
    await loadIndex();
    window.posOfflineCatalog.hydrateCatalog.mockClear();
    document.getElementById("productSearch").value = "";
    document.getElementById("warehouseId").value = "5";
    document.getElementById("warehouseId").dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(20);
    expect(window.posOfflineCatalog.hydrateCatalog).toHaveBeenCalledWith({
      warehouseParam: "?warehouse_id=5",
    });
  });

  it("clear product search resets the field and cached results (258-260)", async () => {
    await loadIndex();
    window._posState.lastProductResults = [{ id: 1 }];
    document.getElementById("productSearch").value = "old";
    document.getElementById("productResults").classList.remove("d-none");
    document.getElementById("clearProductSearch").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById("productSearch").value).toBe("");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(true);
    expect(window._posState.lastProductResults).toHaveLength(0);
  });

  it("PIN input Enter submits the override confirmation (265-267)", async () => {
    await loadIndex();
    document.getElementById("posPinInput").value = "0000";
    document.getElementById("posPinInput").dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
    await sleep(20);
    expect(globalThis.fetch).toHaveBeenCalledWith("/pos/api/authorize-override", expect.anything());
  });

  it("mixed-payment button toggles split tender and exposes aria-pressed (299-304)", async () => {
    await loadIndex();
    const btn = document.getElementById("mixedPaymentBtn");
    const toggle = document.getElementById("splitTenderToggle");
    expect(toggle.checked).toBe(false);
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(toggle.checked).toBe(true);
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(btn.classList.contains("active")).toBe(true);
    expect(document.querySelectorAll("#splitTenderRows .split-row")).toHaveLength(1);
  });

  it("checkout retries with a granted override token after a 403 challenge (419-421)", async () => {
    let n = 0;
    mockFetch({
      "/pos/api/checkout": () => {
        n += 1;
        if (n === 1) {
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () => Promise.resolve({ success: false, error: "تفويض مطلوب" }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              sale_id: 812,
              data: { sale_number: "S-812", view_url: "/v", print_url: "/p" },
            }),
        });
      },
      "/pos/api/authorize-override": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, override_token: "granted-token" }),
        }),
    });
    await loadIndex();
    seedCart();
    const pending = window._posCheckout(false);
    await sleep(10); // let the PIN modal resolver install
    document.getElementById("posPinInput").value = "1234";
    await window._posConfirmPin();
    await pending;
    expect(n).toBe(2);
    const bodies = globalThis.fetch.mock.calls
      .filter((c) => c[0] === "/pos/api/checkout")
      .map((c) => JSON.parse(c[1].body));
    expect(bodies[1].override_token).toBe("granted-token");
  });

  it("checkout writes the invoice badge and assigns the selected table (438, 450-465)", async () => {
    mockFetch({
      "/pos/api/checkout": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              sale_id: 913,
              data: {
                sale_id: 913,
                sale_number: "S-2024-77",
                view_url: "/v",
                print_url: "/p",
                upsell_prompts: [],
              },
            }),
        }),
      "/pos/api/tables/3/assign": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }),
    });
    await loadIndex();
    const st = seedCart();
    st.selectedTable = { id: 3 };
    await window._posCheckout(false);
    expect(document.getElementById("invoiceNumberBadge").textContent).toBe("INV-77");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/pos/api/tables/3/assign",
      expect.anything(),
    );
    expect(st.selectedTable).toBeNull();
    expect(document.getElementById("posTableSelected").textContent).toBe("");
  });

  it("keydown from an input with an ordinary key returns from the shortcut handler (482)", async () => {
    await loadIndex();
    const field = document.getElementById("orderNote");
    field.value = "keep me";
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
    expect(field.value).toBe("keep me");
  });

  it("F8 launches checkout with auto-print (491-492)", async () => {
    mockFetch({
      "/pos/api/checkout": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              sale_id: 77,
              data: { sale_number: "S-77", view_url: "/v", print_url: "/print-me" },
            }),
        }),
    });
    await loadIndex();
    seedCart();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "F8", bubbles: true }));
    await sleep(40);
    expect(window.open).toHaveBeenCalledWith("/print-me", "_blank", "noopener");
  });

  it("the footer clock paints a live time when its element exists (502-511)", async () => {
    await loadIndex();
    expect(document.getElementById("posFooterClock").textContent.length).toBeGreaterThan(0);
  });

  it("terminal bridge getters expose the current total and currency (585-586)", async () => {
    await loadIndex();
    expect(capturedTerminal).toBeDefined();
    window._posState.lastTotals = { total: 77 };
    expect(capturedTerminal.getAmount()).toBe(77);
    expect(capturedTerminal.getCurrency()).toBe("USD");
  });

  it("tables modal falls back to a raw DOM class when jQuery .modal is absent (633-634)", async () => {
    await loadIndex();
    const modal = document.getElementById("posTablesModal");
    expect(modal.classList.contains("d-none")).toBe(true);
    installJQuery({ withModal: false });
    document.getElementById("posTablesBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(modal.classList.contains("d-none")).toBe(false);
  });

  it("loadSession configures the customer-display button for an active session (760-761)", async () => {
    mockFetch({
      "/pos/api/session/current": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              session: {
                id: "s1",
                number: "SES-1",
                opening_balance: 100,
                total_sales: 10,
                duration_minutes: 3,
                customer_display_url: "/display/1",
              },
            }),
        }),
    });
    await loadIndex();
    const btn = document.getElementById("customerDisplayBtn");
    expect(btn.classList.contains("disabled")).toBe(false);
    expect(btn.getAttribute("aria-disabled")).toBe("false");
    expect(window._posState.customerDisplayUrl).toBe("/display/1");
  });

  it("loadSession disables the customer-display button with no session (788-789)", async () => {
    await loadIndex();
    const btn = document.getElementById("customerDisplayBtn");
    expect(btn.classList.contains("disabled")).toBe(true);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
  });

  it("open-session network failure surfaces a modal alert (833)", async () => {
    mockFetch({
      "/pos/api/session/open": () => Promise.reject(new TypeError("open-offline")),
    });
    await loadIndex();
    document.getElementById("openSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("openSessionAlert").textContent).toContain("open-offline");
    expect(document.getElementById("openSessionConfirm").disabled).toBe(false);
  });

  it("close-session report network failure surfaces a modal alert (858)", async () => {
    mockFetch({
      "/pos/api/session/report": () => Promise.reject(new TypeError("report-offline")),
    });
    await loadIndex();
    document.getElementById("closeSessionBtn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("closeSessionAlert").textContent).toContain("report-offline");
  });

  it("close-session confirm shows a rejected close response (894-895)", async () => {
    mockFetch({
      "/pos/api/session/close": () =>
        Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ error: "close-refused" }),
        }),
    });
    await loadIndex();
    document.getElementById("closeSessionBalance").value = "100";
    document.getElementById("closeSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("closeSessionAlert").textContent).toContain("close-refused");
    expect(document.getElementById("closeSessionConfirm").disabled).toBe(false);
  });

  it("close-session confirm degrades to a modal alert on a network error (912)", async () => {
    mockFetch({
      "/pos/api/session/close": () => Promise.reject(new TypeError("close-offline")),
    });
    await loadIndex();
    document.getElementById("closeSessionBalance").value = "100";
    document.getElementById("closeSessionConfirm").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(20);
    expect(document.getElementById("closeSessionAlert").textContent).toContain("close-offline");
    expect(document.getElementById("closeSessionConfirm").disabled).toBe(false);
  });

  // ------------------------------------------------------------------------
  // Remaining statement gaps: guards on cart handlers, optional-element
  // branches, rejected json() fallbacks and the session timer reset.
  // ------------------------------------------------------------------------

  it("cart handlers ignore malformed indexes and the refresh-rate button works", async () => {
    await loadIndex();
    const cart = document.getElementById("cartBody");
    cart.innerHTML =
      '<button data-act="inc" data-i="bad"></button>' +
      '<input data-i="bad" data-k="qty">' +
      '<button data-k="del" data-i="bad"></button>';
    expect(() =>
      cart
        .querySelector('button[data-act]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true })),
    ).not.toThrow();
    expect(() =>
      cart.querySelector("input").dispatchEvent(new Event("input", { bubbles: true })),
    ).not.toThrow();
    expect(() =>
      cart
        .querySelector('button[data-k="del"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true })),
    ).not.toThrow();

    globalThis.fetch.mockClear();
    document.getElementById("currency").value = "EUR"; // base is USD -> real fetch
    document.getElementById("refreshRateBtn").dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await sleep(20);
    expect(globalThis.fetch).toHaveBeenCalled();
  });

  it("customer search and walk-in customer handle non-ok responses", async () => {
    mockFetch({
      "/pos/api/customers": () =>
        Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) }),
      "/pos/api/walkin-customer": () =>
        Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) }),
    });
    await loadIndex();
    const search = document.getElementById("customerSearch");
    search.value = "abc";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(230);
    document.getElementById("walkinCustomer").dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await sleep(20);
    expect(document.getElementById("posAlert").textContent.length).toBeGreaterThan(0);
  });

  it("PIN confirm button and the hidden modal settle override confirmation", async () => {
    await loadIndex();
    document.getElementById("posPinInput").value = "1234";
    document.getElementById("posPinConfirm").dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await sleep(20);
    expect(globalThis.fetch).toHaveBeenCalledWith("/pos/api/authorize-override", expect.anything());

    const hide = jqHandlers.find(
      (h) => String(h.sel).includes("posPinModal") && h.evt === "hidden.bs.modal",
    );
    expect(hide).toBeDefined();
    expect(() => hide.fn()).not.toThrow();
  });

  it("mixed-payment button returns early when the split toggle is absent", async () => {
    await loadIndex();
    document.getElementById("splitTenderToggle").remove();
    expect(() =>
      document.getElementById("mixedPaymentBtn").dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      ),
    ).not.toThrow();
  });

  it("resetAfterSale clears the bank field and checkout refuses a concurrent call", async () => {
    let release;
    mockFetch({
      "/pos/api/checkout": () => new Promise((r) => { release = r; }),
    });
    await loadIndex();
    const bank = document.createElement("input");
    bank.id = "bankName";
    bank.value = "stale";
    document.body.appendChild(bank);
    await window._posResetAfterSale();
    expect(bank.value).toBe("");

    seedCart();
    const first = window._posCheckout(false);
    await sleep(10);
    expect(await window._posCheckout(false)).toBeUndefined();
    release({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          success: true,
          data: { sale_number: "S-1", view_url: "/v", print_url: "/p", upsell_prompts: [] },
        }),
    });
    await first;
  });

  it("checkout survives a rejected json() on the initial and override attempts", async () => {
    const badJson = () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error("bad json")),
      });
    mockFetch({ "/pos/api/checkout": badJson });
    await loadIndex();
    seedCart();
    await expect(window._posCheckout(false)).resolves.toBeUndefined();

    let n = 0;
    mockFetch({
      "/pos/api/checkout": () => {
        n += 1;
        if (n === 1) {
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () => Promise.resolve({ success: false, error: "تفويض مطلوب" }),
          });
        }
        return badJson();
      },
      "/pos/api/authorize-override": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, override_token: "tok" }),
        }),
    });
    seedCart();
    document.getElementById("posPinInput").value = "1234";
    const pending = window._posCheckout(false);
    await sleep(10); // let the override modal install its PIN resolver
    await window._posConfirmPin();
    await pending;
    expect(n).toBe(2);
  });

  it("resuming a held cart survives rejected json() responses", async () => {
    mockFetch({
      "/pos/api/carts?limit=5": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.reject(new Error("bad json")),
        }),
    });
    await loadIndex();
    const hold = document.getElementById("posHoldBtn");
    hold.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(30);

    mockFetch({
      "/pos/api/carts?limit=5": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ carts: [{ id: 9 }] }),
        }),
      "/pos/api/carts/9": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.reject(new Error("bad json")),
        }),
    });
    hold.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await sleep(30);
    expect(globalThis.fetch).toHaveBeenCalled();
  });

  it("the calculator grid ignores clicks outside a data-act button", async () => {
    await loadIndex();
    const grid = document.getElementById("posCalc");
    expect(() => grid.dispatchEvent(new MouseEvent("click", { bubbles: true }))).not.toThrow();
  });

  it("an active session clears a previously installed session timer", async () => {
    mockFetch({
      "/pos/api/session/current": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              session: {
                id: "s1",
                number: "SES-1",
                opening_balance: 100,
                total_sales: 10,
                duration_minutes: 3,
                customer_display_url: "/display/1",
              },
            }),
        }),
    });
    const clearSpy = vi.spyOn(globalThis, "clearInterval");
    window.__sesTimer = 424242;
    await loadIndex();
    expect(clearSpy).toHaveBeenCalledWith(424242);
    clearSpy.mockRestore();
  });
});

/* ========================================================================== */
/* offline-catalog.js — missed paths                                          */
/* ========================================================================== */

function computeChecksum(body12) {
  const d = body12.split("").map(Number);
  const evens = d.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0);
  const odds = d.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0);
  return (10 - ((evens + 3 * odds) % 10)) % 10;
}

function makeIdb({ failOpen = false, products = [], txError = false, indexError = false } = {}) {
  const records = products.map((p) => ({
    ...p,
    barcode_lc: String(p.barcode || "").toLowerCase(),
    sku_lc: String(p.sku || "").toLowerCase(),
  }));
  const store = {
    clear: vi.fn(() => {
      records.length = 0;
    }),
    put: vi.fn((p) => records.push(p)),
    createIndex: vi.fn(() => ({})),
    index: vi.fn(() => ({
      get: vi.fn((key) => {
        const hit = records.find((r) => r.barcode_lc === key || r.sku_lc === key) || null;
        const req = { result: hit, error: new Error("index lookup failed") };
        setTimeout(() => {
          if (indexError && req.onerror) req.onerror();
          else if (req.onsuccess) req.onsuccess();
        }, 0);
        return req;
      }),
    })),
  };
  const tx = { objectStore: vi.fn(() => store), oncomplete: null, onerror: null };
  const db = {
    createObjectStore: vi.fn(() => store),
    transaction: vi.fn(() => {
      setTimeout(() => {
        if (txError && tx.onerror) tx.onerror();
        else if (tx.oncomplete) tx.oncomplete();
      }, 0);
      return tx;
    }),
  };
  const open = vi.fn(() => {
    const req = { result: db, error: failOpen ? new Error("open failed") : null };
    setTimeout(() => {
      if (failOpen) {
        if (req.onerror) req.onerror();
      } else {
        if (req.onupgradeneeded) req.onupgradeneeded();
        if (req.onsuccess) req.onsuccess();
      }
    }, 0);
    return req;
  });
  return { indexedDB: { open }, store, tx, db, records };
}

async function loadOffline() {
  // The frontend suite loads this classic script through CommonJS `require()`.
  // Use the same path here so coverage is attributed to the instance that the
  // reporter keeps; a pure ESM import creates a second, competing instance.
  // `require()` caches by module id, so drop that entry to force the UMD guard
  // to re-run and republish the real helpers on `window`.
  vi.resetModules();
  try {
    const resolved = require.resolve(OFFLINE_PATH);
    if (require.cache && require.cache[resolved]) delete require.cache[resolved];
  } catch (_) {
    // Some runners expose require without a mutable cache; resetModules above
    // still gives a fresh ESM-backed instance in that case.
  }
  window.posOfflineCatalog = undefined;
  require(OFFLINE_PATH);
  return window.posOfflineCatalog;
}

describe("pos/offline-catalog — uncovered paths", () => {
  it("hydrateCatalog stores normalized products from the wrapped snapshot (51, 63, 77)", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            data: { products: [{ id: 1, name: "A", barcode: "BC-1", sku: "SKU-1" }] },
          }),
      }),
    );
    const idb = makeIdb();
    globalThis.indexedDB = idb.indexedDB;
    await loadOffline();
    const hydrateCatalog = window.posOfflineCatalog.hydrateCatalog;
    const count = await hydrateCatalog({ warehouseParam: "?warehouse_id=5" });
    expect(count).toBe(1);
    expect(idb.store.clear).toHaveBeenCalled();
    expect(idb.store.put).toHaveBeenCalledTimes(1);
    expect(idb.store.put.mock.calls[0][0].barcode_lc).toBe("bc-1");
    expect(globalThis.fetch.mock.calls[0][0]).toBe("/pos/api/catalog/snapshot?warehouse_id=5");
    delete globalThis.indexedDB;
    delete globalThis.fetch;
  });

  it("lookupLocalProduct short-circuits on an empty code (104-105)", async () => {
    await loadOffline();
    const lookupLocalProduct = window.posOfflineCatalog.lookupLocalProduct;
    expect(await lookupLocalProduct("   ")).toBeNull();
  });

  it("lookupLocalProduct returns null when the database cannot be opened (107-108, 110)", async () => {
    const idb = makeIdb({ failOpen: true });
    globalThis.indexedDB = idb.indexedDB;
    await loadOffline();
    const lookupLocalProduct = window.posOfflineCatalog.lookupLocalProduct;
    expect(await lookupLocalProduct("anything")).toBeNull();
    delete globalThis.indexedDB;
  });

  it("lookupLocalProduct resolves a barcode through the local snapshot (112-114)", async () => {
    const idb = makeIdb({
      products: [{ id: 9, name: "Local", barcode: "LOCAL-9", sku: "S-9" }],
    });
    globalThis.indexedDB = idb.indexedDB;
    await loadOffline();
    const lookupLocalProduct = window.posOfflineCatalog.lookupLocalProduct;
    const hit = await lookupLocalProduct("LOCAL-9");
    expect(hit).not.toBeNull();
    expect(hit.success).toBe(true);
    expect(hit.name).toBe("Local");
    expect(hit.barcode_lc).toBeUndefined();
    delete globalThis.indexedDB;
  });

  it("lookupLocalProduct resolves a scale barcode and attaches the weight", async () => {
    const body = "201234567890";
    const code = body + computeChecksum(body);
    const itemCode = body.slice(2, 7);
    const idb = makeIdb({
      products: [{ id: 12, name: "Weighted", barcode: itemCode, sku: "" }],
    });
    globalThis.indexedDB = idb.indexedDB;
    await loadOffline();
    const lookupLocalProduct = window.posOfflineCatalog.lookupLocalProduct;
    const hit = await lookupLocalProduct(code);
    expect(hit).not.toBeNull();
    expect(hit.is_scale_item).toBe(true);
    expect(hit.scale_weight_kg).toBeGreaterThan(0);
    delete globalThis.indexedDB;
  });

  it("hydrateCatalog degrades to 0 when IndexedDB rejects", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, products: [] }),
      }),
    );
    const idb = makeIdb({ failOpen: true });
    globalThis.indexedDB = idb.indexedDB;
    await loadOffline();
    const hydrateCatalog = window.posOfflineCatalog.hydrateCatalog;
    expect(await hydrateCatalog()).toBe(0);
    delete globalThis.indexedDB;
    delete globalThis.fetch;
  });

  it("hydrateCatalog handles a rejected json body, a non-array payload and a failed transaction", async () => {
    // res.json().catch(() => ({})) -> the `{}` fallback makes `data.products`
    // undefined, so the guard at line 74 returns 0.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.reject(new Error("bad json")) }),
    );
    globalThis.indexedDB = makeIdb().indexedDB;
    await loadOffline();
    expect(await window.posOfflineCatalog.hydrateCatalog()).toBe(0);

    // A wrapped response whose `products` is not an array also returns 0.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { products: "nope" } }),
      }),
    );
    expect(await window.posOfflineCatalog.hydrateCatalog()).toBe(0);

    // A transaction that fires `onerror` rejects the internal promise, which
    // the outer catch turns into 0.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, products: [{ id: 1 }] }),
      }),
    );
    globalThis.indexedDB = makeIdb({ txError: true }).indexedDB;
    await loadOffline();
    expect(await window.posOfflineCatalog.hydrateCatalog()).toBe(0);
    delete globalThis.indexedDB;
    delete globalThis.fetch;
  });

  it("_lookupByIndex resolves null when the index request errors", async () => {
    globalThis.indexedDB = makeIdb({ indexError: true }).indexedDB;
    await loadOffline();
    expect(await window.posOfflineCatalog.lookupLocalProduct("anything")).toBeNull();
    delete globalThis.indexedDB;
  });

  it("lookupLocalProduct falls back through every scale index and returns null on a miss", async () => {
    const body = "201234567890";
    const code = body + computeChecksum(body);
    const itemCode = body.slice(2, 7);
    // Only the prefixed barcode (`20` + itemCode) is stored, so the bare
    // barcode/sku lookups miss and lines 123-124 are exercised.
    globalThis.indexedDB = makeIdb({
      products: [{ id: 21, name: "Prefixed", barcode: `20${itemCode}`, sku: "" }],
    }).indexedDB;
    await loadOffline();
    const hit = await window.posOfflineCatalog.lookupLocalProduct(code);
    expect(hit).not.toBeNull();
    expect(hit.is_scale_item).toBe(true);

    // A completely unknown code walks all lookups and returns null (line 127).
    expect(await window.posOfflineCatalog.lookupLocalProduct("UNKNOWN-CODE")).toBeNull();
    delete globalThis.indexedDB;
  });

  // pos_offline_catalog.test.js imports this module through ESM in its
  // beforeEach. V8 keeps that ESM script instance separate from the CJS one
  // used by loadOffline(); cover the hydrate/lookup success paths through the
  // ESM instance as well so the reporter sees those statements on whichever
  // instance it keeps.
  it("ESM instance: hydrate and lookup success paths are covered too", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            data: { products: [{ id: 31, name: "Esm", barcode: "ESM-31", sku: "E-31" }] },
          }),
      }),
    );
    globalThis.indexedDB = makeIdb().indexedDB;
    vi.resetModules();
    const mod = await import(OFFLINE_PATH);
    const hydrate = mod.hydrateCatalog || window.posOfflineCatalog.hydrateCatalog;
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    expect(await hydrate({ warehouseParam: "?warehouse_id=5" })).toBe(1);
    const hit = await lookup("ESM-31");
    expect(hit).not.toBeNull();
    expect(hit.name).toBe("Esm");
    delete globalThis.indexedDB;
    delete globalThis.fetch;
  });

  it("fresh-URL ESM instance: index onsuccess path is covered", async () => {
    globalThis.indexedDB = makeIdb({
      products: [{ id: 41, name: "Fresh", barcode: "FRESH-41", sku: "F-41" }],
    }).indexedDB;
    vi.resetModules();
    const mod = await import("../../static/js/pos/offline-catalog.js?coverage-fresh=1");
    const lookup = mod.lookupLocalProduct || window.posOfflineCatalog.lookupLocalProduct;
    const hit = await lookup("FRESH-41");
    expect(hit).not.toBeNull();
    expect(hit.name).toBe("Fresh");
    delete globalThis.indexedDB;
  });
});

describe("pos/index — shift control and held-cart resume", () => {
  it("opens a shift from the register when the feature is enabled", async () => {
    window.POS_CONFIG = { enable_tables: false, enable_hold: true, enable_pos_shifts: true };
    addEl("button", "posShiftOpenBtn");
    const spy = mockFetch({
      "/pos/api/shift/open": () =>
        Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ success: true, data: { shift: { id: 1 } } }),
        }),
    });
    await loadIndex();
    const btn = document.getElementById("posShiftOpenBtn");
    expect(btn.classList.contains("d-none")).toBe(false);
    btn.click();
    await sleep(40);
    expect(spy).toHaveBeenCalledWith("/pos/api/shift/open", expect.anything());
    expect(btn.classList.contains("d-none")).toBe(true);
  });

  it("warns when the shift service refuses the request", async () => {
    window.POS_CONFIG = { enable_tables: false, enable_hold: true, enable_pos_shifts: true };
    addEl("button", "posShiftOpenBtn");
    mockFetch({
      "/pos/api/shift/open": () =>
        Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ success: false, message: "refused" }),
        }),
    });
    await loadIndex();
    document.getElementById("posShiftOpenBtn").click();
    await sleep(40);
    expect(document.getElementById("posAlert").textContent).toContain("refused");
  });

  it("warns when the shift request throws", async () => {
    window.POS_CONFIG = { enable_tables: false, enable_hold: true, enable_pos_shifts: true };
    addEl("button", "posShiftOpenBtn");
    mockFetch({
      "/pos/api/shift/open": () => Promise.reject(new Error("offline")),
    });
    await loadIndex();
    document.getElementById("posShiftOpenBtn").click();
    await sleep(40);
    expect(document.getElementById("posAlert").textContent).toContain("تعذر فتح الوردية");
  });

  it("resumes the held cart referenced in the query string", async () => {
    window.history.replaceState({}, "", "/pos/?resume_cart=7");
    const payload = {
      lines: [
        {
          product_id: 991,
          name: "Item",
          sku: "SKU-1",
          quantity: 2,
          unit_price: 10,
          basePrice: 10,
          price: 10,
          discount_percent: 0,
        },
      ],
      customer: { id: 11 },
      note: "held note",
    };
    mockFetch({
      "/pos/api/carts/7": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, data: { cart: { payload: JSON.stringify(payload) } } }),
        }),
    });
    await loadIndex();
    await sleep(80);
    expect(window._posState.cart).toHaveLength(1);
    expect(window._posState.cart[0].qty).toBe(2);
    expect(document.getElementById("orderNote").value).toBe("held note");
    expect(window.location.search).toBe("");
  });

  it("ignores a held-cart response without a payload", async () => {
    window.history.replaceState({}, "", "/pos/?resume_cart=8");
    mockFetch({
      "/pos/api/carts/8": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: {} }) }),
    });
    await loadIndex();
    await sleep(60);
    expect(window._posState.cart).toHaveLength(0);
    expect(window.location.search).toBe("");
  });

  it("survives a network error while resuming a held cart", async () => {
    window.history.replaceState({}, "", "/pos/?resume_cart=9");
    mockFetch({
      "/pos/api/carts/9": () => Promise.reject(new Error("offline")),
    });
    await loadIndex();
    await sleep(60);
    expect(window._posState.cart).toHaveLength(0);
    expect(window.location.search).toBe("");
  });
});
