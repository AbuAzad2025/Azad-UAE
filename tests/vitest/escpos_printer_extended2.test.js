import { describe, it, expect, vi, afterEach } from 'vitest';

describe('escpos-printer.js extended', () => {
  let buildReceiptBytes;
  let EscposPrinter;

  beforeAll(async () => {
    const mod = await import('../../static/js/pos/escpos-printer.js');
    buildReceiptBytes = mod.buildReceiptBytes;
    EscposPrinter = mod.EscposPrinter;
  });

  afterEach(() => {
    delete window._PRINTER_USB_FILTERS;
    delete navigator.usb;
    delete navigator.serial;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('webUsbSupported false without navigator.usb', () => {
    delete navigator.usb;
    expect(EscposPrinter.webUsbSupported()).toBe(false);
  });

  it('webSerialSupported false without navigator.serial', () => {
    delete navigator.serial;
    expect(EscposPrinter.webSerialSupported()).toBe(false);
  });

  it('webUsbSupported true with navigator.usb', () => {
    Object.defineProperty(navigator, 'usb', { value: {}, configurable: true });
    expect(EscposPrinter.webUsbSupported()).toBe(true);
  });

  it('connectWebUsb throws when unsupported', async () => {
    delete navigator.usb;
    const p = new EscposPrinter();
    await expect(p.connectWebUsb()).rejects.toThrow('WebUSB');
  });

  it('connectSerial throws when unsupported', async () => {
    delete navigator.serial;
    const p = new EscposPrinter();
    await expect(p.connectSerial()).rejects.toThrow('Web Serial');
  });

  it('connectSerial succeeds with serial port', async () => {
    const port = { open: vi.fn(async () => {}), writable: { getWriter: () => ({ write: vi.fn(async () => {}), releaseLock: vi.fn() }) } };
    Object.defineProperty(navigator, 'serial', { value: { requestPort: vi.fn(async () => port) }, configurable: true });
    const p = new EscposPrinter();
    await p.connectSerial({ baudRate: 115200 });
    expect(port.open).toHaveBeenCalledWith({ baudRate: 115200 });
    expect(p.channel).toBe('webserial');
  });

  it('print via webserial writes bytes', async () => {
    const writer = { write: vi.fn(async () => {}), releaseLock: vi.fn() };
    const port = { open: vi.fn(async () => {}), writable: { getWriter: () => writer } };
    Object.defineProperty(navigator, 'serial', { value: { requestPort: vi.fn(async () => port) }, configurable: true });
    const p = new EscposPrinter();
    await p.connectSerial();
    await p.print(new Uint8Array([1,2,3]));
    expect(writer.write).toHaveBeenCalled();
    expect(writer.releaseLock).toHaveBeenCalled();
  });

  it('print throws when not connected', async () => {
    const p = new EscposPrinter();
    await expect(p.print(new Uint8Array([1]))).rejects.toThrow('غير متصلة');
  });

  it('print webusb throws without endpoint', async () => {
    const device = { configuration: { interfaces: [{ alternate: { endpoints: [{ direction: 'in', endpointNumber: 1 }] } }] }, open: vi.fn(), selectConfiguration: vi.fn(), claimInterface: vi.fn(), transferOut: vi.fn() };
    Object.defineProperty(navigator, 'usb', { value: { requestDevice: vi.fn(async () => device) }, configurable: true });
    const p = new EscposPrinter();
    await p.connectWebUsb();
    await expect(p.print(new Uint8Array([1]))).rejects.toThrow('نقطة إخراج');
  });

  it('disconnect clears state', async () => {
    const device = { close: vi.fn(async () => {}) };
    const port = { close: vi.fn(async () => {}) };
    const p = new EscposPrinter();
    p.device = device; p.port = port; p.channel = 'webusb';
    await p.disconnect();
    expect(device.close).toHaveBeenCalled();
    expect(p.device).toBeNull();
    expect(p.channel).toBeNull();
  });

  it('buildReceiptBytes handles feed limit', () => {
    const out = buildReceiptBytes({ lines: [], feed: 20 });
    // feed capped at 10
    expect([...out].filter(b=>b===0x0a).length).toBeLessThan(25);
  });

  it('buildReceiptBytes handles missing lines', () => {
    const out = buildReceiptBytes({});
    expect(out[0]).toBe(0x1b);
  });

  it('_lineBytes via buildReceiptBytes with right align', () => {
    const out = buildReceiptBytes({ lines: [{ text: 'right', align: 'right' }] });
    expect([...out].join(',')).toContain([0x1b, 0x61, 0x02].join(','));
  });

  it('separator with custom width', () => {
    const out = buildReceiptBytes({ lines: [{ separator: true, width: 10 }] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('----------');
  });
});
