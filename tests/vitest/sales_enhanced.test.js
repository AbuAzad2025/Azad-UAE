import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/* ------------------------------------------------------------------ */
/*  Functional jQuery mock – wraps real jsdom DOM                       */
/* ------------------------------------------------------------------ */
function createjQuery() {
  const elData = new WeakMap();

  function chainify(elements) {
    const api = {
      length: elements.length,
      0: elements[0],
      each(fn) {
        elements.forEach((el, i) => fn.call(el, i, el));
        return api;
      },
      find(sel) {
        const found = [];
        elements.forEach((el) => {
          if (el.querySelectorAll) found.push(...el.querySelectorAll(sel));
        });
        return chainify(found);
      },
      closest(sel) {
        const found = [];
        elements.forEach((el) => {
          if (el.closest) {
            const c = el.closest(sel);
            if (c) found.push(c);
          }
        });
        return chainify(found);
      },
      parent() {
        return chainify(
          elements.map((el) => el.parentElement).filter(Boolean),
        );
      },
      append(content) {
        elements.forEach((el) => {
          if (typeof content === 'string') {
            el.insertAdjacentHTML('beforeend', content);
          } else if (content instanceof HTMLElement) {
            el.appendChild(content);
          } else if (content && typeof content.length === 'number' && content[0] instanceof HTMLElement) {
            for (let i = 0; i < content.length; i++)
              el.appendChild(content[i]);
          }
        });
        return api;
      },
      remove() {
        elements.forEach((el) => el.remove());
        return api;
      },
      empty() {
        elements.forEach((el) => {
          el.innerHTML = '';
        });
        return api;
      },
      val(v) {
        if (v !== undefined) {
          elements.forEach((el) => {
            el.value = v;
          });
          return api;
        }
        return elements[0] ? elements[0].value : '';
      },
      text(v) {
        if (v !== undefined) {
          elements.forEach((el) => {
            el.textContent = String(v);
          });
          return api;
        }
        return elements[0] ? elements[0].textContent : '';
      },
      html(v) {
        if (v !== undefined) {
          elements.forEach((el) => {
            el.innerHTML = v;
          });
          return api;
        }
        return elements[0] ? elements[0].innerHTML : '';
      },
      data(key, val) {
        if (val !== undefined) {
          elements.forEach((el) => {
            if (!elData.has(el)) elData.set(el, {});
            elData.get(el)[key] = val;
          });
          return api;
        }
        if (elements[0]) {
          const store = elData.get(elements[0]);
          if (store && key in store) return store[key];
          const attr = elements[0].getAttribute(`data-${key}`);
          if (attr !== null) {
            if (attr === 'true') return true;
            if (attr === 'false') return false;
            if (attr === 'null') return null;
            if (!Number.isNaN(Number(attr)) && attr !== '') return Number(attr);
            return attr;
          }
          return undefined;
        }
        return undefined;
      },
      on(event, selectorOrHandler, maybeHandler) {
        const handler =
          typeof selectorOrHandler === 'function'
            ? selectorOrHandler
            : maybeHandler;
        if (typeof handler === 'function') {
          elements.forEach((el) => {
            String(event).split(/\s+/).filter(Boolean).forEach((ev) => {
              el.addEventListener(ev, handler);
            });
          });
        }
        return api;
      },
      off(event) {
        return api;
      },
      trigger(event) {
        elements.forEach((el) =>
          el.dispatchEvent(new Event(event, { bubbles: true })),
        );
        return api;
      },
      css(prop, val) {
        if (val !== undefined) {
          elements.forEach((el) => {
            el.style[prop] = val;
          });
          return api;
        }
        return elements[0] ? elements[0].style[prop] : '';
      },
      show() {
        elements.forEach((el) => {
          el.style.display = '';
        });
        return api;
      },
      hide() {
        elements.forEach((el) => {
          el.style.display = 'none';
        });
        return api;
      },
      attr(name, val) {
        if (val !== undefined) {
          elements.forEach((el) => el.setAttribute(name, val));
          return api;
        }
        return elements[0] ? elements[0].getAttribute(name) : null;
      },
      prop(name, val) {
        if (val !== undefined) {
          elements.forEach((el) => {
            el[name] = val;
          });
          return api;
        }
        return elements[0] ? elements[0][name] : undefined;
      },
      addClass(cls) {
        elements.forEach((el) => {
          String(cls).split(/\s+/).filter(Boolean).forEach((c) => el.classList.add(c));
        });
        return api;
      },
      removeClass(cls) {
        elements.forEach((el) => {
          String(cls).split(/\s+/).filter(Boolean).forEach((c) => el.classList.remove(c));
        });
        return api;
      },
      hasClass(cls) {
        return elements[0] ? elements[0].classList.contains(cls) : false;
      },
      is() {
        return false;
      },
      select2() {
        return api;
      },
      modal() {
        return api;
      },
      focus() {
        if (elements[0] && elements[0].focus) elements[0].focus();
        return api;
      },
      ready(fn) {
        if (typeof fn === 'function') fn();
        return api;
      },
      jquery: '3.6.0',
    };
    return api;
  }

  function $(selector) {
    if (typeof selector === 'function') {
      selector();
      return chainify([]);
    }
    if (selector === document || selector === window) {
      return chainify([selector]);
    }
    if (typeof selector === 'string') {
      if (selector.trim().startsWith('<')) {
        const temp = document.createElement('div');
        temp.innerHTML = selector.trim();
        const el = temp.firstElementChild;
        return el ? chainify([el]) : chainify([]);
      }
      return chainify([...document.querySelectorAll(selector)]);
    }
    if (selector instanceof HTMLElement) {
      return chainify([selector]);
    }
    return chainify([]);
  }

  $.ajax = vi.fn();
  $.ajaxSetup = vi.fn();
  $.fn = { select2: vi.fn() };
  $.each = function (obj, fn) {
    if (Array.isArray(obj)) {
      obj.forEach((v, i) => fn.call(v, i, v));
    } else if (obj && typeof obj === 'object') {
      Object.keys(obj).forEach((k) => fn.call(obj[k], k, obj[k]));
    }
  };
  $.notify = vi.fn();
  return $;
}

/* ------------------------------------------------------------------ */
/*  DOM helpers                                                         */
/* ------------------------------------------------------------------ */
function buildBaseDOM() {
  document.head.innerHTML = '<meta name="csrf-token" content="csrf123">';
  document.body.innerHTML = `
    <select id="currency">
      <option value="AED">AED</option>
      <option value="USD">USD</option>
    </select>
    <input id="exchange_rate" value="1.000000">
    <select id="payment_method">
      <option value="">--</option>
      <option value="cash">Cash</option>
    </select>
    <div id="payment_fields_container"></div>
    <div id="payment_amount_group"></div>
    <span id="payment_currency_display"></span>
    <div id="linesContainer"></div>
    <input type="hidden" id="line_count" value="0">
    <input id="customer_id" value="">
    <div id="serialNumberModal">
      <span id="serial_product_name"></span>
      <span id="serial_quantity_needed"></span>
      <ul id="serial_list"></ul>
      <span id="serial_count">0</span>
      <input id="serial_input">
      <button id="add_serial_btn">Add</button>
      <button id="generate_serial_btn">Generate</button>
      <button id="print_serials_btn">Print</button>
      <button id="save_serials_btn">Save</button>
    </div>
    <span id="subtotal"></span>
    <span id="total"></span>
    <span id="line_count_display"></span>
    <span id="discount_currency"></span>
    <span id="shipping_currency"></span>
    <span id="total_currency_label"></span>
    <input name="discount_amount" value="0">
    <input name="shipping_cost" value="0">
    <input name="tax_rate" value="0">
    <form id="saleForm">
      <button type="submit">Submit</button>
    </form>
  `;
}

function addLineDOM(
  index,
  { qty = '1', price = '100', discount = '0', serialNeeded = false } = {},
) {
  const div = document.createElement('div');
  div.className = 'product-line';
  div.id = `line_${index}`;
  div.innerHTML = `
    <select name="lines[${index}][product_id]" class="product-select"
            data-index="${index}">
      <option value="1">Prod</option>
    </select>
    <input type="number" name="lines[${index}][quantity]"
           class="quantity-input" value="${qty}">
    <input type="number" name="lines[${index}][unit_price]"
           class="price-input" id="price_${index}" value="${price}"
           data-base-price="${price}">
    <input type="number" name="lines[${index}][discount_percent]"
           class="discount-input" value="${discount}">
    <div id="serial_btn_container_${index}"
         style="${serialNeeded ? '' : 'display:none;'}">
      <button type="button" id="serial_btn_${index}"
              data-needed="${serialNeeded}"
              data-product-name="Widget">Serial</button>
    </div>
    <div id="line_info_${index}" style="display:none;"></div>
    <span id="stock_${index}"></span>
    <span id="cost_${index}"></span>
  `;
  document.getElementById('linesContainer').appendChild(div);
}

function removeAutoLine() {
  const auto = document.getElementById('line_0');
  if (auto) auto.remove();
}

/* ------------------------------------------------------------------ */
/*  Import + setup                                                      */
/* ------------------------------------------------------------------ */
async function loadModule() {
  vi.resetModules();
  const $ = createjQuery();
  globalThis.$ = $;
  window.$ = $;
  const mod = await import('../../static/js/sales-enhanced.js');
  return mod;
}

async function wait(ms = 30) {
  await new Promise((r) => setTimeout(r, ms));
}

/* ================================================================== */
/*  Tests                                                              */
/* ================================================================== */

describe('sales-enhanced.js', () => {
  let origFetch;
  let origOpen;

  beforeEach(() => {
    buildBaseDOM();
    window._FX_FALLBACK_BASE = 'AED';
    window._CURRENCY_SYMBOL = '₪';
    window._CURRENCY_NAME_AR = 'درهم';
    window.SmartSelectors = undefined;
    window.azad = {
      showLoading: vi.fn(),
      hideLoading: vi.fn(),
      showError: vi.fn(),
      showWarning: vi.fn(),
      showInfo: vi.fn(),
      showSuccess: vi.fn(),
      formatNumber: vi.fn((v) => String(v)),
    };
    origFetch = globalThis.fetch;
    origOpen = window.open;
  });

  afterEach(() => {
    globalThis.fetch = origFetch;
    window.open = origOpen;
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  /* ================================================================ */
  /* 1. getCsrfToken                                                   */
  /* ================================================================ */
  describe('getCsrfToken', () => {
    it('reads token from meta[name="csrf-token"]', async () => {
      await loadModule();
      const meta = document.querySelector('meta[name="csrf-token"]');
      expect(meta.getAttribute('content')).toBe('csrf123');
    });

    it('returns empty string when meta is missing', async () => {
      document.querySelector('meta[name="csrf-token"]')?.remove();
      await loadModule();
      expect(document.querySelector('meta[name="csrf-token"]')).toBeNull();
    });
  });

  /* ================================================================ */
  /* 2-3. _applyBasePrice via select2:select event                     */
  /* ================================================================ */
  describe('_applyBasePrice via select2:select', () => {
    it('converts price by exchange rate for non-base currency', async () => {
      await loadModule();
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '3.67';

      const select = document.querySelector(
        'select[name="lines[0][product_id]"]',
      );
      if (select) {
        const evt = new Event('select2:select', { bubbles: true });
        evt.params = { data: { id: 1, price: 367, stock: 10, cost: 50 } };
        select.dispatchEvent(evt);
        await wait();
        const priceInput = document.getElementById('price_0');
        expect(priceInput.value).toBe('100.00');
      }
    });
  });

  /* ================================================================ */
  /* 4-5. window.removeLine                                             */
  /* ================================================================ */
  describe('window.removeLine', () => {
    it('removes the line element from DOM', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(5);
      expect(document.getElementById('line_5')).not.toBeNull();
      window.removeLine(5);
      expect(document.getElementById('line_5')).toBeNull();
    });

    it('removes only the targeted line', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0);
      addLineDOM(1);
      window.removeLine(0);
      expect(document.getElementById('line_0')).toBeNull();
      expect(document.getElementById('line_1')).not.toBeNull();
    });
  });

  /* ================================================================ */
  /* 6-8. Serial modal + _serialQtyNeeded                              */
  /* ================================================================ */
  describe('_serialQtyNeeded via triggerSerialModal', () => {
    it('shows correct quantity in modal', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '7', serialNeeded: true });
      window.triggerSerialModal(0);
      expect(
        document.getElementById('serial_quantity_needed').textContent,
      ).toBe('7');
    });

    it('returns 0 when quantity input is missing', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(99, { qty: '5', serialNeeded: true });
      window.triggerSerialModal(99);
      expect(
        document.getElementById('serial_quantity_needed').textContent,
      ).toBe('5');
    });
  });

  /* ================================================================ */
  /* 9-10. _serialSyncFromHidden via triggerSerialModal                 */
  /* ================================================================ */
  describe('_serialSyncFromHidden', () => {
    it('syncs hidden inputs into serial list', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '3', serialNeeded: true });
      const line = document.getElementById('line_0');
      ['SN-A', 'SN-B'].forEach((sn) => {
        const h = document.createElement('input');
        h.type = 'hidden';
        h.name = 'lines[0][serials][]';
        h.value = sn;
        line.appendChild(h);
      });
      window.triggerSerialModal(0);
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(2);
    });

    it('filters whitespace-only hidden inputs', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: true });
      const line = document.getElementById('line_0');
      const h = document.createElement('input');
      h.type = 'hidden';
      h.name = 'lines[0][serials][]';
      h.value = '   ';
      line.appendChild(h);
      window.triggerSerialModal(0);
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(0);
    });
  });

  /* ================================================================ */
  /* 11-13. _serialAdd via button click                                 */
  /* ================================================================ */
  describe('_serialAdd', () => {
    it('adds serial via button click', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'SN-NEW-1';
      document.getElementById('add_serial_btn').click();
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(1);
      expect(items[0].textContent).toContain('SN-NEW-1');
    });

    it('rejects duplicate serials', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'SN-DUP';
      document.getElementById('add_serial_btn').click();
      document.getElementById('serial_input').value = 'SN-DUP';
      document.getElementById('add_serial_btn').click();
      expect(window.azad.showError).toHaveBeenCalled();
      expect(document.querySelectorAll('#serial_list li').length).toBe(1);
    });

    it('does nothing when input is empty', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = '';
      document.getElementById('add_serial_btn').click();
      expect(document.querySelectorAll('#serial_list li').length).toBe(0);
    });
  });

  /* ================================================================ */
  /* 14-15. _serialGenerate                                             */
  /* ================================================================ */
  describe('_serialGenerate', () => {
    it('generates serials up to the needed count', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '3', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('generate_serial_btn').click();
      expect(document.querySelectorAll('#serial_list li').length).toBe(3);
      expect(document.getElementById('serial_count').textContent).toBe('3');
    });

    it('does not duplicate existing manual serials', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'MANUAL-SN';
      document.getElementById('add_serial_btn').click();
      document.getElementById('generate_serial_btn').click();
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(2);
      expect(items[0].textContent).toContain('MANUAL-SN');
    });
  });

  /* ================================================================ */
  /* 16. _serialRemove                                                  */
  /* ================================================================ */
  describe('_serialRemove', () => {
    it('removes a serial when × button is clicked', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'SN-KEEP';
      document.getElementById('add_serial_btn').click();
      document.getElementById('serial_input').value = 'SN-DEL';
      document.getElementById('add_serial_btn').click();
      expect(document.querySelectorAll('#serial_list li').length).toBe(2);

      const removeBtns = document.querySelectorAll(
        '#serial_list .btn-link.text-danger',
      );
      removeBtns[1].click();
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(1);
      expect(items[0].textContent).toContain('SN-KEEP');
    });
  });

  /* ================================================================ */
  /* 17. _serialSave                                                    */
  /* ================================================================ */
  describe('_serialSave', () => {
    it('writes hidden inputs to line and closes modal', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'SN-S1';
      document.getElementById('add_serial_btn').click();
      document.getElementById('serial_input').value = 'SN-S2';
      document.getElementById('add_serial_btn').click();
      document.getElementById('save_serials_btn').click();

      const line = document.getElementById('line_0');
      const hidden = line.querySelectorAll(
        'input[name="lines[0][serials][]"]',
      );
      expect(hidden.length).toBe(2);
      expect(hidden[0].value).toBe('SN-S1');
      expect(hidden[1].value).toBe('SN-S2');
    });
  });

  /* ================================================================ */
  /* 18-20. _serialPrint                                                */
  /* ================================================================ */
  describe('_serialPrint', () => {
    it('opens print window with serial HTML', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'SN-P1';
      document.getElementById('add_serial_btn').click();

      const mockDoc = { open: vi.fn(), write: vi.fn(), close: vi.fn() };
      window.open = vi.fn(() => ({
        document: mockDoc,
        print: vi.fn(),
      }));
      document.getElementById('print_serials_btn').click();

      expect(window.open).toHaveBeenCalled();
      expect(mockDoc.write).toHaveBeenCalled();
      expect(mockDoc.open).toHaveBeenCalled();
      expect(mockDoc.close).toHaveBeenCalled();
    });

    it('does nothing when serials list is empty', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: true });
      window.triggerSerialModal(0);
      const spy = vi.fn();
      window.open = spy;
      document.getElementById('print_serials_btn').click();
      expect(spy).not.toHaveBeenCalled();
    });

    it('escapes HTML in serial numbers', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = '<b>XSS</b>';
      document.getElementById('add_serial_btn').click();

      const mockDoc = { open: vi.fn(), write: vi.fn(), close: vi.fn() };
      window.open = vi.fn(() => ({
        document: mockDoc,
        print: vi.fn(),
      }));
      document.getElementById('print_serials_btn').click();

      const allWrites = mockDoc.write.mock.calls.map((c) => c[0]).join('');
      expect(allWrites).not.toContain('<b>XSS</b>');
      expect(allWrites).toContain('&lt;b&gt;XSS&lt;/b&gt;');
    });
  });

  /* ================================================================ */
  /* 21-22. _serialRenderList                                           */
  /* ================================================================ */
  describe('_serialRenderList', () => {
    it('does nothing when _serialModalLine is null', async () => {
      await loadModule();
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(0);
      expect(document.getElementById('serial_count').textContent).toBe('0');
    });

    it('renders list items and updates count', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '3', serialNeeded: true });
      window.triggerSerialModal(0);
      document.getElementById('serial_input').value = 'A';
      document.getElementById('add_serial_btn').click();
      document.getElementById('serial_input').value = 'B';
      document.getElementById('add_serial_btn').click();

      expect(document.querySelectorAll('#serial_list li').length).toBe(2);
      expect(document.getElementById('serial_count').textContent).toBe('2');
    });
  });

  /* ================================================================ */
  /* 23-27. calculateTotalsClientSide via event dispatch                 */
  /* ================================================================ */
  function triggerCalc() {
    document
      .querySelector('[name="discount_amount"]')
      .dispatchEvent(new Event('change'));
  }

  describe('calculateTotalsClientSide', () => {
    it('computes subtotal, discount, shipping, tax, total', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', price: '100', discount: '10' });
      document.querySelector('[name="discount_amount"]').value = '20';
      document.querySelector('[name="shipping_cost"]').value = '30';
      document.querySelector('[name="tax_rate"]').value = '10';
      triggerCalc();
      await wait();
      // line: 2*100*0.9=180; after disc: 180-20+30=190; tax=19; total=209
      expect(document.getElementById('subtotal').textContent).toBe('180');
      expect(document.getElementById('total').textContent).toBe('209');
      expect(document.getElementById('line_count_display').textContent).toBe(
        '1',
      );
    });

    it('returns all zeros when no lines exist', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('0');
      expect(document.getElementById('total').textContent).toBe('0');
      expect(document.getElementById('line_count_display').textContent).toBe(
        '0',
      );
    });

    it('handles multiple lines correctly', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', price: '100', discount: '0' });
      addLineDOM(1, { qty: '3', price: '50', discount: '0' });
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('350');
      expect(document.getElementById('line_count_display').textContent).toBe(
        '2',
      );
    });

    it('skips lines where qty or price is zero', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '0', price: '100', discount: '0' });
      addLineDOM(1, { qty: '1', price: '50', discount: '0' });
      triggerCalc();
      await wait();
      expect(document.getElementById('line_count_display').textContent).toBe(
        '1',
      );
      expect(document.getElementById('subtotal').textContent).toBe('50');
    });

    it('applies line-level percentage discount', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '4', price: '25', discount: '20' });
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('80');
    });
  });

  /* ================================================================ */
  /* 28-29. updateCurrencyLabels                                        */
  /* ================================================================ */
  describe('updateCurrencyLabels', () => {
    it('updates all three labels on exchange_rate change', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '3.67';
      document.getElementById('exchange_rate')
        .dispatchEvent(new Event('change'));
      expect(document.getElementById('discount_currency').textContent).toBe(
        'USD',
      );
      expect(document.getElementById('shipping_currency').textContent).toBe(
        'USD',
      );
      expect(
        document.getElementById('total_currency_label').textContent,
      ).toBe('USD');
    });

    it('sets labels to AED for base currency', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      document.getElementById('currency').value = 'AED';
      document.getElementById('exchange_rate').value = '1.000000';
      document.getElementById('exchange_rate')
        .dispatchEvent(new Event('change'));
      expect(document.getElementById('discount_currency').textContent).toBe(
        'AED',
      );
    });
  });

  /* ================================================================ */
  /* 30-31. _clientSideFallback                                          */
  /* ================================================================ */
  describe('_clientSideFallback', () => {
    it('warns once on first server failure, not on second', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('fail'));
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', price: '100', discount: '0' });
      document
        .querySelector('[name="discount_amount"]')
        .dispatchEvent(new Event('change'));
      await wait();
      expect(window.azad.showWarning).toHaveBeenCalledTimes(1);

      window.azad.showWarning.mockClear();
      document
        .querySelector('[name="shipping_cost"]')
        .dispatchEvent(new Event('change'));
      await wait();
      expect(window.azad.showWarning).toHaveBeenCalledTimes(0);
    });
  });

  /* ================================================================ */
  /* 32-34. calculateTotals – server paths                               */
  /* ================================================================ */
  describe('calculateTotals – server success', () => {
    it('uses server result and updates DOM', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', price: '200', discount: '0' });
      globalThis.fetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            success: true,
            subtotal: 200,
            total: 220,
            discount: 0,
            shipping: 0,
            tax_amount: 20,
            line_count: 1,
          }),
      });
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('200');
      expect(document.getElementById('total').textContent).toBe('220');
      expect(document.getElementById('line_count_display').textContent).toBe(
        '1',
      );
    });
  });

  describe('calculateTotals – server failure', () => {
    it('falls back on success:false', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', price: '200', discount: '0' });
      globalThis.fetch = vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ success: false }),
      });
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('200');
    });

    it('falls back on network error', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', price: '200', discount: '0' });
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network'));
      triggerCalc();
      await wait();
      expect(document.getElementById('subtotal').textContent).toBe('200');
    });
  });

  /* ================================================================ */
  /* 35-36. updateLinePrices via exchange_rate change                     */
  /* ================================================================ */
  describe('updateLinePrices', () => {
    it('recalculates prices from base-price on rate change', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { price: '367' });
      document.getElementById('price_0')
        .setAttribute('data-base-price', '367');
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '3.67';
      document.getElementById('exchange_rate')
        .dispatchEvent(new Event('change'));
      expect(document.getElementById('price_0').value).toBe('100.00');
    });

    it('preserves price when base-price is absent', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { price: '55' });
      document.getElementById('price_0').removeAttribute('data-base-price');
      document.getElementById('currency').value = 'USD';
      document.getElementById('exchange_rate').value = '2.00';
      document.getElementById('exchange_rate')
        .dispatchEvent(new Event('change'));
      expect(document.getElementById('price_0').value).toBe('55');
    });
  });

  /* ================================================================ */
  /* 37-39. window.triggerSerialModal                                    */
  /* ================================================================ */
  describe('window.triggerSerialModal', () => {
    it('opens modal and displays product name', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      window.triggerSerialModal(0);
      expect(
        document.getElementById('serial_product_name').textContent,
      ).toBe('Widget');
      expect(
        document.getElementById('serial_quantity_needed').textContent,
      ).toBe('2');
    });

    it('returns early when data-needed is falsy', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '1', serialNeeded: false });
      window.triggerSerialModal(0);
      expect(
        document.getElementById('serial_product_name').textContent,
      ).toBe('');
    });

    it('syncs pre-existing hidden serials into store', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '2', serialNeeded: true });
      const line = document.getElementById('line_0');
      const h = document.createElement('input');
      h.type = 'hidden';
      h.name = 'lines[0][serials][]';
      h.value = 'EXISTING-SN';
      line.appendChild(h);
      window.triggerSerialModal(0);
      const items = document.querySelectorAll('#serial_list li');
      expect(items.length).toBe(1);
      expect(items[0].textContent).toContain('EXISTING-SN');
    });
  });

  /* ================================================================ */
  /* 40-42. window exposure                                             */
  /* ================================================================ */
  describe('window exposure', () => {
    it('exposes triggerSerialModal', async () => {
      await loadModule();
      expect(typeof window.triggerSerialModal).toBe('function');
    });

    it('exposes removeLine', async () => {
      await loadModule();
      expect(typeof window.removeLine).toBe('function');
    });

    it('exposes loadProductPrice', async () => {
      await loadModule();
      expect(typeof window.loadProductPrice).toBe('function');
    });
  });

  /* ================================================================ */
  /* 43-45. jQuery event handlers                                        */
  /* ================================================================ */
  describe('currency change handler', () => {
    it('sets rate to 1 for base currency AED', async () => {
      await loadModule();
      document.getElementById('currency').value = 'AED';
      document.getElementById('exchange_rate').value = '5.00';
      document.getElementById('currency')
        .dispatchEvent(new Event('change'));
      expect(document.getElementById('exchange_rate').value).toBe(
        '1.000000',
      );
    });
  });

  describe('payment_method change handler', () => {
    it('hides amount group when no method selected', async () => {
      await loadModule();
      document.getElementById('payment_method').value = '';
      document.getElementById('payment_method')
        .dispatchEvent(new Event('change'));
      expect(
        document.getElementById('payment_amount_group').style.display,
      ).toBe('none');
    });

    it('shows amount group when method is selected', async () => {
      await loadModule();
      document.getElementById('payment_method').value = 'cash';
      document.getElementById('payment_method')
        .dispatchEvent(new Event('change'));
      expect(
        document.getElementById('payment_amount_group').style.display,
      ).toBe('');
    });
  });

  /* ================================================================ */
  /* 47. calculateTotals payload                                         */
  /* ================================================================ */
  describe('calculateTotals – sends correct payload', () => {
    it('sends lines, discount, shipping, tax to server', async () => {
      await loadModule();
      removeAutoLine();
      addLineDOM(0, { qty: '3', price: '100', discount: '10' });
      document.querySelector('[name="discount_amount"]').value = '50';
      document.querySelector('[name="shipping_cost"]').value = '25';
      document.querySelector('[name="tax_rate"]').value = '15';

      globalThis.fetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            success: true,
            subtotal: 270,
            total: 286.5,
            discount: 50,
            shipping: 25,
            tax_amount: 41.5,
            line_count: 1,
          }),
      });

      document
        .querySelector('[name="tax_rate"]')
        .dispatchEvent(new Event('change'));
      await wait();

      expect(fetch).toHaveBeenCalled();
      const [url, opts] = fetch.mock.calls[0];
      expect(url).toBe('/sales/api/calculate-totals');
      expect(opts.method).toBe('POST');
      const body = JSON.parse(opts.body);
      expect(body.lines.length).toBe(1);
      expect(body.lines[0].quantity).toBe(3);
      expect(body.lines[0].unit_price).toBe(100);
      expect(body.lines[0].discount_percent).toBe(10);
      expect(body.discount_amount).toBe(50);
      expect(body.shipping_cost).toBe(25);
      expect(body.tax_rate).toBe(15);
    });
  });

  /* ================================================================ */
  /* 48-49. Module initialization                                        */
  /* ================================================================ */
  describe('module initialization', () => {
    it('adds one product line during import', async () => {
      await loadModule();
      const lines = document.querySelectorAll(
        '#linesContainer .product-line',
      );
      expect(lines.length).toBe(1);
    });

    it('increments line_count hidden input', async () => {
      await loadModule();
      expect(document.getElementById('line_count').value).toBe('1');
    });
  });
});
