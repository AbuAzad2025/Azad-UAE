import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const handlers = new Map();
const dataStores = new Map();
const valStores = new Map();
const propStores = new Map();
const textStores = new Map();
const modalSpy = vi.fn(() => undefined);

function makeJQuery() {
  const dataStore = (key) => {
    if (!dataStores.has(key)) dataStores.set(key, {});
    return dataStores.get(key);
  };
  const chain = (sel) => {
    const api = {
      length: typeof sel === 'string' ? (sel === 'body' || sel.startsWith('#') ? 1 : 0) : (sel ? 1 : 0),
      on: (types, fn) => {
        String(types).split(' ').forEach((t) => {
          const key = String(sel) + '|' + t;
          if (!handlers.has(key)) handlers.set(key, []);
          handlers.get(key).push(fn);
        });
        return api;
      },
      off: () => api,
      trigger: (type, event) => {
        const key = String(sel) + '|' + type;
        const ev = event || { type, preventDefault() {} };
        (handlers.get(key) || []).slice().forEach((fn) => fn.call(api, ev));
        return api;
      },
      data: (k, v) => {
        const s = dataStore('data:' + String(sel));
        if (v !== undefined) { s[k] = v; return api; }
        return s[k];
      },
      val: (v) => {
        const s = valStores;
        if (v !== undefined) { s.set('val:' + String(sel), v); return api; }
        return s.get('val:' + String(sel)) ?? '';
      },
      prop: (k, v) => {
        if (v !== undefined) { propStores.set('prop:' + String(sel) + ':' + k, v); return api; }
        return propStores.get('prop:' + String(sel) + ':' + k);
      },
      addClass: () => api,
      removeClass: () => api,
      text: (t) => {
        if (t !== undefined) { textStores.set('text:' + String(sel), t); return api; }
        return textStores.get('text:' + String(sel)) ?? '';
      },
      modal: modalSpy,
      each: (fn) => { if (fn) fn.call(api, 0, null); return api; },
      find: () => chain('.inner'),
      first: () => api,
      css: () => api,
      remove: () => api,
      prepend: () => api,
      append: (html) => {
        if (typeof sel === 'string' && (sel === 'body' || sel === document.body)) {
          document.body.insertAdjacentHTML('beforeend', String(html));
        }
        return api;
      },
    };
    return api;
  };
  const $ = (sel) => chain(sel);
  $.fn = {};
  $.extend = (...args) => {
    let deep = false;
    let target = args[0];
    let i = 1;
    if (typeof args[0] === 'boolean') { deep = args[0]; target = args[1]; i = 2; }
    for (; i < args.length; i += 1) {
      const src = args[i];
      if (!src) continue;
      Object.keys(src).forEach((k) => {
        const v = src[k];
        if (deep && v && typeof v === 'object' && !Array.isArray(v)) {
          const prev = target[k];
          target[k] = $.extend(true, (prev && typeof prev === 'object' && !Array.isArray(prev)) ? prev : {}, v);
        } else {
          target[k] = v;
        }
      });
    }
    return target;
  };
  $.Event = function (type) { this.type = type; };
  return $;
}

function makeTable() {
  const indexes = { toArray: () => [0, 1, 2, 3] };
  const btnNode = document.createElement('button');
  const buttonsApi = {
    exportData: vi.fn(() => ({ header: ['عمود'], body: [['قيمة']], footer: ['إجمالي'] })),
    exportInfo: vi.fn(() => ({ title: 'تقرير', messageTop: 'أعلى', messageBottom: 'أسفل' })),
    count: () => 0,
  };
  const buttons = vi.fn(() => buttonsApi);
  buttons.exportData = buttonsApi.exportData;
  buttons.exportInfo = buttonsApi.exportInfo;
  const table = {
    rows: vi.fn(() => ({ indexes: () => indexes, nodes: () => [], data: () => [], length: 0 })),
    page: { info: () => ({ page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 }) },
    button: vi.fn(() => ({ length: 1, node: () => btnNode })),
    buttons,
    table: vi.fn(() => ({ header: () => document.createElement('thead'), footer: () => document.createElement('tfoot') })),
  };
  return { table, btnNode, indexes };
}

async function importSmartPrint($) {
  window.$ = $;
  window.jQuery = $;
  await import('../../static/js/smart-print.js');
  return window.SmartPrint;
}

function flush(ms = 550) {
  return new Promise((r) => setTimeout(r, ms));
}

describe('smart-print.js', () => {
  let $;

  beforeEach(() => {
    document.body.innerHTML = '';
    handlers.clear();
    dataStores.clear();
    valStores.clear();
    propStores.clear();
    textStores.clear();
    modalSpy.mockClear();
    delete window.SmartPrint;
    delete window.jQuery;
    delete window.$;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.SmartPrint;
    delete window.jQuery;
    delete window.$;
    vi.resetModules();
  });

  it('exposes SmartPrint without the DataTables print extension and warns', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    $ = makeJQuery();
    const SmartPrint = await importSmartPrint($);
    expect(SmartPrint).toBeDefined();
    expect(typeof SmartPrint.buildButtons).toBe('function');
    expect(typeof SmartPrint.attachTrigger).toBe('function');
    expect(typeof SmartPrint.trigger).toBe('function');
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('SmartPrint'));
    warn.mockRestore();
  });

  it('buildButtons returns excel, pdf and print buttons with config', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const buttons = SmartPrint.buildButtons({ title: 'كشف' });
    expect(buttons).toHaveLength(3);
    const printBtn = buttons[2];
    expect(printBtn.extend).toBe('print');
    expect(printBtn.name).toBe('smart-print');
    expect(printBtn.smartPrintOptions.title).toBe('كشف');
    expect(printBtn.smartPrintOptions.headerColor).toBe('#0d6efd');
    expect(typeof printBtn.action).toBe('function');
    expect(typeof printBtn.customize).toBe('function');
    expect(typeof printBtn.init).toBe('function');
  });

  it('buildButtons applies default options when none given', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const buttons = SmartPrint.buildButtons();
    expect(buttons[2].smartPrintOptions.title).toBe('');
  });

  it('print button action opens the smart print modal', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const printBtn = SmartPrint.buildButtons({ title: 'تقرير' })[2];
    const { table, btnNode } = makeTable();
    const ctx = { node: () => btnNode };
    printBtn.action.call(ctx, { type: 'click' }, table, btnNode, printBtn);
    expect($('#smartPrintModal').modal).toHaveBeenCalledWith('show');
    expect(document.getElementById('smartPrintModal')).toBeTruthy();
  });

  it('trigger opens modal and preloads options from button config', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    $(btnNode).data('smartPrintConfig', { smartPrintOptions: { title: 'مخزن', headerColor: '#28a745' } });
    SmartPrint.trigger(table);
    expect($('#smartPrintModal').modal).toHaveBeenCalledWith('show');
  });

  it('trigger warns when no table provided', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    SmartPrint.trigger(null);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('trigger warns when print button cannot be located', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const { table } = makeTable();
    table.button.mockReturnValue({ length: 0 });
    SmartPrint.trigger(table);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('attachTrigger binds click on found trigger and returns early for missing table', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    $(btnNode).data('smartPrintConfig', { smartPrintOptions: {} });
    expect(() => SmartPrint.attachTrigger(null, '#x')).not.toThrow();
  });

  it('handleConfirm runs default print action with rows selector', async () => {
    const defaultAction = vi.fn();
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: defaultAction } } } };
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    $(btnNode).data('smartPrintConfig', { exportOptions: { columns: ':visible' } });
    $('input[name="smartPrintRange"]:checked').val('all');
    SmartPrint.trigger(table);
    expect($('#smartPrintModal').modal).toHaveBeenCalledWith('show');
    $('body').append('<div id="smartPrintModal"></div>');
    $('#smartPrintModalConfirm').trigger('click');
    expect(defaultAction).toHaveBeenCalledTimes(1);
    const config = defaultAction.mock.calls[0][3];
    expect(config.exportOptions.columns).toBe(':visible');
    expect(typeof config.exportOptions.rows).toBe('function');
    expect(config.exportOptions.rows(0)).toBe(true);
    expect(config.exportOptions.rows(5)).toBe(false);
    expect($('#smartPrintModal').modal).toHaveBeenCalledWith('hide');
  });

  it('handleConfirm falls back to fallbackPrint when default action throws', async () => {
    const defaultAction = vi.fn(() => { throw new Error('fail'); });
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: defaultAction } } } };
    const printWin = {
      document: { write: vi.fn(), close: vi.fn(), open: vi.fn() },
      focus: vi.fn(),
      print: vi.fn(),
      close: vi.fn(),
    };
    window.open = vi.fn(() => printWin);
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    $(btnNode).data('smartPrintConfig', { header: true, footer: true });
    $('input[name="smartPrintRange"]:checked').val('all');
    SmartPrint.trigger(table);
    $('#smartPrintModalConfirm').trigger('click');
    const writes = printWin.document.write.mock.calls.join('\n');
    expect(writes).toContain('تقرير');
    expect(writes).toContain('عمود');
    expect(writes).toContain('قيمة');
    expect(writes).toContain('إجمالي');
    await flush();
    expect(printWin.print).toHaveBeenCalled();
    expect(printWin.close).toHaveBeenCalled();
  });

  it('fallbackPrint warns when popup blocked', async () => {
    window.open = vi.fn(() => null);
    global.alert = vi.fn();
    $ = makeJQuery();
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    $(btnNode).data('smartPrintConfig', {});
    $('input[name="smartPrintRange"]:checked').val('all');
    SmartPrint.trigger(table);
    $('#smartPrintModalConfirm').trigger('click');
    expect(global.alert).toHaveBeenCalled();
  });

  it('fallbackPrint catches extraction errors and alerts', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    global.alert = vi.fn();
    window.open = vi.fn(() => null);
    $ = makeJQuery();
    const SmartPrint = await importSmartPrint($);
    const { table, btnNode } = makeTable();
    table.buttons.exportData.mockImplementation(() => { throw new Error('boom'); });
    $(btnNode).data('smartPrintConfig', {});
    $('input[name="smartPrintRange"]:checked').val('all');
    SmartPrint.trigger(table);
    $('#smartPrintModalConfirm').trigger('click');
    expect(global.alert).toHaveBeenCalled();
    expect(err).toHaveBeenCalled();
    err.mockRestore();
  });

  it('handleConfirm does nothing without table state', async () => {
    $ = makeJQuery();
    $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
    const SmartPrint = await importSmartPrint($);
    $('body').append('<div id="smartPrintModal"></div>');
    $('#smartPrintModalConfirm').trigger('click');
    expect(SmartPrint).toBeDefined();
  });

  describe('_buildRowsSelector', () => {
    function makeTableForSelector(applied = [10, 11, 12, 13], current = [10, 11], pageInfo = { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 }) {
      return {
        rows: vi.fn((mod) => {
          if (mod?.page === 'current') return { indexes: () => ({ toArray: () => current }) };
          return { indexes: () => ({ toArray: () => applied }) };
        }),
        page: { info: () => pageInfo },
      };
    }

    it('mode "all" returns a selector including all applied indexes', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      const sel = SmartPrint._buildRowsSelector('all', table, {});
      expect(typeof sel).toBe('function');
      expect(sel(10)).toBe(true);
      expect(sel(13)).toBe(true);
      expect(sel(99)).toBe(false);
    });

    it('mode "page" returns a selector for current page indexes', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11]);
      const sel = SmartPrint._buildRowsSelector('page', table, {});
      expect(sel(10)).toBe(true);
      expect(sel(11)).toBe(true);
      expect(sel(12)).toBe(false);
    });

    it('mode "page" shows error when no current page rows', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], []);
      const sel = SmartPrint._buildRowsSelector('page', table, {});
      expect(sel).toBeNull();
    });

    it('mode "rows" returns selector for valid range', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      const sel = SmartPrint._buildRowsSelector('rows', table, { rowStart: '2', rowEnd: '3' });
      expect(sel(10)).toBe(false);
      expect(sel(11)).toBe(true);
      expect(sel(12)).toBe(true);
      expect(sel(13)).toBe(false);
    });

    it('mode "rows" defaults end to start when omitted', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      const sel = SmartPrint._buildRowsSelector('rows', table, { rowStart: '2' });
      expect(sel(11)).toBe(true);
      expect(sel(10)).toBe(false);
      expect(sel(12)).toBe(false);
    });

    it('mode "rows" shows error for invalid start', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      expect(SmartPrint._buildRowsSelector('rows', table, { rowStart: '' })).toBeNull();
      expect(SmartPrint._buildRowsSelector('rows', table, { rowStart: '0' })).toBeNull();
      expect(SmartPrint._buildRowsSelector('rows', table, { rowStart: '-1' })).toBeNull();
    });

    it('mode "rows" shows error when end < start', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      expect(SmartPrint._buildRowsSelector('rows', table, { rowStart: '3', rowEnd: '1' })).toBeNull();
    });

    it('mode "rows" shows error when start exceeds total', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      expect(SmartPrint._buildRowsSelector('rows', table, { rowStart: '10' })).toBeNull();
    });

    it('mode "pages" returns selector for valid page range', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11], { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 });
      const sel = SmartPrint._buildRowsSelector('pages', table, { pageStart: '1', pageEnd: '2' });
      expect(sel(10)).toBe(true);
      expect(sel(11)).toBe(true);
      expect(sel(12)).toBe(true);
      expect(sel(13)).toBe(true);
    });

    it('mode "pages" defaults end to start when omitted', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11], { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 });
      const sel = SmartPrint._buildRowsSelector('pages', table, { pageStart: '2' });
      expect(sel(10)).toBe(false);
      expect(sel(11)).toBe(false);
      expect(sel(12)).toBe(true);
      expect(sel(13)).toBe(true);
    });

    it('mode "pages" shows error when totalPages <= 1', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11, 12, 13], { page: 0, pages: 1, length: -1, recordsTotal: 4, recordsDisplay: 4 });
      expect(SmartPrint._buildRowsSelector('pages', table, { pageStart: '1' })).toBeNull();
    });

    it('mode "pages" shows error for invalid start', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11], { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 });
      expect(SmartPrint._buildRowsSelector('pages', table, { pageStart: '' })).toBeNull();
      expect(SmartPrint._buildRowsSelector('pages', table, { pageStart: '0' })).toBeNull();
    });

    it('mode "pages" shows error when end < start', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11], { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 });
      expect(SmartPrint._buildRowsSelector('pages', table, { pageStart: '2', pageEnd: '1' })).toBeNull();
    });

    it('mode "pages" shows error when startPage > totalPages', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([10, 11, 12, 13], [10, 11], { page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 });
      expect(SmartPrint._buildRowsSelector('pages', table, { pageStart: '5' })).toBeNull();
    });

    it('returns null when no applied indexes', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector([]);
      expect(SmartPrint._buildRowsSelector('all', table, {})).toBeNull();
    });

    it('returns null for unknown mode', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = makeTableForSelector();
      expect(SmartPrint._buildRowsSelector('bogus', table, {})).toBeNull();
    });
  });

  describe('_updateInputStates', () => {
    it('disables all inputs for mode "all"', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      SmartPrint._updateInputStates('all');
      expect($('#smartPrintRowStart, #smartPrintRowEnd').prop('disabled')).toBe(true);
      expect($('#smartPrintPageStart, #smartPrintPageEnd').prop('disabled')).toBe(true);
    });

    it('enables row inputs for mode "rows"', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      SmartPrint._updateInputStates('rows');
      expect($('#smartPrintRowStart, #smartPrintRowEnd').prop('disabled')).toBe(false);
      expect($('#smartPrintPageStart, #smartPrintPageEnd').prop('disabled')).toBe(true);
    });

    it('enables page inputs for mode "pages"', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      SmartPrint._updateInputStates('pages');
      expect($('#smartPrintRowStart, #smartPrintRowEnd').prop('disabled')).toBe(true);
      expect($('#smartPrintPageStart, #smartPrintPageEnd').prop('disabled')).toBe(false);
    });
  });

  describe('_resetModal', () => {
    it('resets radio to all and clears inputs', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      $('input[name="smartPrintRange"]').prop('checked', false);
      $('#smartPrintRowStart, #smartPrintRowEnd, #smartPrintPageStart, #smartPrintPageEnd').val('5');
      SmartPrint._resetModal();
      expect($('#smartPrintAll').prop('checked')).toBe(true);
      expect($('#smartPrintRowStart, #smartPrintRowEnd, #smartPrintPageStart, #smartPrintPageEnd').val()).toBe('');
    });
  });

  describe('_applyPrintStyles', () => {
    function makeWinJQuery(doc) {
      const wrap = (el) => ({
        length: el ? 1 : 0,
        css: (k, v) => { if (el) el.style[k] = v; return wrap(el); },
        find: (s) => wrap(el ? el.querySelector(s) : null),
        first: () => wrap(el),
        remove: () => { if (el && el.parentNode) el.parentNode.removeChild(el); return wrap(el); },
        prepend: (html) => { if (el) el.insertAdjacentHTML('afterbegin', html); return wrap(el); },
        removeClass: (c) => { if (el) el.classList.remove(...c.split(' ')); return wrap(el); },
        addClass: (c) => { if (el) el.classList.add(...c.split(' ')); return wrap(el); },
      });
      return (sel) => wrap(typeof sel === 'string' ? doc.querySelector(sel) : sel);
    }

    it('injects styles and title into print window', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const doc = document.implementation.createHTMLDocument('print');
      doc.body.innerHTML = '<table><tr><td>test</td></tr></table>';
      const win = { document: doc, jQuery: makeWinJQuery(doc) };
      SmartPrint._applyPrintStyles(win, { title: 'كشف', headerColor: '#28a745', wide: false });
      expect(doc.querySelector('style')).toBeTruthy();
      expect(doc.querySelector('h1.print-title')?.textContent).toBe('كشف');
      expect(doc.querySelector('.print-meta')?.textContent).toBe('Azad ERP System');
    });

    it('works without jQuery in window', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const doc = document.implementation.createHTMLDocument('print');
      const win = { document: doc };
      delete window.jQuery;
      SmartPrint._applyPrintStyles(win, { title: '', wide: true });
      expect(doc.querySelector('style')).toBeTruthy();
    });

    it('skips title when empty', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const doc = document.implementation.createHTMLDocument('print');
      doc.body.innerHTML = '<table><tr><td>test</td></tr></table>';
      const win = { document: doc, jQuery: makeWinJQuery(doc) };
      SmartPrint._applyPrintStyles(win, { title: '', wide: true });
      expect(doc.querySelector('h1.print-title')).toBeFalsy();
    });
  });

  describe('_fallbackPrint', () => {
    it('extracts data via buttons exportData when available', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const printWin = {
        document: { write: vi.fn(), close: vi.fn() },
        focus: vi.fn(), print: vi.fn(), close: vi.fn(),
      };
      window.open = vi.fn(() => printWin);
      const buttonsFn = vi.fn(() => ({}));
      buttonsFn.exportData = vi.fn(() => ({ header: ['H'], body: [['B']], footer: ['F'] }));
      buttonsFn.exportInfo = vi.fn(() => ({ title: 'T', messageTop: 'MT', messageBottom: 'MB' }));
      const dt = { buttons: buttonsFn };
      SmartPrint._fallbackPrint(dt, { header: true, footer: true, smartPrintOptions: {} });
      const writes = printWin.document.write.mock.calls.map(c => c[0]).join('');
      expect(writes).toContain('H');
      expect(writes).toContain('B');
      expect(writes).toContain('F');
      expect(writes).toContain('MT');
      expect(writes).toContain('MB');
    });

    it('extracts data from DOM when buttons extension is missing', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const printWin = {
        document: { write: vi.fn(), close: vi.fn() },
        focus: vi.fn(), print: vi.fn(), close: vi.fn(),
      };
      window.open = vi.fn(() => printWin);
      const realTable = document.createElement('table');
      const thead = document.createElement('thead');
      const tr = document.createElement('tr');
      const th = document.createElement('th');
      th.textContent = 'العنوان';
      tr.appendChild(th);
      thead.appendChild(tr);
      realTable.appendChild(thead);
      const tbody = document.createElement('tbody');
      const trow = document.createElement('tr');
      const td = document.createElement('td');
      td.textContent = 'القيمة';
      trow.appendChild(td);
      tbody.appendChild(trow);
      realTable.appendChild(tbody);
      document.body.appendChild(realTable);
      const dt = {
        table: () => ({ header: () => thead, footer: () => document.createElement('tfoot') }),
        rows: () => ({ nodes: () => [trow], data: () => [], length: 1 }),
      };
      SmartPrint._fallbackPrint(dt, { header: true, footer: false, smartPrintOptions: {}, title: 'تقرير' });
      const writes = printWin.document.write.mock.calls.map(c => c[0]).join('');
      expect(writes).toContain('العنوان');
      expect(writes).toContain('القيمة');
      realTable.remove();
    });

    it('extracts raw data when nodes are empty', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const printWin = {
        document: { write: vi.fn(), close: vi.fn() },
        focus: vi.fn(), print: vi.fn(), close: vi.fn(),
      };
      window.open = vi.fn(() => printWin);
      const thead = document.createElement('thead');
      const dt = {
        table: () => ({ header: () => thead, footer: () => document.createElement('tfoot') }),
        rows: () => ({ nodes: () => [], data: () => [['مباشر']], length: 1 }),
      };
      SmartPrint._fallbackPrint(dt, { header: false, footer: false, smartPrintOptions: {} });
      const writes = printWin.document.write.mock.calls.map(c => c[0]).join('');
      expect(writes).toContain('مباشر');
    });

    it('extracts object raw data with Object.values', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const printWin = {
        document: { write: vi.fn(), close: vi.fn() },
        focus: vi.fn(), print: vi.fn(), close: vi.fn(),
      };
      window.open = vi.fn(() => printWin);
      const dt = {
        table: () => ({ header: () => document.createElement('thead'), footer: () => document.createElement('tfoot') }),
        rows: () => ({ nodes: () => [], data: () => [{ a: 'x', b: 'y' }], length: 1 }),
      };
      SmartPrint._fallbackPrint(dt, { header: false, footer: false, smartPrintOptions: {} });
      const writes = printWin.document.write.mock.calls.map(c => c[0]).join('');
      expect(writes).toContain('x');
      expect(writes).toContain('y');
    });

    it('shows alert when popup is blocked', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      window.open = vi.fn(() => null);
      global.alert = vi.fn();
      const buttonsFn = vi.fn(() => ({}));
      buttonsFn.exportData = vi.fn(() => ({ header: [], body: [], footer: [] }));
      buttonsFn.exportInfo = vi.fn(() => ({}));
      const dt = { buttons: buttonsFn };
      SmartPrint._fallbackPrint(dt, { smartPrintOptions: {} });
      expect(global.alert).toHaveBeenCalledWith(expect.stringContaining('النوافذ المنبثقة'));
    });
  });

  describe('attachTrigger', () => {
    it('binds click and calls trigger on click', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const { table, btnNode } = makeTable();
      $(btnNode).data('smartPrintConfig', { smartPrintOptions: { title: 'X' } });
      const triggerSpy = vi.spyOn(SmartPrint, 'trigger').mockImplementation(() => {});
      SmartPrint.attachTrigger(table, btnNode);
      $(btnNode).trigger('click.smartPrint');
      expect(triggerSpy).toHaveBeenCalledWith(table, undefined);
      triggerSpy.mockRestore();
    });

    it('returns early for same selector', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const { table, btnNode } = makeTable();
      SmartPrint.attachTrigger(table, btnNode);
      const triggerSpy = vi.spyOn(SmartPrint, 'trigger').mockImplementation(() => {});
      SmartPrint.attachTrigger(table, btnNode);
      $(btnNode).trigger('click.smartPrint');
      expect(triggerSpy).toHaveBeenCalledTimes(1);
      triggerSpy.mockRestore();
    });
  });

  describe('trigger fallback button finding', () => {
    it('falls back to last button when smart-print-button not found', async () => {
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const btnNode = document.createElement('button');
      const table = {
        button: vi.fn((sel) => {
          if (sel === '.smart-print-button') return { length: 0 };
          if (sel === 'smart-print:name') return { length: 0 };
          return { length: 1, node: () => btnNode };
        }),
        buttons: vi.fn(() => ({ count: () => 3 })),
      };
      $(btnNode).data('smartPrintConfig', { smartPrintOptions: { title: 'fallback' } });
      SmartPrint.trigger(table);
      expect($('#smartPrintModal').modal).toHaveBeenCalledWith('show');
    });

    it('warns when no buttons exist at all', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
      $ = makeJQuery();
      $.fn.dataTable = { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } };
      const SmartPrint = await importSmartPrint($);
      const table = {
        button: vi.fn(() => ({ length: 0 })),
        buttons: vi.fn(() => ({ count: () => 0 })),
      };
      SmartPrint.trigger(table);
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('hidden print button'));
      warn.mockRestore();
    });
  });
});
