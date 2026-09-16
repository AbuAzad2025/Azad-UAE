import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// tests/vitest/setup.js provides global.$ / window.$ — save and restore them
// around the per-describe mocks instead of deleting them.
const SETUP_DOLLAR = global.$;
const SETUP_JQUERY = global.jQuery;

function restoreGlobals() {
  global.$ = SETUP_DOLLAR;
  window.$ = SETUP_DOLLAR;
  if (SETUP_JQUERY === undefined) {
    delete global.jQuery;
    delete window.jQuery;
  } else {
    global.jQuery = SETUP_JQUERY;
    window.jQuery = SETUP_JQUERY;
  }
}

// ---------- customer-select ----------

let select2Calls;
let destroyCalls;
let loadHandlers;

function makeSelectJQuery() {
  const mk = (els) => {
    const getEl = () => els[0] || null;
    const api = {
      els,
      get length() {
        return els.length;
      },
      hasClass(cls) {
        return getEl()?.classList.contains(cls) || false;
      },
      each(fn) {
        els.forEach((el, i) => fn.call(el, i, el));
        return api;
      },
      select2(arg) {
        if (arg === "destroy") destroyCalls.push(getEl());
        else select2Calls.push({ el: getEl(), opts: arg });
        return api;
      },
      on(evt, fn) {
        const el = getEl();
        if (el) el.addEventListener(evt, fn);
        return api;
      },
      attr(name, val) {
        const el = getEl();
        if (!el) return val !== undefined ? api : undefined;
        if (val !== undefined) {
          el.setAttribute(name, val);
          return api;
        }
        return el.getAttribute(name);
      },
    };
    return api;
  };

  const $ = (arg) => {
    if (arg === document) {
      return {
        ready(fn) {
          fn();
          return this;
        },
        on(evt, fn) {
          document.addEventListener(evt, fn);
          return this;
        },
      };
    }
    if (arg === window) {
      return {
        on(evt, fn) {
          loadHandlers.push({ evt, fn });
          window.addEventListener(evt, fn);
          return this;
        },
      };
    }
    if (typeof arg === "string") {
      let nodes = [];
      try {
        nodes = Array.from(document.querySelectorAll(arg));
      } catch {
        nodes = [];
      }
      return mk(nodes);
    }
    return mk(arg ? [arg] : []);
  };
  return $;
}

describe("customer-select.js gaps", () => {
  beforeEach(() => {
    select2Calls = [];
    destroyCalls = [];
    loadHandlers = [];
    document.body.innerHTML = "";
    const $ = makeSelectJQuery();
    global.$ = $;
    window.$ = $;
    global.jQuery = $;
    window.jQuery = $;
    vi.useFakeTimers();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    restoreGlobals();
    delete window.SmartSearch;
    vi.useRealTimers();
    vi.resetModules();
  });

  async function load() {
    await import("../../static/js/customer-select.js");
    return window.SmartSearch;
  }

  function addSelect(cls, initialized) {
    const el = document.createElement("select");
    el.className = cls + (initialized ? " select2-hidden-accessible" : "");
    document.body.appendChild(el);
    return el;
  }

  it("destroys existing select2 instances before re-init", async () => {
    addSelect("customer-select", true);
    addSelect("supplier-select", true);
    addSelect("product-select", true);
    const ss = await load();
    ss.init();
    expect(destroyCalls.length).toBe(3);
    expect(select2Calls.length).toBe(3);
  });

  it("builds supplier and product ajax data params", async () => {
    addSelect("supplier-select", false);
    addSelect("product-select", false);
    const ss = await load();
    ss.init();
    const supplier = select2Calls.find((c) => c.opts.ajax.url === "/suppliers/api/search");
    expect(supplier.opts.ajax.data({ term: "a", page: 3 })).toEqual({ q: "a", page: 3 });
    expect(supplier.opts.ajax.data({})).toEqual({ q: "", page: 1 });
    const product = select2Calls.find((c) => c.opts.ajax.url === "/products/api/search");
    expect(product.opts.ajax.data({ term: "b" })).toEqual({ q: "b", page: 1 });
  });

  it("formats customer and supplier selections with ids", async () => {
    const ss = await load();
    expect(ss.formatCustomerSelection({ id: 1, name: "A", phone: "050" })).toBe("A - 050");
    expect(ss.formatCustomerSelection({ text: "t" })).toBe("t");
    expect(ss.formatSupplierSelection({ id: 2, name: "B", phone: "" })).toBe("B");
    expect(ss.formatSupplierSelection({ text: "u" })).toBe("u");
  });

  it("formats product result loading/empty states and selections", async () => {
    const ss = await load();
    expect(ss.formatProductResult({ loading: true })).toBe(window.t("searching"));
    expect(ss.formatProductResult({ text: "none" })).toBe("none");
    expect(ss.formatProductSelection({ id: 3, name: "P", code: "C1" })).toBe("P (C1)");
    expect(ss.formatProductSelection({ text: "z" })).toBe("z");
  });

  it("re-initialises on window load", async () => {
    addSelect("customer-select", false);
    const ss = await load();
    expect(loadHandlers.map((h) => h.evt)).toContain("load");
    window.dispatchEvent(new Event("load"));
    await vi.advanceTimersByTimeAsync(200);
    expect(select2Calls.length).toBeGreaterThan(0);
    expect(ss).toBeTruthy();
  });
});

// ---------- delete-manager ----------

let swalConfigs;
let swalResolve;
let docClickHandlers;

function makeDeleteJQuery() {
  const mk = (els) => {
    const getEl = () => els[0] || null;
    return {
      els,
      get length() {
        return els.length;
      },
      data(key, value) {
        const el = getEl();
        if (!el) return value === undefined ? undefined : this;
        const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (value === undefined) return el.dataset[camel];
        el.dataset[camel] = value;
        return this;
      },
      val(v) {
        const el = getEl();
        if (v === undefined) return el ? el.value : undefined;
        if (el) el.value = v;
        return this;
      },
      attr(name) {
        return getEl()?.getAttribute(name) || undefined;
      },
      closest(sel) {
        const el = getEl()?.closest(sel);
        return mk(el ? [el] : []);
      },
      remove() {
        getEl()?.remove();
        return this;
      },
      fadeOut(_d, cb) {
        const el = getEl();
        if (el && typeof cb === "function") cb.call(el);
        return this;
      },
      trigger(evt) {
        getEl()?.dispatchEvent(new Event(evt, { bubbles: true }));
        return this;
      },
    };
  };
  const docApi = {
    ready(fn) {
      fn();
      return this;
    },
    on(evt, sel, fn) {
      docClickHandlers.push({ evt, sel, fn });
      return this;
    },
  };
  const $ = (arg) => {
    if (arg === document) return docApi;
    if (typeof arg === "string") {
      let nodes = [];
      try {
        nodes = Array.from(document.querySelectorAll(arg));
      } catch {
        nodes = [];
      }
      return mk(nodes);
    }
    return mk(arg ? [arg] : []);
  };
  $.ajax = () => Promise.resolve();
  return $;
}

describe("delete-manager.js gaps", () => {
  let origSubmit;

  beforeEach(() => {
    swalConfigs = [];
    docClickHandlers = [];
    document.body.innerHTML =
      '<input name="csrf_token" value="tok"><meta name="csrf-token" content="tok">';
    const $ = makeDeleteJQuery();
    global.$ = $;
    window.$ = $;
    global.jQuery = $;
    window.jQuery = $;
    swalResolve = { isLoading: false };
    global.Swal = window.Swal = {
      fire: (cfg) => {
        swalConfigs.push(cfg);
        return Promise.resolve({ isConfirmed: false });
      },
      showValidationMessage: vi.fn(),
      isLoading: () => swalResolve.isLoading,
    };
    origSubmit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = vi.fn();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    HTMLFormElement.prototype.submit = origSubmit;
    restoreGlobals();
    delete global.Swal;
    delete window.Swal;
    delete window.deleteItem;
    delete window.deleteMultiple;
    delete window.deleteTableRow;
    delete window.restoreItem;
    vi.resetModules();
  });

  async function load() {
    await import("../../static/js/delete-manager.js");
  }

  it("resolves delete endpoints for every entity type", async () => {
    await load();
    for (const t of ["suppliers", "purchases", "receipts", "payments", "expenses", "cheques", "users", "warehouses"]) {
      window.deleteItem(t, 7, "Item");
    }
    expect(swalConfigs.length).toBe(8);
    expect(swalConfigs[0].title).toBe("حذف مورد");
  });

  it("maps singular aliases and empty types", async () => {
    await load();
    window.deleteItem("supplier", 3, "S");
    expect(swalConfigs[0].title).toBe("حذف مورد");
    window.deleteItem("", 1, "x");
    expect(swalConfigs[1].icon).toBe("info");
  });

  it("exposes allowOutsideClick guards for bulk delete and restore", async () => {
    await load();
    window.deleteMultiple([1, 2], "sales");
    await new Promise((r) => setTimeout(r, 0));
    const bulk = swalConfigs[swalConfigs.length - 1];
    swalResolve.isLoading = true;
    expect(bulk.allowOutsideClick()).toBe(false);
    swalResolve.isLoading = false;
    expect(bulk.allowOutsideClick()).toBe(true);

    window.restoreItem(4, "sales", "F-1");
    await new Promise((r) => setTimeout(r, 0));
    const restore = swalConfigs[swalConfigs.length - 1];
    expect(restore.allowOutsideClick()).toBe(true);
  });
});

// ---------- keyboard-shortcuts ----------

describe("keyboard-shortcuts.js gaps", () => {
  let addedListeners;

  beforeEach(() => {
    addedListeners = [];
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    localStorage.clear();
    global.notify = window.notify = { info: vi.fn(), success: vi.fn() };
    vi.useFakeTimers();
    vi.resetModules();
  });

  afterEach(() => {
    (addedListeners || []).forEach(({ evt, listener }) => document.removeEventListener(evt, listener));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    delete global.notify;
    delete window.notify;
    delete window.shortcuts;
    localStorage.clear();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  function watchKeydown() {
    if (document.addEventListener.isMock) return;
    const orig = document.addEventListener.bind(document);
    vi.spyOn(document, "addEventListener").mockImplementation((evt, fn, opts) => {
      if (evt === "keydown") addedListeners.push({ evt, listener: fn });
      return orig(evt, fn, opts);
    });
  }

  function fireKey(key, extra = {}) {
    const ev = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...extra, key });
    Object.defineProperty(ev, "key", { value: key });
    (extra.target || document.body).dispatchEvent(ev);
    return ev;
  }

  async function load() {
    watchKeydown();
    await import("../../static/js/keyboard-shortcuts.js");
    return window.shortcuts;
  }

  it("builds shift-modified key strings", async () => {
    await load();
    const ev = fireKey("S", { target: document.body, shiftKey: true });
    expect(ev.defaultPrevented).toBe(false);
  });

  it("opens customers and products via alt shortcuts", async () => {
    const c = document.createElement("a");
    c.href = "/customers/list";
    document.body.appendChild(c);
    const p = document.createElement("a");
    p.href = "/products/list";
    document.body.appendChild(p);
    const clickSpy = vi.spyOn(HTMLElement.prototype, "click").mockImplementation(() => {});
    try {
      await load();
      fireKey("c", { target: document.body, altKey: true });
      fireKey("p", { target: document.body, altKey: true });
      expect(clickSpy).toHaveBeenCalledTimes(2);
    } finally {
      clickSpy.mockRestore();
    }
  });

  it("shows help on ctrl+/ and keeps an existing help button", async () => {
    document.body.innerHTML = '<button id="shortcuts-help-btn"></button>';
    const modalSpy = vi.fn(() => ({ appendTo: () => ({ modal: modalSpy }) }));
    const orig$ = global.$;
    const $ = (sel) => {
      if (sel === document) return { ready: (fn) => (fn(), { on: () => {} }) };
      if (sel === "#shortcuts-modal") return { remove: vi.fn() };
      return { appendTo: () => ({ modal: modalSpy }) };
    };
    global.$ = $;
    window.$ = $;
    try {
      const ks = await load();
      expect(document.querySelectorAll("#shortcuts-help-btn").length).toBe(1);
      fireKey("/", { target: document.body, ctrlKey: true });
      expect(modalSpy).toHaveBeenCalledWith("show");
      expect(ks).toBeTruthy();
    } finally {
      global.$ = orig$;
      window.$ = orig$;
    }
  });

  it("shows the first-load tip after delay", async () => {
    await load();
    await vi.advanceTimersByTimeAsync(2100);
    expect(window.notify.info).toHaveBeenCalledWith(
      "اضغط ? لعرض اختصارات لوحة المفاتيح",
      "نصيحة سريعة"
    );
  });
});

// ---------- ai-sales ----------

let ajaxCalls;
let fadeOutCalls;
let aiHandlers;
let aiListeners;

function makeAiJQuery() {
  const mk = (arg, els) => {
    const getEl = () => els[0] || null;
    const api = {
      els,
      get length() {
        return els.length;
      },
      val(v) {
        const el = getEl();
        if (el) {
          if (v === undefined) return el.value;
          el.value = v;
        }
        return api;
      },
      data(key, value) {
        const el = getEl();
        if (!el) return api;
        const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (value === undefined) return el.dataset[camel];
        el.dataset[camel] = value;
        return api;
      },
      parent() {
        return mk(arg, els.map((e) => e.parentElement).filter(Boolean));
      },
      find(sel) {
        const found = [];
        els.forEach((e) => e.querySelectorAll(sel).forEach((n) => found.push(n)));
        return mk(sel, found);
      },
      remove() {
        getEl()?.remove();
        return api;
      },
      after(html) {
        getEl()?.insertAdjacentHTML("afterend", html);
        return api;
      },
      empty() {
        const el = getEl();
        if (el) el.innerHTML = "";
        return api;
      },
      html(v) {
        const el = getEl();
        if (el) {
          if (v === undefined) return el.innerHTML;
          el.innerHTML = v;
        }
        return api;
      },
      each(fn) {
        els.forEach((el, i) => fn.call(el, i, el));
        return api;
      },
      fadeOut() {
        fadeOutCalls.push(arg);
        return api;
      },
      trigger(evt) {
        getEl()?.dispatchEvent(new Event(evt, { bubbles: true }));
        return api;
      },
      select2() {
        return api;
      },
    };
    return api;
  };

  const $ = (arg) => {
    if (arg === document) {
      return {
        ready(fn) {
          fn();
          return this;
        },
        on(evt, sel, fn) {
          aiHandlers.push({ evt, sel, fn });
          const listener = (e) => {
            const t = e.target && typeof e.target.closest === "function" ? e.target.closest(sel) : null;
            if (t) fn.call(t, e);
          };
          aiListeners.push({ evt, listener });
          document.addEventListener(evt, listener);
          return this;
        },
      };
    }
    if (typeof arg === "string") {
      let nodes = [];
      try {
        nodes = Array.from(document.querySelectorAll(arg));
      } catch {
        nodes = [];
      }
      return mk(arg, nodes);
    }
    return mk(arg, [arg]);
  };
  $.ajax = (opts) => {
    ajaxCalls.push(opts);
  };
  return $;
}

describe("ai-sales.js gaps", () => {
  function setupDom() {
    const meta = document.createElement("meta");
    meta.name = "csrf-token";
    meta.content = "tok123";
    document.head.appendChild(meta);
  }

  function addCustomer(value) {
    const customer = document.createElement("select");
    customer.id = "customer_id";
    const opt = document.createElement("option");
    opt.value = value;
    customer.appendChild(opt);
    customer.value = value;
    document.body.appendChild(customer);
    return customer;
  }

  function addProduct(line = "0", value = "7") {
    const product = document.createElement("select");
    product.className = "product-select";
    product.dataset.lineIndex = line;
    const opt = document.createElement("option");
    opt.value = value;
    product.appendChild(opt);
    product.value = value;
    document.body.appendChild(product);
    return product;
  }

  beforeEach(() => {
    ajaxCalls = [];
    fadeOutCalls = [];
    aiHandlers = [];
    aiListeners = [];
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    window._CURRENCY_SYMBOL = "د.إ";
    window._FX_FALLBACK_BASE = "ILS";
    const $ = makeAiJQuery();
    global.$ = $;
    window.$ = $;
    global.jQuery = $;
    window.jQuery = $;
    vi.resetModules();
  });

  afterEach(() => {
    aiListeners.forEach(({ evt, listener }) => document.removeEventListener(evt, listener));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    restoreGlobals();
    delete window._CURRENCY_SYMBOL;
    delete window._FX_FALLBACK_BASE;
    delete window._applyRecommendedPrice;
    delete window._applyMarketPrice;
    delete window.applyRecommendedPrice;
    delete window.applyMarketPrice;
    vi.resetModules();
  });

  it("bails out of price recommendation without ids", async () => {
    setupDom();
    const customer = addCustomer("");
    customer.value = "";
    addProduct("0", "7");
    await import("../../static/js/ai-sales.js");
    customer.dispatchEvent(new Event("change", { bubbles: true }));
    expect(ajaxCalls.filter((c) => c.url === "/ai/recommend-price")).toHaveLength(0);
    expect(ajaxCalls.filter((c) => c.url.startsWith("/ai/analyze-customer"))).toHaveLength(0);
  });

  it("applies a recommended price from the badge button", async () => {
    setupDom();
    addCustomer("5");
    addProduct("0", "7");
    document.body.insertAdjacentHTML("beforeend", '<input id="unit_price_0" value="0">');
    await import("../../static/js/ai-sales.js");
    document.querySelector(".product-select").dispatchEvent(new Event("change", { bubbles: true }));
    ajaxCalls.find((c) => c.url === "/ai/recommend-price").success({ recommended_price: 5.5 });
    const btn = document.getElementById("aiApplyPrice_0");
    expect(btn).toBeTruthy();
    window._applyRecommendedPrice = vi.fn();
    btn.click();
    expect(window._applyRecommendedPrice).toHaveBeenCalledWith("0", 5.5);
  });

  it("applies a global market price from the badge button", async () => {
    setupDom();
    addCustomer("5");
    addProduct("0", "7");
    document.body.insertAdjacentHTML("beforeend", '<div id="market_info_0"></div>');
    await import("../../static/js/ai-sales.js");
    document.querySelector(".product-select").dispatchEvent(new Event("change", { bubbles: true }));
    ajaxCalls
      .find((c) => c.url === "/ai/search-market-price/7")
      .success({ found: true, suggested_price_aed: 12.345, average_price_usd: 3.36 });
    const btn = document.getElementById("aiApplyMarket_0");
    expect(btn).toBeTruthy();
    window._applyMarketPrice = vi.fn();
    btn.click();
    expect(window._applyMarketPrice).toHaveBeenCalledWith("0", 12.35);
  });
});

// ---------- barcode-scanner ----------

describe("barcode-scanner.js gaps", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    delete window.BarcodeDetector;
    delete window.CameraBarcodeScannerForceJsQr;
    if (navigator.mediaDevices) delete navigator.mediaDevices;
    delete window.BarcodeScanner;
    delete window.CameraBarcodeScanner;
    delete window.setupCameraScanUI;
    delete global.alert;
    vi.resetModules();
    vi.useRealTimers();
  });

  async function load() {
    await import("../../static/js/barcode-scanner.js");
  }

  it("ignores keypresses while inactive", async () => {
    await load();
    const s = new window.BarcodeScanner({ onScan: vi.fn() });
    s.handleKeyPress({ target: document.body, key: "a" });
    expect(s.buffer).toBe("");
  });

  it("falls back to alert for camera errors by default", async () => {
    await load();
    global.alert = vi.fn();
    const video = document.createElement("video");
    const s = new window.CameraBarcodeScanner(video);
    s.onError("boom");
    expect(global.alert).toHaveBeenCalledWith("boom");
  });

  it("no-ops schedule and scan while idle, and detects nothing without a detector", async () => {
    await load();
    const video = document.createElement("video");
    const s = new window.CameraBarcodeScanner(video, { onScan: vi.fn() });
    s._scheduleNext();
    expect(s._timer).toBeNull();
    await expect(s.scan()).resolves.toBeUndefined();
    await expect(s.detectBarcode(video)).resolves.toBeNull();
  });

  it("returns null without a button", async () => {
    await load();
    expect(window.setupCameraScanUI({})).toBeNull();
    const btn = document.createElement("button");
    document.body.appendChild(btn);
    expect(window.setupCameraScanUI({ button: btn })).toBeNull();
  });

  it("opens the overlay, guards re-entry, and closes it", async () => {
    await load();
    window.BarcodeDetector = class {
      static async getSupportedFormats() {
        return ["qr_code"];
      }
      async detect() {
        return [];
      }
    };
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [] })) },
      configurable: true,
    });
    const btn = document.createElement("button");
    document.body.appendChild(btn);
    const onScan = vi.fn();
    const ui = window.setupCameraScanUI({ button: btn, onScan });
    expect(ui).toBeTruthy();
    btn.click();
    btn.click();
    await new Promise((r) => setTimeout(r, 20));
    const overlay = document.getElementById("cameraScanOverlay");
    expect(overlay).toBeTruthy();
    overlay.querySelector("button").click();
    expect(overlay.style.display).toBe("none");
    ui.stop();
  });
});
