import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let ajaxCalls;
let fadeOutCalls;
let handlers;
let addedListeners;

function makeJQuery() {
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
        getEl()?.insertAdjacentHTML('afterend', html);
        return api;
      },
      empty() {
        const el = getEl();
        if (el) el.innerHTML = '';
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
          handlers.push({ evt, sel, fn });
          const listener = (e) => {
            const t = e.target && typeof e.target.closest === 'function' ? e.target.closest(sel) : null;
            if (t) fn.call(t, e);
          };
          addedListeners.push({ evt, listener });
          document.addEventListener(evt, listener);
          return this;
        },
      };
    }
    if (typeof arg === 'string') {
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

async function importAiSales() {
  await import('../../static/js/ai-sales.js');
}

function setupDom() {
  const meta = document.createElement('meta');
  meta.name = 'csrf-token';
  meta.content = 'tok123';
  document.head.appendChild(meta);
}

beforeEach(() => {
  ajaxCalls = [];
  fadeOutCalls = [];
  handlers = [];
  addedListeners = [];
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  global._CURRENCY_SYMBOL = 'د.إ';
  window._CURRENCY_SYMBOL = 'د.إ';
  global._FX_FALLBACK_BASE = 'ILS';
  window._FX_FALLBACK_BASE = 'ILS';
  const $ = makeJQuery();
  global.$ = $;
  window.$ = $;
  global.jQuery = $;
  window.jQuery = $;
  vi.resetModules();
});

afterEach(() => {
  (addedListeners || []).forEach(({ evt, listener }) => document.removeEventListener(evt, listener));
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  delete global.$;
  delete window.$;
  delete global.jQuery;
  delete window.jQuery;
  delete global._CURRENCY_SYMBOL;
  delete window._CURRENCY_SYMBOL;
  delete global._FX_FALLBACK_BASE;
  delete window._FX_FALLBACK_BASE;
  delete window.applyRecommendedPrice;
  delete window.applyMarketPrice;
  vi.resetModules();
});

describe('ai-sales.js', () => {
  it('registers delegated change handlers on load', async () => {
    setupDom();
    await importAiSales();
    expect(handlers.map((h) => h.evt + ':' + h.sel).sort()).toEqual([
      'change:#currency',
      'change:#customer_id',
      'change:.product-select',
      'change:.quantity-input',
    ]);
  });

  it('analyzes customer and renders risk alerts', async () => {
    setupDom();
    const customer = document.createElement('select');
    customer.id = 'customer_id';
    const opt = document.createElement('option');
    opt.value = '5';
    customer.appendChild(opt);
    customer.value = '5';
    document.body.appendChild(customer);
    document.body.insertAdjacentHTML('beforeend', '<div id="customer_analysis"></div>');
    await importAiSales();
    customer.dispatchEvent(new Event('change', { bubbles: true }));
    expect(ajaxCalls.length).toBe(1);
    expect(ajaxCalls[0].url).toBe('/ai/analyze-customer/5');
    ajaxCalls[0].success({ risk_level: 'high', current_balance: 100.5, avg_payment_delay_days: 12, recommendation: 'احذر' });
    expect(document.getElementById('customer_analysis').innerHTML).toContain('alert-danger');
    expect(document.getElementById('customer_analysis').innerHTML).toContain('100.50');
    ajaxCalls[0].success({ risk_level: 'medium', current_balance: 0, avg_payment_delay_days: 3, recommendation: 'ok' });
    expect(document.getElementById('customer_analysis').innerHTML).toContain('alert-warning');
    ajaxCalls[0].success({ risk_level: 'low', current_balance: 0, avg_payment_delay_days: 1, recommendation: '<b>x</b>' });
    const html = document.getElementById('customer_analysis').innerHTML;
    expect(html).toContain('alert-info');
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;');
  });

  it('recommends price when product and customer selected', async () => {
    setupDom();
    const customer = document.createElement('select');
    customer.id = 'customer_id';
    const copt = document.createElement('option');
    copt.value = '5';
    customer.appendChild(copt);
    customer.value = '5';
    document.body.appendChild(customer);
    const product = document.createElement('select');
    product.className = 'product-select';
    product.dataset.lineIndex = '0';
    const popt = document.createElement('option');
    popt.value = '7';
    product.appendChild(popt);
    product.value = '7';
    document.body.appendChild(product);
    document.body.insertAdjacentHTML('beforeend', '<input id="unit_price_0" value="0">');
    await importAiSales();
    product.dispatchEvent(new Event('change', { bubbles: true }));
    const recommend = ajaxCalls.find((c) => c.url === '/ai/recommend-price');
    expect(recommend).toBeTruthy();
    expect(recommend.data).toBe(JSON.stringify({ product_id: '7', customer_id: '5' }));
    recommend.success({ recommended_price: 5.5 });
    expect(document.getElementById('unit_price_0').parentElement.querySelector('.ai-recommendation')).toBeTruthy();
  });

  it('skips price badge when current price matches recommendation', async () => {
    setupDom();
    const customer = document.createElement('select');
    customer.id = 'customer_id';
    const copt = document.createElement('option');
    copt.value = '5';
    customer.appendChild(copt);
    customer.value = '5';
    document.body.appendChild(customer);
    const product = document.createElement('select');
    product.className = 'product-select';
    product.dataset.lineIndex = '0';
    const popt = document.createElement('option');
    popt.value = '7';
    product.appendChild(popt);
    product.value = '7';
    document.body.appendChild(product);
    document.body.insertAdjacentHTML('beforeend', '<input id="unit_price_0" value="5.50">');
    await importAiSales();
    product.dispatchEvent(new Event('change', { bubbles: true }));
    ajaxCalls.find((c) => c.url === '/ai/recommend-price').success({ recommended_price: 5.5 });
    expect(document.querySelector('.ai-recommendation')).toBeNull();
  });

  it('rechecks price recommendations for all lines on customer change', async () => {
    setupDom();
    const customer = document.createElement('select');
    customer.id = 'customer_id';
    const copt = document.createElement('option');
    copt.value = '5';
    customer.appendChild(copt);
    customer.value = '5';
    document.body.appendChild(customer);
    document.body.insertAdjacentHTML(
      'beforeend',
      '<select class="product-select" data-line-index="0"><option value="7">7</option></select>' +
        '<input id="unit_price_0" value="0">',
    );
    document.querySelector('.product-select').value = '7';
    await importAiSales();
    customer.dispatchEvent(new Event('change', { bubbles: true }));
    const recommend = ajaxCalls.find((c) => c.url === '/ai/recommend-price');
    expect(recommend.data).toBe(JSON.stringify({ product_id: '7', customer_id: '5' }));
  });

  it('searches global market and shows found price or message', async () => {
    setupDom();
    const product = document.createElement('select');
    product.className = 'product-select';
    product.dataset.lineIndex = '0';
    const popt = document.createElement('option');
    popt.value = '7';
    product.appendChild(popt);
    product.value = '7';
    document.body.appendChild(product);
    document.body.insertAdjacentHTML('beforeend', '<div id="market_info_0"></div>');
    await importAiSales();
    product.dispatchEvent(new Event('change', { bubbles: true }));
    const market = ajaxCalls.find((c) => c.url === '/ai/search-market-price/7');
    market.success({ found: true, suggested_price_aed: 12.345, average_price_usd: 3.36, notes: 'note' });
    expect(document.getElementById('market_info_0').innerHTML).toContain('12.35');
    market.success({ message: 'قيد التطوير' });
    expect(document.getElementById('market_info_0').innerHTML).toContain('قيد التطوير');
  });

  it('finds compatible vehicles with escaping', async () => {
    setupDom();
    const product = document.createElement('select');
    product.className = 'product-select';
    product.dataset.lineIndex = '0';
    const popt = document.createElement('option');
    popt.value = '7';
    product.appendChild(popt);
    product.value = '7';
    document.body.appendChild(product);
    document.body.insertAdjacentHTML('beforeend', '<div id="compatible_vehicles"></div>');
    await importAiSales();
    product.dispatchEvent(new Event('change', { bubbles: true }));
    const compat = ajaxCalls.find((c) => c.url === '/ai/find-compatible/7');
    compat.success({
      found: true,
      vehicles: [
        { brand: '<b>Honda</b>', models: ['Civic', 'Accord'], years: '2020-2024', engine: '1.5T' },
      ],
      total_count: 6,
      notes: 'n1',
    });
    const html = document.getElementById('compatible_vehicles').innerHTML;
    expect(html).toContain('&lt;b&gt;Honda&lt;/b&gt;');
    expect(html).toContain('و 1 أخرى');
    compat.success({ message: '<script>alert(1)</script>' });
    expect(document.getElementById('compatible_vehicles').innerHTML).toContain('&lt;script&gt;');
    compat.success({ raw_response: 'raw' });
    expect(document.getElementById('compatible_vehicles').innerHTML).toContain('raw');
  });

  it('checks stock alert types', async () => {
    setupDom();
    const product = document.createElement('select');
    product.className = 'product-select';
    product.dataset.lineIndex = '0';
    const popt = document.createElement('option');
    popt.value = '7';
    product.appendChild(popt);
    product.value = '7';
    document.body.appendChild(product);
    document.body.insertAdjacentHTML('beforeend', '<div id="stock_alert_0"></div>');
    const qty = document.createElement('input');
    qty.className = 'quantity-input';
    qty.dataset.lineIndex = '0';
    qty.value = '3';
    document.body.appendChild(qty);
    await importAiSales();
    qty.dispatchEvent(new Event('change', { bubbles: true }));
    const stock = ajaxCalls.find((c) => c.url === '/ai/check-stock');
    expect(stock.data).toBe(JSON.stringify({ product_id: '7', quantity: 3 }));
    stock.success({ type: 'error', message: '<i>none</i>' });
    expect(document.getElementById('stock_alert_0').querySelector('.alert-danger').innerHTML).toContain('&lt;i&gt;none&lt;/i&gt;');
    stock.success({ type: 'warning', message: 'low' });
    expect(document.getElementById('stock_alert_0').querySelector('.alert-warning')).toBeTruthy();
  });

  it('sets base currency rate without ajax', async () => {
    setupDom();
    document.body.insertAdjacentHTML('beforeend', '<input id="exchange_rate">');
    document.body.insertAdjacentHTML('beforeend', '<select id="currency"><option value="ILS">ILS</option></select>');
    const currency = document.getElementById('currency');
    currency.value = 'ILS';
    await importAiSales();
    currency.dispatchEvent(new Event('change', { bubbles: true }));
    expect(ajaxCalls.length).toBe(0);
    expect(document.getElementById('exchange_rate').value).toBe('1.00');
  });

  it('suggests exchange rate and appends source info', async () => {
    setupDom();
    document.body.insertAdjacentHTML('beforeend', '<input id="exchange_rate">');
    const currency = document.createElement('select');
    currency.id = 'currency';
    const opt = document.createElement('option');
    opt.value = 'USD';
    currency.appendChild(opt);
    currency.value = 'USD';
    document.body.appendChild(currency);
    await importAiSales();
    currency.dispatchEvent(new Event('change', { bubbles: true }));
    const fx = ajaxCalls.find((c) => c.url === '/ai/exchange-rate/USD');
    fx.success({ suggested_rate: 3.6725, source: 'بيانات', count: 5 });
    expect(document.getElementById('exchange_rate').value).toBe('3.672500');
    const small = document.getElementById('exchange_rate').parentElement.querySelector('small');
    expect(small.textContent).toContain('بيانات');
    expect(small.textContent).toContain('بناءً على 5 معاملات');
    fx.success({ suggested_rate: 1, source: 'x', count: 0 });
    expect(document.querySelector('#exchange_rate + small').textContent).not.toContain('معاملات');
  });

  it('initializes exchange rate from currency on load', async () => {
    setupDom();
    document.body.insertAdjacentHTML('beforeend', '<input id="exchange_rate">');
    document.body.insertAdjacentHTML(
      'beforeend',
      '<select id="currency"><option value="EUR">EUR</option></select>',
    );
    await importAiSales();
    const fx = ajaxCalls.find((c) => c.url === '/ai/exchange-rate/EUR');
    expect(fx).toBeTruthy();
  });

  it('applies recommended and market prices', async () => {
    setupDom();
    document.body.insertAdjacentHTML('beforeend', '<input id="unit_price_0" value="1">');
    document.body.insertAdjacentHTML('beforeend', '<div id="market_info_0"></div>');
    await importAiSales();
    window.applyRecommendedPrice(0, 12.345);
    expect(document.getElementById('unit_price_0').value).toBe('12.35');
    expect(fadeOutCalls).toContain('.ai-recommendation');
    window.applyMarketPrice(0, 9.876);
    expect(document.getElementById('unit_price_0').value).toBe('9.88');
    expect(fadeOutCalls).toContain('#market_info_0');
  });
});
