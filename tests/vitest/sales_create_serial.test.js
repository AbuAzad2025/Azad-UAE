import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let modalCalls;

function buildJQuery() {
  function wrapEls(els) {
    const inst = {
      length: els.length,
      0: els[0] || null,
      on(event, selectorOrHandler, maybeHandler) {
        if (typeof selectorOrHandler === 'function') {
          els.forEach(el => el.addEventListener(event, selectorOrHandler));
        } else {
          const selector = selectorOrHandler;
          const handler = maybeHandler;
          els.forEach(el => {
            el.addEventListener(event, (e) => {
              let target = e.target;
              while (target && target !== el) {
                if (target.matches(selector)) {
                  handler.call(target, e);
                  return;
                }
                target = target.parentElement;
              }
            });
          });
        }
        return inst;
      },
      off() { return inst; },
      trigger() { return inst; },
      each(fn) { els.forEach((el, i) => fn.call(el, i, el)); return inst; },
      append(html) { els.forEach(el => el.insertAdjacentHTML('beforeend', html)); return inst; },
      empty() { els.forEach(el => { el.innerHTML = ''; }); return inst; },
      remove() { els.forEach(el => el.remove()); return inst; },
      closest(selector) {
        const found = [];
        els.forEach(el => { const p = el.closest(selector); if (p && !found.includes(p)) found.push(p); });
        return wrapEls(found);
      },
      find(selector) {
        const found = [];
        els.forEach(el => found.push(...el.querySelectorAll(selector)));
        return wrapEls(found);
      },
      val(v) {
        if (v !== undefined) { els.forEach(el => { if ('value' in el) el.value = String(v); }); return inst; }
        return els[0]?.value ?? '';
      },
      text(v) {
        if (v !== undefined) { els.forEach(el => { el.textContent = String(v); }); return inst; }
        return els[0]?.textContent ?? '';
      },
      modal(action) { modalCalls.push({ id: els[0]?.id, action }); return inst; },
    };
    return inst;
  }

  const $ = (sel) => {
    if (typeof sel === 'function') { sel(); return wrapEls([]); }
    if (typeof sel === 'string') return wrapEls(Array.from(document.querySelectorAll(sel)));
    if (sel === document) {
      const inst = wrapEls([]);
      inst.ready = (fn) => { if (typeof fn === 'function') fn(); return inst; };
      return inst;
    }
    if (sel instanceof Element || (sel && sel.nodeType)) return wrapEls([sel]);
    return wrapEls([]);
  };

  $.fn = {};
  return $;
}

function setupDOM(withContainer = true) {
  let html = '';
  if (withContainer) html += '<div id="serials_input_container"></div>';
  html += `
    <input type="hidden" id="product_id" value="">
    <input type="hidden" id="product_name" value="">
    <input type="hidden" id="serial_line_index" value="0">
    <input type="hidden" id="quantity" value="1">
    <div id="serials_count">0</div>
    <div id="serialModal"></div>
    <button id="add_serial_btn"></button>
    <button id="generate_serial_btn"></button>
    <button id="print_serials_btn"></button>
    <button id="save_serials_btn"></button>
  `;
  document.body.innerHTML = html;
}

async function loadModule() {
  const $ = buildJQuery();
  global.$ = $;
  window.$ = $;
  window.alert = vi.fn();
  modalCalls = [];
  await import('../../static/js/sales-create.js');
}

function addSerials(productId, quantity) {
  document.getElementById('product_id').value = productId;
  document.getElementById('quantity').value = quantity;
  document.getElementById('add_serial_btn').click();
}

function fillFirstInput(value) {
  const input = document.querySelector('.serial-input');
  if (input) input.value = value;
}

describe('sales-create.js', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  describe('module bail-out', () => {
    it('bails when #serials_input_container is missing', async () => {
      setupDOM(false);
      await loadModule();
      document.getElementById('add_serial_btn').click();
      expect(window.alert).not.toHaveBeenCalled();
    });

    it('does not attach any event handlers when container is absent', async () => {
      setupDOM(false);
      await loadModule();
      document.getElementById('generate_serial_btn').click();
      document.getElementById('print_serials_btn').click();
      document.getElementById('save_serials_btn').click();
      expect(window.alert).not.toHaveBeenCalled();
    });
  });

  describe('serial number format', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('produces YYYYMMDD-XXXX format', () => {
      document.getElementById('product_id').value = '';
      const container = document.getElementById('serials_input_container');
      container.insertAdjacentHTML('beforeend', `
        <div class="input-group mb-2 serial-row" data-serial-index="10">
          <input type="text" class="form-control form-control-sm serial-input" placeholder="أدخل الرقم التسلسلي" required>
          <div class="input-group-append">
            <button type="button" class="btn btn-success btn-sm generate-serial-btn"></button>
          </div>
        </div>
      `);
      document.querySelector('.generate-serial-btn').click();
      const val = document.querySelector('.serial-input').value;
      const datePart = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      expect(val).toMatch(new RegExp(`^${datePart}-[A-Z0-9]{4}$`));
    });

    it('includes product ID suffix', () => {
      addSerials('ABC123', '1');
      document.querySelector('.generate-serial-btn').click();
      expect(document.querySelector('.serial-input').value).toMatch(/-ABC123$/);
    });

    it('omits product ID suffix when product is empty', () => {
      const container = document.getElementById('serials_input_container');
      container.insertAdjacentHTML('beforeend', `
        <div class="input-group mb-2 serial-row" data-serial-index="999">
          <input type="text" class="form-control form-control-sm serial-input" placeholder="أدخل الرقم التسلسلي" required>
          <div class="input-group-append">
            <button type="button" class="btn btn-success btn-sm generate-serial-btn"></button>
          </div>
        </div>
      `);
      document.getElementById('product_id').value = '';
      document.querySelector('.generate-serial-btn').click();
      const val = document.querySelector('.serial-input').value;
      const datePart = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      expect(val).toMatch(new RegExp(`^${datePart}-[A-Z0-9]{4}$`));
      expect(val.split('-')).toHaveLength(2);
    });

    it('generates unique values on successive calls', () => {
      addSerials('P1', '2');
      const btns = document.querySelectorAll('.generate-serial-btn');
      btns[0].click();
      btns[1].click();
      const inputs = document.querySelectorAll('.serial-input');
      expect(inputs[0].value).not.toBe(inputs[1].value);
    });
  });

  describe('addSerialInput (via add_serial_btn)', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('creates the right number of rows', () => {
      addSerials('P1', '3');
      expect(document.querySelectorAll('.serial-row').length).toBe(3);
    });

    it('updates count display', () => {
      addSerials('P1', '5');
      expect(document.getElementById('serials_count').textContent).toBe('5');
    });

    it('defaults to 1 row when quantity is not a number', () => {
      addSerials('P1', 'abc');
      expect(document.querySelectorAll('.serial-row').length).toBe(1);
    });

    it('creates rows with generate and remove buttons', () => {
      addSerials('P1', '1');
      expect(document.querySelector('.generate-serial-btn')).not.toBeNull();
      expect(document.querySelector('.remove-serial-btn')).not.toBeNull();
    });
  });

  describe('generateSerials', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('empties container then adds count inputs', () => {
      const container = document.getElementById('serials_input_container');
      container.insertAdjacentHTML('beforeend', '<div class="serial-row" data-serial-index="old"></div>');
      container.insertAdjacentHTML('beforeend', '<div class="serial-row" data-serial-index="old2"></div>');
      expect(document.querySelectorAll('.serial-row').length).toBe(2);
      addSerials('P1', '3');
      expect(document.querySelectorAll('.serial-row').length).toBe(3);
    });
  });

  describe('updateSerialsCount', () => {
    it('shows correct count after adding serials', async () => {
      setupDOM(true);
      await loadModule();
      addSerials('P1', '4');
      expect(document.getElementById('serials_count').textContent).toBe('4');
    });

    it('updates count after removing a row', async () => {
      setupDOM(true);
      await loadModule();
      addSerials('P1', '3');
      document.querySelector('.remove-serial-btn').click();
      expect(document.getElementById('serials_count').textContent).toBe('2');
    });
  });

  describe('.generate-serial-btn click', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('fills input with generated serial', () => {
      addSerials('P1', '1');
      document.querySelector('.generate-serial-btn').click();
      expect(document.querySelector('.serial-input').value).not.toBe('');
    });
  });

  describe('.remove-serial-btn click', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('removes row when more than 1', () => {
      addSerials('P1', '3');
      expect(document.querySelectorAll('.serial-row').length).toBe(3);
      document.querySelector('.remove-serial-btn').click();
      expect(document.querySelectorAll('.serial-row').length).toBe(2);
    });

    it('clears input when only 1 row remains', () => {
      addSerials('P1', '1');
      fillFirstInput('TEST-SERIAL');
      document.querySelector('.remove-serial-btn').click();
      expect(document.querySelector('.serial-input').value).toBe('');
      expect(document.querySelectorAll('.serial-row').length).toBe(1);
    });
  });

  describe('#add_serial_btn', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('alerts when no product_id', () => {
      document.getElementById('product_id').value = '';
      document.getElementById('add_serial_btn').click();
      expect(window.alert).toHaveBeenCalledWith('يرجى اختيار منتج أولاً');
    });

    it('generates serials and shows modal when product selected', () => {
      addSerials('P1', '2');
      expect(window.alert).not.toHaveBeenCalled();
      expect(document.querySelectorAll('.serial-input').length).toBe(2);
      expect(modalCalls).toEqual(
        expect.arrayContaining([expect.objectContaining({ action: 'show' })]),
      );
    });
  });

  describe('#generate_serial_btn', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('fills empty inputs only', () => {
      addSerials('P1', '3');
      const inputs = document.querySelectorAll('.serial-input');
      inputs[0].value = 'EXISTING-SERIAL';
      document.getElementById('generate_serial_btn').click();
      expect(inputs[0].value).toBe('EXISTING-SERIAL');
      expect(inputs[1].value).not.toBe('');
      expect(inputs[2].value).not.toBe('');
    });

    it('fills all inputs when all are empty', () => {
      addSerials('P1', '2');
      document.getElementById('generate_serial_btn').click();
      const inputs = document.querySelectorAll('.serial-input');
      expect(inputs[0].value).not.toBe('');
      expect(inputs[1].value).not.toBe('');
    });
  });

  describe('#print_serials_btn', () => {
    beforeEach(async () => {
      setupDOM(true);
      await loadModule();
    });

    it('alerts when no serials', () => {
      addSerials('P1', '1');
      document.getElementById('print_serials_btn').click();
      expect(window.alert).toHaveBeenCalledWith('لا توجد أرقام تسلسلية للطباعة');
    });

    it('opens print window with serials', () => {
      addSerials('P1', '2');
      document.querySelectorAll('.generate-serial-btn').forEach(btn => btn.click());

      const mockPrint = vi.fn();
      const mockDoc = { open: vi.fn(), write: vi.fn(), close: vi.fn() };
      window.open = vi.fn(() => ({ document: mockDoc, print: mockPrint }));

      document.getElementById('print_serials_btn').click();
      expect(window.open).toHaveBeenCalled();
      expect(mockDoc.write).toHaveBeenCalled();
      expect(mockPrint).toHaveBeenCalled();
    });

    it('writes serial values into print document', () => {
      addSerials('P1', '1');
      document.querySelector('.generate-serial-btn').click();
      const serialVal = document.querySelector('.serial-input').value;

      const mockPrint = vi.fn();
      const mockDoc = { open: vi.fn(), write: vi.fn(), close: vi.fn() };
      window.open = vi.fn(() => ({ document: mockDoc, print: mockPrint }));

      document.getElementById('print_serials_btn').click();
      const written = mockDoc.write.mock.calls.map(c => c[0]).join('');
      expect(written).toContain(serialVal);
    });
  });

  describe('#save_serials_btn', () => {
    it('hides modal', async () => {
      setupDOM(true);
      await loadModule();
      document.getElementById('save_serials_btn').click();
      expect(modalCalls).toEqual(
        expect.arrayContaining([expect.objectContaining({ action: 'hide' })]),
      );
    });
  });
});
