/**
 * Final statement-coverage tests for three classic (IIFE) scripts:
 *   static/js/shop-search.js
 *   static/js/delete-manager.js
 *   static/js/base-helpers.js
 *
 * The rest of the suite loads these files with ESM `import()`; the frontend
 * suite loads classic scripts with CommonJS `require()`.  V8 keys script
 * instances by URL, so the two variants compete for the same statement ids and
 * the reporter keeps one instance while zeroing the other.  Every scenario
 * below is therefore run twice: once through `require()` (the CJS path the
 * reporter keeps) and once through a fresh-URL `import()` (an additive instance
 * whose counts merge by file path).  Together the two paths leave no
 * statements uncovered whichever instance the reporter decides to keep.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const SHOP_PATH = "../../static/js/shop-search.js";
const DELETE_PATH = "../../static/js/delete-manager.js";
const HELPERS_PATH = "../../static/js/base-helpers.js";

const sleep = (ms = 0) => new Promise((r) => setTimeout(r, ms));

/**
 * Load a classic script through the CommonJS path.  `require()` caches by
 * module id, so drop the entry to force the IIFE to run again and republish
 * its helpers on `window`.
 */
function loadCjs(path) {
  vi.resetModules();
  try {
    const resolved = require.resolve(path);
    if (require.cache && require.cache[resolved]) delete require.cache[resolved];
  } catch (_) {
    // Some runners expose require without a writable cache; resetModules()
    // still gives a fresh instance in that case.
  }
  require(path);
}

/* ========================================================================== */
/* shop-search.js                                                              */
/* ========================================================================== */

describe("shop-search.js — final statement gaps", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    document.body.innerHTML =
      '<form id="s"><input name="q" data-search-autocomplete></form>' +
      '<div class="ps-autocomplete-results"></div>';
    document.body.setAttribute("data-store-slug", "demo");
    delete window.AzadUtils;
    vi.useFakeTimers();
    vi.resetModules();
  });

  afterEach(() => {
    vi.useRealTimers();
    globalThis.fetch = originalFetch;
    window.fetch = originalFetch;
    document.body.removeAttribute("data-store-slug");
    document.body.innerHTML = "";
    delete window.AzadUtils;
    vi.resetModules();
  });

  function respond(results) {
    const spy = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ results }) }),
    );
    globalThis.fetch = spy;
    window.fetch = spy;
    return spy;
  }

  async function type(value = "ab") {
    const input = document.querySelector('input[name="q"]');
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    await Promise.resolve();
    return document.querySelector(".ps-autocomplete-results");
  }

  /** The complete set of gap scenarios, parameterised by the loader. */
  async function scenarios(load) {
    // Guard: no store slug -> the IIFE returns before wiring anything.
    document.body.removeAttribute("data-store-slug");
    await load();
    expect(document.querySelector(".ps-autocomplete-results").innerHTML).toBe("");
    document.body.setAttribute("data-store-slug", "demo");

    // AzadUtils delegates cover the escapeHtml/safeRedirectUrl fast paths.
    const escapeHtml = vi.fn((s) => `E:${s}`);
    const safeRedirectUrl = vi.fn((u) => `/safe-${u}`);
    window.AzadUtils = { escapeHtml, safeRedirectUrl };
    respond([{ name: "X", url: "/p/1", image: "/i.png", price: "2", currency: "ILS" }]);
    await load();
    const delegated = await type();
    expect(delegated.querySelectorAll(".ps-autocomplete-item")).toHaveLength(1);
    expect(escapeHtml).toHaveBeenCalledWith("X");
    expect(safeRedirectUrl).toHaveBeenCalledWith("/p/1");

    // Without AzadUtils the built-in sanitizer handles null, same-origin,
    // cross-origin and malformed URLs (the try/catch and both return paths).
    delete window.AzadUtils;
    respond([
      { name: "Null", url: null, price: 1 },
      { name: "Same", url: `${window.location.origin}/p/2?x=1#f`, price: 1 },
      { name: "Cross", url: "https://evil.example/x", price: 1 },
      { name: "Bad", url: "http://[invalid", price: 1 },
    ]);
    await load();
    const fallback = await type();
    const links = Array.from(fallback.querySelectorAll(".ps-autocomplete-item"));
    expect(links).toHaveLength(4);
    expect(links[0].getAttribute("href")).toBe("#");
    expect(links[1].getAttribute("href")).toBe("/p/2?x=1#f");
    expect(links[2].getAttribute("href")).toBe("#");
    expect(links[3].getAttribute("href")).toBe("#");

    // Result click, every keydown branch and the outside-click dismissal.
    const input = document.querySelector('input[name="q"]');
    links[0].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    // Short query early return and the rejected-fetch path.
    input.value = "a";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    globalThis.fetch = window.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    input.value = "zz";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    expect(fallback.style.display).toBe("none");
  }

  it("CJS instance: slug guard, AzadUtils delegates and built-in URL sanitizer", async () => {
    await scenarios(async () => loadCjs(SHOP_PATH));
  });

  it("fresh-URL ESM instance: the same gap branches are covered", async () => {
    await scenarios(async () => {
      vi.resetModules(); // import() caches by URL; re-run the IIFE each time.
      await import("../../static/js/shop-search.js?coverage-e=1");
    });
  });
});

/* ========================================================================== */
/* delete-manager.js                                                           */
/* ========================================================================== */

describe("delete-manager.js — final statement gaps", () => {
  let submittedForms;

  beforeEach(() => {
    submittedForms = [];
    document.body.innerHTML = '<input name="csrf_token" value="tok">';
    delete window.AzadUtils;
    global.Swal = window.Swal = {
      // A synchronous thenable so the `.then(...)` chains in deleteMultiple
      // and restoreItem run without a real modal.
      fire: vi.fn(() => ({
        then(fn) {
          fn({ isConfirmed: true });
          return this;
        },
      })),
      showValidationMessage: vi.fn(),
      isLoading: vi.fn(() => false),
    };
    global.toastr = window.toastr = { success: vi.fn(), warning: vi.fn() };
    global.fetch = window.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    global.$ = window.$ = (arg) => {
      const api = {
        on: () => api,
        val: () => "tok",
        attr: () => "tok",
        data: () => undefined,
        closest: () => api,
        fadeOut: (_ms, cb) => {
          if (typeof cb === "function") cb();
          return api;
        },
        remove: () => api,
        ajax: () => Promise.resolve({}),
      };
      if (typeof arg === "function") arg();
      return api;
    };
    global.jQuery = window.jQuery = global.$;
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function () {
      submittedForms.push(this);
    });
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    delete window.AzadUtils;
    delete global.Swal;
    delete window.Swal;
    delete global.toastr;
    delete window.toastr;
    delete global.$;
    delete window.$;
    delete global.jQuery;
    delete window.jQuery;
    delete window.deleteItem;
    delete window.deleteMultiple;
    delete window.deleteTableRow;
    delete window.restoreItem;
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function scenarios(load) {
    await load();

    // The restore URL builders for payments, expenses and cheques are only
    // evaluated when restoreItem resolves the action URL.
    for (const type of ["payments", "expenses", "cheques"]) {
      window.restoreItem(7, type, "Item");
    }
    // Each restore fires the confirmation modal and (via the thenable) a
    // success modal, so filter on the confirmation title.
    const restores = global.Swal.fire.mock.calls.filter(
      ([cfg]) => cfg.title === "استعادة العنصر",
    );
    expect(restores).toHaveLength(3);

    // AzadUtils.safeRedirectUrl is the preferred sanitizer on the redirect
    // path of deleteMultiple.
    const safeRedirectUrl = vi.fn(() => "/safe");
    window.AzadUtils = { safeRedirectUrl };
    global.Swal.fire.mockClear();
    window.deleteMultiple([1], "customers", "/target");
    expect(safeRedirectUrl).toHaveBeenCalledWith("/target");

    // Local fallback: same-origin, cross-origin and malformed redirect URLs.
    delete window.AzadUtils;
    global.Swal.fire.mockClear();
    window.deleteMultiple([1], "customers", `${window.location.origin}/go?x=1#f`);
    window.deleteMultiple([1], "customers", "https://evil.example/x");
    window.deleteMultiple([1], "customers", "http://[invalid");
    expect(global.Swal.fire).toHaveBeenCalled();
  }

  // Every other suite loads this classic script with ESM `import()`; keep the
  // same instance so the reporter merges counts additively instead of pitting
  // a competing CommonJS instance against it.
  it("restore builders and every safe-redirect branch", async () => {
    await scenarios(async () => {
      vi.resetModules();
      await import(DELETE_PATH);
    });
  });
});

/* ========================================================================== */
/* base-helpers.js                                                             */
/* ========================================================================== */

describe("base-helpers.js — final statement gaps", () => {
  let ajaxErrorHandler;
  let observers;
  let originalFetch;

  beforeEach(() => {
    ajaxErrorHandler = null;
    observers = [];
    originalFetch = globalThis.fetch;
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    document.body.innerHTML =
      '<input id="calcDisplayClassic">' +
      '<div id="calcClassicButtons"><span id="notAButton">x</span></div>' +
      '<input id="calcDisplayScientific">' +
      '<div id="calcScientificButtons"></div>';
    window.t = (k) => k;
    window._LOG_ENDPOINT = "/client-log";
    window._FX_API_URL = "/api/fx";
    window._FX_BASE_CURRENCY = "USD";
    localStorage.clear();
    delete window.AzadUtils;
    delete window.AzadHelpers;
    globalThis.fetch = window.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ rates: {} }) }),
    );

    const api = () => ({
      on: () => api(),
      ajaxError: (fn) => {
        ajaxErrorHandler = fn;
      },
      attr: () => "tok",
      val: () => "",
      ready: (fn) => {
        if (typeof fn === "function") fn();
        return api();
      },
    });
    const $ = (arg) => {
      if (typeof arg === "function") arg();
      return api();
    };
    $.ajaxSetup = () => {};
    $.fn = {};
    global.$ = window.$ = $;
    global.jQuery = window.jQuery = $;

    window.PerformanceObserver = class {
      constructor(cb) {
        this.cb = cb;
        observers.push(this);
      }
      observe(opts) {
        this.opts = opts;
      }
    };
    vi.resetModules();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    delete window.fetch;
    delete window.AzadUtils;
    delete window.AzadHelpers;
    delete window.PerformanceObserver;
    delete global.$;
    delete window.$;
    delete global.jQuery;
    delete window.jQuery;
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function scenarios(load) {
    delete window.AzadUtils;
    await load();
    const h = window.AzadHelpers;
    expect(typeof h.escapeHtml).toBe("function");
    expect(typeof h.safeRedirectUrl).toBe("function");

    // escapeHtml's replace chain and every safeRedirectUrl branch.
    expect(h.escapeHtml('<a & "b">')).toBe("&lt;a &amp; &quot;b&quot;&gt;");
    expect(h.safeRedirectUrl(null)).toBeNull();
    expect(h.safeRedirectUrl("   ")).toBeNull();
    expect(h.safeRedirectUrl("/relative")).toBe("/relative");
    expect(h.safeRedirectUrl("#frag", { allowHash: true })).toBe("#frag");
    expect(h.safeRedirectUrl(`${window.location.origin}/p/1?x=1#f`)).toBe("/p/1?x=1#f");
    expect(h.safeRedirectUrl("http://[invalid")).toBeNull();
    expect(h.safeRedirectUrl("https://evil.example/x")).toBeNull();

    // Function call with a missing ")" reaches the parser's error() guard.
    expect(h.safeEval("sin(1")).toBe("ERR");

    // wirePad ignores clicks not on a [data-calc] button.
    const container = document.getElementById("calcClassicButtons");
    // wirePad replaces the container's innerHTML, so click the container
    // itself: e.target.closest("[data-calc]") is null on that path.
    expect(() =>
      container.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    ).not.toThrow();
    expect(container.querySelectorAll("button").length).toBeGreaterThan(0);

    // jQuery ajaxError and both PerformanceObserver callbacks.
    expect(typeof ajaxErrorHandler).toBe("function");
    ajaxErrorHandler(
      {},
      { status: 500, responseText: '{"a":1}' },
      { url: "/api/report", type: "GET" },
      "boom",
    );
    // The endpoint's own errors are skipped (shouldSkipRequest early return).
    ajaxErrorHandler(
      {},
      { status: 500 },
      { url: window._LOG_ENDPOINT, type: "POST" },
      "self-report",
    );
    const longTask = observers.find((o) => o.opts && o.opts.entryTypes);
    const layoutShift = observers.find((o) => o.opts && o.opts.type === "layout-shift");
    expect(longTask).toBeDefined();
    expect(layoutShift).toBeDefined();
    longTask.cb({ getEntries: () => [{ duration: 400 }] });
    layoutShift.cb({ getEntries: () => [{ hadRecentInput: false, value: 0.5 }] });
    layoutShift.cb({ getEntries: () => [{ hadRecentInput: true, value: 0.5 }] });

    // More than 100 distinct errors clears the dedupe map; more than 20
    // reports in the window hits the rate limit guard.
    for (let i = 0; i < 105; i += 1) {
      const ev = new Event("error");
      Object.defineProperties(ev, {
        message: { value: `err-${i}` },
        filename: { value: "s.js" },
        lineno: { value: 0 },
        colno: { value: 0 },
      });
      window.dispatchEvent(ev);
    }
    await sleep(0);
  }

  // base-helpers has 575 statements, most covered by other ESM suites. Using
  // require() here would make the reporter keep a CJS instance with hundreds
  // of zeroed statements, so stay on the shared ESM instance.
  it("helper parsers, DOM wiring and telemetry guard branches", async () => {
    await scenarios(async () => {
      vi.resetModules();
      await import(HELPERS_PATH);
    });
  });
});
