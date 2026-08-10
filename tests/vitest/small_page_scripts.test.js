import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let scrollSpy;
let observerCb;
let observed = [];
let tooltipSpy;
let DataTableCalls;
let isDataTableSpy;
let smartPrint;

function makePageJQuery() {
  const DataTable = vi.fn((opts) => {
    DataTableCalls.push(opts);
    return { settings: {} };
  });
  DataTable.isDataTable = isDataTableSpy;
  const mk = (selector) => {
    const els = Array.from(document.querySelectorAll(selector));
    const api = {
      length: els.length,
      data: (key, val) => {
        const el = els[0];
        const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (!el) return val === undefined ? undefined : api;
        if (val === undefined) return el.dataset[k];
        el.dataset[k] = val;
        return api;
      },
      DataTable,
    };
    return api;
  };
  const $ = (arg) => {
    if (typeof arg === 'function') {
      arg();
      return { on: vi.fn() };
    }
    return mk(arg);
  };
  $.fn = { DataTable };
  return $;
}

function setReadyState(state) {
  Object.defineProperty(document, 'readyState', { configurable: true, value: state });
}

function restoreReadyState() {
  delete document.readyState;
}

describe('landing.js', () => {
  let originalIO;

  beforeEach(() => {
    document.body.innerHTML = `
      <a href="#pricing" class="landing-scroll-link">Pricing</a>
      <a href="#missing">Missing</a>
      <section id="pricing"></section>
      <div class="feature-card" id="fc1"></div>
      <div class="price-card" id="pc1"></div>
      <button id="landingSidebarOpen"></button>
      <button id="landingSidebarClose"></button>
      <div id="landingSidebarBackdrop"></div>
      <aside id="landingSidebar"></aside>
    `;
    scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    observerCb = null;
    observed = [];
    originalIO = global.IntersectionObserver;
    global.IntersectionObserver = class {
      constructor(cb) {
        observerCb = cb;
      }
      observe(el) {
        observed.push(el);
      }
      unobserve() {}
      disconnect() {}
    };
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    if (originalIO === undefined) delete global.IntersectionObserver;
    else global.IntersectionObserver = originalIO;
    delete Element.prototype.scrollIntoView;
    vi.resetModules();
  });

  it('smooth-scrolls to a matching anchor', async () => {
    await import('../../static/js/landing.js');
    const anchor = document.querySelector('a[href="#pricing"]');
    const ev = new MouseEvent('click', { bubbles: true, cancelable: true });
    anchor.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(scrollSpy).toHaveBeenCalledWith({ behavior: 'smooth' });
    expect(scrollSpy.mock.instances[0]).toBe(document.querySelector('#pricing'));
  });

  it('does not scroll when the target is missing', async () => {
    await import('../../static/js/landing.js');
    const anchor = document.querySelector('a[href="#missing"]');
    anchor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(scrollSpy).not.toHaveBeenCalled();
  });

  it('initialises feature/price cards hidden and observes them', async () => {
    await import('../../static/js/landing.js');
    const fc = document.querySelector('#fc1');
    const pc = document.querySelector('#pc1');
    expect(fc.style.opacity).toBe('0');
    expect(fc.style.transform).toBe('translateY(50px)');
    expect(pc.style.opacity).toBe('0');
    expect(observed).toContain(fc);
    expect(observed).toContain(pc);
  });

  it('reveals observed cards when intersecting', async () => {
    await import('../../static/js/landing.js');
    const fc = document.querySelector('#fc1');
    const pc = document.querySelector('#pc1');
    observerCb([
      { isIntersecting: true, target: fc },
      { isIntersecting: false, target: pc },
    ]);
    expect(fc.style.opacity).toBe('1');
    expect(fc.style.transform).toBe('translateY(0)');
    expect(pc.style.opacity).toBe('0');
  });

  it('opens the sidebar via the open button', async () => {
    await import('../../static/js/landing.js');
    document.getElementById('landingSidebarOpen').click();
    expect(document.body.classList.contains('landing-sidebar-open')).toBe(true);
    expect(document.getElementById('landingSidebar').getAttribute('aria-hidden')).toBe('false');
  });

  it('closes the sidebar via close button, backdrop and scroll links', async () => {
    await import('../../static/js/landing.js');
    document.getElementById('landingSidebarClose').click();
    expect(document.body.classList.contains('landing-sidebar-open')).toBe(false);
    expect(document.getElementById('landingSidebar').getAttribute('aria-hidden')).toBe('true');

    document.getElementById('landingSidebarOpen').click();
    document.getElementById('landingSidebarBackdrop').click();
    expect(document.body.classList.contains('landing-sidebar-open')).toBe(false);

    document.getElementById('landingSidebarOpen').click();
    document.querySelector('.landing-scroll-link').click();
    expect(document.body.classList.contains('landing-sidebar-open')).toBe(false);
  });
});

describe('pos-config.js', () => {
  beforeEach(() => {
    delete window.POS_CONFIG;
    document.head.innerHTML = '';
    vi.resetModules();
  });

  afterEach(() => {
    document.head.innerHTML = '';
    delete window.POS_CONFIG;
    vi.resetModules();
  });

  it('falls back to defaults when no meta tag exists', async () => {
    await import('../../static/js/pos/pos-config.js');
    expect(window.POS_CONFIG).toEqual({ enable_tables: false, enable_hold: true });
  });

  it('parses a valid pos-config meta tag', async () => {
    const meta = document.createElement('meta');
    meta.name = 'pos-config';
    meta.content = '{"enable_tables": true, "enable_hold": false}';
    document.head.appendChild(meta);
    await import('../../static/js/pos/pos-config.js');
    expect(window.POS_CONFIG).toEqual({ enable_tables: true, enable_hold: false });
  });

  it('falls back to defaults when the meta JSON is invalid', async () => {
    const meta = document.createElement('meta');
    meta.name = 'pos-config';
    meta.content = '{nope';
    document.head.appendChild(meta);
    await import('../../static/js/pos/pos-config.js');
    expect(window.POS_CONFIG).toEqual({ enable_tables: false, enable_hold: true });
  });

  it('keeps an existing POS_CONFIG value', async () => {
    window.POS_CONFIG = { existing: true };
    await import('../../static/js/pos/pos-config.js');
    expect(window.POS_CONFIG).toEqual({ existing: true });
  });
});

describe('customers-edit.js', () => {
  let orig$;

  beforeEach(() => {
    tooltipSpy = vi.fn();
    orig$ = global.$;
    const $ = vi.fn((arg) => {
      if (typeof arg === 'function') arg();
      return { tooltip: tooltipSpy };
    });
    global.$ = $;
    window.$ = $;
    vi.resetModules();
  });

  afterEach(() => {
    global.$ = orig$;
    if (orig$ === undefined) delete window.$;
    else window.$ = orig$;
    vi.resetModules();
  });

  it('initialises tooltips with top/hover options', async () => {
    await import('../../static/js/customers-edit.js');
    expect(tooltipSpy).toHaveBeenCalledWith({ placement: 'top', trigger: 'hover' });
  });
});

describe('payments-index-page.js', () => {
  let origJQuery;
  let openSpy;

  beforeEach(() => {
    origJQuery = window.jQuery;
    DataTableCalls = [];
    isDataTableSpy = vi.fn(() => false);
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    delete window.ActionHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    if (origJQuery === undefined) delete window.jQuery;
    else window.jQuery = origJQuery;
    delete window.ActionHelpers;
    openSpy.mockRestore();
    restoreReadyState();
    vi.resetModules();
  });

  it('bails out without jQuery DataTable', async () => {
    setReadyState('complete');
    await import('../../static/js/payments-index-page.js');
    expect(DataTableCalls).toHaveLength(0);
  });

  it('returns early when the table element is missing', async () => {
    setReadyState('complete');
    const $ = makePageJQuery();
    window.jQuery = $;
    await import('../../static/js/payments-index-page.js');
    expect(DataTableCalls).toHaveLength(0);
  });

  it('initialises the receipts DataTable with data lang url', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<table id="receiptsTable" data-lang-url="/custom/ar.json"></table>';
    const $ = makePageJQuery();
    window.jQuery = $;
    await import('../../static/js/payments-index-page.js');
    expect(DataTableCalls).toHaveLength(1);
    expect(DataTableCalls[0]).toEqual({
      language: { url: '/custom/ar.json' },
      order: [[2, 'desc']],
      pageLength: 25,
    });
  });

  it('uses the default language url when lang url is absent', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<table id="receiptsTable"></table>';
    const $ = makePageJQuery();
    window.jQuery = $;
    await import('../../static/js/payments-index-page.js');
    expect(DataTableCalls[0].language.url).toBe('/static/datatables/Arabic.json');
  });

  it('opens the print window via ActionHelpers', async () => {
    setReadyState('complete');
    window.ActionHelpers = { openPrintWindow: vi.fn() };
    document.body.innerHTML = '<button class="js-print-receipt" data-print-url="/print/7"></button>';
    await import('../../static/js/payments-index-page.js');
    document.querySelector('.js-print-receipt').click();
    expect(window.ActionHelpers.openPrintWindow).toHaveBeenCalledWith('/print/7');
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('falls back to window.open without ActionHelpers', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<button class="js-print-receipt" data-print-url="/print/8"></button>';
    await import('../../static/js/payments-index-page.js');
    document.querySelector('.js-print-receipt').click();
    expect(openSpy).toHaveBeenCalledWith('/print/8', '_blank');
  });

  it('defers initialisation until DOMContentLoaded while loading', async () => {
    setReadyState('loading');
    document.body.innerHTML = '<table id="receiptsTable"></table>';
    const $ = makePageJQuery();
    window.jQuery = $;
    await import('../../static/js/payments-index-page.js');
    expect(DataTableCalls).toHaveLength(0);
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(DataTableCalls).toHaveLength(1);
  });
});

describe('payments-receipts-page.js', () => {
  let origJQuery;

  beforeEach(() => {
    origJQuery = window.jQuery;
    DataTableCalls = [];
    isDataTableSpy = vi.fn(() => false);
    smartPrint = { buildButtons: vi.fn(() => [{ text: 'print' }]), attachTrigger: vi.fn() };
    window.SmartPrint = smartPrint;
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    delete window.ActionHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    if (origJQuery === undefined) delete window.jQuery;
    else window.jQuery = origJQuery;
    delete window.SmartPrint;
    delete window.ActionHelpers;
    restoreReadyState();
    vi.resetModules();
  });

  it('bails out without jQuery DataTable', async () => {
    setReadyState('complete');
    await import('../../static/js/payments-receipts-page.js');
    expect(DataTableCalls).toHaveLength(0);
    expect(smartPrint.attachTrigger).not.toHaveBeenCalled();
  });

  it('returns early when the table element is missing', async () => {
    setReadyState('complete');
    window.jQuery = makePageJQuery();
    await import('../../static/js/payments-receipts-page.js');
    expect(DataTableCalls).toHaveLength(0);
  });

  it('creates the table with smart-print buttons and attaches the trigger', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<table id="receiptsTable" data-lang-url="/ar.json"></table><button id="printReceiptsBtn"></button>';
    window.jQuery = makePageJQuery();
    await import('../../static/js/payments-receipts-page.js');
    expect(DataTableCalls).toHaveLength(1);
    expect(DataTableCalls[0].language.url).toBe('/ar.json');
    expect(DataTableCalls[0].dom).toBe('Bfrtip');
    expect(DataTableCalls[0].buttons).toEqual([{ text: 'print' }]);
    expect(smartPrint.buildButtons).toHaveBeenCalledWith({
      title: 'جميع المدفوعات',
      headerColor: '#198754',
    });
    expect(smartPrint.attachTrigger).toHaveBeenCalledWith(
      expect.any(Object),
      '#printReceiptsBtn',
      expect.objectContaining({ title: 'جميع المدفوعات' })
    );
    const el = document.querySelector('#receiptsTable');
    expect(el.dataset.smartPrintInit).toBe('true');
  });

  it('reuses an existing DataTable instance', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<table id="receiptsTable"></table><button id="printReceiptsBtn"></button>';
    isDataTableSpy = vi.fn(() => true);
    window.jQuery = makePageJQuery();
    await import('../../static/js/payments-receipts-page.js');
    expect(DataTableCalls).toHaveLength(1);
    expect(DataTableCalls[0]).toBeUndefined();
    expect(smartPrint.attachTrigger).toHaveBeenCalledTimes(1);
  });

  it('does not re-attach smart print when already initialised', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<table id="receiptsTable" data-smart-print-init="true"></table>';
    window.jQuery = makePageJQuery();
    await import('../../static/js/payments-receipts-page.js');
    expect(smartPrint.attachTrigger).not.toHaveBeenCalled();
  });

  it('builds an empty button list without SmartPrint', async () => {
    setReadyState('complete');
    delete window.SmartPrint;
    document.body.innerHTML = '<table id="receiptsTable"></table>';
    window.jQuery = makePageJQuery();
    await import('../../static/js/payments-receipts-page.js');
    expect(DataTableCalls[0].buttons).toEqual([]);
  });

  it('archives a payment item with id and helper', async () => {
    setReadyState('complete');
    window.ActionHelpers = { archivePaymentItem: vi.fn() };
    document.body.innerHTML = '<button class="js-archive-payment" data-item-type="receipt" data-item-id="42" data-item-number="R-001"></button>';
    await import('../../static/js/payments-receipts-page.js');
    document.querySelector('.js-archive-payment').click();
    expect(window.ActionHelpers.archivePaymentItem).toHaveBeenCalledWith('receipt', '42', 'R-001');
  });

  it('ignores archive buttons without an id', async () => {
    setReadyState('complete');
    window.ActionHelpers = { archivePaymentItem: vi.fn() };
    document.body.innerHTML = '<button class="js-archive-payment"></button>';
    await import('../../static/js/payments-receipts-page.js');
    document.querySelector('.js-archive-payment').click();
    expect(window.ActionHelpers.archivePaymentItem).not.toHaveBeenCalled();
  });

  it('ignores archive buttons without ActionHelpers', async () => {
    setReadyState('complete');
    document.body.innerHTML = '<button class="js-archive-payment" data-item-id="1"></button>';
    await import('../../static/js/payments-receipts-page.js');
    expect(() => document.querySelector('.js-archive-payment').click()).not.toThrow();
  });
});
