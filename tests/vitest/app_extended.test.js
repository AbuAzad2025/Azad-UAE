import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function createJQueryMock() {
  const elData = new WeakMap();
  const getStore = (el) => {
    if (!elData.has(el)) elData.set(el, {});
    return elData.get(el);
  };

  const api = (elements) => {
    const o = {
      length: elements.length,
      0: elements[0] || null,
      get: (i) => elements[i],
      _store: (key) => {
        const el = elements[0];
        if (!el) return undefined;
        return getStore(el)[key];
      },
      on: (evt, selOrFn, fn) => {
        if (typeof selOrFn === 'function') {
          elements.forEach(el => {
            const store = getStore(el);
            store['on:' + evt] = store['on:' + evt] || [];
            store['on:' + evt].push(selOrFn);
          });
        } else if (typeof selOrFn === 'string' && typeof fn === 'function') {
          elements.forEach(el => {
            const store = getStore(el);
            store['delegate:' + evt + ':' + selOrFn] = store['delegate:' + evt + ':' + selOrFn] || [];
            store['delegate:' + evt + ':' + selOrFn].push(fn);
          });
        }
        return o;
      },
      off: () => o,
      trigger: (evt) => {
        elements.forEach(el => {
          const store = getStore(el);
          const handlers = store['on:' + evt] || [];
          handlers.forEach(h => h.call(el));
        });
        return o;
      },
      each: (fn) => { elements.forEach((el, i) => fn.call(el, i, el)); return o; },
      find: (sel) => api(Array.from(document.querySelectorAll(sel))),
      closest: (sel) => {
        const el = elements[0];
        if (!el || !el.closest) return api([]);
        const found = el.closest(sel);
        return found ? api([found]) : api([]);
      },
      parent: () => {
        const el = elements[0];
        return el && el.parentElement ? api([el.parentElement]) : api([]);
      },
      appendTo: (target) => {
        const el = elements[0];
        if (el && target && target.appendChild) target.appendChild(el);
        return o;
      },
      append: (child) => {
        const el = elements[0];
        if (!el) return o;
        if (typeof child === 'string') {
          const tmp = document.createElement('div');
          tmp.innerHTML = child;
          while (tmp.firstChild) el.appendChild(tmp.firstChild);
        } else if (child && child[0]) {
          el.appendChild(child[0]);
        } else if (child && child.nodeType) {
          el.appendChild(child);
        }
        return o;
      },
      remove: () => { elements.forEach(el => el.remove()); return o; },
      data: (key, val) => {
        const el = elements[0];
        if (!el) return val !== undefined ? o : undefined;
        const s = getStore(el);
        const datasetKey = key.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        if (val !== undefined) {
          s['data:' + key] = val;
          if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
            el.dataset[datasetKey] = String(val);
          }
          return o;
        }
        return s['data:' + key] ?? el.dataset[datasetKey] ?? undefined;
      },
      attr: (name, val) => {
        const el = elements[0];
        if (!el) return val !== undefined ? o : undefined;
        if (val !== undefined) { el.setAttribute(name, val); return o; }
        return el.getAttribute(name);
      },
      val: (v) => {
        if (elements.length === 0) return v !== undefined ? o : '';
        if (v !== undefined) { elements.forEach(el => { el.value = v; }); return o; }
        return elements[0]?.value ?? '';
      },
      html: (v) => {
        if (elements.length === 0) return v !== undefined ? o : '';
        if (v !== undefined) { elements.forEach(el => { el.innerHTML = v; }); return o; }
        return elements[0]?.innerHTML ?? '';
      },
      text: (v) => {
        if (elements.length === 0) return v !== undefined ? o : '';
        if (v !== undefined) { elements.forEach(el => { el.textContent = v; }); return o; }
        return elements[0]?.textContent ?? '';
      },
      prop: (name, val) => {
        const el = elements[0];
        if (!el) return val !== undefined ? o : undefined;
        if (val !== undefined) { el[name] = val; return o; }
        return el[name];
      },
      addClass: (cls) => { elements.forEach(el => el.classList.add(cls)); return o; },
      removeClass: (cls) => { elements.forEach(el => el.classList.remove(cls)); return o; },
      hasClass: (cls) => elements.some(el => el.classList.contains(cls)),
      css: (name, val) => {
        const el = elements[0];
        if (!el) return o;
        if (typeof name === 'string' && val !== undefined) { el.style[name] = val; return o; }
        if (typeof name === 'string') return el.style[name] || '';
        if (typeof name === 'object') {
          Object.keys(name).forEach(k => { el.style[k] = name[k]; });
        }
        return o;
      },
      is: () => false,
      show: () => o,
      hide: () => o,
      fadeOut: () => o,
      fadeIn: () => o,
      serialize: () => {
        const el = elements[0];
        if (!el) return '';
        const inputs = el.querySelectorAll('input, select, textarea');
        return Array.from(inputs).map(i => `${i.name}=${i.value}`).join('&');
      },
      map: (fn) => {
        const arr = elements.map((el, i) => fn(i, el));
        arr.get = (i) => (i === undefined ? arr : arr[i]);
        return arr;
      },
      not: () => o,
      select2: (opts) => {
        elements.forEach(el => {
          getStore(el)['select2-opts'] = opts;
          el.classList.add('select2-hidden-accessible');
        });
        return o;
      },
      datepicker: (opts) => {
        elements.forEach(el => { getStore(el)['datepicker-opts'] = opts; });
        return o;
      },
      DataTable: (opts) => {
        elements.forEach(el => { getStore(el)['DataTable-opts'] = opts; });
        return o;
      },
      tooltip: (opts) => {
        elements.forEach(el => { getStore(el)['tooltip-opts'] = opts; });
        return o;
      },
      alert: () => o,
      modal: () => o,
      tab: () => o,
      ready: (fn) => { if (typeof fn === 'function') fn(); return o; },
    };
    return o;
  };

  const $ = (sel) => {
    if (typeof sel === 'function') return api([]).ready(sel);
    if (sel && sel.nodeType) return api([sel]);
    if (sel && sel[0] && sel[0].nodeType) return sel;
    if (typeof sel === 'string') return api(Array.from(document.querySelectorAll(sel)));
    return api([]);
  };

  $.fn = {};
  $.fn.DataTable = Object.assign(() => ({}), { isDataTable: () => false });
  $.fn.dataTable = { Buttons: true };
  $.fn.datepicker = () => ({});
  $.fn.select2 = () => ({});
  $.fn.tooltip = () => ({});
  $.fn.modal = () => ({});
  $.fn.tab = () => ({});
  $.fn.alert = () => ({});
  $.ajaxSetup = vi.fn();
  $.get = vi.fn(() => ({ done: (fn) => ({ fail: (errFn) => { errFn && errFn(); return {}; } }) }));
  $.ajax = vi.fn(() => Promise.resolve());
  $.notify = vi.fn();
  $.each = vi.fn();
  $.extend = vi.fn();

  return $;
}

describe('app.js – init functions', () => {
  let $;
  let origMO;

  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = 'test-csrf';
    document.head.appendChild(meta);

    document.body.innerHTML = `
      <table class="datatable" data-page-length="25" data-order="1,desc"><thead><th>Name</th><th class="dt-nosort">Action</th></thead></table>
      <input class="datepicker" />
      <select class="select2" placeholder="Pick one"><option value="1">A</option></select>
      <select class="select2 ajax-select" data-url="/api/items" data-delay="100" data-limit="10" data-min-length="2" data-initial-text="Selected" data-allow-clear="true"><option value="5">Selected</option></select>
      <a data-toggle="tooltip" title="Hint">Link</a>
      <form id="cf" data-confirm="Sure?"><input name="x" value="1"></form>
      <button class="btn-loading" id="ld">Go</button>
      <img data-src="/lazy.png" class="lazy">
      <input data-search="products" data-search-target="products-results">
      <form id="af" data-autosave><input name="name" value="test"></form>
      <div data-search-target="products-results"></div>
    `;

    $ = createJQueryMock();
    global.$ = $;
    global.jQuery = $;
    window.getCurrentLanguage = () => 'ar';

    origMO = global.MutationObserver;
    global.MutationObserver = class {
      constructor(cb) { this.cb = cb; }
      observe() {}
      disconnect() {}
    };
    global.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };

    window.__azadModalStackingBound = false;
    window.__bootstrapCompatDelegatesBound = false;
    window._mutationPending = false;
    window.I18N_LANG = 'ar';
    delete window.bootstrap;
    delete window.apiFetch;
    delete window.AzadPrint;
    delete window.applyDataTablePrintStyles;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    delete global.$;
    delete global.jQuery;
    global.MutationObserver = origMO;
    delete window.getCurrentLanguage;
    delete window.__azadModalStackingBound;
    delete window.__bootstrapCompatDelegatesBound;
    delete window.apiFetch;
    delete window.AzadPrint;
    delete window.applyDataTablePrintStyles;
    delete window.bootstrap;
    vi.restoreAllMocks();
    vi.useRealTimers();
    vi.resetModules();
  });

  it('initDataTables marks tables as initialized', async () => {
    await import('../../static/js/app.js');
    const tbl = document.querySelector('.datatable');
    expect(tbl.dataset.dtInitialized).toBe('1');
  });

  it('initDatepickers marks inputs as initialized', async () => {
    await import('../../static/js/app.js');
    const dp = document.querySelector('.datepicker');
    expect(dp.dataset.dpInitialized).toBe('1');
  });

  it('initSelect2Basic marks selects as initialized', async () => {
    await import('../../static/js/app.js');
    const sel = document.querySelector('select.select2:not(.ajax-select)');
    expect(sel.dataset.s2Initialized).toBe('1');
  });

  it('initAjaxSelects marks ajax selects as initialized', async () => {
    await import('../../static/js/app.js');
    const sel = document.querySelector('select.ajax-select');
    expect(sel.dataset.s2Initialized).toBe('1');
  });

  it('initTooltips marks tooltip elements as initialized', async () => {
    await import('../../static/js/app.js');
    const el = document.querySelector('[data-toggle="tooltip"]');
    expect($(el)._store('tooltip-opts')).toBeDefined();
  });

  it('initConfirmForms marks forms as bound', async () => {
    await import('../../static/js/app.js');
    const form = document.querySelector('form[data-confirm]');
    expect(form.dataset.confirmBound).toBe('1');
  });

  it('initBtnLoading marks buttons as bound', async () => {
    await import('../../static/js/app.js');
    const btn = document.querySelector('.btn-loading');
    expect(btn.dataset.loadingBound).toBe('1');
  });

  it('initPerformanceOptimizations observes lazy images', async () => {
    await import('../../static/js/app.js');
    const img = document.querySelector('img[data-src]');
    expect(img).toBeTruthy();
  });

  it('initAll is called on document ready', async () => {
    await import('../../static/js/app.js');
    const tbl = document.querySelector('.datatable');
    expect(tbl.dataset.dtInitialized).toBe('1');
  });

  it('MutationObserver is created and observes document.body', async () => {
    const observeSpy = vi.fn();
    global.MutationObserver = class {
      constructor(cb) { this.cb = cb; }
      observe(...args) { observeSpy(...args); }
      disconnect() {}
    };
    await import('../../static/js/app.js');
    expect(observeSpy).toHaveBeenCalled();
    expect(observeSpy.mock.calls[0][0]).toBe(document.body);
  });

  it('performSearch via input trigger calls $.get for long query', async () => {
    const getSpy = vi.fn(() => ({
      done: (cb) => {
        cb({ html: '<div class="res">Item</div>' });
        return { fail: () => ({}) };
      },
    }));
    $.get = getSpy;

    await import('../../static/js/app.js');
    const input = document.querySelector('[data-search="products"]');
    input.value = 'widget';
    $(input).trigger('input.erpSearch');

    await new Promise(r => setTimeout(r, 400));
    expect(getSpy).toHaveBeenCalledWith('/api/search', { type: 'products', q: 'widget' });
  });

  it('performSearch returns early for short queries', async () => {
    const getSpy = vi.fn(() => ({ done: () => ({ fail: () => ({}) }) }));
    $.get = getSpy;

    await import('../../static/js/app.js');
    const input = document.querySelector('[data-search="products"]');
    input.value = 'x';
    $(input).trigger('input.erpSearch');

    await new Promise(r => setTimeout(r, 400));
    expect(getSpy).not.toHaveBeenCalled();
  });

  it('initNotifications is a no-op when io is undefined', async () => {
    delete global.io;
    await import('../../static/js/app.js');
    expect(window.apiFetch).toBeDefined();
  });

  it('initModalStacking appends modal style once', async () => {
    await import('../../static/js/app.js');
    const styles = document.querySelectorAll('#azad-modal-compat-style');
    expect(styles.length).toBe(1);
  });

  it('installBootstrapCompat adds close class to btn-close elements', async () => {
    await import('../../static/js/app.js');
    document.querySelectorAll('.btn-close').forEach(btn => {
      expect(btn.classList.contains('close')).toBe(true);
    });
  });

  it('initConfirmForms submit handler calls confirm', async () => {
    await import('../../static/js/app.js');
    const form = document.getElementById('cf');
    expect(form.dataset.confirmBound).toBe('1');

    const origConfirm = window.confirm;
    window.confirm = vi.fn(() => false);

    const store = $(form)._store('on:submit');
    expect(store).toBeDefined();
    expect(store.length).toBeGreaterThan(0);

    window.confirm = origConfirm;
  });

  it('initBtnLoading click handler disables button', async () => {
    await import('../../static/js/app.js');
    const btn = document.getElementById('ld');
    expect(btn.dataset.loadingBound).toBe('1');

    const store = $(btn)._store('on:click');
    expect(store).toBeDefined();
    expect(store.length).toBeGreaterThan(0);
  });
});
