import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let fetchMock;
let escposInstances;

class EscposPrinterMock {
  constructor() {
    this.channel = null;
    escposInstances.push(this);
  }
  connectWebUsb = vi.fn(async function connectWebUsb() {
    this.channel = 'webusb';
  });
  connectSerial = vi.fn(async function connectSerial() {
    this.channel = 'serial';
  });
  print = vi.fn(async () => {});
}

function defaultFetch({ tickets, ticketsOk = true, agentOk = true, agentStatus = 200 } = {}) {
  fetchMock.mockImplementation((url) => {
    const u = String(url);
    if (u.includes('127.0.0.1:8567')) {
      return Promise.resolve({ ok: agentOk, status: agentStatus, json: () => Promise.resolve({}) });
    }
    if (u.includes('/pos/api/sale/')) {
      return Promise.resolve({
        ok: ticketsOk,
        json: () => Promise.resolve({ success: ticketsOk, tickets: ticketsOk ? tickets : [] }),
      });
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  });
}

describe('pos/print-tickets.js', () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    escposInstances = [];
    window.EscposPrinter = EscposPrinterMock;
    window.buildReceiptBytes = vi.fn(() => new Uint8Array([0x1b, 0x40]));
    delete window.printSaleTickets;
    delete window.printQueuedCartReceipt;
    vi.resetModules();
  });

  afterEach(() => {
    delete global.fetch;
    delete window.EscposPrinter;
    delete window.buildReceiptBytes;
    delete window.printSaleTickets;
    delete window.printQueuedCartReceipt;
    vi.resetModules();
  });

  it('exposes the ticket helpers on window', async () => {
    await import('../../static/js/pos/print-tickets.js');
    expect(typeof window.printSaleTickets).toBe('function');
    expect(typeof window.printQueuedCartReceipt).toBe('function');
  });

  it('returns a fetch failure summary when the tickets request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network'));
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(99);
    expect(summary).toEqual({ printed: 0, failed: ['fetch'] });
  });

  it('returns a fetch failure summary when json parsing fails', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.reject(new Error('bad json')) });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(99);
    expect(summary.failed).toEqual(['fetch']);
  });

  it('returns an empty summary when the response is not successful', async () => {
    defaultFetch({ tickets: [], ticketsOk: false });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary).toEqual({ printed: 0, failed: [] });
  });

  it('delivers agent tickets to the hardware agent', async () => {
    defaultFetch({
      tickets: [{ connection_type: 'agent', printer: 'main', content: { lines: [] }, printer_name: 'Main' }],
    });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary).toEqual({ printed: 1, failed: [] });
    const agentCall = fetchMock.mock.calls.find(([url]) => String(url).includes('8567'));
    expect(agentCall).toBeTruthy();
    expect(JSON.parse(agentCall[1].body)).toEqual({ printer: 'main', content: { lines: [] } });
  });

  it('records agent failures using the printer name', async () => {
    defaultFetch({
      tickets: [{ connection_type: 'agent', printer_name: 'Kitchen' }],
      agentOk: false,
      agentStatus: 500,
    });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary).toEqual({ printed: 0, failed: ['Kitchen'] });
  });

  it('falls back to unknown for unlabeled agent failures', async () => {
    defaultFetch({ tickets: [{ connection_type: 'agent' }], agentOk: false, agentStatus: 500 });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary.failed).toEqual(['unknown']);
  });

  it('prints webusb browser tickets over the escpos module', async () => {
    defaultFetch({
      tickets: [{ connection_type: 'webusb', content: { lines: [] }, printer_name: 'USB' }],
    });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary).toEqual({ printed: 1, failed: [] });
    expect(escposInstances).toHaveLength(1);
    const inst = escposInstances[0];
    expect(inst.connectWebUsb).toHaveBeenCalledTimes(1);
    expect(inst.print).toHaveBeenCalledTimes(1);
    expect(inst.print).toHaveBeenCalledWith(new Uint8Array([0x1b, 0x40]));
    expect(inst.channel).toBe('webusb');
  });

  it('uses the serial connection for webserial browser tickets', async () => {
    defaultFetch({
      tickets: [{ connection_type: 'webserial', content: { lines: [] }, printer_name: 'S' }],
    });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary.printed).toBe(1);
    expect(escposInstances[0].connectSerial).toHaveBeenCalledTimes(1);
  });

  it('reuses a single escpos printer across browser tickets', async () => {
    defaultFetch({
      tickets: [
        { connection_type: 'webusb', content: { lines: [] }, printer_name: 'A' },
        { connection_type: 'webusb', content: { lines: [] }, printer_name: 'B' },
      ],
    });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary).toEqual({ printed: 2, failed: [] });
    expect(escposInstances).toHaveLength(1);
  });

  it('reports browser tickets as failed when the escpos module is missing', async () => {
    delete window.EscposPrinter;
    delete window.buildReceiptBytes;
    defaultFetch({ tickets: [{ connection_type: 'webusb', printer_name: 'USB' }] });
    await import('../../static/js/pos/print-tickets.js');
    const summary = await window.printSaleTickets(1);
    expect(summary.failed).toEqual(['USB']);
  });

  it('prints the queued cart receipt to the agent', async () => {
    defaultFetch();
    await import('../../static/js/pos/print-tickets.js');
    const ok = await window.printQueuedCartReceipt(
      [{ qty: 2, name: 'Cola' }, { qty: 1, name: 'Bread' }],
      { total: 12.5 },
      { sale_reference: 'OFF-7' }
    );
    expect(ok).toBe(true);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('8567');
    const body = JSON.parse(opts.body);
    expect(body.content.cut).toBe(true);
    expect(body.content.open_drawer).toBe(true);
    expect(body.content.lines[0].text).toBe('OFF-7');
    expect(body.content.lines.map((l) => l.text).join('|')).toContain('2 x Cola');
    expect(body.content.lines.map((l) => l.text).join('|')).toContain('TOTAL 12.500');
  });

  it('uses OFFLINE as the default queued reference', async () => {
    defaultFetch();
    await import('../../static/js/pos/print-tickets.js');
    await window.printQueuedCartReceipt([], {});
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.content.lines[0].text).toBe('OFFLINE');
    expect(body.content.lines.some((l) => l.text && l.text.startsWith('TOTAL'))).toBe(false);
  });

  it('returns false when the queued receipt agent call fails', async () => {
    defaultFetch({ agentOk: false });
    await import('../../static/js/pos/print-tickets.js');
    const ok = await window.printQueuedCartReceipt([], { total: 1 });
    expect(ok).toBe(false);
  });

  it('returns false when the queued receipt agent call throws', async () => {
    fetchMock.mockRejectedValue(new Error('down'));
    await import('../../static/js/pos/print-tickets.js');
    const ok = await window.printQueuedCartReceipt([{ qty: 1, name: 'X' }], { total: 1 });
    expect(ok).toBe(false);
  });

  it('escPosSafe strips control characters and DEL', async () => {
    await import('../../static/js/pos/print-tickets.js');
    expect(window.escPosSafe('A\x00B\x1bC\x7fD')).toBe('ABCD');
    expect(window.escPosSafe('sale\nItem\t')).toBe('saleItem');
    expect(window.escPosSafe(undefined)).toBe('');
    expect(window.escPosSafe(null)).toBe('');
    expect(window.escPosSafe('plain 123')).toBe('plain 123');
  });

  it('sanitizes product names before they reach the agent payload', async () => {
    defaultFetch();
    await import('../../static/js/pos/print-tickets.js');
    const ok = await window.printQueuedCartReceipt([{ qty: 1, name: 'Col\x1ba\x00B' }], { total: 5 });
    expect(ok).toBe(true);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.content.lines.map((l) => l.text).join('|')).toContain('1 x ColaB');
  });

  it('attaches an abort signal to hardware agent fetches', async () => {
    defaultFetch();
    await import('../../static/js/pos/print-tickets.js');
    await window.printQueuedCartReceipt([], {});
    const opts = fetchMock.mock.calls[0][1];
    expect(opts.signal).toBeInstanceOf(AbortSignal);
  });
});
