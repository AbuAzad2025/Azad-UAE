import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let PosScaleSerial;
let parseScaleFrame;

beforeEach(async () => {
  delete navigator.serial;
  const mod = await import('../../static/js/pos/scale-serial.js');
  PosScaleSerial = mod.PosScaleSerial;
  parseScaleFrame = mod.parseScaleFrame;
});

afterEach(() => {
  delete navigator.serial;
  vi.restoreAllMocks();
});

describe('PosScaleSerial.isSupported', () => {
  it('returns false when navigator.serial is undefined', () => {
    delete navigator.serial;
    expect(PosScaleSerial.isSupported()).toBe(false);
  });

  it('returns true when navigator.serial exists', () => {
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn() },
      configurable: true,
      writable: true,
    });
    expect(PosScaleSerial.isSupported()).toBe(true);
  });
});

describe('PosScaleSerial.connect', () => {
  it('returns false when not supported', async () => {
    delete navigator.serial;
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    const result = await scale.connect();
    expect(result).toBe(false);
    expect(onError).toHaveBeenCalledWith(expect.any(String));
  });

  it('calls onError when requestPort throws', async () => {
    const requestPort = vi.fn().mockRejectedValue(new Error('User cancelled'));
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    const result = await scale.connect();

    expect(result).toBe(false);
    expect(onError).toHaveBeenCalledWith('User cancelled');
    expect(scale.connected).toBe(false);
  });

  it('calls onError with fallback message when error has no message', async () => {
    const requestPort = vi.fn().mockRejectedValue({});
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    const result = await scale.connect();

    expect(result).toBe(false);
    expect(onError).toHaveBeenCalled();
  });

  it('opens port and sets connected on success', async () => {
    const open = vi.fn();
    const requestPort = vi.fn().mockResolvedValue({ open });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const scale = new PosScaleSerial({ onError: vi.fn() });
    const result = await scale.connect();

    expect(result).toBe(true);
    expect(scale.connected).toBe(true);
    expect(scale.port).toBeDefined();
    expect(requestPort).toHaveBeenCalled();
    expect(open).toHaveBeenCalledWith({ baudRate: 9600, dataBits: 8, parity: 'none', stopBits: 1 });
  });

  it('passes custom baudRate to port.open', async () => {
    const open = vi.fn();
    const requestPort = vi.fn().mockResolvedValue({ open });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const scale = new PosScaleSerial({ onError: vi.fn(), baudRate: 19200 });
    await scale.connect();

    expect(open).toHaveBeenCalledWith({ baudRate: 19200, dataBits: 8, parity: 'none', stopBits: 1 });
  });
});

describe('PosScaleSerial.disconnect', () => {
  it('resets state and cancels reader', async () => {
    const cancelReader = vi.fn().mockResolvedValue(undefined);
    const closePort = vi.fn().mockResolvedValue(undefined);
    const requestPort = vi.fn().mockResolvedValue({
      open: vi.fn(),
      readable: {
        getReader: () => ({
          read: vi.fn(),
          cancel: cancelReader,
          releaseLock: vi.fn(),
        }),
      },
      close: closePort,
    });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const scale = new PosScaleSerial({ onError: vi.fn() });
    await scale.connect();
    scale.lastWeightKg = 1.5;
    scale._pendingCount = 3;

    await scale.disconnect();

    expect(scale.connected).toBe(false);
    expect(scale.port).toBeNull();
    expect(scale.reader).toBeNull();
    expect(scale.lastWeightKg).toBe(0);
    expect(scale._pendingCount).toBe(0);
  });

  it('handles disconnect when no port or reader', async () => {
    const scale = new PosScaleSerial();
    scale.connected = false;
    await scale.disconnect();
    expect(scale.connected).toBe(false);
    expect(scale.lastWeightKg).toBe(0);
  });

  it('handles reader.cancel rejection gracefully', async () => {
    const cancelReader = vi.fn().mockRejectedValue(new Error('cancel failed'));
    const closePort = vi.fn().mockResolvedValue(undefined);
    const requestPort = vi.fn().mockResolvedValue({
      open: vi.fn(),
      readable: {
        getReader: () => ({
          read: vi.fn(),
          cancel: cancelReader,
          releaseLock: vi.fn(),
        }),
      },
      close: closePort,
    });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const scale = new PosScaleSerial({ onError: vi.fn() });
    await scale.connect();
    await scale.disconnect();
    expect(scale.connected).toBe(false);
  });

  it('handles port.close rejection gracefully', async () => {
    const cancelReader = vi.fn().mockResolvedValue(undefined);
    const closePort = vi.fn().mockRejectedValue(new Error('close failed'));
    const requestPort = vi.fn().mockResolvedValue({
      open: vi.fn(),
      readable: {
        getReader: () => ({
          read: vi.fn(),
          cancel: cancelReader,
          releaseLock: vi.fn(),
        }),
      },
      close: closePort,
    });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const scale = new PosScaleSerial({ onError: vi.fn() });
    await scale.connect();
    await scale.disconnect();
    expect(scale.connected).toBe(false);
    expect(scale.port).toBeNull();
  });
});

describe('PosScaleSerial._ingest', () => {
  it('splits buffer on newline and calls _handleLine', () => {
    const scale = new PosScaleSerial();
    const spy = vi.spyOn(scale, '_handleLine');

    scale._ingest('1.234\n5.678\n');

    expect(spy).toHaveBeenCalledWith('1.234');
    expect(spy).toHaveBeenCalledWith('5.678');
  });

  it('handles carriage return line endings', () => {
    const scale = new PosScaleSerial();
    const spy = vi.spyOn(scale, '_handleLine');

    scale._ingest('1.234\r\n5.678\r\n');

    expect(spy).toHaveBeenCalledWith('1.234');
    expect(spy).toHaveBeenCalledWith('5.678');
  });

  it('handles multi-line chunks', () => {
    const scale = new PosScaleSerial();
    const spy = vi.spyOn(scale, '_handleLine');

    scale._ingest('line1\nline2\nline3\n');

    expect(spy).toHaveBeenCalledTimes(3);
    expect(spy).toHaveBeenCalledWith('line1');
    expect(spy).toHaveBeenCalledWith('line2');
    expect(spy).toHaveBeenCalledWith('line3');
  });

  it('trims buffer when it exceeds 128 chars', () => {
    const scale = new PosScaleSerial();
    const longChunk = 'x'.repeat(200);
    scale._ingest(longChunk);
    expect(scale._buffer.length).toBeLessThanOrEqual(64);
  });

  it('does not trim buffer when under 128 chars', () => {
    const scale = new PosScaleSerial();
    scale._ingest('hello');
    expect(scale._buffer).toBe('hello');
  });

  it('preserves partial line in buffer', () => {
    const scale = new PosScaleSerial();
    scale._ingest('1.234');
    expect(scale._buffer).toBe('1.234');
  });

  it('handles chunk with no newline', () => {
    const scale = new PosScaleSerial();
    const spy = vi.spyOn(scale, '_handleLine');
    scale._ingest('no newline here');
    expect(spy).not.toHaveBeenCalled();
    expect(scale._buffer).toBe('no newline here');
  });
});

describe('PosScaleSerial._handleLine', () => {
  it('fires callback after 3 stable reads of same weight', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('1.234');
    expect(onStableWeight).not.toHaveBeenCalled();

    scale._handleLine('1.234');
    expect(onStableWeight).not.toHaveBeenCalled();

    scale._handleLine('1.234');
    expect(onStableWeight).toHaveBeenCalledWith(1.234);
    expect(scale.lastWeightKg).toBe(1.234);
  });

  it('unstable reading does not reset the stable counter', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('1.234');
    scale._handleLine('1.234');
    expect(onStableWeight).not.toHaveBeenCalled();

    scale._handleLine('US,NT,- 0.500kg');
    expect(onStableWeight).not.toHaveBeenCalled();

    scale._handleLine('1.234');
    expect(onStableWeight).toHaveBeenCalledWith(1.234);
  });

  it('resets count when weight changes beyond epsilon', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('1.234');
    scale._handleLine('1.234');
    scale._handleLine('1.234');
    expect(onStableWeight).toHaveBeenCalledTimes(1);

    scale._handleLine('2.500');
    scale._handleLine('2.500');
    scale._handleLine('2.500');
    expect(onStableWeight).toHaveBeenCalledTimes(2);
    expect(onStableWeight).toHaveBeenLastCalledWith(2.5);
  });

  it('ignores non-stable frames', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('US,NT,- 1.000kg');
    scale._handleLine('OL,+ 9.999kg');
    expect(onStableWeight).not.toHaveBeenCalled();
    expect(scale._pendingCount).toBe(0);
  });

  it('ignores frames that return null from parseScaleFrame', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('');
    scale._handleLine('abc');
    scale._handleLine(null);
    expect(onStableWeight).not.toHaveBeenCalled();
  });

  it('resets pending count after callback fires', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('1.000');
    scale._handleLine('1.000');
    scale._handleLine('1.000');
    expect(scale._pendingCount).toBe(0);

    scale._handleLine('1.000');
    expect(scale._pendingCount).toBe(1);
  });

  it('calls onStableWeight on third consecutive stable read', () => {
    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });

    scale._handleLine('ST,GS,+  0.500kg');
    scale._handleLine('ST,GS,+  0.500kg');
    scale._handleLine('ST,GS,+  0.500kg');
    expect(onStableWeight).toHaveBeenCalledWith(0.5);
  });
});

describe('PosScaleSerial.getLastWeight', () => {
  it('returns 0 initially', () => {
    const scale = new PosScaleSerial();
    expect(scale.getLastWeight()).toBe(0);
  });

  it('returns stored weight after stable reads', () => {
    const scale = new PosScaleSerial({ onStableWeight: vi.fn() });
    scale._handleLine('1.234');
    scale._handleLine('1.234');
    scale._handleLine('1.234');
    expect(scale.getLastWeight()).toBe(1.234);
  });

  it('returns 0 after disconnect', async () => {
    const scale = new PosScaleSerial({ onStableWeight: vi.fn() });
    scale._handleLine('1.000');
    scale._handleLine('1.000');
    scale._handleLine('1.000');
    scale.lastWeightKg = 1.0;
    await scale.disconnect();
    expect(scale.getLastWeight()).toBe(0);
  });
});

describe('PosScaleSerial._fail', () => {
  it('calls onError with message', () => {
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    scale._fail('Connection lost');
    expect(onError).toHaveBeenCalledWith('Connection lost');
  });

  it('uses default message when none provided', () => {
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    scale._fail();
    expect(onError).toHaveBeenCalledWith('Scale error');
  });

  it('does not throw when onError is null', () => {
    const scale = new PosScaleSerial();
    expect(() => scale._fail('error')).not.toThrow();
  });

  it('converts non-string message to string', () => {
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    scale._fail(42);
    expect(onError).toHaveBeenCalledWith('42');
  });
});

describe('PosScaleSerial constructor', () => {
  it('initializes with default values', () => {
    const scale = new PosScaleSerial();
    expect(scale.onStableWeight).toBeNull();
    expect(scale.onError).toBeNull();
    expect(scale.baudRate).toBe(9600);
    expect(scale.port).toBeNull();
    expect(scale.reader).toBeNull();
    expect(scale.connected).toBe(false);
    expect(scale.lastWeightKg).toBe(0);
    expect(scale._pendingKg).toBe(0);
    expect(scale._pendingCount).toBe(0);
    expect(scale._buffer).toBe('');
  });

  it('accepts callbacks and baudRate', () => {
    const onStableWeight = vi.fn();
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight, onError, baudRate: 4800 });
    expect(scale.onStableWeight).toBe(onStableWeight);
    expect(scale.onError).toBe(onError);
    expect(scale.baudRate).toBe(4800);
  });

  it('handles non-function callbacks gracefully', () => {
    const scale = new PosScaleSerial({ onStableWeight: 'not a fn', onError: 123 });
    expect(scale.onStableWeight).toBeNull();
    expect(scale.onError).toBeNull();
  });
});

describe('PosScaleSerial._readLoop', () => {
  it('reads from port and calls _ingest', async () => {
    const weightLine = '1.234\n';
    const chunks = [
      { value: new TextEncoder().encode(weightLine), done: false },
      { value: new TextEncoder().encode(weightLine), done: false },
      { value: new TextEncoder().encode(weightLine), done: false },
      { value: new TextEncoder().encode(weightLine), done: false },
      { value: undefined, done: true },
    ];
    let readIdx = 0;
    const read = vi.fn(() => Promise.resolve(chunks[readIdx++]));
    const releaseLock = vi.fn();
    const cancel = vi.fn().mockResolvedValue(undefined);
    const port = {
      open: vi.fn(),
      readable: {
        getReader: () => ({ read, releaseLock, cancel }),
      },
      close: vi.fn().mockResolvedValue(undefined),
    };
    const requestPort = vi.fn().mockResolvedValue(port);
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const onStableWeight = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight });
    await scale.connect();

    await new Promise(r => setTimeout(r, 100));

    expect(onStableWeight).toHaveBeenCalled();
    expect(onStableWeight).toHaveBeenCalledWith(1.234);
  });

  it('calls onError when read throws while connected', async () => {
    const read = vi.fn().mockRejectedValue(new Error('Device lost'));
    const releaseLock = vi.fn();
    const port = {
      open: vi.fn(),
      readable: {
        getReader: () => ({ read, releaseLock, cancel: vi.fn() }),
      },
      close: vi.fn().mockResolvedValue(undefined),
    };
    const requestPort = vi.fn().mockResolvedValue(port);
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError });
    await scale.connect();

    await new Promise(r => setTimeout(r, 50));

    expect(onError).toHaveBeenCalledWith('Device lost');
  });
});

describe('setupPosScaleUI', () => {
  let setupPosScaleUI;

  beforeEach(async () => {
    delete navigator.serial;
    vi.resetModules();
    const mod = await import('../../static/js/pos/scale-serial.js');
    PosScaleSerial = mod.PosScaleSerial;
    setupPosScaleUI = window.setupPosScaleUI;
  });

  it('returns null when button is missing', () => {
    const scale = new PosScaleSerial();
    const result = setupPosScaleUI({ button: null, scale });
    expect(result).toBeNull();
  });

  it('returns null when scale is missing', () => {
    const btn = document.createElement('button');
    const result = setupPosScaleUI({ button: btn, scale: null });
    expect(result).toBeNull();
  });

  it('hides button when not supported', () => {
    delete navigator.serial;
    const btn = document.createElement('button');
    btn.title = 'Connect';
    const scale = new PosScaleSerial();

    setupPosScaleUI({ button: btn, scale });

    expect(btn.classList.contains('d-none')).toBe(true);
  });

  it('returns scale instance when supported', () => {
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn() },
      configurable: true,
      writable: true,
    });
    const btn = document.createElement('button');
    btn.title = 'Connect';
    const scale = new PosScaleSerial();

    const result = setupPosScaleUI({ button: btn, scale });

    expect(result).toBe(scale);
  });

  it('toggles button visual state on connect/disconnect', async () => {
    const open = vi.fn().mockResolvedValue(undefined);
    const requestPort = vi.fn().mockResolvedValue({
      open,
      close: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort },
      configurable: true,
      writable: true,
    });

    const btn = document.createElement('button');
    btn.title = 'Connect';
    const scale = new PosScaleSerial({ onError: vi.fn() });

    setupPosScaleUI({ button: btn, scale, connectedTitle: 'Disconnect', disconnectedTitle: 'Connect' });

    expect(btn.title).toBe('Connect');
    expect(btn.classList.contains('pos-scale-live')).toBe(false);

    btn.click();
    await new Promise(r => setTimeout(r, 10));

    expect(btn.title).toBe('Disconnect');
    expect(btn.classList.contains('pos-scale-live')).toBe(true);

    btn.click();
    await new Promise(r => setTimeout(r, 10));

    expect(btn.title).toBe('Connect');
    expect(btn.classList.contains('pos-scale-live')).toBe(false);
  });

  it('uses button title as fallback for disconnectedTitle', () => {
    Object.defineProperty(navigator, 'serial', {
      value: { requestPort: vi.fn() },
      configurable: true,
      writable: true,
    });

    const btn = document.createElement('button');
    btn.title = 'My Scale';
    const scale = new PosScaleSerial();

    setupPosScaleUI({ button: btn, scale });

    expect(btn.title).toBe('My Scale');
  });
});
