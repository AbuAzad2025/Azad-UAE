import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let allHandlers;
let tooltipCalls;
let animateCalls;
let propCalls;
let htmlCalls;
let ajaxOptions;
let dataStore;

function makeJQuery() {
  const mk = (selector, els) => {
    const getEl = () => (els && els[0]) || null;
    const api = {
      length: els.length,
      on(evt, fn) {
        evt.split(' ').forEach((e) => allHandlers.push({ selector, event: e, fn }));
        return api;
      },
      off() {
        return api;
      },
      ready(fn) {
        fn();
        return api;
      },
      hover(fn) {
        return api.on('mouseenter', fn).on('mouseleave', fn);
      },
      each(fn) {
        els.forEach((el, i) => fn.call(el, i, el));
        return api;
      },
      attr(name) {
        const el = getEl();
        return el ? el.getAttribute(name) : undefined;
      },
      data(name, value) {
        const el = getEl();
        if (el) {
          if (value === undefined) return dataStore.get(el)?.[name];
          dataStore.set(el, { ...(dataStore.get(el) || {}), [name]: value });
        }
        return api;
      },
      prop(name, value) {
        propCalls.push({ el: getEl(), name, value });
        const el = getEl();
        if (el && value !== undefined) el[name] = value;
        return api;
      },
      html(value) {
        const el = getEl();
        if (value === undefined) return el ? el.innerHTML : '';
        htmlCalls.push({ el, value });
        if (el) el.innerHTML = value;
        return api;
      },
      find(sel) {
        const kids = [];
        const norm = sel.endsWith(':first') ? sel.slice(0, -6) : sel;
        els.forEach((el) => {
          el.querySelectorAll(norm).forEach((n) => kids.push(n));
        });
        return mk(sel, kids);
      },
      closest() {
        return api;
      },
      focus() {
        const el = getEl();
        if (el) el.focus();
        return api;
      },
      addClass(c) {
        const el = getEl();
        if (el) el.classList.add(c);
        return api;
      },
      removeClass(c) {
        const el = getEl();
        if (el) el.classList.remove(c);
        return api;
      },
      tooltip(opts) {
        tooltipCalls.push({ els, opts });
        return api;
      },
      animate(opts, duration) {
        animateCalls.push({ els, opts, duration });
        return api;
      },
      offset() {
        return { top: 100 };
      },
      trigger(evt) {
        allHandlers
          .filter((h) => h.selector === selector && h.event === evt)
          .forEach((h) => h.fn.call(getEl() || document, { type: evt }));
        return api;
      },
    };
    return api;
  };

  const $ = (arg) => {
    if (typeof arg === 'string') {
      let nodes = [];
      try {
        nodes = Array.from(document.querySelectorAll(arg));
      } catch {
        nodes = [];
      }
      return mk(arg, nodes);
    }
    return mk(typeof arg === 'string' ? arg : 'element', [arg]);
  };
  $.fn = {};
  $.extend = (target, ...sources) => Object.assign(target, ...sources);
  $.ajaxSetup = (opts) => { ajaxOptions = opts; };
  return $;
}

async function importPerf() {
  await import('../../static/js/performance.js');
}

function handler(event, selectorSubstr) {
  const matches = allHandlers.filter((h) => h.event === event);
  const found = selectorSubstr ? matches.find((h) => h.selector.includes(selectorSubstr)) : matches[0];
  return found;
}

function snapshotAjaxError(xhr, status) {
  return () => ajaxOptions.error(xhr, status);
}

beforeEach(() => {
  allHandlers = [];
  tooltipCalls = [];
  animateCalls = [];
  propCalls = [];
  htmlCalls = [];
  ajaxOptions = null;
  dataStore = new WeakMap();
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  global.alert = vi.fn();
  global.getCurrentLanguage = vi.fn(() => 'ar');
  window.getCurrentLanguage = global.getCurrentLanguage;
  global.requestAnimationFrame = (cb) => cb();
  window.requestAnimationFrame = global.requestAnimationFrame;
  const $ = makeJQuery();
  global.$ = $;
  window.$ = $;
  global.jQuery = $;
  window.jQuery = $;
  vi.resetModules();
});

afterEach(() => {
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  delete global.alert;
  delete global.$;
  delete window.$;
  delete global.jQuery;
  delete window.jQuery;
  delete global.getCurrentLanguage;
  delete window.getCurrentLanguage;
  delete global.requestAnimationFrame;
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('performance.js', () => {
  it('injects loading CSS', async () => {
    await importPerf();
    const style = document.head.querySelector('style');
    expect(style).toBeTruthy();
    expect(style.textContent).toContain('.loading');
  });

  it('lazy-loads images through IntersectionObserver', async () => {
    class MockObserver {
      static instances = [];
      constructor(cb) {
        this.cb = cb;
        this.observed = [];
        this.unobserved = [];
        MockObserver.instances.push(this);
      }
      observe(el) {
        this.observed.push(el);
      }
      unobserve(el) {
        this.unobserved.push(el);
      }
    }
    global.IntersectionObserver = MockObserver;
    window.IntersectionObserver = MockObserver;
    const img = document.createElement('img');
    img.dataset.src = '/static/example.jpg';
    img.classList.add('lazy');
    document.body.appendChild(img);
    await importPerf();
    const observer = MockObserver.instances[0];
    expect(observer.observed).toContain(img);
    observer.cb([{ isIntersecting: true, target: img }]);
    expect(img.src).toBe('http://localhost:3000/static/example.jpg');
    expect(img.classList.contains('lazy')).toBe(false);
    expect(observer.unobserved).toContain(img);
  });

  it('debounces search input original handlers', async () => {
    vi.useFakeTimers();
    try {
      const origHandler = vi.fn();
      const input = document.createElement('input');
      input.type = 'search';
      document.body.appendChild(input);
      dataStore.set(input, { events: { input: [{ handler: origHandler }] } });
      await importPerf();
      const debounced = handler('input');
      expect(debounced).toBeTruthy();
      debounced.fn.call(input, {});
      debounced.fn.call(input, {});
      vi.advanceTimersByTime(310);
      expect(origHandler).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('preloads valid internal links on hover and skips invalid ones', async () => {
    const nav = document.createElement('a');
    nav.className = 'nav-link';
    nav.href = '/sales';
    document.body.appendChild(nav);
    const pos = document.createElement('a');
    pos.className = 'btn';
    pos.href = '/pos/scan';
    document.body.appendChild(pos);
    const outbound = document.createElement('a');
    outbound.className = 'nav-link';
    outbound.href = 'https://example.com';
    document.body.appendChild(outbound);
    await importPerf();
    const hover = handler('mouseenter', '.nav-link, .btn');
    hover.fn.call(nav, {});
    expect(document.querySelector('link[rel="prefetch"][href="/sales"]')).toBeTruthy();
    hover.fn.call(pos, {});
    expect(document.querySelector('link[rel="prefetch"][href="/pos/scan"]')).toBeNull();
    hover.fn.call(outbound, {});
    expect(document.querySelector('link[rel="prefetch"][href="https://example.com"]')).toBeNull();
  });

  it('configures DataTables defaults', async () => {
    const adjust = vi.fn();
    const $ = global.$;
    $.fn.DataTable = {};
    $.fn.dataTable = {
      defaults: {},
      tables: vi.fn(() => ({ columns: { adjust } })),
    };
    await importPerf();
    expect($.fn.dataTable.defaults.pageLength).toBe(25);
    expect($.fn.dataTable.defaults.language.url).toBe('/static/datatables/Arabic.json');
    expect($.fn.dataTable.defaults.processing).toBe(true);
    const card = document.createElement('div');
    card.className = 'card';
    const body = document.createElement('div');
    body.className = 'card-body loading';
    card.appendChild(body);
    document.body.appendChild(card);
    $.fn.dataTable.defaults.initComplete.call(card);
    expect(body.classList.contains('loading')).toBe(false);
  });

  it('disables submit button on submit and restores after 5s', async () => {
    vi.useFakeTimers();
    try {
      const form = document.createElement('form');
      const button = document.createElement('button');
      button.type = 'submit';
      button.innerHTML = 'Save';
      form.appendChild(button);
      document.body.appendChild(form);
      await importPerf();
      expect(dataStore.get(button)['original-text']).toBe('Save');
      const submit = handler('submit');
      submit.fn.call(form, {});
      expect(button.disabled).toBe(true);
      vi.advanceTimersByTime(5100);
      expect(button.disabled).toBe(false);
      expect(button.innerHTML).toBe('Save');
    } finally {
      vi.useRealTimers();
    }
  });

  it('stores original submit button text', async () => {
    const form = document.createElement('form');
    const button = document.createElement('button');
    button.type = 'submit';
    button.innerHTML = 'احفظ';
    form.appendChild(button);
    document.body.appendChild(form);
    await importPerf();
    expect(dataStore.get(button)['original-text']).toBe('احفظ');
  });

  it('registers ajaxSetup and toggles loading class', async () => {
    await importPerf();
    expect(ajaxOptions).toBeTruthy();
    ajaxOptions.beforeSend(null, { type: 'POST' });
    expect(document.body.classList.contains('loading')).toBe(true);
    ajaxOptions.complete();
    expect(document.body.classList.contains('loading')).toBe(false);
  });

  it('ajaxSetup alerts on timeout and server error', async () => {
    await importPerf();
    snapshotAjaxError({ status: 0 }, 'timeout')();
    expect(global.alert).toHaveBeenCalledTimes(1);
    snapshotAjaxError({ status: 500 }, 'error')();
    expect(global.alert).toHaveBeenCalledTimes(2);
  });

  it('handles scroll with rAF throttling', async () => {
    const listeners = {};
    const spy = vi.spyOn(window, 'addEventListener').mockImplementation((evt, cb) => {
      listeners[evt] = cb;
    });
    await importPerf();
    expect(listeners.scroll).toBeDefined();
    listeners.scroll();
    listeners.scroll();
    expect(spy).toHaveBeenCalled();
  });

  it('adjusts DataTables columns on resize', async () => {
    vi.useFakeTimers();
    try {
      const adjust = vi.fn();
      const $ = global.$;
      $.fn.DataTable = {};
      $.fn.dataTable = {
        defaults: {},
        tables: vi.fn(() => ({ columns: { adjust } })),
      };
      const listeners = {};
      vi.spyOn(window, 'addEventListener').mockImplementation((evt, cb) => {
        listeners[evt] = cb;
      });
      await importPerf();
      listeners.resize();
      vi.advanceTimersByTime(260);
      expect(adjust).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('initializes tooltips and focuses first input on modal show', async () => {
    const tooltipEl = document.createElement('span');
    tooltipEl.setAttribute('data-toggle', 'tooltip');
    document.body.appendChild(tooltipEl);
    const modal = document.createElement('div');
    modal.className = 'modal';
    const input = document.createElement('input');
    modal.appendChild(input);
    document.body.appendChild(modal);
    const focusSpy = vi.spyOn(input, 'focus');
    await importPerf();
    expect(tooltipCalls.length).toBe(1);
    expect(tooltipCalls[0].opts.delay.show).toBe(500);
    const show = handler('show.bs.modal', '.modal');
    show.fn.call(modal, {});
    expect(focusSpy).toHaveBeenCalled();
  });

  it('smooth scrolls to anchor targets', async () => {
    const target = document.createElement('div');
    target.id = 'target';
    document.body.appendChild(target);
    const anchor = document.createElement('a');
    anchor.href = '#target';
    document.body.appendChild(anchor);
    await importPerf();
    const click = handler('click', 'a[href^="#"]');
    const evt = { preventDefault: vi.fn() };
    click.fn.call(anchor, evt);
    expect(evt.preventDefault).toHaveBeenCalled();
    expect(animateCalls.length).toBe(1);
    expect(animateCalls[0].duration).toBe(500);
  });

  it('runs performance monitoring load handler', async () => {
    vi.useFakeTimers();
    try {
      const listeners = {};
      vi.spyOn(window, 'addEventListener').mockImplementation((evt, cb) => {
        listeners[evt] = cb;
      });
      await importPerf();
      expect(listeners.load).toBeDefined();
      listeners.load();
      vi.advanceTimersByTime(150);
    } finally {
      vi.useRealTimers();
    }
  });
});
