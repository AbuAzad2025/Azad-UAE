import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/* ------------------------------------------------------------------ */
/*  jQuery mock with handler capture and $(document).ready support     */
/* ------------------------------------------------------------------ */
const eventStore = new Map();

function createMock$() {
  const chain = (sel) => {
    const api = {
      length: sel === document ? 1 : (typeof sel === 'string' ? (document.querySelector(sel) ? 1 : 0) : 0),
      on: (events, ns, fn) => {
        if (typeof ns === 'function') { fn = ns; ns = ''; }
        const selector = typeof sel === 'string' ? sel : String(sel);
        String(events).split(/\s+/).forEach((ev) => {
          const key = selector + '|' + ev;
          if (!eventStore.has(key)) eventStore.set(key, []);
          eventStore.get(key).push({ fn, context: api });
        });
        return api;
      },
      off: () => api,
      trigger: (type) => {
        const selector = typeof sel === 'string' ? sel : String(sel);
        const key = selector + '|' + type;
        (eventStore.get(key) || []).forEach((h) => h.fn.call(h.context));
        return api;
      },
      ready: (fn) => { if (typeof fn === 'function') fn(); return api; },
      addClass: () => api,
      removeClass: () => api,
      hasClass: () => false,
      data: (k, v) => {
        if (v !== undefined) { api._data = api._data || {}; api._data[k] = v; return api; }
        return (api._data || {})[k];
      },
      find: () => chain(null),
      each: (fn) => { if (fn) fn.call(api, 0, api); return api; },
      val: () => '',
      text: () => '',
      append: () => api,
      html: () => api,
      DataTable: (...args) => {
        // Delegate to $.fn.DataTable which is set up in importModule
        return (window.$.fn.DataTable || vi.fn())(...args);
      },
    };
    return api;
  };

  const $ = (sel) => {
    if (typeof sel === 'function') { sel(); return chain(null); }
    return chain(sel);
  };
  $.fn = {};
  $.ajaxSetup = vi.fn();
  $.ajax = vi.fn(() => Promise.resolve());
  $.notify = vi.fn();
  return $;
}

/* ================================================================== */
/*  Tests                                                              */
/* ================================================================== */
describe('sales-index.js', () => {
  let mock$;
  let drawSpy;
  let searchSpy;
  let columnSearchSpy;
  let columnObj;
  let tableInstance;

  beforeEach(() => {
    document.body.innerHTML = '';
    eventStore.clear();
    vi.resetModules();

    drawSpy = vi.fn();
    searchSpy = vi.fn(() => ({ draw: drawSpy }));
    columnSearchSpy = vi.fn(() => ({ draw: drawSpy }));
    columnObj = { search: columnSearchSpy };
    tableInstance = {
      search: searchSpy,
      column: vi.fn(() => columnObj),
      draw: drawSpy,
    };

    window.SmartPrint = {
      buildButtons: vi.fn(() => []),
      attachTrigger: vi.fn(),
    };

    document.body.innerHTML = `
      <table id="salesTable">
        <thead><tr><th>A</th><th>B</th><th>C</th><th>Total</th><th>Paid</th><th>E</th><th>F</th><th>G</th><th>Status</th></tr></thead>
        <tbody></tbody>
      </table>
      <div class="btn-group">
        <button id="filterAll">All</button>
        <button id="filterPaid">Paid</button>
        <button id="filterPartial">Partial</button>
        <button id="filterUnpaid">Unpaid</button>
      </div>
      <button id="printSalesBtn">Print</button>`;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    eventStore.clear();
    delete window.SmartPrint;
    delete window.$.fn.DataTable;
    delete window.$;
    delete window.jQuery;
    delete window._DATATABLES_LANG_URL;
    delete window.azad;
    vi.resetModules();
  });

  async function importModule() {
    mock$ = createMock$();
    window.$ = mock$;
    window.jQuery = mock$;
    mock$.fn.DataTable = vi.fn((opts) => tableInstance);
    mock$.fn.DataTable.isDataTable = vi.fn(() => false);
    await import('../../static/js/sales-index.js');
    return tableInstance;
  }

  /* -------------------------------------------------------------- */
  /*  1. DataTable initialization                                    */
  /* -------------------------------------------------------------- */
  it('initializes DataTable when DOM is ready', async () => {
    await importModule();
    expect(mock$.fn.DataTable).toHaveBeenCalled();
    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    expect(dtOpts).toMatchObject({
      order: [[2, 'desc']],
      pageLength: 25,
      responsive: true,
    });
  });

  it('uses existing DataTable if already initialized', async () => {
    mock$ = createMock$();
    window.$ = mock$;
    window.jQuery = mock$;
    mock$.fn.DataTable = vi.fn(() => tableInstance);
    mock$.fn.DataTable.isDataTable = vi.fn(() => true);
    await import('../../static/js/sales-index.js');
    expect(mock$.fn.DataTable).toHaveBeenCalledTimes(1);
  });

  /* -------------------------------------------------------------- */
  /*  2. SmartPrint attach                                           */
  /* -------------------------------------------------------------- */
  it('attaches SmartPrint trigger with print options', async () => {
    await importModule();
    expect(window.SmartPrint.attachTrigger).toHaveBeenCalledWith(
      tableInstance,
      '#printSalesBtn',
      expect.objectContaining({ title: expect.any(String) }),
    );
  });

  /* -------------------------------------------------------------- */
  /*  3. DataTable options verification                              */
  /* -------------------------------------------------------------- */
  it('passes correct language URL', async () => {
    await importModule();
    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    expect(dtOpts.language.url).toBe('/static/datatables/Arabic.json');
  });

  it('uses custom _DATATABLES_LANG_URL when set', async () => {
    window._DATATABLES_LANG_URL = '/custom/ar.json';
    await importModule();
    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    expect(dtOpts.language.url).toBe('/custom/ar.json');
  });

  it('passes SmartPrint buildButtons as buttons config', async () => {
    await importModule();
    expect(window.SmartPrint.buildButtons).toHaveBeenCalled();
    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    expect(dtOpts.buttons).toEqual([]);
  });

  /* -------------------------------------------------------------- */
  /*  4. footerCallback                                              */
  /* -------------------------------------------------------------- */
  it('footerCallback computes totals from columns 3 and 4', async () => {
    await importModule();
    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    expect(typeof dtOpts.footerCallback).toBe('function');

    const fakeData = ['100.00', '200.50', '50.00'];
    const mockApi = {
      column: vi.fn(() => ({
        data: vi.fn(() => ({
          reduce: (fn, init) => fakeData.reduce(fn, init),
        })),
      })),
    };
    dtOpts.footerCallback.call({ api: () => mockApi });
    expect(mockApi.column).toHaveBeenCalledWith(3, { page: 'current' });
    expect(mockApi.column).toHaveBeenCalledWith(4, { page: 'current' });
  });

  it('footerCallback uses window.azad.showInfo when available', async () => {
    const showInfoSpy = vi.fn();
    window.azad = { showInfo: showInfoSpy };
    await importModule();

    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    const mockApi = {
      column: vi.fn(() => ({
        data: vi.fn(() => ({
          reduce: (fn, init) => ['10'].reduce(fn, init),
        })),
      })),
    };
    dtOpts.footerCallback.call({ api: () => mockApi });
    expect(showInfoSpy).toHaveBeenCalledWith(expect.stringContaining('10.00'));
  });

  it('footerCallback falls back to console.info', async () => {
    delete window.azad;
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    await importModule();

    const dtOpts = mock$.fn.DataTable.mock.calls[0][0];
    const mockApi = {
      column: vi.fn(() => ({
        data: vi.fn(() => ({
          reduce: (fn, init) => ['5'].reduce(fn, init),
        })),
      })),
    };
    dtOpts.footerCallback.call({ api: () => mockApi });
    expect(infoSpy).toHaveBeenCalled();
    infoSpy.mockRestore();
  });

  /* -------------------------------------------------------------- */
  /*  5. Filter – All clears search                                 */
  /* -------------------------------------------------------------- */
  it('#filterAll handler calls table.search with empty string and draws', async () => {
    await importModule();
    const handler = (eventStore.get('#filterAll|click.smartPrint') || [])[0];
    expect(handler).toBeDefined();
    handler.fn.call(handler.context);
    expect(searchSpy).toHaveBeenCalledWith('');
    expect(drawSpy).toHaveBeenCalled();
  });

  /* -------------------------------------------------------------- */
  /*  6. Filter – Paid searches column 8 for مدفوع                  */
  /* -------------------------------------------------------------- */
  it('#filterPaid handler searches column 8 for مدفوع', async () => {
    await importModule();
    const handler = (eventStore.get('#filterPaid|click.smartPrint') || [])[0];
    expect(handler).toBeDefined();
    handler.fn.call(handler.context);
    expect(tableInstance.column).toHaveBeenCalledWith(8);
    expect(columnSearchSpy).toHaveBeenCalledWith('مدفوع');
    expect(drawSpy).toHaveBeenCalled();
  });

  /* -------------------------------------------------------------- */
  /*  7. Filter – Partial searches column 8 for جزئي                */
  /* -------------------------------------------------------------- */
  it('#filterPartial handler searches column 8 for جزئي', async () => {
    await importModule();
    const handler = (eventStore.get('#filterPartial|click.smartPrint') || [])[0];
    expect(handler).toBeDefined();
    handler.fn.call(handler.context);
    expect(columnSearchSpy).toHaveBeenCalledWith('جزئي');
    expect(drawSpy).toHaveBeenCalled();
  });

  /* -------------------------------------------------------------- */
  /*  8. Filter – Unpaid searches column 8 for آجل                  */
  /* -------------------------------------------------------------- */
  it('#filterUnpaid handler searches column 8 for آجل', async () => {
    await importModule();
    const handler = (eventStore.get('#filterUnpaid|click.smartPrint') || [])[0];
    expect(handler).toBeDefined();
    handler.fn.call(handler.context);
    expect(columnSearchSpy).toHaveBeenCalledWith('آجل');
    expect(drawSpy).toHaveBeenCalled();
  });

  /* -------------------------------------------------------------- */
  /*  9. All four filter handlers are registered                     */
  /* -------------------------------------------------------------- */
  it('registers click.smartPrint handlers on all four filter buttons', async () => {
    await importModule();
    expect(eventStore.has('#filterAll|click.smartPrint')).toBe(true);
    expect(eventStore.has('#filterPaid|click.smartPrint')).toBe(true);
    expect(eventStore.has('#filterPartial|click.smartPrint')).toBe(true);
    expect(eventStore.has('#filterUnpaid|click.smartPrint')).toBe(true);
  });

  /* -------------------------------------------------------------- */
  /* 10. Filter handlers call off().on() pattern                     */
  /* -------------------------------------------------------------- */
  it('each filter handler is registered exactly once', async () => {
    await importModule();
    expect(eventStore.get('#filterAll|click.smartPrint')).toHaveLength(1);
    expect(eventStore.get('#filterPaid|click.smartPrint')).toHaveLength(1);
    expect(eventStore.get('#filterPartial|click.smartPrint')).toHaveLength(1);
    expect(eventStore.get('#filterUnpaid|click.smartPrint')).toHaveLength(1);
  });
});
