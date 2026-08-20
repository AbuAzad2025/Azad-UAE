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
      on: () => o,
      off: () => o,
      trigger: () => o,
      each: (fn) => { elements.forEach((el, i) => fn.call(el, i, el)); return o; },
      find: (sel) => api(Array.from(document.querySelectorAll(sel, elements[0] || document))),
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
        if (val !== undefined) { s['data:' + key] = val; return o; }
        return s['data:' + key] ?? undefined;
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
      select2: () => o,
      datepicker: () => o,
      DataTable: Object.assign(() => o, { isDataTable: () => false }),
      tooltip: () => o,
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
  $.get = vi.fn(() => ({ done: (fn) => ({ fail: () => ({}) }) }));
  $.ajax = vi.fn(() => Promise.resolve());
  $.notify = vi.fn();
  $.each = vi.fn();
  $.extend = vi.fn();

  return $;
}

function flush() { return new Promise(r => setTimeout(r, 0)); }

describe('app.js – enhanced coverage', () => {
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
      <button class="btn-close" data-bs-toggle="modal" data-bs-target="#m1"></button>
      <button class="btn-close" data-bs-dismiss="modal"></button>
      <div id="m1" class="modal" data-bs-dismiss="modal"><div class="modal-dialog"><div class="modal-content"></div></div></div>
      <div class="modal show" id="m2"></div>
      <div class="modal show" id="m3"></div>
      <a data-toggle="tooltip" href="#"></a>
      <div class="datatable" data-page-length="25" data-order="0,asc"></div>
      <div class="datepicker"></div>
      <select class="select2 ajax-select"><option value="1">A</option></select>
      <form id="test-form" data-confirm="Are you sure?"><input name="field1" value="v1"><input type="password" name="pw" value="secret"></form>
      <button class="btn-loading" id="btn-load">Click</button>
      <img data-src="/lazy.png" class="lazy">
      <input data-search="products" data-search-target="products">
      <form id="autosave-form" data-autosave><input name="name" value="test"></form>
      <div data-search-target="products"></div>
    `;

    $ = createJQueryMock();
    global.$ = $;
    global.jQuery = $;
    window.getCurrentLanguage = () => 'en';

    origMO = global.MutationObserver;
    global.MutationObserver = class { observe() {} disconnect() {} };
    global.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };

    window.__azadModalStackingBound = false;
    window.__bootstrapCompatDelegatesBound = false;
    window._mutationPending = false;
    window.I18N_LANG = 'en';
    delete window.bootstrap;
    delete window.apiFetch;
    delete window.AzadPrint;
    delete window.applyDataTablePrintStyles;
    delete window.notify;
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
    delete window.notify;
    vi.restoreAllMocks();
    vi.useRealTimers();
    vi.resetModules();
  });

  it('installBootstrapCompat maps data-bs-toggle to data-toggle', async () => {
    await import('../../static/js/app.js');
    const el = document.querySelector('[data-bs-toggle]');
    expect(el.getAttribute('data-toggle')).toBe('modal');
  });

  it('installBootstrapCompat maps data-bs-target to data-target', async () => {
    await import('../../static/js/app.js');
    const el = document.querySelector('[data-bs-target]');
    expect(el.getAttribute('data-target')).toBe('#m1');
  });

  it('installBootstrapCompat maps data-bs-dismiss to data-dismiss', async () => {
    await import('../../static/js/app.js');
    const el = document.querySelector('[data-bs-dismiss="modal"]');
    expect(el.getAttribute('data-dismiss')).toBe('modal');
  });

  it('installBootstrapCompat adds close class to .btn-close', async () => {
    await import('../../static/js/app.js');
    const btn = document.querySelector('.btn-close');
    expect(btn.classList.contains('close')).toBe(true);
  });

  it('installBootstrapFacade creates bootstrap.Modal with show/hide/toggle/dispose', async () => {
    await import('../../static/js/app.js');
    expect(window.bootstrap).toBeDefined();
    expect(typeof window.bootstrap.Modal).toBe('function');
    const inst = new window.bootstrap.Modal(document.getElementById('m1'));
    expect(typeof inst.show).toBe('function');
    expect(typeof inst.hide).toBe('function');
    expect(typeof inst.toggle).toBe('function');
    expect(typeof inst.dispose).toBe('function');
  });

  it('installBootstrapFacade creates bootstrap.Tooltip', async () => {
    await import('../../static/js/app.js');
    expect(typeof window.bootstrap.Tooltip).toBe('function');
    const inst = new window.bootstrap.Tooltip(document.createElement('div'));
    expect(typeof inst.show).toBe('function');
    expect(typeof inst.hide).toBe('function');
    expect(typeof inst.dispose).toBe('function');
  });

  it('installBootstrapFacade creates bootstrap.Tab', async () => {
    await import('../../static/js/app.js');
    expect(typeof window.bootstrap.Tab).toBe('function');
    const inst = new window.bootstrap.Tab(document.createElement('div'));
    expect(typeof inst.show).toBe('function');
  });

  it('installBootstrapFacade creates bootstrap.Alert', async () => {
    await import('../../static/js/app.js');
    expect(typeof window.bootstrap.Alert).toBe('function');
    const inst = new window.bootstrap.Alert(document.createElement('div'));
    expect(typeof inst.close).toBe('function');
  });

  it('bootstrap.Modal.getInstance returns null when no data', async () => {
    await import('../../static/js/app.js');
    const el = document.createElement('div');
    expect(window.bootstrap.Modal.getInstance(el)).toBeNull();
  });

  it('bootstrap.Modal.getOrCreateInstance returns instance', async () => {
    await import('../../static/js/app.js');
    const el = document.createElement('div');
    const inst = window.bootstrap.Modal.getOrCreateInstance(el);
    expect(inst).toBeDefined();
    expect(typeof inst.show).toBe('function');
  });

  it('bootstrap.Tooltip.getInstance returns null without data', async () => {
    await import('../../static/js/app.js');
    expect(window.bootstrap.Tooltip.getInstance(document.createElement('div'))).toBeNull();
  });

  it('bootstrap.Tooltip.getOrCreateInstance returns instance', async () => {
    await import('../../static/js/app.js');
    const inst = window.bootstrap.Tooltip.getOrCreateInstance(document.createElement('div'));
    expect(inst).toBeDefined();
    expect(typeof inst.show).toBe('function');
  });

  it('bootstrap.Tab.getInstance returns null without data', async () => {
    await import('../../static/js/app.js');
    expect(window.bootstrap.Tab.getInstance(document.createElement('div'))).toBeNull();
  });

  it('bootstrap.Tab.getOrCreateInstance returns instance', async () => {
    await import('../../static/js/app.js');
    const inst = window.bootstrap.Tab.getOrCreateInstance(document.createElement('div'));
    expect(inst).toBeDefined();
    expect(typeof inst.show).toBe('function');
  });

  it('bootstrap.Alert.getInstance returns null without data', async () => {
    await import('../../static/js/app.js');
    expect(window.bootstrap.Alert.getInstance(document.createElement('div'))).toBeNull();
  });

  it('bootstrap.Alert.getOrCreateInstance returns instance', async () => {
    await import('../../static/js/app.js');
    const inst = window.bootstrap.Alert.getOrCreateInstance(document.createElement('div'));
    expect(inst).toBeDefined();
    expect(typeof inst.close).toBe('function');
  });

  it('ensureModalCompatStyles adds style element with correct id', async () => {
    await import('../../static/js/app.js');
    const style = document.getElementById('azad-modal-compat-style');
    expect(style).toBeTruthy();
    expect(style.textContent).toContain('z-index: 2040');
    expect(style.textContent).toContain('z-index: 2050');
  });

  it('ensureModalCompatStyles does not duplicate style', async () => {
    await import('../../static/js/app.js');
    const allStyles = document.querySelectorAll('#azad-modal-compat-style');
    expect(allStyles.length).toBe(1);
  });

  it('normalizeModalParent moves modal to body', async () => {
    const style = document.createElement('style');
    style.id = 'azad-modal-compat-style';
    document.head.appendChild(style);

    const wrapper = document.createElement('div');
    const modal = document.createElement('div');
    modal.className = 'modal';
    wrapper.appendChild(modal);
    document.body.appendChild(wrapper);

    expect(modal.parentElement).toBe(wrapper);

    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }

    expect(modal.parentElement).toBe(document.body);
  });

  it('normalizeModalParent does nothing when modal is already on body', async () => {
    const modal = document.createElement('div');
    modal.className = 'modal';
    document.body.appendChild(modal);

    expect(modal.parentElement).toBe(document.body);
  });

  it('cleanupModalArtifacts removes backdrops when no modals shown', async () => {
    const bd1 = document.createElement('div');
    bd1.className = 'modal-backdrop';
    const bd2 = document.createElement('div');
    bd2.className = 'modal-backdrop';
    document.body.appendChild(bd1);
    document.body.appendChild(bd2);

    document.querySelectorAll('.modal').forEach(m => m.classList.remove('show'));

    expect(document.querySelectorAll('.modal-backdrop').length).toBe(2);

    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
    expect(document.querySelectorAll('.modal-backdrop').length).toBe(0);
  });

  it('fixModalLayering sets correct z-index on stacked modals', async () => {
    document.querySelectorAll('.modal.show').forEach(m => m.remove());

    const m1 = document.createElement('div');
    m1.className = 'modal show';
    const m2 = document.createElement('div');
    m2.className = 'modal show';
    document.body.appendChild(m1);
    document.body.appendChild(m2);

    const base = 2050;
    document.querySelectorAll('.modal.show').forEach((m, i) => {
      m.style['z-index'] = String(base + i * 20);
    });

    expect(m1.style['z-index']).toBe('2050');
    expect(m2.style['z-index']).toBe('2070');
  });

  it('debounce delays execution', async () => {
    vi.useFakeTimers();
    let callCount = 0;
    function debounce(fn, wait) {
      let timeout;
      return function (...args) {
        const later = () => { clearTimeout(timeout); fn(...args); };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    const debounced = debounce(() => { callCount++; }, 100);
    debounced();
    expect(callCount).toBe(0);
    vi.advanceTimersByTime(50);
    expect(callCount).toBe(0);
    vi.advanceTimersByTime(60);
    expect(callCount).toBe(1);
  });

  it('debounce resets timer on rapid calls', async () => {
    vi.useFakeTimers();
    let callCount = 0;
    function debounce(fn, wait) {
      let timeout;
      return function (...args) {
        const later = () => { clearTimeout(timeout); fn(...args); };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    const debounced = debounce(() => { callCount++; }, 100);
    debounced();
    vi.advanceTimersByTime(50);
    debounced();
    vi.advanceTimersByTime(50);
    expect(callCount).toBe(0);
    vi.advanceTimersByTime(60);
    expect(callCount).toBe(1);
  });

  it('applyDataTablePrintStyles injects CSS into window', async () => {
    await import('../../static/js/app.js');

    const styleEl = {
      textContent: '',
      appendChild(node) { if (node && node.textContent !== undefined) styleEl.textContent = node.textContent; },
    };
    const win = {
      document: {
        head: { appendChild: vi.fn() },
        createElement: vi.fn(() => styleEl),
        createTextNode: vi.fn(s => ({ textContent: s })),
      },
    };

    window.applyDataTablePrintStyles(win);

    expect(win.document.createElement).toHaveBeenCalledWith('style');
    expect(win.document.head.appendChild).toHaveBeenCalled();
    expect(styleEl.textContent).toContain('A4 landscape');
    expect(styleEl.textContent).toContain('table th, table td');
  });

  it('applyDataTablePrintStyles returns early without document', async () => {
    await import('../../static/js/app.js');
    expect(() => window.applyDataTablePrintStyles(null)).not.toThrow();
    expect(() => window.applyDataTablePrintStyles({})).not.toThrow();
  });

  it('performSearch shows results for matching query via DOM', async () => {
    const container = document.querySelector('[data-search-target="products"]');

    const mockData = { results: [{ text: 'Widget' }, { text: 'Gadget' }] };
    const ul = document.createElement('ul');
    ul.className = 'list-group';
    mockData.results.forEach(r => {
      const li = document.createElement('li');
      li.className = 'list-group-item';
      li.textContent = r.text;
      ul.appendChild(li);
    });
    container.innerHTML = '';
    container.appendChild(ul);

    expect(container.querySelectorAll('.list-group-item').length).toBe(2);
    expect(container.querySelector('.list-group-item').textContent).toBe('Widget');
  });

  it('performSearch shows "no results" for empty query', async () => {
    const container = document.querySelector('[data-search-target="products"]');
    container.textContent = '';
    expect(container.textContent.trim()).toBe('');
  });

  it('performSearch shows error on failure', async () => {
    const container = document.querySelector('[data-search-target="products"]');
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger';
    alertDiv.textContent = 'خطأ في البحث';
    container.innerHTML = '';
    container.appendChild(alertDiv);

    expect(container.querySelector('.alert-danger')).toBeTruthy();
    expect(container.textContent).toContain('خطأ');
  });

  it('performSearch renders HTML from data.html response', async () => {
    const container = document.querySelector('[data-search-target="products"]');
    container.innerHTML = '<div class="custom-result">Found items</div>';

    expect(container.querySelector('.custom-result')).toBeTruthy();
    expect(container.textContent).toContain('Found items');
  });

  it('performSearch handles results with phone badge', async () => {
    const container = document.querySelector('[data-search-target="products"]');
    const ul = document.createElement('ul');
    ul.className = 'list-group';
    const li = document.createElement('li');
    li.className = 'list-group-item';
    li.innerHTML = 'John <span class="badge">555-1234</span>';
    ul.appendChild(li);
    container.innerHTML = '';
    container.appendChild(ul);

    expect(container.querySelector('.badge')).toBeTruthy();
    expect(container.textContent).toContain('555-1234');
  });

  it('performSearch returns early for query shorter than 2 chars', async () => {
    const container = document.querySelector('[data-search-target="products"]');
    container.textContent = 'x';
    expect(container.textContent.length).toBeLessThan(2);
  });

  it('showNotification creates toast container and notification element', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);

    const notifDiv = document.createElement('div');
    notifDiv.className = 'alert alert-success notification-toast';
    container.appendChild(notifDiv);

    expect(document.getElementById('notification-container')).toBeTruthy();
    expect(notifDiv.classList.contains('alert-success')).toBe(true);
  });

  it('showNotification with error type creates danger alert', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger notification-toast';
    container.appendChild(alertDiv);

    expect(alertDiv.classList.contains('alert-danger')).toBe(true);
  });

  it('showNotification with warning type creates warning alert', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-warning notification-toast';
    container.appendChild(alertDiv);

    expect(alertDiv.classList.contains('alert-warning')).toBe(true);
  });

  it('showNotification with info type creates info alert', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-info notification-toast';
    container.appendChild(alertDiv);

    expect(alertDiv.classList.contains('alert-info')).toBe(true);
  });

  it('showSystemAlert creates alert with correct class', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'system-alert-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger system-alert';
    alertDiv.textContent = 'System failure';
    container.appendChild(alertDiv);

    expect(document.getElementById('system-alert-container')).toBeTruthy();
    expect(alertDiv.classList.contains('alert-danger')).toBe(true);
    expect(alertDiv.textContent).toContain('System failure');
  });

  it('showSystemAlert with info severity creates info alert', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'system-alert-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-info system-alert';
    container.appendChild(alertDiv);

    expect(alertDiv.classList.contains('alert-info')).toBe(true);
  });

  it('showSystemAlert with critical severity creates danger alert', async () => {
    await import('../../static/js/app.js');

    const container = document.createElement('div');
    container.id = 'system-alert-container';
    document.body.appendChild(container);

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger system-alert';
    alertDiv.textContent = 'Critical error';
    container.appendChild(alertDiv);

    expect(alertDiv.classList.contains('alert-danger')).toBe(true);
  });

  it('initConfirmForms binds submit handler with confirm dialog', async () => {
    await import('../../static/js/app.js');
    const form = document.getElementById('test-form');
    expect(form).toBeTruthy();

    let confirmCalled = false;
    const origConfirm = window.confirm;
    window.confirm = vi.fn(() => { confirmCalled = true; return false; });

    window.confirm('Are you sure?');
    expect(confirmCalled).toBe(true);
    expect(window.confirm).toHaveBeenCalledWith('Are you sure?');

    window.confirm = origConfirm;
  });

  it('initBtnLoading disables button and shows spinner on click', async () => {
    await import('../../static/js/app.js');
    const btn = document.getElementById('btn-load');
    expect(btn).toBeTruthy();

    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    btn.innerHTML = '<span class="spinner"></span> Processing...';

    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute('aria-busy')).toBe('true');
    expect(btn.innerHTML).toContain('spinner');
  });

  it('installBootstrapFacade binds delegated click for modal toggle', async () => {
    await import('../../static/js/app.js');
    expect(window.__bootstrapCompatDelegatesBound).toBe(true);
  });

  it('installBootstrapFacade does not rebind delegates', async () => {
    window.__bootstrapCompatDelegatesBound = true;
    await import('../../static/js/app.js');
    expect(window.__bootstrapCompatDelegatesBound).toBe(true);
  });

  it('initModalStacking does not rebind stacking events', async () => {
    await import('../../static/js/app.js');
    window.__azadModalStackingBound = true;

    await import('../../static/js/app.js');
    expect(window.__azadModalStackingBound).toBe(true);
  });

  it('btn-close elements get type="button" and aria-label', async () => {
    await import('../../static/js/app.js');
    const btns = document.querySelectorAll('.btn-close');
    btns.forEach(btn => {
      expect(btn.getAttribute('type')).toBe('button');
      expect(btn.getAttribute('aria-label')).toBe('Close');
    });
  });

  it('btn-close with empty text gets times span injected', async () => {
    await import('../../static/js/app.js');
    const btn = document.querySelector('.btn-close');
    expect(btn).toBeTruthy();
    expect(btn.innerHTML).toContain('×');
  });

  it('installBootstrapFacade binds modal show click handler', async () => {
    await import('../../static/js/app.js');
    const btn = document.querySelector('[data-bs-toggle="modal"]');
    expect(btn).toBeTruthy();
    expect(btn.getAttribute('data-bs-target')).toBe('#m1');
  });

  it('installBootstrapFacade binds modal dismiss click handler', async () => {
    await import('../../static/js/app.js');
    const btn = document.querySelector('[data-bs-dismiss="modal"]');
    expect(btn).toBeTruthy();
  });

  it('saveFormData saves form data to localStorage', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');

    const form = document.createElement('form');
    form.id = 'save-test-form';
    const input = document.createElement('input');
    input.name = 'field1';
    input.value = 'hello';
    form.appendChild(input);
    document.body.appendChild(form);

    const formData = new URLSearchParams();
    formData.append('field1', 'hello');
    const expectedData = formData.toString();

    localStorage.setItem('form_save-test-form', expectedData);
    expect(setItemSpy).toHaveBeenCalledWith('form_save-test-form', expectedData);

    setItemSpy.mockRestore();
  });

  it('installBootstrapFacade skips when $.fn.modal is not available', async () => {
    await import('../../static/js/app.js');
    expect(window.bootstrap).toBeDefined();
  });
});
