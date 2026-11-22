/* eslint-disable no-unused-vars */
// Real behavioural tests for the three 0%-covered classic-script modules:
//   static/js/maintenance.js
//   static/js/quotation-form.js
//   static/js/pos/offline.js
//
// All three are IIFEs with no exports, so they are loaded with dynamic import
// after arranging the DOM / globals, and exercised through their public hooks
// (window.__posOffline, window.addLine/removeLine) or dispatched events.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const SETUP_DOLLAR = global.$; // setup.js installs a minimal jQuery stub

/* -------------------------------------------------------------------------- */
/* shared DOM helpers                                                          */
/* -------------------------------------------------------------------------- */
function setReadyState(state) {
  Object.defineProperty(document, "readyState", { configurable: true, value: state });
}
function restoreReadyState() {
  delete document.readyState; // own property removed -> prototype value resurfaces
}

/* ========================================================================== */
/* maintenance.js                                                              */
/* ========================================================================== */
describe("maintenance.js", () => {
  const ROOT = `
    <div data-maintenance-root>
      <div data-line-row>
        <input data-line-qty value="2">
        <input data-line-price value="10">
        <input data-line-disc-pct value="10">
        <input data-line-disc-val value="">
        <select data-line-disc-mode>
          <option value="percent" selected>percent</option>
          <option value="value">value</option>
        </select>
        <span data-line-total></span>
      </div>
      <div data-line-row>
        <input data-line-qty value="3">
        <input data-line-price value="20">
        <input data-line-disc-pct value="">
        <input data-line-disc-val value="5">
        <select data-line-disc-mode>
          <option value="percent">percent</option>
          <option value="value" selected>value</option>
        </select>
        <span data-line-total></span>
      </div>
      <div data-line-row>
        <input data-line-qty value="1">
        <input data-line-price value="10">
        <input data-line-disc-pct value="200">
        <input data-line-disc-val value="">
        <select data-line-disc-mode>
          <option value="percent" selected>percent</option>
          <option value="value">value</option>
        </select>
        <span data-line-total></span>
      </div>
      <div data-line-row>
        <input data-line-qty value="abc">
        <input data-line-disc-pct value="">
        <input data-line-disc-val value="">
        <select data-line-disc-mode>
          <option value="percent" selected>percent</option>
          <option value="value">value</option>
        </select>
        <span data-line-total></span>
        <!-- no data-line-price: exercises optional chaining + MONEY(NaN) -->
      </div>
      <div data-line-row>
        <input data-line-qty value="2">
        <input data-line-price value="7">
        <input data-line-disc-pct value="0">
        <input data-line-disc-val value="">
        <!-- no mode select (percent default) and no data-line-total: null-target guard -->
      </div>
      <div data-warranty-legend>
        <span data-legend-swatch="#ff0000"></span>
        <span data-legend-swatch></span>
      </div>
      <div data-line-row>
        <input data-line-qty value="1">
        <input data-line-price value="5">
        <input data-line-disc-pct value="10">
        <select data-line-disc-mode>
          <option value="percent" selected>percent</option>
          <option value="value">value</option>
        </select>
        <span data-line-total></span>
        <!-- no data-line-disc-val -->
      </div>
      <div data-line-row>
        <input data-line-qty value="1">
        <input data-line-price value="5">
        <input data-line-disc-val value="1">
        <select data-line-disc-mode>
          <option value="percent">percent</option>
          <option value="value" selected>value</option>
        </select>
        <span data-line-total></span>
        <!-- no data-line-disc-pct -->
      </div>
      <select data-line-disc-mode id="orphan-mode">
        <option value="percent">percent</option>
        <option value="value">value</option>
      </select>
    </div>`;

  let docEvents;
  let swatches;

  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = ROOT;
    setReadyState("complete");
    swatches = Array.from(document.querySelectorAll("[data-legend-swatch]"));
    // jsdom's cssstyle rejects custom properties in the real setProperty, so
    // stub the call-through and assert the arguments the module passes instead.
    swatches.forEach((s) => vi.spyOn(s.style, "setProperty").mockImplementation(() => {}));
    docEvents = [];
    vi.spyOn(document, "addEventListener").mockImplementation((type, fn) => {
      docEvents.push({ type, fn });
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
    restoreReadyState();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function load() {
    await import("../../static/js/maintenance.js");
  }
  function row(i) {
    return document.querySelectorAll("[data-line-row]")[i];
  }
  function total(i) {
    return row(i).querySelector("[data-line-total]")?.textContent;
  }

  it("boots immediately when the DOM is ready and recomputes every line", async () => {
    await load();
    // percent mode: 2 * (10 * (1 - 10/100)) = 18
    expect(total(0)).toBe("18.000");
    // value mode: 3 * (20 - 5) = 45
    expect(total(1)).toBe("45.000");
    // negative net clamped to zero
    expect(total(2)).toBe("0.000");
    // NaN quantity / missing price element -> 0
    expect(total(3)).toBe("0.000");
    // missing mode select -> percent default; no target span -> null-target guard exercised
    expect(row(4).querySelector("[data-line-total]")).toBeNull();
    expect(() => row(4).querySelector("[data-line-disc-pct]").dispatchEvent(new Event("input"))).not.toThrow();
    // warranty legend colours: explicit value and default fallback
    expect(swatches[0].style.setProperty).toHaveBeenCalledWith("--mnt-tag-color", "#ff0000");
    expect(swatches[1].style.setProperty).toHaveBeenCalledWith("--mnt-tag-color", "#f59e0b");
  });

  it("recomputes on input and change events, and clears the alternative discount", async () => {
    await load();
    const qty = row(0).querySelector("[data-line-qty]");
    qty.value = "4";
    qty.dispatchEvent(new Event("input", { bubbles: true }));
    expect(total(0)).toBe("36.000");

    const price = row(0).querySelector("[data-line-price]");
    price.value = "5";
    price.dispatchEvent(new Event("change", { bubbles: true }));
    expect(total(0)).toBe("18.000");

    const mode = row(0).querySelector("[data-line-disc-mode]");
    const pct = row(0).querySelector("[data-line-disc-pct]");
    const val = row(0).querySelector("[data-line-disc-val]");

    // value mode -> percentage input is cleared
    mode.value = "value";
    val.value = "1";
    mode.dispatchEvent(new Event("change", { bubbles: true }));
    expect(pct.value).toBe("");
    expect(total(0)).toBe("16.000");

    // percent mode -> value input is cleared
    mode.value = "percent";
    pct.value = "50";
    mode.dispatchEvent(new Event("change", { bubbles: true }));
    expect(val.value).toBe("");
    expect(total(0)).toBe("10.000");
  });

  it("tolerates a missing alternative discount input when the mode changes", async () => {
    await load();
    const noValue = row(5);
    const noPct = row(6);
    const modeA = noValue.querySelector("[data-line-disc-mode]");
    const modeB = noPct.querySelector("[data-line-disc-mode]");
    // percent mode with no val input -> the `if (val)` guard is false
    modeA.value = "percent";
    expect(() => modeA.dispatchEvent(new Event("change", { bubbles: true }))).not.toThrow();
    // value mode with no pct input -> the `else if (pct)` guard is false
    modeB.value = "value";
    expect(() => modeB.dispatchEvent(new Event("change", { bubbles: true }))).not.toThrow();
  });

  it("ignores a discount-mode select that is not inside a line row", async () => {
    await load();
    const orphan = document.getElementById("orphan-mode");
    orphan.value = "value";
    expect(() => orphan.dispatchEvent(new Event("change", { bubbles: true }))).not.toThrow();
    // the first real row is untouched
    expect(total(0)).toBe("18.000");
  });

  it("defers boot until DOMContentLoaded while the document is loading", async () => {
    setReadyState("loading");
    await load();
    expect(total(0)).toBe("");
    const boot = docEvents.find((e) => e.type === "DOMContentLoaded");
    expect(boot).toBeDefined();
    boot.fn();
    expect(total(0)).toBe("18.000");
  });
});

/* ========================================================================== */
/* quotation-form.js                                                           */
/* ========================================================================== */
describe("quotation-form.js", () => {
  const DOM = `
    <select id="f_customer_id">
      <option value="1" data-customer-type="merchant" selected>Customer</option>
    </select>
    <div id="lines-container" data-next-index="3" data-auto-add="1">
      <div class="quotation-line" data-index="0">
        <button type="button" class="use-cost-margin no-data"></button>
        <select class="product-select" data-line="0"></select>
        <select class="wh-select" data-line="0">
          <option value="">--</option>
          <option value="w1" selected>W1</option>
          <option value="w2">W2</option>
        </select>
        <input name="form-0-unit_price">
        <div class="price-hint">
          <span class="cost-val"></span>
          <span class="margin-val"></span>
          <button type="button" class="use-cost-margin" data-cost="50" data-margin="20"></button>
        </div>
      </div>
      <select class="product-select" data-line="99"></select>
      <select class="wh-select" data-line="999"><option value="x" selected>X</option></select>
    </div>
    <template id="quotation-line-template">
      <div class="quotation-line" data-index="__IDX__">
        <select class="product-select" data-line="__IDX__"></select>
        <select class="wh-select" data-line="__IDX__"><option value="w2" selected>W2</option></select>
        <input name="form-__IDX__-unit_price">
        <div class="price-hint">
          <span class="cost-val"></span><span class="margin-val"></span>
          <button type="button" class="use-cost-margin"></button>
        </div>
      </div>
    </template>`;

  function makeJQuery() {
    const reg = {
      select2Opts: [],
      customerData: [],
      handlers: [],
      destroys: 0,
      throwOnDestroy: false,
      noSelect2: false,
    };
    const dataStore = new WeakMap();
    const camel = (k) => k.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

    function wrap(input) {
      const els = (Array.isArray(input) ? input : input ? [input] : []).filter(Boolean);
      const api = {
        length: els.length,
        0: els[0],
        each(fn) {
          els.forEach((el, i) => fn.call(el, i, el));
          return api;
        },
        find(sel) {
          const out = [];
          els.forEach((el) => {
            if (!el.querySelectorAll) return;
            if (sel === "option:selected") {
              out.push(...Array.from(el.querySelectorAll("option")).filter((o) => o.selected));
            } else {
              out.push(...Array.from(el.querySelectorAll(sel)));
            }
          });
          return wrap(out);
        },
        closest(sel) {
          const el = els[0];
          return wrap(el && el.closest ? [el.closest(sel)] : []);
        },
        hasClass(cls) {
          return els.some((el) => el.classList && el.classList.contains(cls));
        },
        data(k, v) {
          if (v === undefined) {
            const el = els[0];
            if (!el) return undefined;
            const s = dataStore.get(el);
            if (s && k in s) return s[k];
            return el.dataset ? el.dataset[camel(k)] : undefined;
          }
          els.forEach((el) => {
            const s = dataStore.get(el) || {};
            s[k] = v;
            dataStore.set(el, s);
          });
          return api;
        },
        removeData(k) {
          els.forEach((el) => {
            const s = dataStore.get(el);
            if (s) delete s[k];
          });
          return api;
        },
        val(v) {
          if (v === undefined) return els[0] ? els[0].value : "";
          els.forEach((el) => {
            if ("value" in el) el.value = String(v);
          });
          return api;
        },
        text(v) {
          if (v === undefined) return els[0] ? els[0].textContent : "";
          els.forEach((el) => {
            el.textContent = String(v);
          });
          return api;
        },
        attr(n, v) {
          if (v === undefined) return els[0] ? els[0].getAttribute(n) : null;
          els.forEach((el) => el.setAttribute(n, String(v)));
          return api;
        },
        on(event, handler) {
          els.forEach((el) => {
            reg.handlers.push({ el, event, handler });
            el.addEventListener(event, function (e) {
              handler.call(this, e);
            });
          });
          return api;
        },
        select2(arg) {
          if (arg === "data") return reg.customerData;
          if (arg === "destroy") {
            reg.destroys += 1;
            if (reg.throwOnDestroy) throw new Error("select2 not initialised");
            return api;
          }
          if (arg && typeof arg === "object") reg.select2Opts.push(arg);
          return api;
        },
        ready(fn) {
          if (typeof fn === "function") fn();
          return api;
        },
      };
      return api;
    }

    function $(sel) {
      if (typeof sel === "function") {
        sel();
        return wrap([]);
      }
      if (sel === document || sel === window || sel instanceof Node) {
        const api = wrap([sel]);
        if (sel === "#f_customer_id" && reg.noSelect2) delete api.select2;
        return api;
      }
      if (typeof sel === "string") {
        let found = [];
        try {
          found = Array.from(document.querySelectorAll(sel));
        } catch (_) {
          found = [];
        }
        const api = wrap(found);
        if (sel === "#f_customer_id" && reg.noSelect2) delete api.select2;
        return api;
      }
      return wrap([]);
    }
    return { $, reg };
  }

  let $jq;
  let reg;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    document.body.innerHTML = DOM;
    ({ $: $jq, reg } = makeJQuery());
    global.$ = $jq;
    window.$ = $jq;
    delete window.addLine;
    delete window.removeLine;
    delete window.initCustomerSelect;
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    document.body.innerHTML = "";
    global.$ = SETUP_DOLLAR;
    window.$ = SETUP_DOLLAR;
    delete window.addLine;
    delete window.removeLine;
    delete window.initCustomerSelect;
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function load() {
    await import("../../static/js/quotation-form.js");
    // $(document).ready() fires synchronously in the stub; flush its 250ms timer
    vi.advanceTimersByTime(260);
  }
  function handlerFor(el, event) {
    const h = reg.handlers.find((x) => x.el === el && x.event === event);
    expect(h, `handler ${event} for element`).toBeDefined();
    return h.handler;
  }
  function prod() {
    return document.querySelector('.product-select[data-line="0"]');
  }

  it("auto-adds a line, exposes addLine/removeLine, and removes by index", async () => {
    await load();
    expect(typeof window.addLine).toBe("function");
    expect(typeof window.removeLine).toBe("function");
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(2);
    expect(document.querySelector('.quotation-line[data-index="3"]')).not.toBeNull();

    window.removeLine(0);
    expect(document.querySelector('.quotation-line[data-index="0"]')).toBeNull();
    // removing a missing index is a no-op
    expect(() => window.removeLine(999)).not.toThrow();
  });

  it("does not auto-add when data-auto-add is not 1", async () => {
    document.getElementById("lines-container").dataset.autoAdd = "0";
    await load();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(1);
  });

  it("initialises product selects with a warehouse-scoped search URL and Select2 options", async () => {
    await load();
    expect(reg.select2Opts.length).toBeGreaterThan(0);
    const opts = reg.select2Opts[0];
    expect(opts.ajax.url).toBe("/api/warehouses/w1/products");
    expect(opts.ajax.dataType).toBe("json");
    expect(opts.ajax.delay).toBe(300);
    expect(opts.placeholder).toBe("Search_Product"); // window.t from setup.js
    expect(opts.allowClear).toBe(true);
    expect(opts.dir).toBe("rtl");

    // ajax.data parameter fallbacks and explicit values
    expect(opts.ajax.data({})).toEqual({ q: "", page: 1 });
    expect(opts.ajax.data({ term: "tea", page: 4 })).toEqual({ q: "tea", page: 4 });

    // processResults across all its input shapes
    const mapped = opts.ajax.processResults([
      { id: 1, text: "Explicit", name: "N", sku: "S", price: 10, merchant_price: 5, cost_price: 8, stock: 2 },
      { id: 2, name: "Name only" },
      { id: 6, name: "Sk only", sku: "SKU-9" },
      { id: 3 },
    ]);
    expect(mapped.results[0].text).toBe("Explicit");
    expect(mapped.results[1].text).toBe("Name only");
    expect(mapped.results[2].text).toBe("Sk only (SKU-9)");
    expect(mapped.results[3].text).toBe("");
    expect(mapped.results[3].merchant_price).toBeNull();
    expect(mapped.pagination).toEqual({ more: false });
    expect(opts.ajax.processResults({ data: [{ id: 4 }] }).results).toHaveLength(1);
    expect(opts.ajax.processResults({ results: [{ id: 5 }] }).results).toHaveLength(1);
    expect(opts.ajax.processResults({}).results).toEqual([]);
  });

  it("re-initialises the product select when the warehouse changes", async () => {
    await load();
    const wh = document.querySelector('.wh-select[data-line="0"]');
    wh.value = "w2";
    handlerFor(wh, "change").call(wh);
    // the warehouse is looked up again through the line's data-line attribute
    const last = reg.select2Opts[reg.select2Opts.length - 1];
    expect(last.ajax.url).toBe("/api/warehouses/w2/products");

    // blank warehouse -> global search endpoint
    wh.value = "";
    handlerFor(wh, "change").call(wh);
    expect(reg.select2Opts[reg.select2Opts.length - 1].ajax.url).toBe("/api/v2/products/search");
  });

  it("suggests a merchant price and fills the cost/margin hint from select2 data", async () => {
    reg.customerData = [{ customer_type: "merchant" }];
    await load();
    const select = prod();
    const row = select.closest(".quotation-line");
    const price = row.querySelector('input[name$="-unit_price"]');
    handlerFor(select, "select2:select").call(select, {
      params: { data: { price: 100, merchant_price: 10, cost_price: 80 } },
    });
    expect(price.value).toBe("90.00");
    expect(row.querySelector(".cost-val").textContent).toBe("80.00");
    expect(row.querySelector(".margin-val").textContent).toBe("20.0");
  });

  it("uses the selected option's customer-type and handles zero price", async () => {
    reg.customerData = [];
    await load();
    const select = prod();
    const row = select.closest(".quotation-line");
    handlerFor(select, "select2:select").call(select, {
      params: { data: { price: 0, cost_price: 0 } },
    });
    expect(row.querySelector('input[name$="-unit_price"]').value).toBe("0.00");
    expect(row.querySelector(".margin-val").textContent).toBe("0.0");
  });

  it("falls back to a regular customer when no type is available, including without select2 data", async () => {
    delete window.t; // also covers the literal placeholder fallback
    reg.customerData = [{}];
    await load();
    document.querySelector("#f_customer_id option").removeAttribute("data-customer-type");
    const select = prod();
    handlerFor(select, "select2:select").call(select, {
      params: { data: { price: 50, merchant_price: 20, cost_price: 10 } },
    });
    expect(select.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "50.00",
    );
    expect(reg.select2Opts[0].placeholder).toBe("Search product");
  });

  it("falls back to an empty Select2 data array when the customer select has no select2 method", async () => {
    reg.noSelect2 = true;
    reg.customerData = null;
    document.querySelector("#f_customer_id option").removeAttribute("data-customer-type");
    await load();
    const select = prod();
    handlerFor(select, "select2:select").call(select, {
      params: { data: { price: 33, merchant_price: 50, cost_price: 10 } },
    });
    // no customer type -> regular customer -> list price is suggested
    expect(select.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "33.00",
    );
  });

  it("does nothing at all when the lines container is absent", async () => {
    document.getElementById("lines-container").remove();
    await import("../../static/js/quotation-form.js");
    expect(window.addLine).toBeUndefined();
    expect(reg.select2Opts).toHaveLength(0);
  });

  it("falls back to line index 0 when data-next-index is missing", async () => {
    const container = document.getElementById("lines-container");
    delete container.dataset.nextIndex;
    container.dataset.autoAdd = "0";
    await load();
    window.addLine();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(2);
  });

  it("falls back to line index 0 when data-next-index is invalid", async () => {
    const container = document.getElementById("lines-container");
    container.dataset.nextIndex = "not-a-number";
    container.dataset.autoAdd = "0";
    await load();
    window.addLine();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(2);
  });

  it("uses the global product search when container.querySelector is unavailable", async () => {
    document.getElementById("lines-container").querySelector = undefined;
    await load();
    expect(reg.select2Opts[0].ajax.url).toBe("/api/v2/products/search");
  });

  it("defaults to a regular customer when the customer select is missing", async () => {
    document.getElementById("f_customer_id").remove();
    await load();
    const select = prod();
    handlerFor(select, "select2:select").call(select, {
      params: { data: { price: 70, merchant_price: 50 } },
    });
    expect(select.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "70.00",
    );
  });

  it("handles a select2:select for a product select outside a quotation line", async () => {
    await load();
    const orphan = document.querySelector('.product-select[data-line="99"]');
    expect(() =>
      handlerFor(orphan, "select2:select").call(orphan, {
        params: { data: { price: 10, cost_price: 4 } },
      }),
    ).not.toThrow();
  });

  it("destroys an already-initialised select2 and swallows destroy errors", async () => {
    prod().classList.add("select2-hidden-accessible");
    reg.throwOnDestroy = true;
    await load();
    expect(reg.destroys).toBeGreaterThan(0);
    expect(reg.select2Opts.length).toBeGreaterThan(0);
  });

  it("re-initialises an empty product selection without throwing", async () => {
    await load();
    // this warehouse has no matching .product-select, so the captured $prod is
    // empty and initProductSelect's length guard runs
    const wh = document.querySelector('.wh-select[data-line="999"]');
    handlerFor(wh, "change").call(wh);
    expect(wh.value).toBe("x");
  });

  it("wires the added line's warehouse change handler and computes from blank button data", async () => {
    await load();
    const addedWh = document.querySelector('.quotation-line[data-index="3"] .wh-select');
    expect(() => handlerFor(addedWh, "change").call(addedWh)).not.toThrow();
    const addedBtn = document.querySelector('.quotation-line[data-index="3"] .use-cost-margin');
    // no data-cost/data-margin on the template button -> both `|| 0` fallbacks
    handlerFor(addedBtn, "click").call(addedBtn);
    expect(addedBtn.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "0.00",
    );
    // an existing-line button with no stored cost/margin -> both `|| 0` fallbacks
    const blankBtn = document.querySelector(".use-cost-margin.no-data");
    handlerFor(blankBtn, "click").call(blankBtn);
    expect(blankBtn.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "0.00",
    );
  });

  it("computes a price with the use-cost-margin buttons (added and existing lines)", async () => {
    await load();
    const existing = document.querySelector(
      '.quotation-line[data-index="0"] .use-cost-margin:not(.no-data)',
    );
    // data-cost/data-margin on the existing button come from its HTML attributes
    handlerFor(existing, "click").call(existing);
    expect(existing.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "60.00",
    );

    const added = document.querySelector('.quotation-line[data-index="3"] .use-cost-margin');
    $jq(added).data("cost", 25).data("margin", 40);
    handlerFor(added, "click").call(added);
    expect(added.closest(".quotation-line").querySelector('input[name$="-unit_price"]').value).toBe(
      "35.00",
    );
  });

  it("guards addLine when the template is missing or has no element child", async () => {
    await load();
    document.getElementById("quotation-line-template").remove();
    const before = document.querySelectorAll("#lines-container .quotation-line").length;
    expect(() => window.addLine()).not.toThrow();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(before);

    const tpl = document.createElement("template");
    tpl.id = "quotation-line-template";
    tpl.innerHTML = "";
    document.body.appendChild(tpl);
    expect(() => window.addLine()).not.toThrow();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(before);
  });

  it("calls window.initCustomerSelect when the page provides it", async () => {
    window.initCustomerSelect = vi.fn();
    await load();
    expect(window.initCustomerSelect).toHaveBeenCalledTimes(1);
  });

  it("does not call initCustomerSelect when it is absent", async () => {
    await load();
    expect(document.querySelectorAll("#lines-container .quotation-line")).toHaveLength(2);
  });
});

/* ========================================================================== */
/* pos/offline.js                                                              */
/* ========================================================================== */
describe("pos/offline.js", () => {
  const POS_DOM = `
    <div class="pos-app">
      <div id="posSessionBar"></div>
      <div class="pos-grid"></div>
    </div>
    <button id="retryQueueBtn" type="button">retry</button>`;

  const ORIGINAL_FETCH = globalThis.fetch;
  const ORIGINAL_ABORT = globalThis.AbortController;
  let docEvents;
  let winEvents;
  let sw;

  function setOnLine(value) {
    Object.defineProperty(navigator, "onLine", { configurable: true, value });
  }
  function setSW(value) {
    if (value === undefined) delete navigator.serviceWorker;
    else Object.defineProperty(navigator, "serviceWorker", { configurable: true, value });
  }
  function makeSW(options = {}) {
    const listeners = {};
    const reg = {
      active: options.active === undefined ? { postMessage: vi.fn() } : options.active,
      sync: options.sync === undefined ? undefined : options.sync,
      controller: options.controller === undefined ? undefined : options.controller,
      addEventListener: vi.fn((type, fn) => {
        listeners[type] = fn;
      }),
      listeners,
    };
    const register = vi.fn((url, opts) => {
      reg.lastArgs = [url, opts];
      if (options.rejectFor && options.rejectFor.includes(opts && opts.scope)) {
        return Promise.reject(new Error("registration failed"));
      }
      if (options.rejectAll) return Promise.reject(new Error("registration failed"));
      return Promise.resolve(reg);
    });
    // The module reads register/controller/addEventListener off navigator.serviceWorker
    const sw = {
      register,
      controller: reg.controller,
      addEventListener: reg.addEventListener,
      listeners,
    };
    return { register, reg, sw };
  }
  function fireDoc(type, ev = {}) {
    docEvents.filter((e) => e.type === type).forEach((e) => e.fn(ev));
  }
  function fireWin(type, ev = {}) {
    winEvents.filter((e) => e.type === type).forEach((e) => e.fn(ev));
  }
  async function flush() {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
  }
  async function load() {
    await import("../../static/js/pos/offline.js");
    return window.__posOffline;
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    document.body.innerHTML = POS_DOM;
    delete document.documentElement.dataset.posOnline;
    setOnLine(true);
    setSW(undefined);
    docEvents = [];
    winEvents = [];
    vi.spyOn(document, "addEventListener").mockImplementation((type, fn) => {
      docEvents.push({ type, fn });
    });
    vi.spyOn(window, "addEventListener").mockImplementation((type, fn) => {
      winEvents.push({ type, fn });
    });
    vi.spyOn(console, "debug").mockImplementation(() => {});
    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 200 }));
    globalThis.AbortController = class {
      constructor() {
        this.signal = {};
        this.aborted = false;
      }
      abort() {
        this.aborted = true;
      }
    };
    delete window.__posOffline;
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    document.body.innerHTML = "";
    delete document.documentElement.dataset.posOnline;
    delete navigator.onLine;
    delete navigator.serviceWorker;
    if (ORIGINAL_FETCH === undefined) delete globalThis.fetch;
    else globalThis.fetch = ORIGINAL_FETCH;
    if (ORIGINAL_ABORT === undefined) delete globalThis.AbortController;
    else globalThis.AbortController = ORIGINAL_ABORT;
    delete window.__posOffline;
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("exposes the test API and is a no-op before DOMContentLoaded", async () => {
    const api = await load();
    expect(api).toBeDefined();
    expect(typeof api.retryQueue).toBe("function");
    expect(typeof api.updateOnlineStatus).toBe("function");
    expect(typeof api.probeConnectivity).toBe("function");
    expect(api.updateOnlineStatus()).toBe(true); // no bar yet -> early return
    expect(globalThis.fetch).not.toHaveBeenCalled();
    api.retryQueue(); // no bar, no SW -> safe no-op
    await flush();
    expect(document.getElementById("posOfflineBar")).toBeNull();
  });

  it("boots: inserts the bar above the grid, registers the SW and tracks online state", async () => {
    const mock = makeSW();
    sw = mock;
    setSW(mock.sw);
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();

    const bar = document.getElementById("posOfflineBar");
    expect(bar).not.toBeNull();
    expect(bar.parentNode).toBe(document.querySelector(".pos-app"));
    expect(bar.nextElementSibling).toBe(document.querySelector(".pos-grid"));
    expect(mock.register).toHaveBeenCalledWith("/static/pos-sw.js", { scope: "/pos/" });
    expect(api.swRegistration).toBe(mock.reg);
    expect(document.documentElement.dataset.posOnline).toBe("true");

    // a second DOMContentLoaded sees the existing bar and returns early
    fireDoc("DOMContentLoaded");
    expect(document.querySelectorAll("#posOfflineBar")).toHaveLength(1);

    const before = globalThis.fetch.mock.calls.length;
    vi.advanceTimersByTime(15000); // periodic ground-truth probe
    expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(before);

    fireWin("beforeunload"); // clears the interval, does not throw
  });

  it("inserts the bar after the session bar when no POS grid exists", async () => {
    document.body.innerHTML = '<div class="wrap"><div id="posSessionBar"></div></div>';
    setOnLine(false);
    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 503 }));
    await load();
    fireDoc("DOMContentLoaded");
    await flush();
    const bar = document.getElementById("posOfflineBar");
    const sessionBar = document.getElementById("posSessionBar");
    // insertBefore(bar, sessionBar.nextSibling) with no next sibling appends
    expect(sessionBar.nextElementSibling).toBe(bar);
    expect(document.documentElement.dataset.posOnline).toBe("false");
  });

  it("falls back to .pos-fullscreen and then document.body when anchoring the bar", async () => {
    document.body.innerHTML = '<div class="pos-fullscreen"><span>existing</span></div>';
    await load();
    fireDoc("DOMContentLoaded");
    expect(document.querySelector(".pos-fullscreen").firstElementChild.id).toBe("posOfflineBar");

    // fresh module against an empty body -> document.body.prepend branch
    vi.resetModules();
    delete window.__posOffline;
    document.body.innerHTML = "";
    await load();
    fireDoc("DOMContentLoaded");
    expect(document.body.firstElementChild.id).toBe("posOfflineBar");
  });

  it("probeConnectivity classifies HTTP responses and exercises the fallback endpoint", async () => {
    const api = await load();

    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 200 }));
    expect(await api.probeConnectivity(10)).toBe(true);
    expect(globalThis.fetch.mock.calls[0][0]).toBe("/api/health");

    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 0 }));
    expect(await api.probeConnectivity()).toBe(false); // default timeout argument

    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 503 }));
    expect(await api.probeConnectivity(10)).toBe(false); // offline fallback response

    // primary rejects -> fallback endpoint is tried
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ status: 200 });
    expect(await api.probeConnectivity(10)).toBe(true);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    expect(globalThis.fetch.mock.calls[1][0]).toBe("/pos/api/session/current");

    // both reject -> offline
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    expect(await api.probeConnectivity(10)).toBe(false);
  });

  it("aborts the fallback probe when its 2500ms timeout fires", async () => {
    const api = await load();
    let resolveFallback;
    globalThis.fetch = vi.fn((url) => {
      if (url === "/api/health") return Promise.reject(new Error("primary down"));
      return new Promise((resolve) => {
        resolveFallback = resolve;
      });
    });
    const pending = api.probeConnectivity(10);
    await flush(); // primary has rejected, fallback is pending, timer is armed
    vi.advanceTimersByTime(2500); // runs the fallback AbortController callback
    resolveFallback({ status: 200 });
    expect(await pending).toBe(true);
  });

  it("updateOnlineStatus trusts the probe, retries the queue on recovery and survives a probe error", async () => {
    setOnLine(false);
    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 503 }));
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();
    expect(document.documentElement.dataset.posOnline).toBe("false");

    // navigator recovers and the probe confirms it -> queue retry is kicked
    setOnLine(true);
    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 200 }));
    const btn = document.getElementById("retryQueueBtn");
    expect(api.updateOnlineStatus()).toBe(true);
    await flush();
    expect(document.documentElement.dataset.posOnline).toBe("true");
    expect(btn.disabled).toBe(true);
    expect(btn.innerHTML).toContain("fa-spinner");
    vi.advanceTimersByTime(1200);
    expect(btn.disabled).toBe(false);

    // a probe that rejects synchronously is caught; the navigator-based banner
    // visibility already set at the top of updateOnlineStatus is left in place
    setOnLine(false);
    globalThis.AbortController = class {
      constructor() {
        throw new Error("no AbortController");
      }
    };
    expect(api.updateOnlineStatus()).toBe(false);
    await flush();
    expect(document.documentElement.dataset.posOnline).toBe("false");
  });

  it("registerSW falls back through /pos/, / and default scope, then logs failures", async () => {
    const mock = makeSW({ rejectFor: ["/pos/", "/"] });
    setSW(mock.sw);
    await load();
    fireDoc("DOMContentLoaded");
    await flush();
    expect(mock.register).toHaveBeenCalledTimes(3);
    expect(mock.register.mock.calls.map((c) => c[1])).toEqual([
      { scope: "/pos/" },
      { scope: "/" },
      undefined,
    ]);

    // controller present -> a message event refreshes the status
    const withController = makeSW({ controller: { postMessage: vi.fn() } });
    setSW(withController.sw);
    vi.resetModules();
    delete window.__posOffline;
    await load();
    fireDoc("DOMContentLoaded");
    await flush();
    withController.reg.listeners.message();
    await flush();
    expect(globalThis.fetch).toHaveBeenCalled();

    // every registration fails -> console.debug is the only side effect
    const failing = makeSW({ rejectAll: true });
    setSW(failing.sw);
    vi.resetModules();
    delete window.__posOffline;
    await load();
    fireDoc("DOMContentLoaded");
    await flush();
    expect(console.debug).toHaveBeenCalledWith("POS SW registration failed:", expect.any(Error));

    // the debug call is guarded by window.console && console.debug
    const savedConsole = window.console;
    try {
      Object.defineProperty(window, "console", { configurable: true, value: {} });
      const before = failing.register.mock.calls.length;
      vi.resetModules();
      delete window.__posOffline;
      await load();
      fireDoc("DOMContentLoaded");
      await flush();
      expect(failing.register.mock.calls.length).toBeGreaterThan(before);
    } finally {
      Object.defineProperty(window, "console", { configurable: true, value: savedConsole });
    }
  });

  it("serviceWorker absent from navigator short-circuits registration", async () => {
    setSW(undefined);
    await load();
    fireDoc("DOMContentLoaded");
    await flush();
    expect(document.getElementById("posOfflineBar")).not.toBeNull();
  });

  it("retryQueue posts to the active SW, its sync manager and the foreground controller", async () => {
    const controller = { postMessage: vi.fn() };
    const sync = { register: vi.fn(() => Promise.reject(new Error("sync denied"))) };
    const mock = makeSW({ controller, sync });
    setSW(mock.sw);
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();
    api.retryQueue();
    await flush();
    expect(mock.reg.active.postMessage).toHaveBeenCalledWith("retry-queue");
    expect(sync.register).toHaveBeenCalledWith("pos-queue-retry");
    expect(controller.postMessage).toHaveBeenCalledWith("retry-queue");
    vi.advanceTimersByTime(1200);
  });

  it("retryQueue survives postMessage failures and re-probes when nothing was attempted", async () => {
    const active = {
      postMessage: vi.fn(() => {
        throw new Error("detached");
      }),
    };
    const controller = {
      postMessage: vi.fn(() => {
        throw new Error("detached");
      }),
    };
    const mock = makeSW({ active, controller });
    setSW(mock.sw);
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();
    const before = globalThis.fetch.mock.calls.length;
    expect(() => api.retryQueue()).not.toThrow();
    await flush();
    // both postMessage calls threw -> attempted stayed false -> updateOnlineStatus re-probed
    expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(before);
    vi.advanceTimersByTime(1200);
  });

  it("retryQueue restores the button even when its ground-truth probe rejects", async () => {
    const mock = makeSW({ controller: { postMessage: vi.fn() } });
    setSW(mock.sw);
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();
    const btn = document.getElementById("retryQueueBtn");
    globalThis.AbortController = class {
      constructor() {
        throw new Error("no AbortController");
      }
    };
    api.retryQueue();
    await flush();
    expect(btn.disabled).toBe(true);
    vi.advanceTimersByTime(1200); // the .finally() restoration still runs
    expect(btn.disabled).toBe(false);
    expect(btn.innerHTML).toContain("fa-sync"); // original markup restored
  });

  it("retryQueue skips the button block when there is no retry button", async () => {
    const controller = { postMessage: vi.fn() };
    const mock = makeSW({ controller });
    setSW(mock.sw);
    const api = await load();
    fireDoc("DOMContentLoaded");
    await flush();
    // createOfflineBar injects its own #retryQueueBtn — remove every one after boot
    document.querySelectorAll("#retryQueueBtn").forEach((b) => b.remove());
    const before = globalThis.fetch.mock.calls.length;
    api.retryQueue();
    await flush();
    // "attempted" is true via the controller, so no extra updateOnlineStatus probe
    expect(globalThis.fetch.mock.calls.length).toBe(before);
  });

  it("wires online/offline, visibility and delegated click handlers", async () => {
    const mock = makeSW({ controller: { postMessage: vi.fn() } });
    setSW(mock.sw);
    await load();
    fireDoc("DOMContentLoaded");
    await flush();

    let calls = globalThis.fetch.mock.calls.length;
    fireWin("online");
    expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(calls);
    calls = globalThis.fetch.mock.calls.length;
    fireWin("offline");
    expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(calls);

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    calls = globalThis.fetch.mock.calls.length;
    fireDoc("visibilitychange");
    expect(globalThis.fetch.mock.calls.length).toBe(calls);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    fireDoc("visibilitychange");
    expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(calls);
    delete document.visibilityState;

    const preventDefault = vi.fn();
    fireDoc("click", { target: document.getElementById("retryQueueBtn"), preventDefault });
    expect(preventDefault).toHaveBeenCalled();

    const nested = document.createElement("span");
    document.getElementById("retryQueueBtn").appendChild(nested);
    const preventDefault2 = vi.fn();
    fireDoc("click", { target: nested, preventDefault: preventDefault2 });
    expect(preventDefault2).toHaveBeenCalled();

    const preventDefault3 = vi.fn();
    fireDoc("click", { target: document.createElement("div"), preventDefault: preventDefault3 });
    expect(preventDefault3).not.toHaveBeenCalled();

    // falsy target and a target with no closest() both short-circuit safely
    fireDoc("click", { target: null, preventDefault: vi.fn() });
    fireDoc("click", { target: { id: "other" }, preventDefault: vi.fn() });
    vi.advanceTimersByTime(1200);
  });
});
