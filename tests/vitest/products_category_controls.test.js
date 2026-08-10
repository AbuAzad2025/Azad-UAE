import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let ajaxCalls;
let modalCalls;
let fakeLocation;
let originalLocation;
let origDocAdd;
let docListeners;

function makeCategoryJQuery() {
  const mk = (els) => {
    const el = () => els[0] || null;
    const api = {
      els,
      get length() {
        return els.length;
      },
      first() {
        return mk(els.slice(0, 1));
      },
      find(sel) {
        const matches = [];
        els.forEach((e) => {
          try {
            matches.push(...Array.from(e.querySelectorAll(sel)));
          } catch {
            // jsdom rejects some attribute selectors used in the real code.
          }
        });
        return mk(matches);
      },
      on(evt, sel, fn) {
        els.forEach((e) => {
          if (typeof sel === 'function') {
            e.addEventListener(evt, sel);
          } else {
            e.addEventListener(evt, (ev) => {
              const t = ev.target && typeof ev.target.closest === 'function' ? ev.target.closest(sel) : null;
              if (t && e.contains(t)) fn.call(t, ev);
            });
          }
        });
        return api;
      },
      trigger(evt) {
        els.forEach((e) => e.dispatchEvent(new Event(evt, { bubbles: true })));
        return api;
      },
      val(v) {
        if (v === undefined) return el() ? el().value : undefined;
        els.forEach((e) => {
          e.value = v;
        });
        return api;
      },
      text(v) {
        if (v === undefined) return el() ? el().textContent : '';
        els.forEach((e) => {
          e.textContent = v;
        });
        return api;
      },
      attr(name, val) {
        if (val === undefined) return el() ? el().getAttribute(name) : undefined;
        els.forEach((e) => e.setAttribute(name, val));
        return api;
      },
      data(key, val) {
        const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (val === undefined) return el() ? el().dataset[k] : undefined;
        els.forEach((e) => {
          e.dataset[k] = val;
        });
        return api;
      },
      removeData(key) {
        const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        els.forEach((e) => delete e.dataset[k]);
        return api;
      },
      prop(name, val) {
        if (val === undefined) return el() ? el()[name] : undefined;
        els.forEach((e) => {
          e[name] = val;
        });
        return api;
      },
      append(child) {
        if (el() && child.els) el().appendChild(child.els[0]);
        return api;
      },
      remove() {
        els.forEach((e) => e.remove());
        return api;
      },
      closest(sel) {
        return mk(els.flatMap((e) => [e.closest(sel)]).filter(Boolean));
      },
      fadeOut(_dur, cb) {
        els.forEach((e) => {
          if (typeof cb === 'function') cb.call(e);
        });
        return api;
      },
      modal(action) {
        modalCalls.push(action);
        return api;
      },
      hide() {
        if (el()) el().style.display = 'none';
        return api;
      },
      toggle(force) {
        els.forEach((e) => {
          e.style.display = force === undefined ? (e.style.display === 'none' ? '' : 'none') : force ? '' : 'none';
        });
        return api;
      },
    };
    return api;
  };

  const $ = (arg) => {
    if (typeof arg === 'string') {
      if (arg.startsWith('<')) {
        const tmp = document.implementation.createHTMLDocument('');
        tmp.body.innerHTML = arg;
        return mk(Array.from(tmp.body.children));
      }
      return mk(Array.from(document.querySelectorAll(arg)));
    }
    if (arg && arg.els) return arg;
    if (arg === document) return mk([document]);
    if (typeof arg === 'function') {
      arg();
      return mk([]);
    }
    if (typeof Node !== 'undefined' && arg instanceof Node) return mk([arg]);
    return mk([]);
  };
  $.fn = {};
  $.ajax = (opts) => ajaxCalls.push(opts);
  return $;
}

function mountProductControls() {
  document.body.innerHTML = `
    <select id="product_category">
      <option value="0">-- اختر --</option>
      <option value="5" data-name="Beverages" data-name-ar="مشروبات" data-description="Drinks">Beverages</option>
    </select>
    <div class="js-category-actions">
      <button class="js-category-add"></button>
      <button class="js-category-edit" disabled></button>
      <button class="js-category-delete" disabled></button>
    </div>
    <div class="pc-empty-categories"></div>
    <div id="categoryModal">
      <h5 class="js-category-modal-title"></h5>
      <span class="js-category-save-label"></span>
      <input id="category_name">
      <input id="category_name_ar">
      <input id="category_description">
      <button class="js-category-save"></button>
    </div>
    <input name="csrf_token" value="csrf-abc">
  `;
}

describe('products/category-controls.js — initProductCategoryControls', () => {
  let $;

  beforeEach(() => {
    ajaxCalls = [];
    modalCalls = [];
    docListeners = [];
    originalLocation = window.location;
    fakeLocation = { reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    origDocAdd = document.addEventListener.bind(document);
    document.addEventListener = vi.fn((t, f) => {
      docListeners.push({ t, f });
      origDocAdd(t, f);
    });
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    mountProductControls();
    $ = makeCategoryJQuery();
    global.jQuery = $;
    window.jQuery = $;
    vi.resetModules();
  });

  afterEach(() => {
    docListeners.forEach(({ t, f }) => document.removeEventListener(t, f));
    document.addEventListener = origDocAdd;
    window.confirm.mockRestore();
    window.alert.mockRestore();
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    document.body.innerHTML = '';
    delete global.jQuery;
    delete window.jQuery;
    vi.resetModules();
  });

  function selectCategory(id) {
    const sel = document.querySelector('#product_category');
    sel.value = id;
    sel.dispatchEvent(new Event('change'));
  }

  async function initControls(overrides = {}) {
    await import('../../static/js/products/category-controls.js');
    window.initProductCategoryControls({
      select: '#product_category',
      wrap: '.js-category-actions',
      modal: '#categoryModal',
      createUrl: '/categories/create',
      updateUrl: (id) => `/categories/${id}/update`,
      deleteUrl: (id) => `/categories/${id}/delete`,
      ...overrides,
    });
  }

  it('enables edit/delete actions only when a real category is selected', async () => {
    await initControls();
    const edit = document.querySelector('.js-category-edit');
    const del = document.querySelector('.js-category-delete');
    expect(edit.disabled).toBe(true);
    expect(del.disabled).toBe(true);
    selectCategory('5');
    document.querySelector('#product_category').dispatchEvent(new Event('change'));
    expect(edit.disabled).toBe(false);
    expect(del.disabled).toBe(false);
  });

  it('opens a fresh modal on add', async () => {
    await initControls();
    document.querySelector('.js-category-add').click();
    expect(modalCalls).toContain('show');
    expect(document.querySelector('.js-category-modal-title').textContent).toBe('إضافة فئة منتجات');
    expect(document.querySelector('.js-category-save-label').textContent).toBe('حفظ الفئة');
  });

  it('opens the edit modal populated from the selected option', async () => {
    await initControls();
    selectCategory('5');
    document.querySelector('.js-category-edit').click();
    expect(modalCalls).toContain('show');
    expect(document.querySelector('#categoryModal').dataset.editId).toBe('5');
    expect(document.querySelector('#category_name').value).toBe('Beverages');
    expect(document.querySelector('#category_name_ar').value).toBe('مشروبات');
    expect(document.querySelector('#category_description').value).toBe('Drinks');
    expect(document.querySelector('.js-category-modal-title').textContent).toBe('تعديل فئة المنتجات');
  });

  it('does not open the edit modal without a selected category', async () => {
    await initControls();
    document.querySelector('.js-category-edit').click();
    expect(modalCalls).not.toContain('show');
  });

  it('does not delete without a selected category', async () => {
    await initControls();
    document.querySelector('.js-category-delete').click();
    expect(ajaxCalls).toHaveLength(0);
  });

  it('skips the delete request when the user cancels', async () => {
    window.confirm.mockImplementation(() => false);
    await initControls();
    selectCategory('5');
    document.querySelector('.js-category-delete').click();
    expect(ajaxCalls).toHaveLength(0);
  });

  it('deletes a category and resets the select on success', async () => {
    await initControls();
    selectCategory('5');
    document.querySelector('.js-category-delete').click();
    expect(ajaxCalls).toHaveLength(1);
    expect(ajaxCalls[0].url).toBe('/categories/5/delete');
    expect(ajaxCalls[0].headers['X-CSRFToken']).toBe('csrf-abc');
    ajaxCalls[0].success({ success: true });
    expect(document.querySelector('#product_category option[value="5"]')).toBeNull();
    expect(document.querySelector('#product_category').value).toBe('0');
  });

  it('alerts when delete fails', async () => {
    await initControls();
    selectCategory('5');
    document.querySelector('.js-category-delete').click();
    ajaxCalls[0].success({ success: false, error: 'in use' });
    expect(window.alert).toHaveBeenCalledWith('in use');
  });

  it('alerts with the server error on delete request failure', async () => {
    await initControls();
    selectCategory('5');
    document.querySelector('.js-category-delete').click();
    ajaxCalls[0].error({ responseJSON: { error: 'boom' } });
    expect(window.alert).toHaveBeenCalledWith('boom');
  });

  it('warns when saving with an empty name', async () => {
    await initControls();
    document.querySelector('.js-category-save').click();
    expect(window.alert).toHaveBeenCalledWith('أدخل اسم الفئة');
    expect(ajaxCalls).toHaveLength(0);
  });

  it('creates a new category via createUrl and updates the select', async () => {
    await initControls();
    document.querySelector('#category_name').value = 'Snacks';
    document.querySelector('#category_name_ar').value = 'وجبات خفيفة';
    document.querySelector('#category_description').value = 'Munchies';
    document.querySelector('.js-category-save').click();
    expect(ajaxCalls).toHaveLength(1);
    expect(ajaxCalls[0].url).toBe('/categories/create');
    expect(JSON.parse(ajaxCalls[0].data)).toEqual({
      name: 'Snacks',
      name_ar: 'وجبات خفيفة',
      description: 'Munchies',
    });
    ajaxCalls[0].success({ success: true, category: { id: 9, name: 'Snacks', name_ar: 'وجبات خفيفة' } });
    expect(document.querySelector('#product_category option[value="9"]')).toBeTruthy();
    expect(document.querySelector('#product_category').value).toBe('9');
    expect(modalCalls).toContain('hide');
    expect(document.querySelector('#category_name').value).toBe('');
  });

  it('alerts and re-enables the button when create fails', async () => {
    await initControls();
    document.querySelector('#category_name').value = 'Snacks';
    const btn = document.querySelector('.js-category-save');
    btn.click();
    expect(btn.disabled).toBe(true);
    ajaxCalls[0].success({ success: false, error: 'dup' });
    expect(window.alert).toHaveBeenCalledWith('dup');
    expect(btn.disabled).toBe(false);
  });

  it('alerts with the server error when the create request fails', async () => {
    await initControls();
    document.querySelector('#category_name').value = 'Snacks';
    document.querySelector('.js-category-save').click();
    ajaxCalls[0].error({ responseJSON: { error: 'denied' } });
    expect(window.alert).toHaveBeenCalledWith('denied');
  });

  it('updates an existing category via updateUrl', async () => {
    await initControls();
    selectCategory('5');
    document.querySelector('#categoryModal').dataset.editId = '5';
    document.querySelector('#category_name').value = 'Cold Drinks';
    document.querySelector('.js-category-save').click();
    expect(ajaxCalls[0].url).toBe('/categories/5/update');
    ajaxCalls[0].success({
      success: true,
      category: { id: 5, name: 'Cold Drinks', name_ar: 'مشروبات', description: '' },
    });
    expect(document.querySelector('#product_category option[value="5"]').textContent).toBe('مشروبات');
    expect(document.querySelector('#product_category').value).toBe('5');
  });

  it('resets the modal when it is hidden', async () => {
    await initControls();
    document.querySelector('#categoryModal').dataset.editId = '7';
    document.querySelector('#category_name').value = 'X';
    document.querySelector('#categoryModal').dispatchEvent(new Event('hidden.bs.modal'));
    expect(document.querySelector('#categoryModal').dataset.editId).toBeUndefined();
    expect(document.querySelector('#category_name').value).toBe('');
  });
});

describe('products/category-controls.js — initCategoryListControls', () => {
  let $;

  beforeEach(() => {
    ajaxCalls = [];
    modalCalls = [];
    docListeners = [];
    originalLocation = window.location;
    fakeLocation = { reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    origDocAdd = document.addEventListener.bind(document);
    document.addEventListener = vi.fn((t, f) => {
      docListeners.push({ t, f });
      origDocAdd(t, f);
    });
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    document.body.innerHTML = `
      <div id="categoryModal">
        <h5 class="js-category-modal-title"></h5>
        <span class="js-category-save-label"></span>
        <input id="category_name">
        <input id="category_name_ar">
        <input id="category_description">
        <button class="js-category-save"></button>
      </div>
      <input name="csrf_token" value="csrf-xyz">
      <table>
        <tbody>
          <tr>
            <td>
              <button class="js-category-row-edit" data-id="3" data-name="Fruit" data-name-ar="فواكه" data-description="Fresh"></button>
              <button class="js-category-row-delete" data-id="3" data-label="Fruit"></button>
            </td>
          </tr>
        </tbody>
      </table>
    `;
    $ = makeCategoryJQuery();
    global.jQuery = $;
    window.jQuery = $;
    vi.resetModules();
  });

  afterEach(() => {
    docListeners.forEach(({ t, f }) => document.removeEventListener(t, f));
    document.addEventListener = origDocAdd;
    window.confirm.mockRestore();
    window.alert.mockRestore();
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    document.body.innerHTML = '';
    delete global.jQuery;
    delete window.jQuery;
    vi.resetModules();
  });

  async function initList(overrides = {}) {
    await import('../../static/js/products/category-controls.js');
    window.initCategoryListControls({
      modal: '#categoryModal',
      createUrl: '/categories/create',
      updateUrl: (id) => `/categories/${id}/update`,
      deleteUrl: (id) => `/categories/${id}/delete`,
      ...overrides,
    });
  }

  it('opens the edit modal from a row button', async () => {
    await initList();
    document.querySelector('.js-category-row-edit').click();
    expect(modalCalls).toContain('show');
    expect(document.querySelector('#categoryModal').dataset.editId).toBe('3');
    expect(document.querySelector('#category_name').value).toBe('Fruit');
    expect(document.querySelector('#category_name_ar').value).toBe('فواكه');
    expect(document.querySelector('#category_description').value).toBe('Fresh');
  });

  it('skips row deletion when the user cancels', async () => {
    window.confirm.mockImplementation(() => false);
    await initList();
    document.querySelector('.js-category-row-delete').click();
    expect(ajaxCalls).toHaveLength(0);
  });

  it('deletes a row category and fades out the row on success', async () => {
    await initList();
    document.querySelector('.js-category-row-delete').click();
    expect(ajaxCalls[0].url).toBe('/categories/3/delete');
    expect(ajaxCalls[0].headers['X-CSRFToken']).toBe('csrf-xyz');
    ajaxCalls[0].success({ success: true });
    expect(document.querySelector('tbody tr')).toBeNull();
  });

  it('alerts when row deletion fails', async () => {
    await initList();
    document.querySelector('.js-category-row-delete').click();
    ajaxCalls[0].success({ success: false, error: 'locked' });
    expect(window.alert).toHaveBeenCalledWith('locked');
  });

  it('alerts with the server error on row delete failure', async () => {
    await initList();
    document.querySelector('.js-category-row-delete').click();
    ajaxCalls[0].error({ responseJSON: { error: 'nope' } });
    expect(window.alert).toHaveBeenCalledWith('nope');
  });

  it('warns when saving a list category with an empty name', async () => {
    await initList();
    document.querySelector('.js-category-save').click();
    expect(window.alert).toHaveBeenCalledWith('أدخل اسم الفئة');
  });

  it('creates a list category and reloads the page on success', async () => {
    await initList();
    document.querySelector('#category_name').value = 'Dairy';
    document.querySelector('.js-category-save').click();
    expect(ajaxCalls[0].url).toBe('/categories/create');
    expect(JSON.parse(ajaxCalls[0].data).name).toBe('Dairy');
    ajaxCalls[0].success({ success: true });
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('disables the save button during the request and reloads on success', async () => {
    await initList();
    document.querySelector('#category_name').value = 'Dairy';
    const btn = document.querySelector('.js-category-save');
    btn.click();
    expect(btn.disabled).toBe(true);
    ajaxCalls[0].success({ success: true });
    expect(btn.disabled).toBe(false);
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('alerts with the server error when the list save request fails', async () => {
    await initList();
    document.querySelector('#category_name').value = 'Dairy';
    document.querySelector('.js-category-save').click();
    ajaxCalls[0].error({ responseJSON: { error: 'denied' } });
    expect(window.alert).toHaveBeenCalledWith('denied');
  });
});
