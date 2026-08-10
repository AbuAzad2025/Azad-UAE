import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let select2Calls;
let destroyCalls;

function makeJQuery() {
  const mk = (els) => {
    const getEl = () => els[0] || null;
    return {
      els,
      get length() {
        return els.length;
      },
      hasClass(cls) {
        return getEl()?.classList.contains(cls) || false;
      },
      each(fn) {
        els.forEach((el, i) => fn.call(el, i, el));
        return this;
      },
      select2(arg) {
        const el = getEl();
        if (arg === 'destroy') {
          destroyCalls.push(el);
        } else {
          select2Calls.push({ el, opts: arg });
        }
        return this;
      },
      on(evt, fn) {
        const el = getEl();
        if (el) el.addEventListener(evt, fn);
        return this;
      },
    };
  };

  const $ = (arg) => {
    if (arg === document) {
      return {
        ready(fn) {
          fn();
          return this;
        },
        on(evt, fn) {
          window.addEventListener(evt, fn);
          return this;
        },
      };
    }
    if (typeof arg === 'string') {
      let nodes = [];
      if (arg.trim().startsWith('<')) {
        const container = document.createElement('div');
        container.innerHTML = arg;
        nodes = Array.from(container.children);
      } else {
        try {
          nodes = Array.from(document.querySelectorAll(arg));
        } catch {
          nodes = [];
        }
      }
      return mk(nodes);
    }
    return mk([arg]);
  };
  return $;
}

async function importCustomerSelect() {
  await import('../../static/js/customer-select.js');
  return {
    SmartSearch: window.SmartSearch,
    initCustomerSelect: window.initCustomerSelect,
    initSupplierSelect: window.initSupplierSelect,
    initProductSelect: window.initProductSelect,
  };
}

beforeEach(() => {
  select2Calls = [];
  destroyCalls = [];
  document.body.innerHTML = '';
  const $ = makeJQuery();
  global.$ = $;
  window.$ = $;
  global.jQuery = $;
  window.jQuery = $;
  vi.resetModules();
});

afterEach(() => {
  document.body.innerHTML = '';
  delete global.$;
  delete window.$;
  delete global.jQuery;
  delete window.jQuery;
  delete window.SmartSearch;
  delete window.initCustomerSelect;
  delete window.initSupplierSelect;
  delete window.initProductSelect;
  vi.useRealTimers();
  vi.resetModules();
});

describe('customer-select.js', () => {
  it('exposes SmartSearch and init functions', async () => {
    const exported = await importCustomerSelect();
    expect(exported.SmartSearch).toBeTruthy();
    expect(typeof exported.initCustomerSelect).toBe('function');
    expect(typeof exported.initSupplierSelect).toBe('function');
    expect(typeof exported.initProductSelect).toBe('function');
  });

  it('esc escapes HTML special characters', async () => {
    const { SmartSearch } = await importCustomerSelect();
    expect(SmartSearch.esc('<script>"&\'</script>')).toBe('&lt;script&gt;&quot;&amp;&#39;&lt;/script&gt;');
    expect(SmartSearch.esc(null)).toBe('');
    expect(SmartSearch.esc(undefined)).toBe('');
  });

  function runInit(name, className) {
    const select = document.createElement('select');
    select.className = className;
    document.body.appendChild(select);
    const api = window.SmartSearch[name]();
    return { select, cfg: select2Calls.find((c) => c.el === select).opts };
  }

  it('initializes customer search with processResults', async () => {
    await importCustomerSelect();
    const { select, cfg } = runInit('initCustomerSearch', 'customer-select');
    expect(select2Calls.length).toBe(1);
    expect(cfg.ajax.url).toBe('/customers/api/search');
    expect(cfg.placeholder).toContain('زبون');
    const res = cfg.ajax.processResults([{ id: 1, name: '<b>A</b>', phone: '050' }]);
    expect(res.results[0].name).toBe('&lt;b&gt;A&lt;/b&gt;');
    expect(res.results[0].phone).toBe('050');
    expect(res.results[0].text).toContain('&lt;b&gt;A&lt;/b&gt;');
    const res2 = cfg.ajax.processResults({ results: [{ id: 2, name: 'B', text: 'B text' }] });
    expect(res2.results[0].text).toBe('B text');
    expect(cfg.ajax.data({ term: 'x', page: 2 })).toEqual({ q: 'x', page: 2 });
    expect(cfg.ajax.data({})).toEqual({ q: '', page: 1 });
  });

  it('initializes supplier search', async () => {
    await importCustomerSelect();
    const { cfg } = runInit('initSupplierSearch', 'supplier-select');
    expect(cfg.ajax.url).toBe('/suppliers/api/search');
    const res = cfg.ajax.processResults([{ id: 1, name: 'S', phone: '99' }]);
    expect(res.results[0].text).toContain('99');
    expect(res.results[0].balance).toBe(0);
  });

  it('initializes product search', async () => {
    await importCustomerSelect();
    const { cfg } = runInit('initProductSearch', 'product-select');
    expect(cfg.ajax.url).toBe('/products/api/search');
    const res = cfg.ajax.processResults([{ id: 1, name: 'P', code: 'C1', price: 10, stock: 5 }]);
    expect(res.results[0].text).toContain('C1');
    expect(res.results[0].code).toBe('C1');
  });

  it('destroys existing select2 before re-initializing', async () => {
    await importCustomerSelect();
    const select = document.createElement('select');
    select.className = 'customer-select';
    document.body.appendChild(select);
    select.classList.add('select2-hidden-accessible');
    window.SmartSearch.initCustomerSearch();
    expect(destroyCalls).toContain(select);
    expect(select2Calls.length).toBe(1);
  });

  it('formats customer results', async () => {
    await importCustomerSelect();
    const { SmartSearch } = window;
    expect(SmartSearch.formatCustomerResult({ loading: true })).toContain('جاري البحث');
    expect(SmartSearch.formatCustomerResult({ id: null, text: 'plain' })).toBe('plain');
    const item = { id: 1, name: 'Ali', phone: '050123', balance: '50.5' };
    const html = SmartSearch.formatCustomerResult(item).els[0].innerHTML;
    expect(html).toContain('+50.50');
    expect(html).toContain('Ali');
    const neg = SmartSearch.formatCustomerResult({ id: 1, name: 'N', balance: '-10' }).els[0].innerHTML;
    expect(neg).toContain('-10.00');
    const zero = SmartSearch.formatCustomerResult({ id: 1, name: 'Z', balance: 0 }).els[0].innerHTML;
    expect(zero).not.toContain('+0.00');
  });

  it('formats supplier results', async () => {
    await importCustomerSelect();
    const { SmartSearch } = window;
    expect(SmartSearch.formatSupplierResult({ loading: true })).toContain('جاري البحث');
    expect(SmartSearch.formatSupplierResult({ id: null, text: 'plain' })).toBe('plain');
    const item = { id: 1, name: 'Sup', phone: '77', balance: '5' };
    const html = SmartSearch.formatSupplierResult(item).els[0].innerHTML;
    expect(html).toContain('+5.00');
    expect(SmartSearch.formatSupplierSelection({ id: 1, name: 'Sup', phone: '77' })).toBe('Sup - 77');
  });

  it('formats product results with stock', async () => {
    await importCustomerSelect();
    const { SmartSearch } = window;
    const inStock = SmartSearch.formatProductResult({ id: 1, name: 'P', code: 'C', stock: '3', price: '9.9' }).els[0].innerHTML;
    expect(inStock).toContain('3 متوفر');
    expect(inStock).toContain('text-success');
    const out = SmartSearch.formatProductResult({ id: 1, name: 'P', stock: 0, price: 0 }).els[0].innerHTML;
    expect(out).toContain('غير متوفر');
    expect(out).toContain('text-danger');
    expect(SmartSearch.formatProductSelection({ id: 1, name: 'P', code: 'C' })).toBe('P (C)');
  });

  it('initializes all search types via init', async () => {
    await importCustomerSelect();
    const selects = [
      ['customer-select', 'customer-select'],
      ['supplier-select', 'supplier-select'],
      ['product-select', 'product-select'],
    ];
    selects.forEach(([name, cls]) => {
      const el = document.createElement('select');
      el.className = cls;
      document.body.appendChild(el);
    });
    window.SmartSearch.init();
    expect(select2Calls.length).toBe(3);
  });

  it('auto-initializes after ready timeout', async () => {
    vi.useFakeTimers();
    try {
      const select = document.createElement('select');
      select.className = 'customer-select';
      document.body.appendChild(select);
      await importCustomerSelect();
      vi.advanceTimersByTime(150);
      expect(select2Calls.length).toBeGreaterThanOrEqual(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
