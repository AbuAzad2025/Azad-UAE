import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let R;

function makeStubJQuery() {
  const reg = {
    currencyChange: [],
    exchangeHandlers: [],
    supplierChange: [],
    docDelegated: [],
    select2Select: [],
    taxHandlers: [],
    recalcHandlers: [],
    addLineHandlers: [],
    submitHandlers: [],
    select2OptsList: [],
    lastSelect2Opts: null,
    lastAjaxOpts: null,
    supplierData: [],
  };
  const dataStore = new WeakMap();

  function wrap(els) {
    const list = Array.isArray(els) ? els.filter(Boolean) : [els].filter(Boolean);
    const api = {
      length: list.length,
      each(fn) {
        list.forEach((el, i) => fn.call(el, i, el));
        return api;
      },
      find(sel) {
        const out = [];
        list.forEach((el) => {
          if (el.querySelectorAll) out.push(...Array.from(el.querySelectorAll(sel)));
        });
        return wrap(out);
      },
      append(arg) {
        list.forEach((el) => {
          if (typeof arg === 'string') el.insertAdjacentHTML('beforeend', arg);
          else if (arg instanceof Node) el.appendChild(arg);
        });
        return api;
      },
      html(v) {
        if (v === undefined) return list[0]?.innerHTML ?? '';
        list.forEach((el) => {
          el.innerHTML = v;
        });
        return api;
      },
      text(v) {
        if (v === undefined) return list[0]?.textContent ?? '';
        list.forEach((el) => {
          el.textContent = String(v);
        });
        return api;
      },
      val(v) {
        if (v === undefined) return list[0]?.value ?? '';
        list.forEach((el) => {
          if ('value' in el) el.value = String(v);
        });
        return api;
      },
      attr(n, v) {
        if (v === undefined) return list[0]?.getAttribute(n);
        list.forEach((el) => el.setAttribute(n, String(v)));
        return api;
      },
      data(k, v) {
        if (v === undefined) {
          if (!list[0]) return undefined;
          const s = dataStore.get(list[0]);
          if (s && k in s) return s[k];
          const camel = k.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          return list[0].dataset?.[camel];
        }
        list.forEach((el) => {
          const s = dataStore.get(el) || {};
          s[k] = v;
          dataStore.set(el, s);
        });
        return api;
      },
      hasClass(cls) {
        return list.some((el) => el.classList?.contains(cls));
      },
      show() {
        list.forEach((el) => {
          el.style.display = 'block';
        });
        return api;
      },
      hide() {
        list.forEach((el) => {
          el.style.display = 'none';
        });
        return api;
      },
      remove() {
        list.forEach((el) => {
          if (el.parentNode) el.parentNode.removeChild(el);
        });
        return api;
      },
      select2(...a) {
        if (typeof a[0] === 'string') {
          if (a[0] === 'data') return reg.supplierData;
          return api;
        }
        if (a[0] && typeof a[0] === 'object') {
          reg.select2OptsList.push(a[0]);
          reg.lastSelect2Opts = a[0];
        }
        return api;
      },
      on(...args) {
        let names;
        let sel = null;
        let h = null;
        if (typeof args[0] === 'string' && typeof args[1] === 'function') {
          names = args[0];
          h = args[1];
        } else if (typeof args[1] === 'string' && typeof args[2] === 'function') {
          names = args[0];
          sel = args[1];
          h = args[2];
        } else {
          return api;
        }
        const nameList = names.split(/\s+/).filter(Boolean);
        list.forEach((el) => {
          const id = el.id || '';
          const isDoc = el === document;
          nameList.forEach((n) => {
            if (isDoc && sel && sel.includes('.line-quantity')) {
              reg.docDelegated.push({ sel, h });
            } else if (id === 'currency' && n === 'change') {
              reg.currencyChange.push(h);
            } else if (id === 'exchange_rate') {
              reg.exchangeHandlers.push(h);
            } else if (id === 'supplier_id' && n === 'change') {
              reg.supplierChange.push(h);
            } else if (id === 'tax_rate') {
              reg.taxHandlers.push(h);
            } else if (id === 'recalcTotalsBtn') {
              reg.recalcHandlers.push(h);
            } else if (id === 'addLineBtn') {
              reg.addLineHandlers.push(h);
            } else if (id === 'purchaseForm' && n === 'submit') {
              reg.submitHandlers.push(h);
            } else if (n === 'select2:select') {
              reg.select2Select.push(h);
            }
          });
          nameList.forEach((n) => {
            el.addEventListener(n, function (...a2) {
              if (sel) {
                const t = a2[0] && a2[0].target;
                const hit = t instanceof Element ? t.closest(sel) : null;
                if (!hit) return;
              }
              h.apply(this, a2);
            });
          });
        });
        return api;
      },
      ready(fn) {
        if (typeof fn === 'function') fn();
        return api;
      },
    };
    return api;
  }

  function $(sel) {
    if (typeof sel === 'function') {
      sel();
      return wrap([]);
    }
    if (typeof sel === 'string') {
      const t = sel.trimStart();
      if (t.startsWith('<')) {
        const tpl = document.createElement('template');
        tpl.innerHTML = sel.trim();
        const node = tpl.content.firstElementChild;
        return wrap(node ? [node] : []);
      }
      try {
        return wrap(Array.from(document.querySelectorAll(sel)));
      } catch {
        return wrap([]);
      }
    }
    if (sel instanceof Node || sel === document || sel === window) {
      const a = wrap(sel === window ? [] : [sel]);
      return a;
    }
    return wrap([]);
  }
  $.ajax = vi.fn((opts) => {
    reg.lastAjaxOpts = opts;
  });
  $.fn = {};
  return { $, reg };
}

function setupDOM() {
  document.body.innerHTML = `
    <div id="linesContainer"></div>
    <input type="hidden" id="line_count" value="0">
    <select id="currency"><option value="ILS">ILS</option><option value="USD">USD</option></select>
    <input id="exchange_rate" value="1">
    <input id="tax_rate" value="0">
    <input id="freight" value="0">
    <input id="insurance" value="0">
    <input id="customs_duty" value="0">
    <input id="other_landed_cost" value="0">
    <select id="supplier_id"><option value=""></option><option value="5">Sup</option></select>
    <input id="supplier_phone" value="">
    <input id="supplier_email" value="">
    <div id="summary_subtotal"></div>
    <div id="summary_tax"></div>
    <div id="summary_landed_cost"></div>
    <div id="summary_total"></div>
    <button id="addLineBtn"></button>
    <button id="recalcTotalsBtn"></button>
    <form id="purchaseForm"></form>
    <select id="warehouse_id"><option value="1">WH</option></select>
  `;
}

async function flush(times = 5) {
  for (let i = 0; i < times; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

beforeEach(async () => {
  setupDOM();
  window.purchaseLineIndex = 0;
  window._FX_FALLBACK_BASE = 'ILS';
  window._CURRENCY_SYMBOL = '₪';
  window._PURCHASE_LABELS = {};
  window._PURCHASE_CALC_URL = '/purchases/api/calculate-totals';
  window._PRICES_INCLUDE_VAT = false;
  window._API_SEARCH_URL = '/api/search';
  delete window.SmartSelectors;
  window.toastr = undefined;
  window.alert = vi.fn();
  global.fetch = vi.fn(async () => ({
    json: async () => ({ success: true, subtotal: 0, tax_amount: 0, landed_cost: 0, total: 0 }),
  }));
  const stub = makeStubJQuery();
  R = stub.reg;
  global.$ = stub.$;
  window.$ = stub.$;
  vi.resetModules();
  await import('../../static/js/purchases/create.js');
});

afterEach(() => {
  document.body.innerHTML = '';
  delete global.fetch;
  delete global.$;
  delete window.$;
  delete window.SmartSelectors;
  delete window.azadEsc;
  delete window.notify;
  delete window.addLine;
  delete window.removeLine;
  delete window.calculateLineTotal;
  delete window.calculateTotals;
  delete window.calculateTotalsClientSide;
  delete window._purchaseClientSideFallback;
  delete window.updateLineCosts;
  vi.restoreAllMocks();
});

describe('purchases/create gap100 — select2 fallback config', () => {
  it('ajax data() builds query with defaults and values', () => {
    const opts = R.lastSelect2Opts;
    expect(opts).toBeTruthy();
    document.getElementById('warehouse_id').value = '1';
    const full = opts.ajax.data({ term: 'abc', page: 3 });
    expect(full).toMatchObject({ q: 'abc', type: 'products', purpose: 'purchase', page: 3 });
    expect(full.warehouse_id).toBe('1');
    const dflt = opts.ajax.data({});
    expect(dflt.q).toBe('');
    expect(dflt.page).toBe(1);
  });

  it('processResults() maps products with escaping and fallbacks', () => {
    const opts = R.lastSelect2Opts;
    const out = opts.ajax.processResults({
      results: [
        { id: 1, name: '<b>x</b>', sku: 'S1', cost_price: 5, current_stock: 3 },
        { id: 2, name: 'plain', sku: null },
      ],
      has_more: true,
    });
    expect(out.results[0].text).toBe('&lt;b&gt;x&lt;/b&gt;');
    expect(out.results[0].cost_price).toBe(5);
    expect(out.results[0].current_stock).toBe(3);
    expect(out.results[1].cost_price).toBe(0);
    expect(out.results[1].current_stock).toBe(0);
    expect(out.pagination.more).toBe(true);
    const out2 = opts.ajax.processResults({ results: [], has_more: false });
    expect(out2.pagination.more).toBe(false);
  });

  it('templateResult() covers loading / empty / stock states', () => {
    const opts = R.lastSelect2Opts;
    expect(opts.templateResult({ loading: true })).toBe('جاري البحث...');
    expect(opts.templateResult({ text: 'none' })).toBe('none');
    const withStock = opts.templateResult({
      id: 1,
      text: 'Prod',
      sku: 'SK',
      cost_price: 9.5,
      current_stock: 4,
    });
    expect(withStock.text()).toContain('Prod');
    const noStock = opts.templateResult({ id: 2, text: 'P2', cost_price: 0, current_stock: 0 });
    expect(noStock.text()).toContain('P2');
    const missing = opts.templateResult({ id: 3, text: 'P3' });
    expect(missing.text()).toContain('P3');
  });

  it('templateSelection() covers with-id and without-id', () => {
    const opts = R.lastSelect2Opts;
    expect(opts.templateSelection({ id: 7, text: 'Chosen' })).toBe('📦 Chosen');
    expect(opts.templateSelection({ text: 'placeholder' })).toBe('placeholder');
  });
});

describe('purchases/create gap100 — select2:select handler', () => {
  function addManualLine1() {
    const host = document.createElement('div');
    host.className = 'product-line';
    host.id = 'line_1';
    host.innerHTML = `
      <input class="line-quantity" data-line="1" value="2">
      <input class="line-cost" data-line="1" value="0">
      <input class="line-discount" data-line="1" value="0">
      <input id="line_total_1" data-line="1" value="0.00">
      <div class="row serial-row" id="serial_row_1" style="display:none;"></div>
    `;
    document.getElementById('linesContainer').appendChild(host);
  }

  it('stores base-cost and shows serial row when product has serials', async () => {
    addManualLine1();
    const h = R.select2Select[0];
    h.call(document.querySelector('select.product-select'), {
      params: { data: { cost_price: 20, has_serial_number: true } },
    });
    await flush();
    const cost = document.querySelector('.line-cost[data-line="1"]');
    expect(global.$(cost).data('base-cost')).toBe(20);
    expect(document.getElementById('serial_row_1').style.display).toBe('block');
  });

  it('hides serial row when product has no cost and no serials', async () => {
    addManualLine1();
    const h = R.select2Select[0];
    h.call(document.querySelector('select.product-select'), {
      params: { data: { has_serial_number: false } },
    });
    await flush();
    expect(document.getElementById('serial_row_1').style.display).toBe('none');
  });

  it('handles missing event data without throwing', async () => {
    addManualLine1();
    const h = R.select2Select[0];
    expect(() => h.call(document.querySelector('select.product-select'), { params: {} })).not.toThrow();
    await flush();
    expect(document.getElementById('serial_row_1').style.display).toBe('none');
  });
});

describe('purchases/create gap100 — totals fallback and client-side success', () => {
  function fillLine0(qty, cost) {
    document.querySelector('.line-quantity[data-line="0"]').value = String(qty);
    document.querySelector('.line-cost[data-line="0"]').value = String(cost);
  }

  it('falls back to client-side when backend reports failure', async () => {
    fillLine0(1, 10);
    global.fetch = vi.fn(async () => ({ json: async () => ({ success: false }) }));
    await window.calculateTotals();
    expect(window.alert).toHaveBeenCalled();
    expect(document.getElementById('summary_subtotal').textContent).toContain('10.00');
  });

  it('falls back to client-side when fetch throws', async () => {
    fillLine0(2, 5);
    global.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('net'))
      .mockResolvedValue({ json: async () => ({ success: false }) });
    await window.calculateTotals();
    expect(window.alert).toHaveBeenCalled();
    expect(document.getElementById('summary_subtotal').textContent).toContain('10.00');
  });

  it('applies server success with data envelope in client-side calc', async () => {
    fillLine0(2, 5);
    global.fetch = vi.fn(async () => ({
      json: async () => ({
        success: true,
        data: { subtotal: 9, tax_amount: 1, landed_cost: 2, total: 12 },
      }),
    }));
    await window.calculateTotalsClientSide();
    expect(document.getElementById('summary_subtotal').textContent).toContain('9.00');
    expect(document.getElementById('summary_tax').textContent).toContain('1.00');
    expect(document.getElementById('summary_landed_cost').textContent).toContain('2.00');
    expect(document.getElementById('summary_total').textContent).toContain('12.00');
  });

  it('applies server success with bare response in client-side calc', async () => {
    fillLine0(1, 7);
    global.fetch = vi.fn(async () => ({
      json: async () => ({ success: true, subtotal: 7, tax_amount: 0, landed_cost: 0, total: 7 }),
    }));
    await window.calculateTotalsClientSide();
    expect(document.getElementById('summary_subtotal').textContent).toContain('7.00');
    expect(document.getElementById('summary_total').textContent).toContain('7.00');
  });
});

describe('purchases/create gap100 — currency and supplier handlers', () => {
  it('fetches rate on foreign currency and applies it', async () => {
    const cur = document.getElementById('currency');
    cur.value = 'USD';
    R.currencyChange[0].call(cur);
    expect(global.$.ajax).toHaveBeenCalled();
    R.lastAjaxOpts.success({ rate: 3.5 });
    await flush();
    expect(document.getElementById('exchange_rate').value).toBe('3.500000');
  });

  it('warns when rate is missing and when ajax fails', () => {
    const cur = document.getElementById('currency');
    cur.value = 'USD';
    R.currencyChange[0].call(cur);
    R.lastAjaxOpts.success({});
    expect(window.alert).toHaveBeenCalledWith('يرجى إدخال سعر الصرف يدوياً');
    window.alert.mockClear();
    R.currencyChange[0].call(cur);
    R.lastAjaxOpts.error();
    expect(window.alert).toHaveBeenCalledWith('يرجى إدخال سعر الصرف يدوياً');
  });

  it('resets rate for base currency', async () => {
    const cur = document.getElementById('currency');
    cur.value = 'ILS';
    R.currencyChange[0].call(cur);
    await flush();
    expect(document.getElementById('exchange_rate').value).toBe('1.000000');
  });

  it('recalculates on exchange-rate input', () => {
    const cost = document.querySelector('.line-cost[data-line="0"]');
    global.$(cost).data('base-cost', 70);
    document.getElementById('currency').value = 'USD';
    document.getElementById('exchange_rate').value = '3.5';
    R.exchangeHandlers[0].call(document.getElementById('exchange_rate'));
    expect(cost.value).toBe('20.00');
  });

  it('fills supplier details and notifies verified suppliers', () => {
    window.toastr = { success: vi.fn() };
    R.supplierData = [{ phone: '111', email: 'e@x.com', is_verified: true, name: 'V' }];
    R.supplierChange[0].call(document.getElementById('supplier_id'));
    expect(document.getElementById('supplier_phone').value).toBe('111');
    expect(document.getElementById('supplier_email').value).toBe('e@x.com');
    expect(window.toastr.success).toHaveBeenCalled();
  });

  it('skips notify for unverified supplier and empty selection', () => {
    window.toastr = { success: vi.fn() };
    R.supplierData = [{ phone: '', email: '', is_verified: false, name: 'U' }];
    R.supplierChange[0].call(document.getElementById('supplier_id'));
    expect(window.toastr.success).not.toHaveBeenCalled();
    R.supplierData = [];
    expect(() =>
      R.supplierChange[0].call(document.getElementById('supplier_id')),
    ).not.toThrow();
  });
});

describe('purchases/create gap100 — SmartSelectors path and removeLine', () => {
  it('uses SmartSelectors when available', () => {
    window.SmartSelectors = { initProducts: vi.fn() };
    window.addLine();
    expect(window.SmartSelectors.initProducts).toHaveBeenCalled();
  });

  it('removeLine deletes the line and recalculates', async () => {
    expect(document.getElementById('line_0')).not.toBeNull();
    window.removeLine(0);
    await flush();
    expect(document.getElementById('line_0')).toBeNull();
    expect(global.fetch).toHaveBeenCalled();
  });
});

describe('purchases/create gap100 — delegation and ready/submit handlers', () => {
  it('returns early when line number is missing', () => {
    const orphan = document.createElement('input');
    orphan.className = 'line-quantity';
    document.body.appendChild(orphan);
    const { h } = R.docDelegated[0];
    expect(() => h.call(orphan, {})).not.toThrow();
    orphan.remove();
  });

  it('recalculates line total on quantity input', async () => {
    document.querySelector('.line-quantity[data-line="0"]').value = '4';
    document.querySelector('.line-cost[data-line="0"]').value = '5';
    const { h } = R.docDelegated[0];
    h.call(document.querySelector('.line-quantity[data-line="0"]'), {});
    await flush();
    expect(document.getElementById('line_total_0').value).toBe('20.00');
    expect(global.fetch).toHaveBeenCalled();
  });

  it('tracks base-cost on cost input for foreign and base currency', async () => {
    const cost = document.querySelector('.line-cost[data-line="0"]');
    const { h } = R.docDelegated[0];
    document.getElementById('currency').value = 'USD';
    document.getElementById('exchange_rate').value = '2';
    cost.value = '10';
    h.call(cost, {});
    expect(global.$(cost).data('base-cost')).toBe(20);
    document.getElementById('currency').value = 'ILS';
    cost.value = '7';
    h.call(cost, {});
    expect(global.$(cost).data('base-cost')).toBe(7);
    await flush();
  });

  it('wires tax / recalc / add-line controls', async () => {
    const before = document.querySelectorAll('.product-line').length;
    R.taxHandlers[0].call(document.getElementById('tax_rate'));
    await flush();
    expect(global.fetch).toHaveBeenCalled();
    global.fetch.mockClear();
    R.recalcHandlers[0].call(document.getElementById('recalcTotalsBtn'));
    await flush();
    expect(global.fetch).toHaveBeenCalled();
    R.addLineHandlers[0].call(document.getElementById('addLineBtn'));
    expect(document.querySelectorAll('.product-line').length).toBe(before + 1);
  });

  it('blocks submit when no lines exist', () => {
    document.getElementById('linesContainer').innerHTML = '';
    const form = document.getElementById('purchaseForm');
    const evt = new Event('submit', { cancelable: true });
    form.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(true);
    expect(window.alert).toHaveBeenCalledWith('يجب إضافة منتج واحد على الأقل');
  });

  it('blocks submit when supplier is missing', () => {
    document.getElementById('supplier_id').value = '';
    const form = document.getElementById('purchaseForm');
    const evt = new Event('submit', { cancelable: true });
    form.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(true);
    expect(window.alert).toHaveBeenCalledWith('يجب اختيار المورد');
  });

  it('submits when lines and supplier are present', () => {
    document.querySelector('.line-quantity[data-line="0"]').value = '2';
    document.querySelector('.line-cost[data-line="0"]').value = '8';
    document.getElementById('supplier_id').value = '5';
    const form = document.getElementById('purchaseForm');
    const evt = new Event('submit', { cancelable: true });
    form.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(false);
  });
});
