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
});
