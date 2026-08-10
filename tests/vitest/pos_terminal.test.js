import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function makeTerminalMock() {
  const terminal = {
    discoverReaders: vi.fn(() => Promise.resolve({ discoveredReaders: [{ id: 'r1' }] })),
    connectReader: vi.fn(() => Promise.resolve({ reader: { id: 'r1' } })),
    collectPaymentMethod: vi.fn(() => Promise.resolve({ paymentIntent: { id: 'pi_1' } })),
    processPayment: vi.fn(() =>
      Promise.resolve({ paymentIntent: { id: 'pi_1', status: 'succeeded' } })
    ),
  };
  window.StripeTerminal = { create: vi.fn(() => terminal) };
  return terminal;
}

function mockFetchRoutes({ statusConfigured = true, intentError } = {}) {
  global.fetch = vi.fn((url) => {
    const u = String(url);
    if (u.endsWith('/pos/api/terminal/status')) {
      return Promise.resolve({
        ok: statusConfigured,
        json: () => Promise.resolve({ success: statusConfigured, configured: statusConfigured }),
      });
    }
    if (u.endsWith('/pos/api/terminal/connection_token')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ secret: 'tok_1' }) });
    }
    if (u.endsWith('/pos/api/terminal/payment_intent')) {
      if (intentError) return Promise.resolve({ ok: false, json: () => Promise.resolve({ error: 'ضد رفض' }) });
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ success: true, id: 'pi_intent', amount_minor: 1250, client_secret: 'cs_1' }),
      });
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  });
}

describe('terminal.js', () => {
  beforeEach(() => {
    localStorage.clear();
    document.head.innerHTML = '';
    delete window._FX_FALLBACK_BASE;
    delete window.StripeTerminal;
    delete window.PosTerminal;
    delete window.setupTerminalButton;
    vi.resetModules();
  });

  afterEach(() => {
    document.head.innerHTML = '';
    delete window._FX_FALLBACK_BASE;
    delete window.StripeTerminal;
    delete window.PosTerminal;
    delete window.setupTerminalButton;
    delete global.fetch;
    localStorage.clear();
    vi.resetModules();
  });

  it('defaults the currency to ILS without hints', async () => {
    makeTerminalMock();
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await t.pushPayment({ amount: 5 });
    expect(JSON.parse(fetch.mock.calls[0][1].body).currency).toBe('ILS');
  });

  it('reads the base currency from _FX_FALLBACK_BASE', async () => {
    window._FX_FALLBACK_BASE = 'USD';
    makeTerminalMock();
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await t.pushPayment({ amount: 5 });
    expect(JSON.parse(fetch.mock.calls[0][1].body).currency).toBe('USD');
  });

  it('reads the base currency from the pos-base-currency meta', async () => {
    const meta = document.createElement('meta');
    meta.name = 'pos-base-currency';
    meta.content = 'AED';
    document.head.appendChild(meta);
    makeTerminalMock();
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await t.pushPayment({ amount: 5 });
    expect(JSON.parse(fetch.mock.calls[0][1].body).currency).toBe('AED');
  });

  it('checkStatus is true when the provider is configured', async () => {
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal({ baseUrl: '/b' });
    await expect(t.checkStatus()).resolves.toBe(true);
  });

  it('checkStatus is false when unconfigured', async () => {
    mockFetchRoutes({ statusConfigured: false });
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.checkStatus()).resolves.toBe(false);
  });

  it('checkStatus is false when the request fails', async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error('down')));
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.checkStatus()).resolves.toBe(false);
  });

  it('gets the terminal and wires connection-token/disconnect callbacks', async () => {
    makeTerminalMock();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, secret: 'tok_x' }) })
    );
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal({ baseUrl: '/b' });
    const terminal = await t._getTerminal();
    expect(window.StripeTerminal.create).toHaveBeenCalledTimes(1);
    expect(t._terminal).toBe(terminal);
    const opts = window.StripeTerminal.create.mock.calls[0][0];
    await expect(opts.onFetchConnectionToken()).resolves.toBe('tok_x');
    t._reader = { id: 'r1' };
    opts.onUnexpectedReaderDisconnect();
    expect(t._reader).toBeNull();
  });

  it('caches the terminal instance', async () => {
    makeTerminalMock();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await t._getTerminal();
    await t._getTerminal();
    expect(window.StripeTerminal.create).toHaveBeenCalledTimes(1);
  });

  it('connects the remembered reader when present', async () => {
    const terminal = makeTerminalMock();
    localStorage.setItem('pos.terminal.reader_id', 'r1');
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    const reader = await t._connectReader(terminal);
    expect(reader).toEqual({ id: 'r1' });
    expect(terminal.connectReader).toHaveBeenCalledWith({ id: 'r1' });
    expect(localStorage.getItem('pos.terminal.reader_id')).toBe('r1');
  });

  it('throws when reader discovery fails', async () => {
    const terminal = makeTerminalMock();
    terminal.discoverReaders.mockResolvedValue({ error: 'boom' });
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t._connectReader(terminal)).rejects.toThrow('تعذر البحث عن قارئ البطاقات.');
  });

  it('throws when no readers are found', async () => {
    const terminal = makeTerminalMock();
    terminal.discoverReaders.mockResolvedValue({ discoveredReaders: [] });
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t._connectReader(terminal)).rejects.toThrow('لا يوجد قارئ بطاقات');
  });

  it('throws when connecting the reader fails', async () => {
    const terminal = makeTerminalMock();
    terminal.connectReader.mockResolvedValue({ error: 'nope' });
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t._connectReader(terminal)).rejects.toThrow('تعذر الاتصال بقارئ البطاقات.');
  });

  it('pushes a payment and returns the intent id', async () => {
    const terminal = makeTerminalMock();
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    const result = await t.pushPayment({ amount: 12.5, currency: 'AED', saleReference: 'S-1' });
    expect(result).toEqual({ intentId: 'pi_1', amountMinor: 1250 });
    expect(terminal.collectPaymentMethod).toHaveBeenCalledWith('cs_1');
    expect(terminal.processPayment).toHaveBeenCalledWith({ id: 'pi_1' });
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/pos/api/terminal/payment_intent');
    expect(JSON.parse(opts.body)).toEqual({ amount: '12.5', currency: 'AED', sale_reference: 'S-1' });
  });

  it('throws a safe error when collection is cancelled', async () => {
    const terminal = makeTerminalMock();
    terminal.collectPaymentMethod.mockResolvedValue({ error: 'cancelled' });
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.pushPayment({ amount: 5 })).rejects.toThrow('ألغيت العملية');
  });

  it('throws a safe error when the issuer declines', async () => {
    const terminal = makeTerminalMock();
    terminal.processPayment.mockResolvedValue({ error: 'declined' });
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.pushPayment({ amount: 5 })).rejects.toThrow('رفضت جهة الإصدار');
  });

  it('throws when the payment intent is not succeeded', async () => {
    const terminal = makeTerminalMock();
    terminal.processPayment.mockResolvedValue({ paymentIntent: { status: 'requires_payment_method' } });
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.pushPayment({ amount: 5 })).rejects.toThrow('لم تكتمل عملية الدفع');
  });

  it('throws the server error when the payment intent request fails', async () => {
    makeTerminalMock();
    mockFetchRoutes({ intentError: true });
    await import('../../static/js/pos/terminal.js');
    const t = new window.PosTerminal();
    await expect(t.pushPayment({ amount: 5 })).rejects.toThrow('ضد رفض');
  });

  it('returns null when the terminal button is absent', async () => {
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const result = await window.setupTerminalButton({ button: null });
    expect(result).toBeNull();
  });

  it('keeps the button hidden when the provider is not configured', async () => {
    mockFetchRoutes({ statusConfigured: false });
    await import('../../static/js/pos/terminal.js');
    const button = document.createElement('button');
    button.classList.add('d-none');
    const result = await window.setupTerminalButton({ button });
    expect(result).toBeNull();
    expect(button.classList.contains('d-none')).toBe(true);
  });

  it('warns when the cart amount is not positive', async () => {
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const button = document.createElement('button');
    button.classList.add('d-none');
    const onError = vi.fn();
    await window.setupTerminalButton({ button, getAmount: () => 0, onError });
    expect(button.classList.contains('d-none')).toBe(false);
    button.click();
    expect(onError).toHaveBeenCalledWith('أضف أصنافاً إلى السلة أولاً.');
  });

  it('approves the payment and re-enables the button', async () => {
    makeTerminalMock();
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const button = document.createElement('button');
    button.classList.add('d-none');
    const onApproved = vi.fn();
    const onError = vi.fn();
    await window.setupTerminalButton({
      button,
      getAmount: () => 50,
      getCurrency: () => 'AED',
      onApproved,
      onError,
    });
    expect(button.classList.contains('d-none')).toBe(false);
    button.click();
    expect(button.disabled).toBe(true);
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(onApproved).toHaveBeenCalledWith({ intentId: 'pi_1', amountMinor: 1250 });
    expect(onError).not.toHaveBeenCalled();
    expect(button.disabled).toBe(false);
  });

  it('surfaces push errors through onError', async () => {
    const terminal = makeTerminalMock();
    terminal.collectPaymentMethod.mockResolvedValue({ error: 'x' });
    mockFetchRoutes();
    await import('../../static/js/pos/terminal.js');
    const button = document.createElement('button');
    const onError = vi.fn();
    await window.setupTerminalButton({ button, getAmount: () => 10, onError });
    button.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(onError).toHaveBeenCalledWith('ألغيت العملية أو تعذرت قراءة البطاقة.');
    expect(button.disabled).toBe(false);
  });
});
