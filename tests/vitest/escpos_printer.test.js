import { describe, it, expect, vi, afterEach } from 'vitest';

describe('escpos-printer.js', () => {
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
    vi.useRealTimers();
  });

  it('buildReceiptBytes starts with init command', () => {
    const out = buildReceiptBytes({ lines: [] });
    expect([out[0], out[1]]).toEqual([0x1b, 0x40]);
  });

  it('centered bold line has alignment and emphasis bytes', () => {
    const out = buildReceiptBytes({ lines: [{ text: 'Hi', align: 'center', bold: true }] });
    const arr = [...out];
    expect(arr).toContain(0x1b);
    // ESC a 01 center
    expect(arr.join(',')).toContain([0x1b, 0x61, 0x01].join(','));
    // ESC E 01 bold on
    expect(arr.join(',')).toContain([0x1b, 0x45, 0x01].join(','));
  });

  it('double size emits GS ! 0x11', () => {
    const out = buildReceiptBytes({ lines: [{ text: 'Big', double: true }] });
    expect([...out].join(',')).toContain([0x1d, 0x21, 0x11].join(','));
  });

  it('separator line renders dashes', () => {
    const out = buildReceiptBytes({ lines: [{ separator: true }] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('--------------------------------');
  });

  it('adds feed lines', () => {
    const out = buildReceiptBytes({ lines: [], feed: 3 });
    const arr = [...out];
    const feedLines = arr.filter(b => b === 0x0a).length;
    expect(feedLines).toBeGreaterThanOrEqual(3);
  });

  it('adds open_drawer command when requested', () => {
    const out = buildReceiptBytes({ lines: [], open_drawer: true });
    const arr = [...out];
    expect(arr.join(',')).toContain([0x1b, 0x70, 0x00, 0x19, 0xfa].join(','));
  });

  it('adds cut command by default', () => {
    const out = buildReceiptBytes({ lines: [] });
    const arr = [...out];
    // GS V 0x00 cut
    expect(arr.includes(0x1d)).toBe(true);
    expect(arr.includes(0x56)).toBe(true);
  });

  it('can disable cut', () => {
    const withCut = buildReceiptBytes({ lines: [] });
    const withoutCut = buildReceiptBytes({ lines: [], cut: false });
    expect(withoutCut.length).toBeLessThan(withCut.length);
  });

  it('handles string lines', () => {
    const out = buildReceiptBytes({ lines: ['Hello', 'World'] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('Hello');
    expect(text).toContain('World');
  });

  function makeUsbDevice() {
    return {
      configuration: null,
      open: vi.fn(async () => {}),
      selectConfiguration: vi.fn(async () => {}),
      claimInterface: vi.fn(async () => {}),
      transferOut: vi.fn(async () => ({ status: 'ok', bytesWritten: 0 })),
    };
  }

  function setUsb(usb) {
    Object.defineProperty(navigator, 'usb', { value: usb, configurable: true });
  }

  it('falls back to empty filters without a USB filter config', async () => {
    const usb = { requestDevice: vi.fn(() => Promise.resolve(makeUsbDevice())) };
    setUsb(usb);
    const printer = new EscposPrinter();
    await printer.connectWebUsb();
    expect(usb.requestDevice).toHaveBeenCalledWith({ filters: [] });
  });

  it('passes tenant USB filters to requestDevice when configured', async () => {
    const filters = [{ vendorId: 0x1234, productId: 0xabcd }];
    window._PRINTER_USB_FILTERS = filters;
    const usb = { requestDevice: vi.fn(() => Promise.resolve(makeUsbDevice())) };
    setUsb(usb);
    const printer = new EscposPrinter();
    await printer.connectWebUsb();
    expect(usb.requestDevice).toHaveBeenCalledWith({ filters });
  });

  it('times out a wedged USB transfer after 10 seconds', async () => {
    vi.useFakeTimers();
    const device = {
      configuration: {
        interfaces: [{ alternate: { endpoints: [{ direction: 'out', endpointNumber: 1 }] } }],
      },
      open: vi.fn(async () => {}),
      claimInterface: vi.fn(async () => {}),
      transferOut: vi.fn(() => new Promise(() => {})),
    };
    const usb = { requestDevice: vi.fn(() => Promise.resolve(device)) };
    setUsb(usb);
    const printer = new EscposPrinter();
    await printer.connectWebUsb();
    const assertion = expect(printer.print(new Uint8Array([0x1b, 0x40]))).rejects.toThrow(
      'تجاوزت مهلة الطباعة عبر USB.'
    );
    await vi.advanceTimersByTimeAsync(10000);
    await assertion;
  });

  it('propagates a fast transferOut error without a timeout', async () => {
    const device = {
      configuration: {
        interfaces: [{ alternate: { endpoints: [{ direction: 'out', endpointNumber: 1 }] } }],
      },
      open: vi.fn(async () => {}),
      claimInterface: vi.fn(async () => {}),
      transferOut: vi.fn(async () => {
        throw new Error('bus reset');
      }),
    };
    const usb = { requestDevice: vi.fn(() => Promise.resolve(device)) };
    setUsb(usb);
    const printer = new EscposPrinter();
    await printer.connectWebUsb();
    await expect(printer.print(new Uint8Array([0x1b]))).rejects.toThrow('bus reset');
  });
});
