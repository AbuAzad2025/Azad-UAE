import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let modalCalls = [];

function wrapEls(els) {
  const inst = {
    length: els.length,
    0: els[0] || null,
    on: () => inst,
    off: () => inst,
    trigger: () => inst,
    each: (fn) => {
      els.forEach((el, i) => fn.call(el, i, el));
      return inst;
    },
    append: (html) => {
      els.forEach((el) => { el.insertAdjacentHTML('beforeend', html); });
      return inst;
    },
    remove: vi.fn(() => inst),
    addClass: () => inst,
    removeClass: () => inst,
    hasClass: (cls) => els.some((el) => el.classList?.contains(cls)),
    css: () => inst,
    show: () => inst,
    hide: () => inst,
    closest: () => wrapEls([]),
    find: (sel) => {
      const found = [];
      els.forEach((el) => {
        if (el.querySelectorAll) found.push(...Array.from(el.querySelectorAll(sel)));
      });
      return wrapEls(found);
    },
    parent: () => wrapEls([]),
    prop: () => undefined,
    is: () => false,
    select2: () => inst,
    ready: (fn) => {
      if (typeof fn === 'function') fn();
      return inst;
    },
    text: (v) => {
      if (v !== undefined) {
        els.forEach((el) => { el.textContent = v; });
        return inst;
      }
      return els[0]?.textContent ?? '';
    },
    html: (v) => {
      if (v !== undefined) return inst;
      return els[0]?.innerHTML ?? '';
    },
    val: (v) => {
      if (v !== undefined) {
        els.forEach((el) => { if ('value' in el) el.value = v; });
        return inst;
      }
      return els[0]?.value ?? '';
    },
    data: (key, val) => {
      const el = els[0];
      if (!el) return val !== undefined ? inst : undefined;
      const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      if (val !== undefined) {
        if (el.dataset) el.dataset[camel] = val;
        return inst;
      }
      return el.dataset?.[camel] ?? undefined;
    },
    attr: (name, val) => {
      const el = els[0];
      if (!el) return val !== undefined ? inst : undefined;
      if (val !== undefined) {
        el.setAttribute(name, val);
        return inst;
      }
      return el.getAttribute(name);
    },
    modal: (action) => {
      modalCalls.push({ id: els[0]?.id, action });
      return inst;
    },
  };
  return inst;
}

function buildJQuery() {
  const $ = (sel) => {
    if (typeof sel === 'function') {
      sel();
      return wrapEls([]);
    }
    if (typeof sel === 'string') {
      try {
        return wrapEls(Array.from(document.querySelectorAll(sel)));
      } catch {
        return wrapEls([]);
      }
    }
    if (sel && typeof sel === 'object') {
      if (sel.nodeType) return wrapEls([sel]);
      if (sel === document) {
        const inst = wrapEls([]);
        inst.ready = (fn) => {
          if (typeof fn === 'function') fn();
          return inst;
        };
        return inst;
      }
    }
    return wrapEls([]);
  };
  $.ajaxSetup = vi.fn();
  $.ajax = vi.fn(() => ({ done: () => ({ fail: () => {} }), fail: () => ({ done: () => {} }) }));
  $.fn = {};
  return $;
}

function setupDOM() {
  document.body.innerHTML = `
    <div id="linesContainer"></div>
    <input type="hidden" id="line_count" value="0">
    <select id="currency"><option value="ILS">ILS</option><option value="USD">USD</option></select>
    <input type="hidden" id="exchange_rate" value="1">
    <input type="hidden" id="tax_rate" value="0">
    <input type="hidden" id="freight" value="0">
    <input type="hidden" id="insurance" value="0">
    <input type="hidden" id="customs_duty" value="0">
    <input type="hidden" id="other_landed_cost" value="0">
    <input type="hidden" id="supplier_id" value="">
    <div id="summary_subtotal"></div>
    <div id="summary_tax"></div>
    <div id="summary_landed_cost"></div>
    <div id="summary_total"></div>
    <button id="addLineBtn"></button>
    <button id="recalcTotalsBtn"></button>
    <form id="purchaseForm"></form>
  `;
}

function addProductLine(index, qty, cost, discount) {
  const div = document.createElement('div');
  div.className = 'product-line';
  div.id = `line_${index}`;
  div.innerHTML = `
    <input class="line-quantity" data-line="${index}" value="${qty}">
    <input class="line-cost" data-line="${index}" value="${cost}" data-base-cost="${cost}">
    <input class="line-discount" data-line="${index}" value="${discount}">
    <input class="line-total" id="line_total_${index}" data-line="${index}" value="0.00">
  `;
  document.getElementById('linesContainer').appendChild(div);
}

function mockFetchSuccess() {
  global.fetch = vi.fn(async () => ({
    json: async () => ({
      success: true,
      subtotal: 0,
      tax_amount: 0,
      landed_cost: 0,
      total: 0,
    }),
  }));
}

function mockFetchFail() {
  global.fetch = vi.fn(async () => ({
    json: async () => ({ success: false }),
  }));
}

async function loadModule() {
  window._FX_FALLBACK_BASE = 'ILS';
  window._CURRENCY_SYMBOL = '\u20AA';
  window._PURCHASE_LABELS = {};
  window._PURCHASE_CALC_URL = '/purchases/api/calculate-totals';
  window._PRICES_INCLUDE_VAT = false;
  window.SmartSelectors = { initProducts: vi.fn() };
  window.toastr = undefined;
  window.alert = vi.fn();
  mockFetchSuccess();
  const $ = buildJQuery();
  global.$ = $;
  window.$ = $;
  modalCalls = [];
  await import('../../static/js/purchases/create.js');
}

beforeEach(async () => {
  vi.resetModules();
  setupDOM();
  await loadModule();
  // Clear the auto-added first line so tests start fresh
  const lc = document.getElementById('linesContainer');
  if (lc) lc.innerHTML = '';
  window.toastr = undefined;
  window.alert = vi.fn();
  mockFetchSuccess();
  const $ = buildJQuery();
  global.$ = $;
  window.$ = $;
  if (typeof globalThis._purchaseTotalsServerDown !== 'undefined') {
    globalThis._purchaseTotalsServerDown = false;
  }
});

afterEach(() => {
  document.body.innerHTML = '';
  delete global.fetch;
  delete window.toastr;
  delete global.$;
  delete window.$;
  delete window.SmartSelectors;
  delete window.azadEsc;
  delete window.notify;
  delete window.calculateLineTotal;
  delete window.calculateTotals;
  delete window.calculateTotalsClientSide;
  delete window._purchaseClientSideFallback;
  delete window.updateLineCosts;
  delete window.addLine;
  delete window.removeLine;
  vi.restoreAllMocks();
});

describe('purchases/create.js', () => {
  describe('azadEsc', () => {
    it('escapes & < > " \' characters', () => {
      expect(window.azadEsc('a&b')).toBe('a&amp;b');
      expect(window.azadEsc('<script>')).toBe('&lt;script&gt;');
      expect(window.azadEsc('x"y')).toBe('x&quot;y');
      expect(window.azadEsc("a'b")).toBe('a&#39;b');
      expect(window.azadEsc('a<b&c"d\'e')).toBe('a&lt;b&amp;c&quot;d&#39;e');
    });

    it('returns empty string for null and undefined', () => {
      expect(window.azadEsc(null)).toBe('');
      expect(window.azadEsc(undefined)).toBe('');
    });

    it('passes through plain strings unchanged', () => {
      expect(window.azadEsc('hello world 123')).toBe('hello world 123');
    });
  });

  describe('notify', () => {
    it('calls toastr.warning when toastr is available', () => {
      window.toastr = { warning: vi.fn(), success: vi.fn(), error: vi.fn() };
      window.notify('warning', 'test message');
      expect(window.toastr.warning).toHaveBeenCalledWith('test message');
      expect(window.alert).not.toHaveBeenCalled();
    });

    it('calls toastr.success for success kind', () => {
      window.toastr = { success: vi.fn() };
      window.notify('success', 'done');
      expect(window.toastr.success).toHaveBeenCalledWith('done');
    });

    it('calls alert when toastr is unavailable', () => {
      window.toastr = undefined;
      window.notify('warning', 'fallback msg');
      expect(window.alert).toHaveBeenCalledWith('fallback msg');
    });

    it('calls alert when toastr[kind] is not a function', () => {
      window.toastr = { warning: 'not a function' };
      window.notify('warning', 'msg');
      expect(window.alert).toHaveBeenCalledWith('msg');
    });
  });

  describe('_removeLine', () => {
    it('is exposed on window.removeLine', () => {
      expect(typeof window.removeLine).toBe('function');
    });
  });

  describe('calculateLineTotal', () => {
    it('computes qty * cost - discount correctly', () => {
      addProductLine(0, 10, 5, 10);
      window.calculateLineTotal(0);
      const el = document.getElementById('line_total_0');
      expect(el.value).toBe('45.00');
    });

    it('handles zero values gracefully', () => {
      addProductLine(5, 0, 0, 0);
      window.calculateLineTotal(5);
      const el = document.getElementById('line_total_5');
      expect(el.value).toBe('0.00');
    });
  });

  describe('calculateTotalsClientSide', () => {
    it('computes correct totals for multiple lines', async () => {
      addProductLine(0, 2, 100, 10);
      addProductLine(1, 1, 50, 0);
      mockFetchFail();

      await window.calculateTotalsClientSide();

      expect(document.getElementById('line_total_0').value).toBe('180.00');
      expect(document.getElementById('line_total_1').value).toBe('50.00');
    });

    it('sets summary text elements with calculated values', async () => {
      addProductLine(0, 5, 20, 0);
      mockFetchFail();

      await window.calculateTotalsClientSide();

      expect(document.getElementById('summary_subtotal').textContent).toContain('100.00');
      expect(document.getElementById('summary_total').textContent).toBeDefined();
    });
  });

  describe('_purchaseClientSideFallback', () => {
    it('warns once per outage episode', async () => {
      window.toastr = { warning: vi.fn() };
      globalThis._purchaseTotalsServerDown = false;
      addProductLine(0, 1, 10, 0);
      mockFetchFail();

      await window._purchaseClientSideFallback();
      await window._purchaseClientSideFallback();

      expect(window.toastr.warning).toHaveBeenCalledTimes(1);
    });
  });

  describe('updateLineCosts', () => {
    it('converts costs by exchange rate when currency differs', () => {
      addProductLine(0, 5, 100, 0);
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '3.5';
      mockFetchSuccess();

      window.updateLineCosts();

      expect(document.querySelector('.line-cost').value).toBe('28.57');
    });

    it('keeps base cost when currency matches tenant base', () => {
      addProductLine(0, 5, 75, 0);
      document.getElementById('currency').value = 'ILS';
      document.getElementById('exchange_rate').value = '1';
      mockFetchSuccess();

      window.updateLineCosts();

      expect(document.querySelector('.line-cost').value).toBe('75.00');
    });

    it('skips lines with NaN base-cost', () => {
      addProductLine(0, 1, 10, 0);
      const costInput = document.querySelector('.line-cost');
      delete costInput.dataset.baseCost;
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '3.5';
      mockFetchSuccess();

      window.updateLineCosts();

      expect(costInput.value).toBe('10');
    });
  });
});
