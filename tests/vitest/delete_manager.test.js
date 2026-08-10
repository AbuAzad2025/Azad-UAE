import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let swalFire;
let showValidationMessage;
let swalIsLoading;
let ajaxMock;
let fetchMock;
let handlers;
let addedListeners;

function makeJQuery() {
  const mk = (els) => {
    const getEl = () => els[0] || null;
    return {
      els,
      get length() {
        return els.length;
      },
      data(key, value) {
        const el = getEl();
        if (!el) return this;
        const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (value === undefined) return el.dataset[camel];
        el.dataset[camel] = value;
        return this;
      },
      val(v) {
        const el = getEl();
        if (v === undefined) return el ? el.value : undefined;
        if (el) el.value = v;
        return this;
      },
      attr(name) {
        return getEl()?.getAttribute(name) || undefined;
      },
      closest(sel) {
        return mk([getEl()?.closest(sel)]);
      },
      remove() {
        getEl()?.remove();
        return this;
      },
      fadeOut(_duration, cb) {
        const el = getEl();
        if (el && typeof cb === 'function') cb.call(el);
        return this;
      },
      trigger(evt) {
        getEl()?.dispatchEvent(new Event(evt, { bubbles: true }));
        return this;
      },
    };
  };

  const docApi = {
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

  const $ = (arg) => {
    if (arg && typeof arg === 'object' && Array.isArray(arg.els)) return arg;
    if (arg === document) return docApi;
    if (typeof arg === 'string') {
      let nodes = [];
      try {
        nodes = Array.from(document.querySelectorAll(arg));
      } catch {
        nodes = [];
      }
      return mk(nodes);
    }
    return mk([arg]);
  };
  $.ajax = ajaxMock;
  return $;
}

async function importDeleteManager() {
  await import('../../static/js/delete-manager.js');
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 5));
}

beforeEach(() => {
  handlers = [];
  addedListeners = [];
  swalFire = vi.fn(() => Promise.resolve({ isConfirmed: true }));
  showValidationMessage = vi.fn();
  swalIsLoading = vi.fn(() => false);
  global.Swal = {
    fire: swalFire,
    showValidationMessage: showValidationMessage,
    isLoading: swalIsLoading,
  };
  window.Swal = global.Swal;
  ajaxMock = vi.fn(() => Promise.resolve({ ok: true }));
  fetchMock = vi.fn(async () => ({ ok: true }));
  global.fetch = fetchMock;
  global.toastr = { success: vi.fn(), warning: vi.fn() };
  window.toastr = global.toastr;
  vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(function () {
    submittedForms.push(this);
  });
  document.body.innerHTML = '';
  const $ = makeJQuery();
  global.$ = $;
  window.$ = $;
  global.jQuery = $;
  window.jQuery = $;
  vi.resetModules();
});

let submittedForms;

let originalLocation;

beforeEach(() => {
  submittedForms = [];
  originalLocation = window.location;
});

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  (addedListeners || []).forEach(({ evt, listener }) => document.removeEventListener(evt, listener));
  document.body.innerHTML = '';
  delete global.Swal;
  delete window.Swal;
  delete global.toastr;
  delete window.toastr;
  delete global.$;
  delete window.$;
  delete global.jQuery;
  delete window.jQuery;
  delete global.fetch;
  delete window.deleteItem;
  delete window.deleteMultiple;
  delete window.deleteTableRow;
  delete window.restoreItem;
  vi.restoreAllMocks();
  vi.resetModules();
});

describe('delete-manager.js', () => {
  it('deleteItem submits an archiving form with CSRF token', async () => {
    document.body.insertAdjacentHTML(
      'beforeend',
      '<input name="csrf_token" value="secret123"><button data-delete-item="5" data-item-type="customer" data-item-name="أحمد"></button>',
    );
    await importDeleteManager();
    document.querySelector('[data-delete-item]').click();
    expect(swalFire).toHaveBeenCalledTimes(1);
    const opts = swalFire.mock.calls[0][0];
    expect(opts.title).toBe('حذف زبون');
    expect(opts.icon).toBe('warning');
    opts.preConfirm();
    await flush();
    expect(submittedForms.length).toBe(1);
    const form = submittedForms[0];
    expect(form.getAttribute('method')).toBe('POST');
    expect(form.action).toContain('/customers/5/delete');
    expect(form.querySelector('input[name="csrf_token"]').value).toBe('secret123');
  });

  it('deleteItem warns for unsupported types without submitting', async () => {
    await importDeleteManager();
    window.deleteItem('widgets', 1, 'شيء');
    expect(swalFire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'info' }));
    expect(submittedForms.length).toBe(0);
  });

  it('deleteItem uses default title for unknown but supported endpoints', async () => {
    document.body.insertAdjacentHTML(
      'beforeend',
      '<meta name="csrf-token" content="m1"><button data-delete-item="9" data-item-type="sales" data-item-name="ف"></button>',
    );
    await importDeleteManager();
    document.querySelector('[data-delete-item]').click();
    const opts = swalFire.mock.calls[0][0];
    expect(opts.title).toBe('حذف فاتورة مبيعات');
    opts.preConfirm();
    await flush();
    expect(submittedForms[0].action).toContain('/sales/9/delete');
    expect(submittedForms[0].querySelector('input[name="csrf_token"]').value).toBe('m1');
  });

  it('deleteMultiple warns when nothing selected', async () => {
    await importDeleteManager();
    window.deleteMultiple([], 'customers', '/customers');
    expect(global.toastr.warning).toHaveBeenCalled();
    expect(swalFire).not.toHaveBeenCalled();
  });

  it('deleteMultiple falls back to alert without toastr', async () => {
    delete global.toastr;
    delete window.toastr;
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    await importDeleteManager();
    window.deleteMultiple([], 'customers', '/customers');
    expect(alertSpy).toHaveBeenCalled();
  });

  it('deleteMultiple deletes each id via fetch and redirects', async () => {
    const fakeLocation = { href: 'http://localhost:3000/', reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    await importDeleteManager();
    window.deleteMultiple([3, 4], 'sales', '/sales');
    const opts = swalFire.mock.calls[0][0];
    await opts.preConfirm();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain('/sales/3/delete');
    expect(fetchMock.mock.calls[1][0]).toContain('/sales/4/delete');
    expect(fetchMock.mock.calls[0][1].headers['X-CSRFToken']).toBe('');
    await flush();
    expect(swalFire.mock.calls.some((c) => c[0].icon === 'success')).toBe(true);
    await flush();
    expect(fakeLocation.href).toBe('/sales');
  });

  it('deleteMultiple reports failure for unsupported type', async () => {
    await importDeleteManager();
    window.deleteMultiple([1], 'widgets', '/widgets');
    const opts = swalFire.mock.calls[0][0];
    await opts.preConfirm();
    expect(showValidationMessage).toHaveBeenCalled();
  });

  it('deleteMultiple reports failed fetch', async () => {
    global.fetch = vi.fn(async () => ({ ok: false }));
    await importDeleteManager();
    window.deleteMultiple([7], 'products', '/products');
    const opts = swalFire.mock.calls[0][0];
    await opts.preConfirm();
    expect(showValidationMessage).toHaveBeenCalledWith('فشل حذف العنصر رقم 7');
  });

  it('deleteTableRow fades out and removes the row when confirmed', async () => {
    const row = document.createElement('tr');
    row.id = 'row1';
    const cell = document.createElement('td');
    row.appendChild(cell);
    document.body.appendChild(row);
    await importDeleteManager();
    window.deleteTableRow(row, 'تأكيد؟');
    const opts = swalFire.mock.calls[0][0];
    expect(opts.text).toBe('تأكيد؟');
    await opts.confirmHandler ? null : opts.then;
    await flush();
    expect(document.getElementById('row1')).toBeNull();
    expect(global.toastr.success).toHaveBeenCalled();
  });

  it('deleteTableRow keeps the row when cancelled', async () => {
    swalFire.mockReturnValueOnce(Promise.resolve({ isConfirmed: false }));
    const row = document.createElement('tr');
    document.body.appendChild(row);
    await importDeleteManager();
    window.deleteTableRow(row);
    await flush();
    expect(document.querySelector('tr')).not.toBeNull();
  });

  it('deleteMultiple reloads page when no redirect url', async () => {
    const fakeLocation = { href: 'http://localhost:3000/', reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    await importDeleteManager();
    window.deleteMultiple([1], 'customers', undefined);
    const opts = swalFire.mock.calls[0][0];
    await opts.preConfirm();
    await flush();
    await flush();
    expect(fakeLocation.reload).toHaveBeenCalled();
  });

  it('restoreItem informs when restore is not supported', async () => {
    await importDeleteManager();
    window.restoreItem(1, 'customers', 'أحمد');
    expect(swalFire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'info' }));
  });

  it('restoreItem calls ajax and reloads on success', async () => {
    await importDeleteManager();
    window.restoreItem(5, 'sales', 'فاتورة');
    const opts = swalFire.mock.calls[0][0];
    expect(opts.icon).toBe('question');
    await opts.preConfirm();
    expect(ajaxMock).toHaveBeenCalledTimes(1);
    expect(ajaxMock.mock.calls[0][0].url).toContain('/sales/5/restore');
    expect(ajaxMock.mock.calls[0][0].headers['X-CSRFToken']).toBe('');
    await flush();
    expect(swalFire.mock.calls.some((c) => c[0].title === 'تمت الاستعادة')).toBe(true);
  });

  it('restoreItem shows validation message on ajax error', async () => {
    global.$.ajax = vi.fn(() =>
      Promise.reject({ responseJSON: { message: 'تعذر الاستعادة' } }),
    );
    await importDeleteManager();
    window.restoreItem(5, 'sales', 'فاتورة');
    const opts = swalFire.mock.calls[0][0];
    await opts.preConfirm();
    expect(showValidationMessage).toHaveBeenCalledWith('حدث خطأ: تعذر الاستعادة');
  });

  it('delegated delete-row button click triggers deleteTableRow', async () => {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    const btn = document.createElement('button');
    btn.setAttribute('data-delete-row', '1');
    btn.setAttribute('data-confirm-message', 'احذف السطر؟');
    cell.appendChild(btn);
    row.appendChild(cell);
    document.body.appendChild(row);
    await importDeleteManager();
    btn.click();
    expect(swalFire).toHaveBeenCalledWith(expect.objectContaining({ title: 'تأكيد الحذف' }));
    const opts = swalFire.mock.calls[0][0];
    expect(opts.text).toBe('احذف السطر؟');
    await flush();
    expect(document.querySelector('tr')).toBeNull();
  });

  it('delegated restore-item button click triggers restoreItem', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-restore-item', '2');
    btn.setAttribute('data-item-type', 'receipts');
    btn.setAttribute('data-item-name', 'سند');
    document.body.appendChild(btn);
    await importDeleteManager();
    btn.click();
    const opts = swalFire.mock.calls[0][0];
    expect(opts.html).toContain('سند');
    await opts.preConfirm();
    expect(ajaxMock.mock.calls[0][0].url).toContain('/payments/receipts/2/restore');
  });

  it('allowOutsideClick defers to Swal loading state', async () => {
    await importDeleteManager();
    window.deleteItem('customers', 1, 'x');
    const opts = swalFire.mock.calls[0][0];
    expect(opts.allowOutsideClick()).toBe(true);
    swalIsLoading.mockReturnValue(true);
    expect(opts.allowOutsideClick()).toBe(false);
  });
});
