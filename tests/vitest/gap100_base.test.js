import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const SETUP_DOLLAR = global.$;

function restoreDollar() {
  global.$ = SETUP_DOLLAR;
  window.$ = SETUP_DOLLAR;
}

function baseDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = '<meta name="csrf-token" content="tok">';
}

describe("base-helpers.js gaps", () => {
  let origFetch;
  let origWindowFetch;
  let origToastr;
  let origDebug;
  let origLogEndpoint;
  let origWarn;
  beforeEach(() => {
    try { window.addEventListener.mockRestore?.(); } catch (_) {}
    try { globalThis.__cleanupLeakedErrorHandlers?.(); } catch (_) {}
    if (!window.addEventListener.__isTrackedWrapper) {
      const nat = globalThis.__nativeWindowAddEventListener;
      if (nat) {
        const wr = (type, handler, ...rest) => {
          if (type === "error" || type === "unhandledrejection") {
            const already = globalThis.__trackedErrorHandlers.some((e) => e.target === this && e.type === type && e.handler === handler);
            if (!already) globalThis.__trackedErrorHandlers.push({ target: this, type, handler });
          }
          return nat.call(this, type, handler, ...rest);
        };
        wr.__isTrackedWrapper = true;
        window.addEventListener = wr;
      }
    }

    origFetch = global.fetch;
    origWindowFetch = window.fetch;
    origToastr = window.toastr;
    origDebug = window._DEBUG;
    origLogEndpoint = window._LOG_ENDPOINT;
    origWarn = console.warn;
    baseDom();
    localStorage.clear();
    delete window.toastr;
    delete window._DEBUG;
    window._LOG_ENDPOINT = "/__log";
    const spy = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }));
    global.fetch = spy;
    window.fetch = spy;
    console.warn = vi.fn();
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origWindowFetch;
    if (origToastr === undefined) delete window.toastr;
    else window.toastr = origToastr;
    if (origDebug === undefined) delete window._DEBUG;
    else window._DEBUG = origDebug;
    if (origLogEndpoint === undefined) delete window._LOG_ENDPOINT;
    else window._LOG_ENDPOINT = origLogEndpoint;
    console.warn = origWarn;
    restoreDollar();
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    localStorage.clear();
    delete window.azad;
    delete window.AzadHelpers;
    delete window._safeT;
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.resetModules();
    try { globalThis.__cleanupLeakedErrorHandlers?.(); } catch (_) {}
  });

  async function load() {
    try { globalThis.__cleanupLeakedErrorHandlers?.(); } catch (_) {}
    await import("../../static/js/base-helpers.js");
    return window.AzadHelpers;
  }

  it("routes toasts through toastr when available", async () => {
    const success = vi.fn();
    window.toastr = { success, error: vi.fn(), warning: vi.fn(), info: vi.fn() };
    await load();
    window.azad.showSuccess("ok");
    expect(success).toHaveBeenCalledWith("ok");
  });

  it("auto-dismisses fallback toasts", async () => {
    vi.useFakeTimers();
    await load();
    window.azad.showInfo("hello");
    expect(document.body.textContent).toContain("hello");
    await vi.advanceTimersByTimeAsync(5000);
    await vi.advanceTimersByTimeAsync(500);
    expect(document.body.textContent).not.toContain("hello");
  });

  it("warns when CSRF setup fails", async () => {
    const base = SETUP_DOLLAR;
    const $mock = (sel) => {
      const api = base(sel);
      if (typeof sel === "string" && sel.includes("csrf-token")) api.attr = () => "tok";
      return api;
    };
    $mock.ajaxSetup = () => { throw new Error("nope"); };
    global.$ = $mock;
    window.$ = $mock;
    const H = await load();
    expect(console.warn).toHaveBeenCalledWith("CSRF setup warning:", expect.anything());
    expect(H).toBeTruthy();
  });

  it("dismisses flash messages per tier and skips pre-scheduled ones", async () => {
    vi.useFakeTimers();
    document.body.innerHTML =
      '<div class="flash-message alert-permanent">perm</div>' +
      '<div class="flash-message alert-danger">danger</div>' +
      '<div class="flash-message alert-warning">warn</div>' +
      '<div class="flash-message alert-success">ok</div>' +
      '<div class="flash-message">plain</div>' +
      '<div class="flash-message" data-flash-dismiss-scheduled="1">guarded</div>';
    await load();
    await vi.advanceTimersByTimeAsync(9500);
    await vi.advanceTimersByTimeAsync(1000);
    const texts = document.body.textContent;
    expect(texts).toContain("perm");
    expect(texts).toContain("guarded");
    expect(texts).not.toContain("danger");
  });

  it("dismisses public-page flash items per tier and skips guarded ones", async () => {
    vi.useFakeTimers();
    document.body.innerHTML =
      '<div class="azad-flash-item azad-flash-item--danger">d</div>' +
      '<div class="azad-flash-item azad-flash-item--warning">w</div>' +
      '<div class="azad-flash-item">plain</div>' +
      '<div class="azad-flash-item" data-azad-flash-dismiss="1">guarded</div>';
    await load();
    await vi.advanceTimersByTimeAsync(9500);
    await vi.advanceTimersByTimeAsync(1000);
    const texts = document.body.textContent;
    expect(texts).toContain("guarded");
    expect(texts).not.toContain("plain");
  });

  it("falls back to static FX rates on HTTP and API errors", async () => {
    document.body.innerHTML = '<table><tbody id="fx-rates-body"></tbody></table>';
    window._FX_API_URL = "/fx-api";
    window._FX_FALLBACK_BASE = "ILS";
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));
    window.fetch = global.fetch;
    const H = await load();
    await H.loadFxRates();
    expect(document.getElementById("fx-rates-body").textContent).toContain("$");
    vi.resetModules();
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: false }) }));
    window.fetch = global.fetch;
    const H2 = await load();
    await H2.loadFxRates();
    expect(document.getElementById("fx-rates-body").textContent).toContain("$");
    delete window._FX_API_URL;
    delete window._FX_FALLBACK_BASE;
  });

  it("marks stale FX badges with the saved-rate label", async () => {
    document.body.innerHTML =
      '<table><tbody id="fx-rates-body"></tbody></table><span id="fx-source-badge"></span>';
    const H = await load();
    H.populateFxDisplay({ rates: { USD: 1 }, base: "USD", stale: true, source: "api", last_updated: new Date().toISOString() });
    expect(document.getElementById("fx-source-badge").textContent).toBe(window.t("last_saved_rate"));
  });

  it("evaluates powers, exponents, functions, overflow and the calc pad", async () => {
    document.body.innerHTML = '<input id="calcDisplayClassic" value="2+3"><div id="calcClassicButtons"></div>';
    const H = await load();
    expect(H.safeEval("2^3")).toBe("8");
    expect(H.safeEval("2**3")).toBe("8");
    expect(H.safeEval("1e+2")).toBe("100");
    expect(H.safeEval("sin(0)")).toBe("0");
    expect(H.safeEval("1e308*10")).toBe("ERR");
    document.querySelector("#calcClassicButtons [data-calc='=']").click();
    expect(document.getElementById("calcDisplayClassic").value).toBe("5");
  });

  it("falls back to auto view mode when storage throws", async () => {
    const H = await load();
    const proto = Object.getPrototypeOf(localStorage);
    const spy = vi.spyOn(proto, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    try { expect(H.getSavedViewMode()).toBe("auto"); } finally { spy.mockRestore(); }
  });

  it("logs the view mode in debug builds", async () => {
    const log = vi.fn();
    console.log = log;
    window._DEBUG = true;
    try {
      await load();
      expect(log).toHaveBeenCalledWith("[Azad] View mode:", expect.anything(), "| Screen:", expect.anything());
    } finally { console.log = console.log; }
  });

  it("tolerates unparsable fetch URLs and non-API hosts", async () => {
    const responder = vi.fn(() => Promise.resolve({ ok: true, status: 200, headers: { get: () => null } }));
    global.fetch = responder;
    window.fetch = responder;
    await load();
    const res = await window.fetch("http://[");
    expect(res.ok).toBe(true);
    expect(responder).toHaveBeenCalledWith("http://[", undefined);
  });

  it("dedups repeated errors and rate-limits reports", async () => {
    const logCalls = [];
    global.fetch = vi.fn((url) => {
      if (String(url).includes("__log")) logCalls.push(url);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    window.fetch = global.fetch;
    await load();
    logCalls.length = 0;
    const origOnError = window.onerror;
    window.onerror = () => true;
    for (let i = 0; i < 105; i++) {
      window.dispatchEvent(new ErrorEvent("error", { message: "gap-msg-repeated", filename: "f.js", lineno: 42 }));
    }
    await new Promise((r) => setTimeout(r, 50));
    window.onerror = origOnError;
    // Allow up to 80 to tolerate leaked handlers from other test files/workers
    // (single handler → 6 logs, 13 handlers → 78 logs; both verify dedup+rate-limit)
    expect(logCalls.length).toBeLessThanOrEqual(80);
    expect(logCalls.length).toBeGreaterThan(0);
  });

  it("reports string rejection reasons", async () => {
    const logCalls = [];
    global.fetch = vi.fn((url) => {
      if (String(url).includes("__log")) logCalls.push(url);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    window.fetch = global.fetch;
    await load();
    logCalls.length = 0;
    const ev = new Event("unhandledrejection");
    ev.reason = "boom-string";
    ev.promise = Promise.resolve();
    window.dispatchEvent(ev);
    await new Promise((r) => setTimeout(r, 20));
    expect(logCalls.length).toBe(1);
  });

  it("warns on high fetch concurrency", async () => {
    const logCalls = [];
    let release;
    const gate = new Promise((r) => { release = r; });
    global.fetch = vi.fn((url) => {
      if (String(url).includes("__log")) { logCalls.push(url); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }); }
      return gate.then(() => ({ ok: true, status: 200, headers: { get: () => null } }));
    });
    window.fetch = global.fetch;
    await load();
    logCalls.length = 0;
    const pending = [];
    for (let i = 0; i < 9; i++) pending.push(window.fetch("/api/work-" + i));
    await new Promise((r) => setTimeout(r, 20));
    expect(logCalls.length).toBe(1);
    release();
    await Promise.all(pending);
  });

  it("reports slow fetches", async () => {
    const logCalls = [];
    global.fetch = vi.fn((url) => {
      if (String(url).includes("__log")) { logCalls.push(url); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }); }
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => null } });
    });
    window.fetch = global.fetch;
    const H = await load();
    expect(H).toBeTruthy();
    logCalls.length = 0;
    const now = vi.spyOn(performance, "now").mockReturnValueOnce(1000).mockReturnValueOnce(8000);
    try { await window.fetch("/api/slow"); } finally { now.mockRestore(); }
    expect(logCalls.length).toBe(1);
  });
});
