import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function createJQuery() {
  const chain = (selector) => {
    const isDoc = selector === document || selector === window;
    const set = isDoc
      ? []
      : Array.from(typeof selector === 'string'
          ? (document.querySelectorAll(selector))
          : [selector]).filter(Boolean);
    const api = {
      length: set.length,
      selector,
      on: vi.fn(() => api),
      off: vi.fn(() => api),
      trigger: vi.fn(() => api),
      each: (fn) => { set.forEach((el, i) => fn.call(el, i, el)); return api; },
      find: (sel) => chain(sel),
      filter: (sel) => chain(sel),
      closest: (sel) => chain(sel),
      parents: () => chain('.parents'),
      data: vi.fn((key, val) => (val !== undefined ? api : undefined)),
      attr: vi.fn(() => ''),
      val: vi.fn(() => ''),
      text: vi.fn(),
      html: vi.fn(),
      append: vi.fn(() => api),
      remove: vi.fn(() => api),
      addClass: vi.fn(() => api),
      removeClass: vi.fn(() => api),
      hasClass: vi.fn(() => false),
      css: vi.fn(() => api),
      show: vi.fn(() => api),
      hide: vi.fn(() => api),
      fadeOut: vi.fn(() => api),
      fadeIn: vi.fn(() => api),
      clone: vi.fn(() => {
        const c = chain(selector);
        c[0] = set[0];
        return c;
      }),
      ready: vi.fn((cb) => { if (typeof cb === 'function') cb(); return api; }),
      prop: vi.fn(() => undefined),
      is: vi.fn(() => false),
      serialize: vi.fn(() => ''),
    };
    api[0] = set[0];
    api.get = (i) => set[i];
    return api;
  };
  const $ = (sel) => chain(sel);
  $.fn = {};
  $.ajaxSetup = vi.fn();
  $.get = vi.fn(() => Promise.resolve([]));
  $.ajax = vi.fn(() => Promise.resolve());
  $.notify = vi.fn();
  $.each = vi.fn();
  $.extend = vi.fn();
  return $;
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('app.js', () => {
  let $;
  let origMutationObserver;

  beforeEach(() => {
    document.body.innerHTML = '<div id="app-root"></div>';
    const meta = document.createElement('meta');
    meta.setAttribute('name', 'csrf-token');
    meta.setAttribute('content', 'test-csrf');
    document.head.appendChild(meta);
    $ = createJQuery();
    global.$ = $;
    global.jQuery = $;
    origMutationObserver = global.MutationObserver;
    global.MutationObserver = class {
      constructor(cb) { this.cb = cb; }
      observe() {}
      disconnect() {}
    };
    window.__azadModalStackingBound = false;
    window.__bootstrapCompatDelegatesBound = false;
    window._mutationPending = false;
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
    delete window.apiFetch;
    delete window.AzadPrint;
    delete window.applyDataTablePrintStyles;
    global.MutationObserver = origMutationObserver;
    vi.resetModules();
  });

  it('should bail out without jQuery', async () => {
    global.$ = undefined;
    global.jQuery = undefined;
    await import('../../static/js/app.js');
    expect(window.apiFetch).toBeUndefined();
  });

  it('should expose apiFetch, AzadPrint and applyDataTablePrintStyles', async () => {
    await import('../../static/js/app.js');
    expect(typeof window.apiFetch).toBe('function');
    expect(window.AzadPrint).toBeDefined();
    expect(typeof window.AzadPrint.printPageReport).toBe('function');
    expect(typeof window.AzadPrint.printElement).toBe('function');
    expect(typeof window.applyDataTablePrintStyles).toBe('function');
  });

  it('apiFetch returns parsed JSON on success', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 5 }) }));
    await import('../../static/js/app.js');
    const data = await window.apiFetch('/api/x');
    expect(data).toEqual({ id: 5 });
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/x');
    expect(opts.credentials).toBe('same-origin');
    expect(opts.headers['X-CSRFToken']).toBe('test-csrf');
    expect(opts.headers.Accept).toBe('application/json');
  });

  it('apiFetch adds Content-Type when body present', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    await import('../../static/js/app.js');
    await window.apiFetch('/api/x', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers['Content-Type']).toBe('application/json');
  });

  it('apiFetch throws localized message on network failure', async () => {
    global.fetch = vi.fn(() => Promise.reject(new TypeError('fetch failed')));
    await import('../../static/js/app.js');
    await expect(window.apiFetch('/api/x')).rejects.toThrow('تعذر الاتصال بالخادم');
  });

  it('apiFetch uses server error message on non-OK response', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ error: 'bad request' }) })
    );
    await import('../../static/js/app.js');
    await expect(window.apiFetch('/api/x')).rejects.toThrow('bad request');
  });

  it('apiFetch falls back to status code message', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) }));
    await import('../../static/js/app.js');
    await expect(window.apiFetch('/api/x')).rejects.toThrow('ليس لديك صلاحية');
  });

  it('apiFetch tolerates unparsable json body', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.reject(new Error('bad')) }));
    await import('../../static/js/app.js');
    const data = await window.apiFetch('/api/x');
    expect(data).toEqual({});
  });

  it('AzadPrint.printPageReport toggles body class around print', async () => {
    global.print = vi.fn();
    await import('../../static/js/app.js');
    window.AzadPrint.printPageReport();
    expect(document.body.classList.contains('is-printing-report')).toBe(true);
    await new Promise((r) => setTimeout(r, 150));
    expect(global.print).toHaveBeenCalled();
    await new Promise((r) => setTimeout(r, 550));
    expect(document.body.classList.contains('is-printing-report')).toBe(false);
  });

  it('AzadPrint.printElement writes clone to print window', async () => {
    document.body.innerHTML = '<div id="rpt"><table><tr><td>x</td></tr></table></div>';
    const printWin = {
      document: {
        open: vi.fn(),
        write: vi.fn(),
        close: vi.fn(),
      },
      print: vi.fn(),
      close: vi.fn(),
    };
    window.open = vi.fn(() => printWin);
    await import('../../static/js/app.js');
    window.AzadPrint.printElement('#rpt', { title: 'Report', headerColor: '#123456' });
    expect(window.open).toHaveBeenCalled();
    expect(printWin.document.write).toHaveBeenCalled();
    expect(printWin.document.write.mock.calls.join('\n')).toContain('Report');
    expect(printWin.document.write.mock.calls.join('\n')).toContain('#123456');
    await new Promise((r) => setTimeout(r, 550));
    expect(printWin.print).toHaveBeenCalled();
    expect(printWin.close).toHaveBeenCalled();
  });

  it('AzadPrint.printElement returns early when element missing', async () => {
    window.open = vi.fn();
    await import('../../static/js/app.js');
    window.AzadPrint.printElement('#nope');
    expect(window.open).not.toHaveBeenCalled();
  });

  it('AzadPrint.printElement returns early when window.open returns null', async () => {
    document.body.innerHTML = '<div id="rpt">x</div>';
    window.open = vi.fn(() => null);
    await import('../../static/js/app.js');
    window.AzadPrint.printElement('#rpt');
    expect(window.open).toHaveBeenCalled();
  });

  it('applyDataTablePrintStyles injects a style element', async () => {
    await import('../../static/js/app.js');
    const win = { document: document };
    window.applyDataTablePrintStyles(win);
    const styles = document.querySelectorAll('style');
    const printStyle = Array.from(styles).find((s) => s.textContent.includes('A4 landscape'));
    expect(printStyle).toBeTruthy();
    expect(printStyle.textContent).toContain('table th, table td');
  });

  it('applyDataTablePrintStyles returns early without document', async () => {
    await import('../../static/js/app.js');
    expect(() => window.applyDataTablePrintStyles(null)).not.toThrow();
    expect(() => window.applyDataTablePrintStyles({})).not.toThrow();
  });

  it('registers unhandledrejection handler that toasts via window.notify', async () => {
    window.notify = { show: vi.fn() };
    await import('../../static/js/app.js');
    const rejected = Promise.reject(new Error('boom'));
    rejected.catch(() => {});
    window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection', {
      promise: rejected,
      reason: new Error('boom'),
    }));
    await flush();
    expect(window.notify.show).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }));
    delete window.notify;
  });

  it('unhandledrejection falls back to Swal when no notify', async () => {
    const swal = { fire: vi.fn() };
    globalThis.Swal = swal;
    await import('../../static/js/app.js');
    const rejected = Promise.reject(new Error('boom'));
    rejected.catch(() => {});
    window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection', {
      promise: rejected,
      reason: new Error('boom'),
    }));
    await flush();
    expect(swal.fire).toHaveBeenCalledWith(expect.objectContaining({ toast: true, icon: 'error' }));
    delete globalThis.Swal;
  });
});
