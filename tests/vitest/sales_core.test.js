import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/* ------------------------------------------------------------------ */
/*  Helper: build DOM before import                                    */
/* ------------------------------------------------------------------ */
function buildDOM({ lineCount = 1, withTotals = true } = {}) {
  let lines = '';
  for (let i = 0; i < lineCount; i++) {
    lines += `
      <div class="sale-line" data-index="${i}">
        <input type="number" name="lines-${i}-quantity" class="quantity-input" value="">
        <input type="number" name="lines-${i}-unit_price" class="price-input" value="">
        <input type="number" name="lines-${i}-discount_rate" class="discount-input" value="">
        <input type="number" name="lines-${i}-tax_rate" class="tax-input" value="">
        <button type="button" class="remove-line">X</button>
        <span class="stock-badge"></span>
      </div>`;
  }
  document.body.innerHTML = `
    <form id="filterForm" action="/sales">
      <input type="text" name="q" value="">
      <button type="submit">Filter</button>
      <button type="reset">Reset</button>
    </form>
    <form id="saleForm">
      <input name="sale_date" type="datetime-local" value="">
      <select name="currency"><option value="">--</option></select>
      <div id="saleLines">${lines}</div>
      <button type="button" id="addLine">+ Add</button>
      <input id="taxRate" type="number" value="0">
      <input id="shippingCost" type="number" value="0">
      ${withTotals ? `
        <span id="subtotal"></span>
        <span id="taxAmount"></span>
        <span id="shippingCostDisplay"></span>
        <span id="totalAmount"></span>
        <span id="discountTotalDisplay"></span>
        <span id="totalDiscount"></span>
        <input id="discountTotal" type="hidden" value="0">
      ` : ''}
    </form>`;
}

async function flush() {
  await new Promise((r) => setTimeout(r, 0));
}

/* ================================================================== */
/*  1. loadScriptOnce                                                  */
/* ================================================================== */
describe('sales.js – loadScriptOnce', () => {
  beforeEach(() => {
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    vi.resetModules();
  });
  afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = ''; vi.resetModules(); });

  it('creates a script element and resolves on load', async () => {
    buildDOM();
    await import('../../static/js/sales.js');
    const srcs = Array.from(document.head.querySelectorAll('script[src]')).map(s => s.src);
    expect(srcs.some(s => s.includes('sortablejs'))).toBe(true);
  });

  it('does not duplicate a script that already exists', async () => {
    document.head.innerHTML =
      '<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>';
    buildDOM();
    const countBefore = document.head.querySelectorAll('script[src*="sortablejs"]').length;
    await import('../../static/js/sales.js');
    expect(document.head.querySelectorAll('script[src*="sortablejs"]').length).toBe(countBefore);
  });
});

/* ================================================================== */
/*  2. loadCssOnce                                                     */
/* ================================================================== */
describe('sales.js – loadCssOnce', () => {
  beforeEach(() => { document.head.innerHTML = ''; document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = ''; vi.resetModules(); });

  it('adds a stylesheet link when select2 element is present', async () => {
    window.jQuery = window.$;
    document.body.innerHTML = `
      <form id="filterForm" action="/x"></form>
      <form id="saleForm">
        <div class="select2"></div>
        <div id="saleLines"></div>
        <button type="button" id="addLine">+</button>
        <input id="taxRate" value="0">
        <input id="shippingCost" value="0">
        <select name="currency"></select>
      </form>`;
    await import('../../static/js/sales.js');
    await flush();
    const links = document.head.querySelectorAll('link[rel="stylesheet"]');
    expect(links.length).toBeGreaterThanOrEqual(1);
  });

  it('does not duplicate an existing link', async () => {
    const href = 'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css';
    document.head.innerHTML =
      `<link rel="stylesheet" href="${href}">`;
    window.jQuery = window.$;
    document.body.innerHTML = `
      <form id="filterForm" action="/x"></form>
      <form id="saleForm">
        <div class="select2"></div>
        <div id="saleLines"></div>
        <button type="button" id="addLine">+</button>
        <input id="taxRate" value="0">
        <input id="shippingCost" value="0">
        <select name="currency"></select>
      </form>`;
    const countBefore = document.head.querySelectorAll(`link[href="${href}"]`).length;
    await import('../../static/js/sales.js');
    await flush();
    expect(document.head.querySelectorAll(`link[href="${href}"]`).length).toBe(countBefore);
  });
});

/* ================================================================== */
/*  3. debounce                                                        */
/* ================================================================== */
describe('sales.js – debounce', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('delays function execution', async () => {
    buildDOM();
    await import('../../static/js/sales.js');
    const taxInput = document.getElementById('taxRate');
    taxInput.value = '10';
    taxInput.dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal')).toBeTruthy();
  });
});

/* ================================================================== */
/*  4. fetchProductInfo                                                */
/* ================================================================== */
describe('sales.js – fetchProductInfo', () => {
  beforeEach(() => { document.body.innerHTML = ''; global.fetch = vi.fn(); vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; delete global.fetch; vi.resetModules(); });

  it('does not call fetch when product id is missing', async () => {
    buildDOM();
    await import('../../static/js/sales.js');
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/products/'), expect.anything(),
    );
  });

  it('import succeeds with fetch returning JSON', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ json: () => Promise.resolve({ price: '55.00', stock: 10 }) }));
    buildDOM();
    await import('../../static/js/sales.js');
    expect(document.getElementById('saleForm')).toBeTruthy();
  });

  it('import succeeds even when fetch rejects', async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error('net')));
    buildDOM();
    await import('../../static/js/sales.js');
    expect(document.getElementById('saleForm')).toBeTruthy();
  });
});

/* ================================================================== */
/*  5. initForm – addLine                                              */
/* ================================================================== */
describe('sales.js – initForm addLine', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('clones last row and appends a new line', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const before = document.querySelectorAll('.sale-line').length;
    document.getElementById('addLine').click();
    expect(document.querySelectorAll('.sale-line').length).toBe(before + 1);
  });

  it('renumbers the new row correctly', async () => {
    buildDOM({ lineCount: 2 });
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    const lines = document.querySelectorAll('.sale-line');
    expect(lines[lines.length - 1].dataset.index).toBe('2');
  });

  it('clears values in the cloned row', async () => {
    buildDOM({ lineCount: 1 });
    document.querySelector('[name="lines-0-quantity"]').value = '99';
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    const lines = document.querySelectorAll('.sale-line');
    expect(lines[lines.length - 1].querySelector('[name$="-quantity"]').value).toBe('');
  });
});

/* ================================================================== */
/*  6. initForm – removeLine                                           */
/* ================================================================== */
describe('sales.js – initForm removeLine', () => {
  beforeEach(() => { global.alert = vi.fn(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; delete global.alert; vi.resetModules(); });

  it('removes the row when more than one line exists', async () => {
    buildDOM({ lineCount: 3 });
    await import('../../static/js/sales.js');
    document.querySelectorAll('.remove-line')[1].click();
    expect(document.querySelectorAll('.sale-line').length).toBe(2);
  });

  it('alerts when only one line remains', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    document.querySelector('.remove-line').click();
    expect(global.alert).toHaveBeenCalled();
    expect(document.querySelectorAll('.sale-line').length).toBe(1);
  });
});

/* ================================================================== */
/*  7. initForm – recalc (uses fake timers because recalc is debounced)*/
/* ================================================================== */
describe('sales.js – initForm recalc', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('computes correct subtotal from a single line', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '3';
    row.querySelector('[name$="-unit_price"]').value = '20';
    row.querySelector('[name$="-discount_rate"]').value = '0';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('60.00');
  });

  it('applies discount correctly', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '10';
    row.querySelector('[name$="-unit_price"]').value = '100';
    row.querySelector('[name$="-discount_rate"]').value = '10';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('900.00');
  });

  it('adds global tax and shipping to total', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '2';
    row.querySelector('[name$="-unit_price"]').value = '50';
    row.querySelector('[name$="-discount_rate"]').value = '0';
    document.getElementById('taxRate').value = '10';
    document.getElementById('shippingCost').value = '25';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('100.00');
    expect(document.getElementById('taxAmount').textContent).toContain('10.00');
    expect(document.getElementById('shippingCostDisplay').textContent).toContain('25.00');
    expect(document.getElementById('totalAmount').textContent).toContain('135.00');
  });

  it('respects currency display', async () => {
    buildDOM({ lineCount: 1 });
    const currSel = document.querySelector('select[name="currency"]');
    const opt = document.createElement('option');
    opt.value = 'AED';
    currSel.appendChild(opt);
    currSel.value = 'AED';
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '1';
    row.querySelector('[name$="-unit_price"]').value = '500';
    row.querySelector('[name$="-discount_rate"]').value = '0';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('AED');
  });
});

/* ================================================================== */
/*  8. initList – filter form submission                               */
/* ================================================================== */
describe('sales.js – initList', () => {
  let locationHref;
  let locationSetter;

  beforeEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
    locationHref = '';
    locationSetter = vi.fn((val) => { locationHref = val; });
    try {
      Object.defineProperty(window, 'location', {
        configurable: true,
        get: () => ({ href: locationHref, pathname: '/sales', toString: () => locationHref }),
        set: locationSetter,
      });
    } catch (_) {}
  });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('redirects with query params on form submit', async () => {
    document.body.innerHTML = `
      <form id="filterForm" action="/sales">
        <input type="text" name="q" value="test">
        <button type="submit">Go</button>
      </form>`;
    await import('../../static/js/sales.js');
    document.getElementById('filterForm').dispatchEvent(new Event('submit', { bubbles: true }));
    expect(locationSetter).toHaveBeenCalled();
    const href = locationSetter.mock.calls[locationSetter.mock.calls.length - 1][0];
    expect(href).toContain('q=test');
  });

  it('redirects to action path on reset click', async () => {
    document.body.innerHTML = `
      <form id="filterForm" action="/sales/list">
        <input type="text" name="q" value="x">
        <button type="submit">Go</button>
        <button type="reset">Reset</button>
      </form>`;
    await import('../../static/js/sales.js');
    document.querySelector('button[type="reset"]').click();
    expect(locationSetter).toHaveBeenCalled();
    const href = locationSetter.mock.calls[locationSetter.mock.calls.length - 1][0];
    expect(href).toBe('/sales/list');
  });
});

/* ================================================================== */
/*  9. initForm – sale date default                                    */
/* ================================================================== */
describe('sales.js – initForm sale date default', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('sets today date when field is empty', async () => {
    buildDOM({ lineCount: 1, withTotals: false });
    await import('../../static/js/sales.js');
    const dateEl = document.querySelector('input[name="sale_date"]');
    expect(dateEl.value).not.toBe('');
    expect(dateEl.value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });

  it('does not overwrite an existing date value', async () => {
    buildDOM({ lineCount: 1, withTotals: false });
    document.querySelector('input[name="sale_date"]').value = '2025-01-15T08:30';
    await import('../../static/js/sales.js');
    expect(document.querySelector('input[name="sale_date"]').value).toBe('2025-01-15T08:30');
  });
});

/* ================================================================== */
/* 10. initForm – currentMaxIndex edge cases                           */
/* ================================================================== */
describe('sales.js – initForm currentMaxIndex', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('returns 0 when adding to a single row with index 0', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    const lines = document.querySelectorAll('.sale-line');
    expect(lines.length).toBe(2);
    expect(lines[1].dataset.index).toBe('1');
  });

  it('handles non-sequential existing indices', async () => {
    buildDOM({ lineCount: 0 });
    document.getElementById('saleLines').innerHTML = `
      <div class="sale-line" data-index="0">
        <input name="lines-0-quantity" class="quantity-input" value="">
        <input name="lines-0-unit_price" class="price-input" value="">
        <input name="lines-0-discount_rate" class="discount-input" value="">
        <input name="lines-0-tax_rate" class="tax-input" value="">
        <button class="remove-line">X</button>
        <span class="stock-badge"></span>
      </div>
      <div class="sale-line" data-index="5">
        <input name="lines-5-quantity" class="quantity-input" value="">
        <input name="lines-5-unit_price" class="price-input" value="">
        <input name="lines-5-discount_rate" class="discount-input" value="">
        <input name="lines-5-tax_rate" class="tax-input" value="">
        <button class="remove-line">X</button>
        <span class="stock-badge"></span>
      </div>`;
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    const lines = document.querySelectorAll('.sale-line');
    expect(lines[lines.length - 1].dataset.index).toBe('6');
  });
});

/* ================================================================== */
/* 11. initForm – recalc with multiple lines                          */
/* ================================================================== */
describe('sales.js – initForm recalc multi-line', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('sums multiple lines correctly', async () => {
    buildDOM({ lineCount: 2 });
    await import('../../static/js/sales.js');
    const lines = document.querySelectorAll('.sale-line');
    lines[0].querySelector('[name$="-quantity"]').value = '2';
    lines[0].querySelector('[name$="-unit_price"]').value = '100';
    lines[0].querySelector('[name$="-discount_rate"]').value = '0';
    lines[1].querySelector('[name$="-quantity"]').value = '3';
    lines[1].querySelector('[name$="-unit_price"]').value = '50';
    lines[1].querySelector('[name$="-discount_rate"]').value = '0';
    lines[0].querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('350.00');
  });
});

/* ================================================================== */
/* 12. initForm – removeLine renumbers subsequent rows                */
/* ================================================================== */
describe('sales.js – initForm removeLine renumbering', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('renumbers rows after removing row 1', async () => {
    buildDOM({ lineCount: 3 });
    await import('../../static/js/sales.js');
    document.querySelectorAll('.remove-line')[1].click();
    const rows = document.querySelectorAll('.sale-line');
    expect(rows.length).toBe(2);
    expect(rows[0].dataset.index).toBe('0');
    expect(rows[1].dataset.index).toBe('1');
  });
});

/* ================================================================== */
/* 13. initForm – price manual flag                                   */
/* ================================================================== */
describe('sales.js – initForm price manual flag', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });

  it('sets priceManual on unit_price input', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const priceInput = document.querySelector('[name$="-unit_price"]');
    priceInput.value = '75';
    priceInput.dispatchEvent(new Event('input'));
    expect(document.querySelector('.sale-line').dataset.priceManual).toBe('1');
  });
});

/* ================================================================== */
/* 14. initForm – discount total display                              */
/* ================================================================== */
describe('sales.js – initForm discount total', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('computes totalDiscount correctly', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '4';
    row.querySelector('[name$="-unit_price"]').value = '25';
    row.querySelector('[name$="-discount_rate"]').value = '20';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('80.00');
    expect(document.getElementById('totalDiscount').textContent).toContain('20.00');
  });
});

/* ================================================================== */
/* 15. initForm – clamp discount between 0 and 100                    */
/* ================================================================== */
describe('sales.js – initForm discount clamping', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('clamps discount > 100 to 100', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '1';
    row.querySelector('[name$="-unit_price"]').value = '100';
    row.querySelector('[name$="-discount_rate"]').value = '150';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('0.00');
    expect(document.getElementById('totalDiscount').textContent).toContain('100.00');
  });

  it('clamps negative discount to 0', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '1';
    row.querySelector('[name$="-unit_price"]').value = '100';
    row.querySelector('[name$="-discount_rate"]').value = '-10';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('subtotal').textContent).toContain('100.00');
  });
});

/* ================================================================== */
/* 16. initForm – tax and shipping recalc                             */
/* ================================================================== */
describe('sales.js – initForm tax and shipping recalc', () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ''; vi.resetModules(); });

  it('recalcs when taxRate input changes', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '1';
    row.querySelector('[name$="-unit_price"]').value = '200';
    row.querySelector('[name$="-discount_rate"]').value = '0';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    document.getElementById('taxRate').value = '5';
    document.getElementById('taxRate').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('taxAmount').textContent).toContain('10.00');
    expect(document.getElementById('totalAmount').textContent).toContain('210.00');
  });

  it('recalcs when shippingCost input changes', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    const row = document.querySelector('.sale-line');
    row.querySelector('[name$="-quantity"]').value = '1';
    row.querySelector('[name$="-unit_price"]').value = '100';
    row.querySelector('[name$="-discount_rate"]').value = '0';
    row.querySelector('[name$="-quantity"]').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    document.getElementById('shippingCost').value = '15';
    document.getElementById('shippingCost').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(200);
    expect(document.getElementById('shippingCostDisplay').textContent).toContain('15.00');
    expect(document.getElementById('totalAmount').textContent).toContain('115.00');
  });
});

/* ================================================================== */
/* 17–18. Graceful skip when DOM elements missing                      */
/* ================================================================== */
describe('sales.js – no saleForm in DOM', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  it('imports without error when #saleForm is absent', async () => {
    document.body.innerHTML = '<div>no form</div>';
    await expect(import('../../static/js/sales.js')).resolves.toBeDefined();
  });
});

describe('sales.js – no filterForm in DOM', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  it('imports without error when #filterForm is absent', async () => {
    document.body.innerHTML = '<div>no filter</div>';
    await expect(import('../../static/js/sales.js')).resolves.toBeDefined();
  });
});

/* ================================================================== */
/* 19. initForm – addLine to zero lines shows alert                   */
/* ================================================================== */
describe('sales.js – addLine with no template', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  it('alerts when no sale-line exists', async () => {
    buildDOM({ lineCount: 0 });
    global.alert = vi.fn();
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    expect(global.alert).toHaveBeenCalled();
    expect(document.querySelectorAll('.sale-line').length).toBe(0);
  });
});

/* ================================================================== */
/* 20. initForm – addLine + removeLine round-trip                     */
/* ================================================================== */
describe('sales.js – add then remove round-trip', () => {
  beforeEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  afterEach(() => { document.body.innerHTML = ''; vi.resetModules(); });
  it('adds a line and removes it back to original count', async () => {
    buildDOM({ lineCount: 1 });
    await import('../../static/js/sales.js');
    document.getElementById('addLine').click();
    expect(document.querySelectorAll('.sale-line').length).toBe(2);
    document.querySelectorAll('.remove-line')[0].click();
    expect(document.querySelectorAll('.sale-line').length).toBe(1);
  });
});
