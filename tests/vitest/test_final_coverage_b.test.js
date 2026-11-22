import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Hoisted, shared fakes.  toolkit.js imports four sibling POS modules; we mock
// them at the boundary so every branch in toolkit.js itself is reachable and
// assertable without booting the real cart/ui/payment machinery.
// ---------------------------------------------------------------------------
const m = vi.hoisted(() => ({
  fetchJson: vi.fn(),
  showAlert: vi.fn(),
  recalc: vi.fn(),
  requestOverrideToken: vi.fn(),
  modalFn: vi.fn(),
  fetch: vi.fn(),
  state: { lastTotals: null, customerDisplayUrl: null, sessionToken: null },
}));

vi.mock('../../static/js/pos/core.js', () => ({
  csrf: 'csrf-test-token',
  esc: (s) => (s == null ? '' : String(s)),
  fetchJson: (...a) => m.fetchJson(...a),
  fmt: (n) => Number(n || 0).toFixed(2),
  qs: (s) => document.querySelector(s),
  qsa: (s) => Array.from(document.querySelectorAll(s)),
  selectedCurrency: () => document.querySelector('#currency')?.value || 'USD',
  sessionHeaders: () =>
    m.state.sessionToken ? { 'X-POS-Session-Token': m.state.sessionToken } : {},
  state: m.state,
  toNum: (v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  },
}));
vi.mock('../../static/js/pos/cart.js', () => ({ recalc: (...a) => m.recalc(...a) }));
vi.mock('../../static/js/pos/payments.js', () => ({
  requestOverrideToken: (...a) => m.requestOverrideToken(...a),
}));
vi.mock('../../static/js/pos/ui.js', () => ({
  showAlert: (...a) => m.showAlert(...a),
}));

import * as toolkit from '../../static/js/pos/toolkit.js';

// These classic scripts are ALSO loaded with CommonJS `require()` by
// tests/frontend/*.test.js. V8 keys script instances by URL, so an ESM import
// and a CJS require of the same file are two different instances; when both
// are present the reporter merges their per-statement counts by statement id
// and the ESM-only statements are attributed to the CJS instance (where they
// are zero). Load the modules through the SAME CommonJS path as the frontend
// suite so every statement we exercise below lands on the instance that is
// actually reported.
let parseScaleFrame;
let PosScaleSerial;
let buildReceiptBytes;
let EscposPrinter;

function loadPosModules() {
  // Keep the CommonJS instance cached: a single instance shared with the
  // frontend suite is what the V8 reporter merges into the final report.
  // (Busting the cache here creates hundreds of instances and the merge
  // starts dropping statements.)
  vi.resetModules();
  const scale = require('../../static/js/pos/scale-serial.js');
  parseScaleFrame = scale.parseScaleFrame;
  PosScaleSerial = scale.PosScaleSerial;
  const printer = require('../../static/js/pos/escpos-printer.js');
  buildReceiptBytes = printer.buildReceiptBytes;
  EscposPrinter = printer.EscposPrinter;
}

const nativeFetch = globalThis.fetch;

const jsonResponse = (status, ok, body, jsonReject = false) => ({
  status,
  ok,
  json: jsonReject
    ? vi.fn(() => Promise.reject(new Error('bad json')))
    : vi.fn(() => Promise.resolve(body)),
});

const FULL_DOM = `
  <meta name="csrf-token" content="csrf-test-token">
  <input id="currency" value="USD">
  <div id="sessionReportBody"></div>
  <div id="cashMovementsList"></div>
  <div id="cashMovementAlert" class="d-none"></div>
  <input id="cashMovementAmount" value="0">
  <textarea id="cashMovementReason"></textarea>
  <select id="cashMovementType">
    <option value="pay_in">pay_in</option>
    <option value="pay_out">pay_out</option>
  </select>
  <div id="returnAlert" class="d-none"></div>
  <input id="returnReceiptNumber" value="">
  <div id="returnReceiptInfo" class="d-none"></div>
  <div id="returnLines"></div>
  <select id="returnRefundMethod"><option value="cash">cash</option></select>
  <textarea id="returnNotes"></textarea>
  <div id="stockLookupAlert" class="d-none"></div>
  <div id="stockLookupResult"></div>
  <input id="stockLookupQuery" value="">
  <div id="posFastCash"></div>
  <input id="paidAmount" value="">
  <div id="hardwareStatusBadge"></div>
  <button id="customerDisplayBtn"></button>
  <button id="sessionReportBtn"></button>
  <button id="cashMovementBtn"></button>
  <button id="cashMovementSave"></button>
  <button id="returnsBtn"></button>
  <button id="returnLookupBtn"></button>
  <button id="returnSubmitBtn"></button>
  <button id="stockLookupBtn"></button>
  <button id="stockLookupGo"></button>
`;

beforeEach(() => {
  loadPosModules();
  document.body.innerHTML = FULL_DOM;
  window.POS_CONFIG = {};
  m.state.lastTotals = null;
  m.state.customerDisplayUrl = null;
  m.state.sessionToken = null;
  m.modalFn.mockReset();
  m.fetchJson.mockReset();
  m.fetchJson.mockResolvedValue({ ok: false, error: 'offline' });
  m.showAlert.mockReset();
  m.recalc.mockReset();
  m.requestOverrideToken.mockReset();
  m.requestOverrideToken.mockResolvedValue(null);
  m.fetch.mockReset();
  m.fetch.mockResolvedValue(jsonResponse(200, true, { success: true }));
  globalThis.fetch = m.fetch;
  window.$ = vi.fn(() => ({ modal: m.modalFn }));
  vi.spyOn(window, 'setInterval').mockImplementation(() => 0);
  vi.spyOn(window, 'open').mockImplementation(() => null);
});

afterEach(() => {
  document.body.innerHTML = '';
  globalThis.fetch = nativeFetch;
  delete navigator.serial;
  delete navigator.usb;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ===========================================================================
// toolkit.js — session report
// ===========================================================================
describe('toolkit: openSessionReport', () => {
  it('returns early when the body element is absent', async () => {
    document.getElementById('sessionReportBody').remove();
    await toolkit.openSessionReport();
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('renders an info alert when no session is returned', async () => {
    m.fetchJson.mockResolvedValue({ ok: false, error: 'no open session' });
    await toolkit.openSessionReport();
    const html = document.getElementById('sessionReportBody').innerHTML;
    expect(html).toContain('alert-info');
    expect(html).toContain('no open session');
    expect(m.modalFn).not.toHaveBeenCalled();
  });

  it('falls back to the default "no session" message', async () => {
    m.fetchJson.mockResolvedValue({ ok: false });
    await toolkit.openSessionReport();
    expect(document.getElementById('sessionReportBody').innerHTML).toContain('لا توجد جلسة مفتوحة');
  });

  it('renders the full report including closing/difference and notes', async () => {
    const session = {
      number: 'S-1',
      status: 'open',
      opening_balance: 100,
      duration_minutes: 30,
      branch_id: 2,
      expected_balance: 50,
      total_sales: 10,
      total_cash_sales: 5,
      total_card_sales: 5,
      total_change_given: 1,
      total_pay_ins: 2,
      total_pay_outs: 3,
      closing_balance: 49,
      difference: -1,
      notes: 'hello-note',
    };
    m.fetchJson.mockResolvedValue({ ok: true, data: { session } });
    await toolkit.openSessionReport();
    const html = document.getElementById('sessionReportBody').innerHTML;
    expect(html).toContain('S-1');
    expect(html).toContain('مفتوحة');
    expect(html).toContain('50.00');
    expect(html).toContain('49.00');
    expect(html).toContain('-1.00');
    expect(html).toContain('hello-note');
    expect(m.modalFn).toHaveBeenCalledWith('show');
  });

  it('skips the expected/closing block and notes when absent', async () => {
    const session = { number: 'S-2', status: 'closed', opening_balance: 0, notes: '' };
    m.fetchJson.mockResolvedValue({ ok: true, data: { session } });
    await toolkit.openSessionReport();
    const html = document.getElementById('sessionReportBody').innerHTML;
    expect(html).toContain('S-2');
    expect(html).toContain('مغلقة');
    expect(html).not.toContain('الرصيد المتوقع');
    expect(html).not.toContain('الرصيد المعدود');
  });

  it('tolerates a missing jQuery modal helper', async () => {
    m.fetchJson.mockResolvedValue({ ok: true, data: { session: { number: 'S-3' } } });
    window.$ = null;
    await expect(toolkit.openSessionReport()).resolves.toBeUndefined();
    expect(document.getElementById('sessionReportBody').innerHTML).toContain('S-3');
  });
});

// ===========================================================================
// toolkit.js — drawer cash movements
// ===========================================================================
describe('toolkit: cash movements', () => {
  it('loadCashMovements returns early without a list element', async () => {
    document.getElementById('cashMovementsList').remove();
    await toolkit.loadCashMovements();
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('loadCashMovements shows the server error', async () => {
    m.fetchJson.mockResolvedValue({ ok: false, error: 'boom' });
    await toolkit.loadCashMovements();
    expect(document.getElementById('cashMovementsList').innerHTML).toContain('boom');
  });

  it('loadCashMovements shows the empty message', async () => {
    m.fetchJson.mockResolvedValue({ ok: true, data: {} });
    await toolkit.loadCashMovements();
    expect(document.getElementById('cashMovementsList').innerHTML).toContain('لا توجد حركات بعد');
  });

  it('loadCashMovements renders pay-ins and pay-outs', async () => {
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        movements: [
          { movement_type: 'pay_in', amount: 10, reason: 'deposit' },
          { type: 'pay_out', amount: 5, created_at: '2026-01-01' },
        ],
      },
    });
    await toolkit.loadCashMovements();
    const html = document.getElementById('cashMovementsList').innerHTML;
    expect(html).toContain('pos-in');
    expect(html).toContain('pos-out');
    expect(html).toContain('10.00');
    expect(html).toContain('5.00');
    expect(html).toContain('deposit');
    expect(html).toContain('2026-01-01');
  });

  it('openCashMovements resets the form, loads rows and opens the modal', async () => {
    document.getElementById('cashMovementAmount').value = '999';
    document.getElementById('cashMovementReason').value = 'stale';
    m.fetchJson.mockResolvedValue({ ok: true, data: {} });
    await toolkit.openCashMovements();
    expect(document.getElementById('cashMovementAmount').value).toBe('0');
    expect(document.getElementById('cashMovementReason').value).toBe('');
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/cash-movements?limit=8');
    expect(m.modalFn).toHaveBeenCalledWith('show');
  });

  it('saveCashMovement refuses a non-positive amount', async () => {
    await toolkit.saveCashMovement();
    const el = document.getElementById('cashMovementAlert');
    expect(el.textContent).toContain('أدخل مبلغاً صحيحاً');
    expect(el.classList.contains('alert-warning')).toBe(true);
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('saveCashMovement posts and resets on success', async () => {
    document.getElementById('cashMovementAmount').value = '10';
    document.getElementById('cashMovementReason').value = '  sale  ';
    document.getElementById('cashMovementType').value = 'pay_in';
    m.state.sessionToken = 'STOK';
    m.fetch.mockResolvedValue(jsonResponse(200, true, { success: true }));
    m.fetchJson.mockResolvedValue({ ok: true, data: {} });
    await toolkit.saveCashMovement();
    expect(m.fetch).toHaveBeenCalledTimes(1);
    const [url, opts] = m.fetch.mock.calls[0];
    expect(url).toBe('/pos/api/cash-movements');
    expect(opts.headers['X-CSRFToken']).toBe('csrf-test-token');
    expect(opts.headers['X-POS-Session-Token']).toBe('STOK');
    expect(JSON.parse(opts.body)).toEqual({ type: 'pay_in', amount: 10, reason: 'sale' });
    expect(m.showAlert).toHaveBeenCalledWith('تم تسجيل الحركة', 'success');
    expect(document.getElementById('cashMovementAmount').value).toBe('0');
    expect(document.getElementById('cashMovementReason').value).toBe('');
  });

  it('saveCashMovement renders a failed post with message/error/default fallbacks', async () => {
    document.getElementById('cashMovementAmount').value = '10';
    m.fetch.mockResolvedValue(jsonResponse(400, false, { success: false, message: 'message-err' }));
    await toolkit.saveCashMovement();
    expect(document.getElementById('cashMovementAlert').textContent).toBe('message-err');

    m.fetch.mockResolvedValue(jsonResponse(400, false, { success: false, error: 'error-err' }));
    await toolkit.saveCashMovement();
    expect(document.getElementById('cashMovementAlert').textContent).toBe('error-err');

    m.fetch.mockResolvedValue(jsonResponse(400, false, {}, true)); // json() rejects -> {}
    await toolkit.saveCashMovement();
    expect(document.getElementById('cashMovementAlert').textContent).toBe('تعذر تسجيل الحركة');
  });

  it('retries once with an override token after a 403', async () => {
    document.getElementById('cashMovementAmount').value = '10';
    m.fetch
      .mockResolvedValueOnce(jsonResponse(403, false, {}))
      .mockResolvedValueOnce(jsonResponse(200, true, { success: true }));
    m.requestOverrideToken.mockResolvedValue('tok-123');
    m.fetchJson.mockResolvedValue({ ok: true, data: {} });
    await toolkit.saveCashMovement();
    expect(m.requestOverrideToken).toHaveBeenCalledWith('pay_in');
    expect(m.fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(m.fetch.mock.calls[1][1].body)).toMatchObject({
      override_token: 'tok-123',
    });
    expect(m.showAlert).toHaveBeenCalledWith('تم تسجيل الحركة', 'success');
  });

  it('does not retry a 403 when no override token is granted', async () => {
    document.getElementById('cashMovementAmount').value = '10';
    m.fetch.mockResolvedValue(jsonResponse(403, false, {}));
    m.requestOverrideToken.mockResolvedValue(null);
    await toolkit.saveCashMovement();
    expect(m.fetch).toHaveBeenCalledTimes(1);
    expect(document.getElementById('cashMovementAlert').textContent).toBe('تعذر تسجيل الحركة');
  });
});

// ===========================================================================
// toolkit.js — returns
// ===========================================================================
describe('toolkit: returns', () => {
  it('openReturns clears prior state and opens the modal', () => {
    document.getElementById('returnReceiptNumber').value = 'stale';
    document.getElementById('returnReceiptInfo').classList.remove('d-none');
    document.getElementById('returnLines').innerHTML = '<p>x</p>';
    toolkit.openReturns();
    expect(document.getElementById('returnReceiptNumber').value).toBe('');
    expect(document.getElementById('returnReceiptInfo').classList.contains('d-none')).toBe(true);
    expect(document.getElementById('returnLines').innerHTML).toBe('');
    expect(m.modalFn).toHaveBeenCalledWith('show');
  });

  it('lookupReceipt warns on an empty number', async () => {
    await toolkit.lookupReceipt();
    expect(document.getElementById('returnAlert').textContent).toContain('أدخل رقم الإيصال');
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('lookupReceipt clears state when the receipt is missing', async () => {
    document.getElementById('returnReceiptNumber').value = 'NOPE';
    m.fetchJson.mockResolvedValue({ ok: false, error: 'not found' });
    await toolkit.lookupReceipt();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/receipts/lookup?number=NOPE');
    expect(document.getElementById('returnAlert').textContent).toBe('not found');
    expect(document.getElementById('returnLines').innerHTML).toBe('');
    await toolkit.submitReturn();
    expect(document.getElementById('returnAlert').textContent).toContain('ابحث عن الإيصال أولاً');
  });

  it('lookupReceipt renders returnable lines only', async () => {
    document.getElementById('returnReceiptNumber').value = 'INV-7';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        receipt: {
          sale_id: 7,
          sale_number: 'INV-7',
          customer_name: 'Cust',
          total_amount: 99,
          currency: 'USD',
          lines: [
            {
              sale_line_id: 11,
              product_name: 'Apple',
              quantity_sold: 3,
              quantity_returnable: 2,
              unit_price: 10,
            },
            {
              sale_line_id: 12,
              sku: 'BETA',
              quantity_sold: 1,
              quantity_returnable: 0,
              unit_price: 5,
            },
          ],
        },
      },
    });
    await toolkit.lookupReceipt();
    const info = document.getElementById('returnReceiptInfo');
    expect(info.classList.contains('d-none')).toBe(false);
    expect(info.innerHTML).toContain('INV-7');
    expect(info.innerHTML).toContain('Cust');
    expect(info.innerHTML).toContain('99.00');
    const lines = document.getElementById('returnLines').innerHTML;
    expect(lines).toContain('Apple');
    expect(lines).toContain('data-line="11"');
    expect(lines).not.toContain('data-line="12"');
  });

  it('submitReturn refuses when no line has a positive quantity', async () => {
    document.getElementById('returnReceiptNumber').value = 'INV-7';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: { receipt: { sale_id: 7, sale_number: 'INV-7', lines: [{ sale_line_id: 11, product_name: 'Apple', quantity_sold: 1, quantity_returnable: 2 }] } },
    });
    await toolkit.lookupReceipt();
    document.querySelector('#returnLines .rl-qty').value = '0';
    await toolkit.submitReturn();
    expect(document.getElementById('returnAlert').textContent).toContain('حدد أصنافاً للإرجاع');
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('submitReturn posts the selected lines and refreshes on success', async () => {
    document.getElementById('returnReceiptNumber').value = 'INV-7';
    m.fetchJson
      .mockResolvedValueOnce({
        ok: true,
        data: {
          receipt: {
            sale_id: 7,
            sale_number: 'INV-7',
            lines: [{ sale_line_id: 11, product_name: 'Apple', quantity_sold: 3, quantity_returnable: 2, unit_price: 10 }],
          },
        },
      })
      .mockResolvedValueOnce({ ok: false, error: 'gone' });
    m.fetch.mockResolvedValue(jsonResponse(200, true, { success: true }));
    await toolkit.lookupReceipt();
    document.querySelector('#returnLines .rl-qty').value = '1';
    document.getElementById('returnRefundMethod').value = 'cash';
    document.getElementById('returnNotes').value = '  damaged  ';
    await toolkit.submitReturn();
    const body = JSON.parse(m.fetch.mock.calls[0][1].body);
    expect(body).toMatchObject({
      sale_id: 7,
      sale_number: 'INV-7',
      refund_method: 'cash',
      notes: 'damaged',
    });
    expect(body.lines).toEqual([{ sale_line_id: 11, quantity: 1 }]);
    expect(m.showAlert).toHaveBeenCalledWith('تم تسجيل المرتجع', 'success');
    expect(m.modalFn).toHaveBeenCalledWith('hide');
    // lookupReceipt is re-run after a successful return.
    expect(m.fetchJson).toHaveBeenCalledTimes(2);
  });

  it('submitReturn surfaces a rejected return', async () => {
    document.getElementById('returnReceiptNumber').value = 'INV-7';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: { receipt: { sale_id: 7, sale_number: 'INV-7', lines: [{ sale_line_id: 11, product_name: 'Apple', quantity_returnable: 2 }] } },
    });
    m.fetch.mockResolvedValue(jsonResponse(422, false, { success: false, message: 'cannot return' }));
    await toolkit.lookupReceipt();
    document.querySelector('#returnLines .rl-qty').value = '1';
    await toolkit.submitReturn();
    expect(document.getElementById('returnAlert').textContent).toBe('cannot return');
    expect(m.showAlert).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// toolkit.js — stock lookup, fast cash, hardware status
// ===========================================================================
describe('toolkit: stock lookup', () => {
  it('openStockLookup clears and focuses', () => {
    document.getElementById('stockLookupResult').innerHTML = 'old';
    toolkit.openStockLookup();
    expect(document.getElementById('stockLookupResult').innerHTML).toBe('');
    expect(m.modalFn).toHaveBeenCalledWith('show');
  });

  it('runStockLookup warns on an empty query', async () => {
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupAlert').textContent).toContain('أدخل باركود أو رقم صنف');
  });

  it('runStockLookup clears results on an error', async () => {
    document.getElementById('stockLookupQuery').value = 'X';
    document.getElementById('stockLookupResult').innerHTML = 'old';
    m.fetchJson.mockResolvedValue({ ok: false, error: 'missing' });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupAlert').textContent).toBe('missing');
    expect(document.getElementById('stockLookupResult').innerHTML).toBe('');
  });

  it('runStockLookup uses product_id for numeric queries and renders warehouses', async () => {
    document.getElementById('stockLookupQuery').value = ' 123 ';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        product_name: 'Widget',
        warehouses: [
          { warehouse_name: 'Main', quantity: 4 },
          { name: 'Backup', stock: 2 },
        ],
      },
    });
    await toolkit.runStockLookup();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/stock/lookup?product_id=123');
    const html = document.getElementById('stockLookupResult').innerHTML;
    expect(html).toContain('Widget');
    expect(html).toContain('Main');
    expect(html).toContain('4.00');
    expect(html).toContain('Backup');
  });

  it('runStockLookup falls back to barcode and the breakdown array', async () => {
    document.getElementById('stockLookupQuery').value = 'ABC-1';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: { name: 'X', breakdown: [{ name: 'W1', on_hand: 3 }] },
    });
    await toolkit.runStockLookup();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/stock/lookup?barcode=ABC-1');
    expect(document.getElementById('stockLookupResult').innerHTML).toContain('W1');
  });

  it('runStockLookup renders a flat total when no breakdown is given', async () => {
    document.getElementById('stockLookupQuery').value = 'ABC-2';
    m.fetchJson.mockResolvedValue({ ok: true, data: { name: 'Y', total: 9 } });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupResult').innerHTML).toContain('9.00');
  });
});

describe('toolkit: renderFastCash', () => {
  it('returns early when the container is missing', async () => {
    document.getElementById('posFastCash').remove();
    await toolkit.renderFastCash();
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('clears the box when there is no positive cart total', async () => {
    document.getElementById('posFastCash').innerHTML = 'old';
    await toolkit.renderFastCash();
    expect(document.getElementById('posFastCash').innerHTML).toBe('');
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('clears the box when the API fails', async () => {
    m.state.lastTotals = { total: 100 };
    document.getElementById('posFastCash').innerHTML = 'old';
    m.fetchJson.mockResolvedValue({ ok: false });
    await toolkit.renderFastCash();
    expect(document.getElementById('posFastCash').innerHTML).toBe('');
  });

  it('renders cash keys with the exact class on exact-change options', async () => {
    m.state.lastTotals = { total: 100 };
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        options: [
          { amount: 100, change: 0, is_exact: true },
          { amount: 50, change: 50, is_exact: false },
        ],
      },
    });
    await toolkit.renderFastCash();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/fast-cash?total=100&currency=USD');
    const html = document.getElementById('posFastCash').innerHTML;
    expect(html).toContain('pos-fast-key exact');
    expect(html).toContain('data-amount="100"');
    expect(html).toContain('data-amount="50"');
    expect(html.match(/pos-fast-key/g)).toHaveLength(2);
  });
});

describe('toolkit: refreshHardwareStatus', () => {
  it('returns early when the badge is missing', async () => {
    document.getElementById('hardwareStatusBadge').remove();
    await toolkit.refreshHardwareStatus();
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('sets state and title from the API response', async () => {
    m.fetchJson.mockResolvedValue({ ok: true, data: { status: 'connected' } });
    await toolkit.refreshHardwareStatus();
    const badge = document.getElementById('hardwareStatusBadge');
    expect(badge.dataset.state).toBe('connected');
    expect(badge.title).toContain('connected');
  });

  it('defaults to disconnected when no status is returned', async () => {
    m.fetchJson.mockResolvedValue({ ok: true, data: {} });
    await toolkit.refreshHardwareStatus();
    expect(document.getElementById('hardwareStatusBadge').dataset.state).toBe('disconnected');
  });
});

// ===========================================================================
// toolkit.js — setupPosToolkit wiring
// ===========================================================================
describe('toolkit: setupPosToolkit', () => {
  it('SaaS-gates return and shift actions when disabled', () => {
    window.POS_CONFIG = { enable_pos_returns: false, enable_pos_shifts: false };
    toolkit.setupPosToolkit();
    for (const id of ['returnsBtn', 'cashMovementBtn']) {
      const btn = document.getElementById(id);
      expect(btn.getAttribute('disabled')).toBe('disabled');
      expect(btn.classList.contains('disabled')).toBe(true);
      expect(btn.title).toBe('متاح في الباقة الاحترافية');
    }
  });

  it('leaves gated actions enabled when config is absent', () => {
    toolkit.setupPosToolkit();
    expect(document.getElementById('returnsBtn').hasAttribute('disabled')).toBe(false);
    expect(document.getElementById('cashMovementBtn').hasAttribute('disabled')).toBe(false);
  });

  it('wires all buttons and keyboard shortcuts', async () => {
    toolkit.setupPosToolkit();

    document.getElementById('sessionReportBtn').click();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/session/report');

    document.getElementById('cashMovementBtn').click();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/cash-movements?limit=8');

    document.getElementById('returnsBtn').click();
    expect(m.modalFn).toHaveBeenCalledWith('show');

    document.getElementById('returnLookupBtn').click();
    expect(document.getElementById('returnAlert').textContent).toContain('أدخل رقم الإيصال');

    document.getElementById('returnSubmitBtn').click();
    expect(document.getElementById('returnAlert').textContent).toContain('ابحث عن الإيصال أولاً');

    document.getElementById('stockLookupBtn').click();
    expect(m.modalFn).toHaveBeenCalledWith('show');

    document.getElementById('stockLookupGo').click();
    expect(document.getElementById('stockLookupAlert').textContent).toContain('أدخل باركود أو رقم صنف');

    document.getElementById('cashMovementAmount').value = '10';
    document.getElementById('cashMovementSave').click();
    expect(m.fetch).toHaveBeenCalledWith('/pos/api/cash-movements', expect.any(Object));

    const enter = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true });
    document.getElementById('returnReceiptNumber').dispatchEvent(enter);
    expect(document.getElementById('returnAlert').textContent).toContain('أدخل رقم الإيصال');
    document.getElementById('stockLookupQuery').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', cancelable: true }));
    expect(document.getElementById('stockLookupAlert').textContent).toContain('أدخل باركود أو رقم صنف');

    // Non-Enter keys must not trigger lookups.
    document.getElementById('returnAlert').textContent = '';
    document.getElementById('returnReceiptNumber').dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(document.getElementById('returnAlert').textContent).toBe('');

    // Fast-cash key click updates the paid amount and recalculates; a click
    // with no button target is a no-op.
    const box = document.getElementById('posFastCash');
    box.innerHTML = '<button type="button" data-amount="25">25</button>';
    box.querySelector('button').click();
    expect(document.getElementById('paidAmount').value).toBe('25');
    expect(m.recalc).toHaveBeenCalledTimes(1);
    box.click();
    expect(m.recalc).toHaveBeenCalledTimes(1);
  });

  it('opens the customer display or warns when no session URL is set', () => {
    toolkit.setupPosToolkit();
    const btn = document.getElementById('customerDisplayBtn');
    btn.click();
    expect(m.showAlert).toHaveBeenCalledWith('افتح جلسة كاشير أولاً', 'warning');
    expect(window.open).not.toHaveBeenCalled();

    m.state.customerDisplayUrl = '/customer-display';
    btn.click();
    expect(window.open).toHaveBeenCalledWith('/customer-display', '_blank', 'noopener,noreferrer');
  });

  it('debounces fast-cash rendering from the paid input and pos:totals event', () => {
    vi.useFakeTimers();
    toolkit.setupPosToolkit();
    m.fetchJson.mockClear();
    m.state.lastTotals = { total: 100 };

    document.getElementById('paidAmount').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(250);
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/fast-cash?total=100&currency=USD');

    m.fetchJson.mockClear();
    window.dispatchEvent(new Event('pos:totals'));
    vi.advanceTimersByTime(250);
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/fast-cash?total=100&currency=USD');
  });
});

// ===========================================================================
// scale-serial.js
// ===========================================================================
describe('scale-serial: parseScaleFrame', () => {
  it('parses stable and unstable protocol headers', () => {
    expect(parseScaleFrame('ST,GS,+  1.234kg')).toEqual({ weightKg: 1.234, stable: true });
    expect(parseScaleFrame('US,NT,- 0.500kg')).toEqual({ weightKg: 0.5, stable: false });
    expect(parseScaleFrame('OL,+ 9.999kg')).toEqual({ weightKg: 9.999, stable: false });
    expect(parseScaleFrame('GS,1.000')).toEqual({ weightKg: 1, stable: true });
    expect(parseScaleFrame('NT 2.500')).toEqual({ weightKg: 2.5, stable: true });
  });

  it('parses plain, comma-decimal and gram frames', () => {
    expect(parseScaleFrame('1.234')).toEqual({ weightKg: 1.234, stable: true });
    expect(parseScaleFrame('+0001.234')).toEqual({ weightKg: 1.234, stable: true });
    expect(parseScaleFrame('1,234kg')).toEqual({ weightKg: 1.234, stable: true });
    expect(parseScaleFrame('500g')).toEqual({ weightKg: 0.5, stable: true });
  });

  it('rejects null, blank, non-numeric and negative frames', () => {
    expect(parseScaleFrame(null)).toBeNull();
    expect(parseScaleFrame('')).toBeNull();
    expect(parseScaleFrame('   ')).toBeNull();
    expect(parseScaleFrame('abc')).toBeNull();
    expect(parseScaleFrame('-1.234')).toBeNull();
  });
});

describe('scale-serial: PosScaleSerial', () => {
  it('constructs with defaults and with explicit options', () => {
    const a = new PosScaleSerial();
    expect(a.onStableWeight).toBeNull();
    expect(a.onError).toBeNull();
    expect(a.baudRate).toBe(9600);
    expect(a.port).toBeNull();
    expect(a.reader).toBeNull();
    expect(a.connected).toBe(false);
    expect(a.lastWeightKg).toBe(0);
    expect(a._pendingKg).toBe(0);
    expect(a._pendingCount).toBe(0);
    expect(a._buffer).toBe('');

    const onStableWeight = vi.fn();
    const onError = vi.fn();
    const b = new PosScaleSerial({ onStableWeight, onError, baudRate: 4800 });
    expect(b.onStableWeight).toBe(onStableWeight);
    expect(b.onError).toBe(onError);
    expect(b.baudRate).toBe(4800);

    const c = new PosScaleSerial({ onStableWeight: 'no', onError: 1 });
    expect(c.onStableWeight).toBeNull();
    expect(c.onError).toBeNull();
  });

  it('reports Web Serial support from navigator.serial', () => {
    delete navigator.serial;
    expect(PosScaleSerial.isSupported()).toBe(false);
    Object.defineProperty(navigator, 'serial', { value: { requestPort: vi.fn() }, configurable: true });
    expect(PosScaleSerial.isSupported()).toBe(true);
  });

  it('connect fails with a translated error when unsupported', async () => {
    delete navigator.serial;
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    expect(await scale.connect()).toBe(false);
    expect(onError).toHaveBeenCalledWith(expect.any(String));
  });

  it('connect opens the port and starts the read loop', async () => {
    const open = vi.fn();
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open,
          close: vi.fn().mockResolvedValue(undefined),
          readable: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true }), releaseLock: vi.fn() }) },
        }),
      },
      configurable: true,
    });
    const scale = new PosScaleSerial({ baudRate: 19200 });
    expect(await scale.connect()).toBe(true);
    expect(open).toHaveBeenCalledWith({ baudRate: 19200, dataBits: 8, parity: 'none', stopBits: 1 });
    expect(scale.connected).toBe(true);
    await scale.disconnect();
  });

  it('connect handles requestPort errors and error objects without a message', async () => {
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    const onError = vi.fn();
    expect(await new PosScaleSerial({ onError }).connect()).toBe(false);
    expect(onError).toHaveBeenCalledWith('denied');

    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockRejectedValue({}) },
      configurable: true,
    });
    const onError2 = vi.fn();
    expect(await new PosScaleSerial({ onError: onError2 }).connect()).toBe(false);
    expect(onError2).toHaveBeenCalledWith(expect.any(String));
  });

  it('disconnect cancels the reader and closes the port, tolerating rejections', async () => {
    const cancel = vi.fn().mockRejectedValue(new Error('cancel'));
    const close = vi.fn().mockRejectedValue(new Error('close'));
    const scale = new PosScaleSerial();
    scale.connected = true;
    scale.reader = { cancel, releaseLock: vi.fn() };
    scale.port = { close };
    scale.lastWeightKg = 1.5;
    scale._pendingCount = 3;
    await scale.disconnect();
    expect(scale.connected).toBe(false);
    expect(scale.reader).toBeNull();
    expect(scale.port).toBeNull();
    expect(scale.lastWeightKg).toBe(0);
    expect(scale._pendingCount).toBe(0);
  });

  it('disconnect works with no reader or port', async () => {
    const scale = new PosScaleSerial();
    await scale.disconnect();
    expect(scale.connected).toBe(false);
  });

  it('_ingest splits lines, handles CR/LF and trims an overlong buffer', () => {
    const scale = new PosScaleSerial();
    const spy = vi.spyOn(scale, '_handleLine');
    scale._ingest('1.000\r\n2.000\npartial');
    expect(spy).toHaveBeenCalledWith('1.000');
    expect(spy).toHaveBeenCalledWith('2.000');
    expect(scale._buffer).toBe('partial');
    scale._ingest('x'.repeat(200));
    expect(scale._buffer.length).toBeLessThanOrEqual(64);
  });

  it('_handleLine requires three stable reads and honours the epsilon', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });
    scale._handleLine('1.000');
    scale._handleLine('1.001'); // within epsilon -> same run
    scale._handleLine('1.0009'); // still within epsilon (avoid FP 0.002 edge)
    // The pending weight is pinned to the first reading of the stable run.
    expect(onStableWeight).toHaveBeenCalledWith(1);
    expect(scale.getLastWeight()).toBe(1);

    scale._handleLine('US,NT,- 1.000kg'); // unstable -> ignored
    expect(onStableWeight).toHaveBeenCalledTimes(1);
    scale._handleLine(''); // null frame -> ignored
    scale._handleLine('abc');
    expect(onStableWeight).toHaveBeenCalledTimes(1);
  });

  it('_readLoop ingests framed weight until done', async () => {
    const line = new TextEncoder().encode('1.234\n');
    const chunks = [
      { value: line, done: false },
      { value: line, done: false },
      { value: line, done: false },
      { value: undefined, done: true },
    ];
    let i = 0;
    const reader = {
      read: vi.fn(() => Promise.resolve(chunks[i++])),
      releaseLock: vi.fn(),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockResolvedValue({ open: vi.fn(), readable: { getReader: () => reader }, close: vi.fn() }) },
      configurable: true,
    });
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });
    await scale.connect();
    await new Promise((r) => setTimeout(r, 50));
    expect(onStableWeight).toHaveBeenCalledWith(1.234);
    expect(reader.releaseLock).toHaveBeenCalled();
    scale.connected = false;
  });

  it('_readLoop reports a read error while connected', async () => {
    const reader = {
      read: vi.fn().mockRejectedValue(new Error('device lost')),
      releaseLock: vi.fn(),
    };
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockResolvedValue({ open: vi.fn(), readable: { getReader: () => reader }, close: vi.fn() }) },
      configurable: true,
    });
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    await scale.connect();
    await new Promise((r) => setTimeout(r, 50));
    expect(onError).toHaveBeenCalledWith('device lost');
    scale.connected = false;
  });

  it('_fail always strings the message and tolerates no handler', () => {
    const onError = vi.fn();
    const a = new PosScaleSerial({ onError });
    a._fail(42);
    expect(onError).toHaveBeenCalledWith('42');
    a._fail();
    expect(onError).toHaveBeenCalledWith('Scale error');
    expect(() => new PosScaleSerial()._fail('x')).not.toThrow();
  });

  it('exposes itself on window and wires setupPosScaleUI', async () => {
    expect(typeof window.PosScaleSerial).toBe('function');
    const setupPosScaleUI = window.setupPosScaleUI;
    expect(typeof setupPosScaleUI).toBe('function');

    expect(setupPosScaleUI({ button: null, scale: new PosScaleSerial() })).toBeNull();
    expect(setupPosScaleUI({ button: document.createElement('button'), scale: null })).toBeNull();

    delete navigator.serial;
    const hiddenBtn = document.createElement('button');
    expect(setupPosScaleUI({ button: hiddenBtn, scale: new PosScaleSerial() })).toBeNull();
    expect(hiddenBtn.classList.contains('d-none')).toBe(true);

    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockResolvedValue({ open: vi.fn(), close: vi.fn().mockResolvedValue(undefined) }) },
      configurable: true,
    });
    const btn = document.createElement('button');
    btn.title = 'Connect';
    const scale = new PosScaleSerial();
    expect(setupPosScaleUI({ button: btn, scale, connectedTitle: 'Disconnect' })).toBe(scale);
    expect(btn.title).toBe('Connect');
    btn.click();
    await new Promise((r) => setTimeout(r, 20));
    expect(btn.title).toBe('Disconnect');
    expect(btn.classList.contains('pos-scale-live')).toBe(true);
    btn.click();
    await new Promise((r) => setTimeout(r, 20));
    expect(btn.title).toBe('Connect');
  });
});

// ===========================================================================
// escpos-printer.js
// ===========================================================================
describe('escpos-printer: byte builder', () => {
  it('builds an initialized receipt with text, separator, feed, drawer and cut', () => {
    const out = buildReceiptBytes({
      lines: ['Hello', { text: 'sep', separator: true, width: 10 }, { text: 'R', align: 'right', bold: true, double: true }],
      feed: 3,
      open_drawer: true,
    });
    const arr = [...out];
    expect(arr.slice(0, 2)).toEqual([0x1b, 0x40]);
    const text = new TextDecoder().decode(out);
    expect(text).toContain('Hello');
    expect(text).toContain('----------');
    expect(arr.join(',')).toContain([0x1b, 0x61, 0x02].join(',')); // right align
    expect(arr.join(',')).toContain([0x1b, 0x45, 0x01].join(',')); // bold on
    expect(arr.join(',')).toContain([0x1d, 0x21, 0x11].join(',')); // double
    expect(arr.join(',')).toContain([0x1b, 0x70, 0x00, 0x19, 0xfa].join(',')); // drawer
    expect(arr.join(',')).toContain([0x1d, 0x56, 0x00].join(',')); // cut
  });

  it('uses the default align for an unknown value and can omit the cut', () => {
    const withCut = buildReceiptBytes({ lines: [{ text: 'x', align: 'weird' }] });
    const withoutCut = buildReceiptBytes({ lines: [{ text: 'x', align: 'weird' }], cut: false });
    expect([...withCut].join(',')).toContain([0x1b, 0x61, 0x00].join(','));
    expect(withoutCut.length).toBeLessThan(withCut.length);
  });

  it('caps the feed at ten lines', () => {
    const out = buildReceiptBytes({ lines: [], feed: 50 });
    // 2 feed bytes before the drawer/cut + 2 after = 4 baseline; cap adds 10.
    expect([...out].filter((b) => b === 0x0a).length).toBeLessThanOrEqual(14);
  });

  it('encodes CP864 Arabic, ASCII and unmapped code points', () => {
    const arabic = buildReceiptBytes({ lines: [{ text: 'ا', encoding: 'cp864' }] });
    expect([...arabic]).toContain(0xc7);
    const ascii = buildReceiptBytes({ lines: [{ text: 'A', encoding: 'cp864' }] });
    expect([...ascii]).toContain(0x41);
    const unmapped = buildReceiptBytes({ lines: [{ text: '€', encoding: 'cp864' }] });
    expect([...unmapped]).toEqual(expect.arrayContaining([0xe2, 0x82, 0xac]));
  });

  it('handles missing content entirely', () => {
    expect(buildReceiptBytes()[0]).toBe(0x1b);
    expect(buildReceiptBytes(undefined).length).toBeGreaterThan(0);
  });
});

describe('escpos-printer: EscposPrinter', () => {
  it('constructs empty and reports browser support', () => {
    const p = new EscposPrinter();
    expect(p.device).toBeNull();
    expect(p.port).toBeNull();
    expect(p.channel).toBeNull();

    delete navigator.usb;
    delete navigator.serial;
    expect(EscposPrinter.webUsbSupported()).toBe(false);
    expect(EscposPrinter.webSerialSupported()).toBe(false);
    Object.defineProperty(navigator, 'usb', { value: {}, configurable: true });
    Object.defineProperty(navigator, 'serial', { value: {}, configurable: true });
    expect(EscposPrinter.webUsbSupported()).toBe(true);
    expect(EscposPrinter.webSerialSupported()).toBe(true);
  });

  it('connectWebUsb throws when unsupported and selects a configuration when needed', async () => {
    delete navigator.usb;
    await expect(new EscposPrinter().connectWebUsb()).rejects.toThrow('WebUSB');

    const device = {
      configuration: null,
      open: vi.fn(),
      selectConfiguration: vi.fn(),
      claimInterface: vi.fn(),
    };
    Object.defineProperty(navigator, 'usb', {
      value: { requestDevice: vi.fn().mockResolvedValue(device) },
      configurable: true,
    });
    window._PRINTER_USB_FILTERS = [{ vendorId: 1 }];
    const p = new EscposPrinter();
    expect(await p.connectWebUsb()).toBe(true);
    expect(device.selectConfiguration).toHaveBeenCalledWith(1);
    expect(device.claimInterface).toHaveBeenCalledWith(0);
    expect(p.channel).toBe('webusb');
    delete window._PRINTER_USB_FILTERS;
  });

  it('connectWebUsb skips configuration selection when one exists', async () => {
    const device = {
      configuration: { interfaces: [] },
      open: vi.fn(),
      selectConfiguration: vi.fn(),
      claimInterface: vi.fn(),
    };
    Object.defineProperty(navigator, 'usb', {
      value: { requestDevice: vi.fn().mockResolvedValue(device) },
      configurable: true,
    });
    const p = new EscposPrinter();
    await p.connectWebUsb();
    expect(device.selectConfiguration).not.toHaveBeenCalled();
  });

  it('connectSerial throws when unsupported and opens with the given baud rate', async () => {
    delete navigator.serial;
    await expect(new EscposPrinter().connectSerial()).rejects.toThrow('Web Serial');

    const port = { open: vi.fn() };
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockResolvedValue(port) },
      configurable: true,
    });
    const p = new EscposPrinter();
    expect(await p.connectSerial({ baudRate: 115200 })).toBe(true);
    expect(port.open).toHaveBeenCalledWith({ baudRate: 115200 });
    expect(p.channel).toBe('webserial');
  });

  it('prints over webserial and releases the writer even on failure', async () => {
    const writer = { write: vi.fn().mockResolvedValue(undefined), releaseLock: vi.fn() };
    const port = { open: vi.fn(), writable: { getWriter: () => writer } };
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn().mockResolvedValue(port) },
      configurable: true,
    });
    const p = new EscposPrinter();
    await p.connectSerial();
    expect(await p.print(new Uint8Array([1, 2]))).toBe(true);
    expect(writer.write).toHaveBeenCalled();
    expect(writer.releaseLock).toHaveBeenCalled();

    const badWriter = { write: vi.fn().mockRejectedValue(new Error('write failed')), releaseLock: vi.fn() };
    port.writable.getWriter = () => badWriter;
    await expect(p.print(new Uint8Array([1]))).rejects.toThrow('write failed');
    expect(badWriter.releaseLock).toHaveBeenCalled();
  });

  it('prints over webusb and rejects when no out endpoint exists', async () => {
    const device = {
      configuration: {
        interfaces: [{ alternate: { endpoints: [{ direction: 'out', endpointNumber: 3 }] } }],
      },
      open: vi.fn(),
      claimInterface: vi.fn(),
      transferOut: vi.fn().mockResolvedValue({ status: 'ok' }),
    };
    Object.defineProperty(navigator, 'usb', {
      value: { requestDevice: vi.fn().mockResolvedValue(device) },
      configurable: true,
    });
    const p = new EscposPrinter();
    await p.connectWebUsb();
    expect(await p.print(new Uint8Array([1]))).toBe(true);
    expect(device.transferOut).toHaveBeenCalledWith(3, expect.any(Uint8Array));

    device.configuration.interfaces[0].alternate.endpoints = [{ direction: 'in', endpointNumber: 1 }];
    await expect(p.print(new Uint8Array([1]))).rejects.toThrow('نقطة إخراج');
  });

  it('rejects a print when not connected', async () => {
    await expect(new EscposPrinter().print(new Uint8Array([1]))).rejects.toThrow('غير متصلة');
  });

  it('disconnect closes both transports and clears state even on rejection', async () => {
    const device = { close: vi.fn().mockRejectedValue(new Error('close failed')) };
    const port = { close: vi.fn() };
    const p = new EscposPrinter();
    p.device = device;
    p.port = port;
    p.channel = 'webusb';
    await expect(p.disconnect()).rejects.toThrow('close failed');
    expect(device.close).toHaveBeenCalled();
    // The finally block clears every transport reference even when close throws.
    expect(p.device).toBeNull();
    expect(p.port).toBeNull();
    expect(p.channel).toBeNull();
  });

  it('exposes the builder and printer on window', () => {
    expect(typeof window.EscposPrinter).toBe('function');
    expect(typeof window.buildReceiptBytes).toBe('function');
  });
});

// ===========================================================================
// Remaining reachable branches — fallback/default paths in all three modules
// ===========================================================================
describe('toolkit: remaining fallback branches', () => {
  it('renders an em-dash when the session has no number', async () => {
    m.fetchJson.mockResolvedValue({ ok: true, data: { session: { status: 'open', opening_balance: 0 } } });
    await toolkit.openSessionReport();
    expect(document.getElementById('sessionReportBody').innerHTML).toContain('—');
  });

  it('uses the raw string when window.t is unavailable', async () => {
    const saved = window.t;
    window.t = null;
    try {
      m.fetchJson.mockResolvedValue({ ok: false, error: 'raw-error' });
      await expect(toolkit.openSessionReport()).resolves.toBeUndefined();
      expect(document.getElementById('sessionReportBody').innerHTML).toContain('raw-error');
    } finally {
      window.t = saved;
    }
  });

  it('loadCashMovements tolerates an omitted error and missing reason keys', async () => {
    m.fetchJson.mockResolvedValue({ ok: false });
    await toolkit.loadCashMovements();
    expect(document.getElementById('cashMovementsList').innerHTML).toContain('text-muted small');

    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        movements: [
          { movement_type: 'pay_out', amount: 1, reason: '', created_at: 'date-x' },
          { movement_type: 'pay_out', amount: 1 },
        ],
      },
    });
    await toolkit.loadCashMovements();
    const html = document.getElementById('cashMovementsList').innerHTML;
    expect(html).toContain('date-x');
    expect(html.match(/pos-mini-row/g)).toHaveLength(2);
  });

  it('alertIn/clearAlert are no-ops when their target element is absent', async () => {
    document.getElementById('cashMovementAlert').remove();
    document.getElementById('returnAlert').remove();
    await expect(toolkit.saveCashMovement()).resolves.toBeUndefined();
    expect(() => toolkit.openReturns()).not.toThrow();
  });

  it('lookupReceipt uses its default error and handles a receipt with no lines', async () => {
    document.getElementById('returnReceiptNumber').value = 'X';
    m.fetchJson.mockResolvedValue({ ok: false });
    await toolkit.lookupReceipt();
    expect(document.getElementById('returnAlert').textContent).toContain('الإيصال غير موجود');

    m.fetchJson.mockResolvedValue({
      ok: true,
      data: { receipt: { sale_id: 1, sale_number: 'R1', lines: undefined } },
    });
    await toolkit.lookupReceipt();
    expect(document.getElementById('returnLines').innerHTML).toBe('');
  });

  it('lookupReceipt names a line by product_id when it has no name or sku', async () => {
    document.getElementById('returnReceiptNumber').value = 'R2';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        receipt: {
          sale_id: 2,
          sale_number: 'R2',
          lines: [{ sale_line_id: 5, product_id: 99, quantity_sold: 1, quantity_returnable: 1 }],
        },
      },
    });
    await toolkit.lookupReceipt();
    expect(document.getElementById('returnLines').innerHTML).toContain('99');
  });

  it('submitReturn falls back to its default failure message', async () => {
    document.getElementById('returnReceiptNumber').value = 'R3';
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: {
        receipt: {
          sale_id: 3,
          sale_number: 'R3',
          lines: [{ sale_line_id: 6, product_name: 'P', quantity_returnable: 1 }],
        },
      },
    });
    m.fetch.mockResolvedValue(jsonResponse(500, false, { success: false }));
    await toolkit.lookupReceipt();
    document.querySelector('#returnLines .rl-qty').value = '1';
    await toolkit.submitReturn();
    expect(document.getElementById('returnAlert').textContent).toBe('تعذر تسجيل المرتجع');
  });

  it('runStockLookup covers its error/name/quantity fallbacks', async () => {
    document.getElementById('stockLookupQuery').value = 'QQ';
    m.fetchJson.mockResolvedValue({ ok: false });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupAlert').textContent).toContain('المنتج غير موجود');

    m.fetchJson.mockResolvedValue({ ok: true, data: { quantity: 0 } });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupResult').innerHTML).toContain('QQ');

    m.fetchJson.mockResolvedValue({ ok: true, data: { name: 'W', warehouses: [{}] } });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupResult').innerHTML).toContain('0.00');

    m.fetchJson.mockResolvedValue({ ok: true, data: { name: 'F' } });
    await toolkit.runStockLookup();
    expect(document.getElementById('stockLookupResult').innerHTML).toContain('0.00');
  });

  it('tolerates a missing POS_CONFIG and runs the hardware poll callback', () => {
    window.POS_CONFIG = null;
    toolkit.setupPosToolkit();
    const poll = window.setInterval.mock.calls[0][0];
    m.fetchJson.mockClear();
    poll();
    expect(m.fetchJson).toHaveBeenCalledWith('/pos/api/hardware/status');
  });
});

describe('scale-serial: remaining fallback branches', () => {
  it('_readLoop uses the default error text when the failure has no message', async () => {
    const reader = { read: vi.fn().mockRejectedValue({}), releaseLock: vi.fn() };
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open: vi.fn(),
          readable: { getReader: () => reader },
          close: vi.fn().mockResolvedValue(undefined),
        }),
      },
      configurable: true,
    });
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    await scale.connect();
    await new Promise((r) => setTimeout(r, 50));
    expect(onError).toHaveBeenCalledWith(expect.any(String));
    scale.connected = false;
  });

  it('setupPosScaleUI falls back to empty titles when none are supplied', () => {
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn() },
      configurable: true,
    });
    const btn = document.createElement('button');
    const scale = new PosScaleSerial();
    expect(window.setupPosScaleUI({ button: btn, scale })).toBe(scale);
    expect(btn.title).toBe('');
  });

  // `pos_scale_serial_enhanced.test.js` imports this module through ESM in its
  // own beforeEach. V8 keeps that ESM script instance separate from the CJS
  // one used above, and the reporter keeps a handful of statements from the
  // ESM instance. Exercise the same three paths through the ESM instance too
  // so they are covered whichever instance wins the merge.
  it('ESM instance: disconnect, read loop and ingest are covered too', async () => {
    const mod = await import('../../static/js/pos/scale-serial.js');
    const Scale = mod.PosScaleSerial;

    const disconnected = new Scale();
    disconnected.connected = true;
    disconnected.reader = { cancel: vi.fn().mockRejectedValue(new Error('cancel')) };
    disconnected.port = { close: vi.fn().mockRejectedValue(new Error('close')) };
    disconnected.lastWeightKg = 2;
    await disconnected.disconnect();
    expect(disconnected.lastWeightKg).toBe(0);

    const ingested = new Scale();
    ingested._ingest('1.000\r\n2.000\npartial');
    expect(ingested._buffer).toBe('partial');

    const chunk = new TextEncoder().encode('1.234\n');
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ value: chunk, done: false })
        .mockResolvedValue({ value: undefined, done: true }),
      releaseLock: vi.fn(),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open: vi.fn(),
          readable: { getReader: () => reader },
          close: vi.fn().mockResolvedValue(undefined),
        }),
      },
      configurable: true,
    });
    const looping = new Scale();
    await looping.connect();
    await new Promise((r) => setTimeout(r, 30));
    expect(reader.releaseLock).toHaveBeenCalled();
    looping.connected = false;
  });

  // A third instance under its own URL: the V8 reporter keys scripts by URL,
  // so one more variant guarantees the ingest/read-loop statements are hit on
  // the exact range that the final report keeps.
  it('fresh-URL ESM instance: ingest and read loop', async () => {
    const mod = await import('../../static/js/pos/scale-serial.js?coverage-fresh=1');
    const Scale = mod.PosScaleSerial;
    const s = new Scale();
    s._ingest('1.000\r\n2.000\npartial');
    expect(s._buffer).toBe('partial');

    const chunk = new TextEncoder().encode('1.234\n');
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ value: chunk, done: false })
        .mockResolvedValue({ value: undefined, done: true }),
      releaseLock: vi.fn(),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open: vi.fn(),
          readable: { getReader: () => reader },
          close: vi.fn().mockResolvedValue(undefined),
        }),
      },
      configurable: true,
    });
    const looping = new Scale();
    await looping.connect();
    await new Promise((r) => setTimeout(r, 30));
    expect(reader.releaseLock).toHaveBeenCalled();
    looping.connected = false;
  });
});

describe('escpos-printer: remaining fallback branches', () => {
  it('separator defaults to width 32 and a line object defaults to empty text', () => {
    const out = buildReceiptBytes({ lines: [{ separator: true }, {}] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('-'.repeat(32));
  });

  it('times out a wedged webusb transfer', async () => {
    vi.useFakeTimers();
    const device = {
      configuration: { interfaces: [{ alternate: { endpoints: [{ direction: 'out', endpointNumber: 1 }] } }] },
      open: vi.fn(),
      claimInterface: vi.fn(),
      transferOut: vi.fn(() => new Promise(() => {})),
    };
    Object.defineProperty(navigator, 'usb', {
      value: { requestDevice: vi.fn().mockResolvedValue(device) },
      configurable: true,
    });
    const p = new EscposPrinter();
    await p.connectWebUsb();
    const assertion = expect(p.print(new Uint8Array([1]))).rejects.toThrow('تجاوزت مهلة الطباعة عبر USB.');
    await vi.advanceTimersByTimeAsync(10000);
    await assertion;
  });

  it('propagates a fast webusb transfer rejection', async () => {
    const device = {
      configuration: { interfaces: [{ alternate: { endpoints: [{ direction: 'out', endpointNumber: 1 }] } }] },
      open: vi.fn(),
      claimInterface: vi.fn(),
      transferOut: vi.fn().mockRejectedValue(new Error('bus reset')),
    };
    Object.defineProperty(navigator, 'usb', {
      value: { requestDevice: vi.fn().mockResolvedValue(device) },
      configurable: true,
    });
    const p = new EscposPrinter();
    await p.connectWebUsb();
    await expect(p.print(new Uint8Array([1]))).rejects.toThrow('bus reset');
  });

  it('disconnect closes a serial port when no USB device is present', async () => {
    const port = { close: vi.fn().mockResolvedValue(undefined) };
    const p = new EscposPrinter();
    p.port = port;
    p.channel = 'webserial';
    await p.disconnect();
    expect(port.close).toHaveBeenCalled();
    expect(p.port).toBeNull();
    expect(p.channel).toBeNull();
  });

  it('disconnect handles a successfully closed device with no serial port', async () => {
    const device = { close: vi.fn().mockResolvedValue(undefined) };
    const p = new EscposPrinter();
    p.device = device;
    p.channel = 'webusb';
    await p.disconnect();
    expect(device.close).toHaveBeenCalled();
    expect(p.device).toBeNull();
  });
});

// ===========================================================================
// Final implicit-else branches (guards whose false path was not yet taken)
// ===========================================================================
describe('final implicit-else branches', () => {
  it('toolkit: omits the closing block when closing_balance is null', async () => {
    m.fetchJson.mockResolvedValue({
      ok: true,
      data: { session: { status: 'open', opening_balance: 0, expected_balance: 5, closing_balance: null } },
    });
    await toolkit.openSessionReport();
    const html = document.getElementById('sessionReportBody').innerHTML;
    expect(html).toContain('الرصيد المتوقع');
    expect(html).not.toContain('الرصيد المعدود');
  });

  it('toolkit: a non-Enter stock query keypress is ignored', () => {
    toolkit.setupPosToolkit();
    m.fetchJson.mockClear();
    document.getElementById('stockLookupQuery').dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(m.fetchJson).not.toHaveBeenCalled();
  });

  it('toolkit: a fast-cash key click with no paid field still recalculates', () => {
    document.getElementById('paidAmount').remove();
    toolkit.setupPosToolkit();
    const box = document.getElementById('posFastCash');
    box.innerHTML = '<button type="button" data-amount="25">25</button>';
    box.querySelector('button').click();
    expect(m.recalc).toHaveBeenCalledTimes(1);
  });

  it('scale-serial: _readLoop skips empty values and stops when disconnected', async () => {
    const line = new TextEncoder().encode('2.000\n');
    const chunks = [
      { value: undefined, done: false },
      { value: line, done: false },
      { value: line, done: false },
      { value: line, done: false },
      { value: undefined, done: true },
    ];
    let i = 0;
    const reader = {
      read: vi.fn(() => Promise.resolve(chunks[i++])),
      releaseLock: vi.fn(),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open: vi.fn(),
          readable: { getReader: () => reader },
          close: vi.fn().mockResolvedValue(undefined),
        }),
      },
      configurable: true,
    });
    const scale = new PosScaleSerial();
    await scale.connect();
    scale.connected = false;
    await new Promise((r) => setTimeout(r, 50));
    expect(reader.releaseLock).toHaveBeenCalled();
  });

  it('scale-serial: a read failure after disconnect does not call onError', async () => {
    let rejectRead;
    const reader = {
      read: vi.fn(() => new Promise((_, reject) => { rejectRead = reject; })),
      releaseLock: vi.fn(),
    };
    Object.defineProperty(navigator, 'serial', {
      value: {
        requestPort: vi.fn().mockResolvedValue({
          open: vi.fn(),
          readable: { getReader: () => reader },
          close: vi.fn().mockResolvedValue(undefined),
        }),
      },
      configurable: true,
    });
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    await scale.connect();
    scale.connected = false;
    rejectRead(new Error('ignored'));
    await new Promise((r) => setTimeout(r, 20));
    expect(onError).not.toHaveBeenCalled();
  });

  it('scale-serial: three stable reads with no callback still update the weight', () => {
    const scale = new PosScaleSerial();
    scale._handleLine('3.000');
    scale._handleLine('3.000');
    scale._handleLine('3.000');
    expect(scale.getLastWeight()).toBe(3);
    expect(scale._pendingCount).toBe(0);
  });
});
