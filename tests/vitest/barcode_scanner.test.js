import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

async function importScanner() {
  await import('../../static/js/barcode-scanner.js');
  return {
    BarcodeScanner: window.BarcodeScanner,
    CameraBarcodeScanner: window.CameraBarcodeScanner,
    setupCameraScanUI: window.setupCameraScanUI,
  };
}

function fireKey(el, init) {
  el.dispatchEvent(new KeyboardEvent('keypress', { bubbles: true, cancelable: true, ...init }));
}

const originalMediaDevices = navigator.mediaDevices;

beforeEach(() => {
  document.body.innerHTML = '';
  vi.resetModules();
});

afterEach(() => {
  document.body.innerHTML = '';
  delete window.BarcodeDetector;
  delete window.BarcodeScanner;
  delete window.CameraBarcodeScanner;
  delete window.setupCameraScanUI;
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: originalMediaDevices });
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('BarcodeScanner', () => {
  it('accumulates keys and fires onScan on Enter', async () => {
    const { BarcodeScanner } = await importScanner();
    const onScan = vi.fn();
    const s = new BarcodeScanner({ onScan });
    s.start();
    fireKey(document, { key: '1' });
    fireKey(document, { key: '2' });
    fireKey(document, { key: '3' });
    fireKey(document, { key: 'Enter' });
    expect(onScan).toHaveBeenCalledWith('123');
    expect(s.buffer).toBe('');
    s.stop();
  });

  it('does not fire onScan below minLength', async () => {
    const { BarcodeScanner } = await importScanner();
    const onScan = vi.fn();
    const s = new BarcodeScanner({ onScan, minLength: 4 });
    s.start();
    fireKey(document, { key: '1' });
    fireKey(document, { key: '2' });
    fireKey(document, { key: '3' });
    fireKey(document, { key: 'Enter' });
    expect(onScan).not.toHaveBeenCalled();
    s.stop();
  });

  it('clears buffer after scanDelay', async () => {
    vi.useFakeTimers();
    try {
      const { BarcodeScanner } = await importScanner();
      const onScan = vi.fn();
      const s = new BarcodeScanner({ onScan, scanDelay: 100 });
      s.start();
      fireKey(document, { key: '1' });
      fireKey(document, { key: '2' });
      expect(s.buffer).toBe('12');
      vi.advanceTimersByTime(110);
      expect(s.buffer).toBe('');
      fireKey(document, { key: 'Enter' });
      expect(onScan).not.toHaveBeenCalled();
      s.stop();
    } finally {
      vi.useRealTimers();
    }
  });

  it('ignores keys in non-barcode input fields', async () => {
    const { BarcodeScanner } = await importScanner();
    const onScan = vi.fn();
    const s = new BarcodeScanner({ onScan });
    s.start();
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireKey(input, { key: '1' });
    expect(s.buffer).toBe('');
    fireKey(document, { key: 'Enter' });
    expect(onScan).not.toHaveBeenCalled();
    s.stop();
  });

  it('accepts keys in barcode-input fields', async () => {
    const { BarcodeScanner } = await importScanner();
    const onScan = vi.fn();
    const s = new BarcodeScanner({ onScan, minLength: 2 });
    s.start();
    const input = document.createElement('input');
    input.classList.add('barcode-input');
    document.body.appendChild(input);
    fireKey(input, { key: '1' });
    fireKey(input, { key: '2' });
    fireKey(input, { key: 'Enter' });
    expect(onScan).toHaveBeenCalledWith('12');
    s.stop();
  });

  it('stops listening after stop()', async () => {
    const { BarcodeScanner } = await importScanner();
    const onScan = vi.fn();
    const s = new BarcodeScanner({ onScan });
    s.start();
    s.stop();
    fireKey(document, { key: '1' });
    fireKey(document, { key: '2' });
    fireKey(document, { key: '3' });
    fireKey(document, { key: 'Enter' });
    expect(onScan).not.toHaveBeenCalled();
    expect(s.active).toBe(false);
  });
});

describe('CameraBarcodeScanner', () => {
  function makeVideo() {
    const video = document.createElement('video');
    Object.defineProperty(video, 'readyState', { configurable: true, value: 4 });
    return video;
  }

  function installDetector({ formats = ['ean_13', 'code_128'], result = [] } = {}) {
    const detect = vi.fn(async () => result);
    window.BarcodeDetector = class {
      static getSupportedFormats = vi.fn(async () => formats);
      constructor(opts) {
        this.opts = opts;
      }
      detect = detect;
    };
    return detect;
  }

  it('isSupported requires getUserMedia and BarcodeDetector', async () => {
    const { CameraBarcodeScanner } = await importScanner();
    expect(CameraBarcodeScanner.isSupported()).toBe(false);
    window.BarcodeDetector = class {};
    expect(CameraBarcodeScanner.isSupported()).toBe(false);
  });

  it('isSupported true with both APIs present', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    window.BarcodeDetector = class {};
    const { CameraBarcodeScanner } = await importScanner();
    expect(CameraBarcodeScanner.isSupported()).toBe(true);
  });

  it('start returns false and reports error when BarcodeDetector missing', async () => {
    const onError = vi.fn();
    const { CameraBarcodeScanner } = await importScanner();
    const cam = new CameraBarcodeScanner(makeVideo(), { onError });
    await expect(cam.start()).resolves.toBe(false);
    expect(onError).toHaveBeenCalled();
  });

  it('start initializes stream and schedules scanning', async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }, { stop }] };
    const getUserMedia = vi.fn(async () => stream);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    installDetector({ result: [{ rawValue: '' }] });
    const { CameraBarcodeScanner } = await importScanner();
    const cam = new CameraBarcodeScanner(makeVideo(), { scanIntervalMs: 50 });
    await expect(cam.start()).resolves.toBe(true);
    expect(getUserMedia).toHaveBeenCalled();
    expect(play).toHaveBeenCalled();
    expect(cam.isScanning).toBe(true);
    cam.stop();
  });

  it('start reports camera error and stops on rejection', async () => {
    const onError = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => { throw new Error('denied'); }) },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    installDetector();
    const { CameraBarcodeScanner } = await importScanner();
    const cam = new CameraBarcodeScanner(makeVideo(), { onError });
    await expect(cam.start()).resolves.toBe(false);
    expect(onError).toHaveBeenCalled();
    expect(cam.isScanning).toBe(false);
  });

  it('scan invokes onScan and stops for new code', async () => {
    vi.useFakeTimers();
    try {
      const code = '1234567890123';
      const onScan = vi.fn();
      installDetector({ result: [{ rawValue: code }] });
      const { CameraBarcodeScanner } = await importScanner();
      const cam = new CameraBarcodeScanner(makeVideo(), { onScan, scanIntervalMs: 50 });
      cam.isScanning = true;
      cam.detector = new window.BarcodeDetector();
      await cam.scan();
      expect(onScan).toHaveBeenCalledWith(code);
      expect(cam.isScanning).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('scan skips duplicates within cooldown', async () => {
    vi.useFakeTimers();
    try {
      const code = '1234567890123';
      const onScan = vi.fn();
      installDetector({ result: [{ rawValue: code }] });
      const { CameraBarcodeScanner } = await importScanner();
      const cam = new CameraBarcodeScanner(makeVideo(), { onScan, scanIntervalMs: 50, duplicateCooldownMs: 2500 });
      cam.isScanning = true;
      cam._lastCode = code;
      cam._lastCodeAt = Date.now();
      await cam.scan();
      expect(onScan).not.toHaveBeenCalled();
      expect(cam.isScanning).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('detectBarcode returns null for no detector or empty results', async () => {
    const { CameraBarcodeScanner } = await importScanner();
    const cam = new CameraBarcodeScanner(makeVideo());
    await expect(cam.detectBarcode(makeVideo())).resolves.toBeNull();
    installDetector({ result: [] });
    const cam2 = new CameraBarcodeScanner(makeVideo());
    await expect(cam2.detectBarcode(makeVideo())).resolves.toBeNull();
  });

  it('scan keeps scanning when detection fails', async () => {
    vi.useFakeTimers();
    try {
      const onScan = vi.fn();
      installDetector({});
      window.BarcodeDetector = class {
        static getSupportedFormats = vi.fn(async () => ['ean_13']);
        constructor() {}
        async detect() {
          throw new Error('decode fail');
        }
      };
      const { CameraBarcodeScanner } = await importScanner();
      const cam = new CameraBarcodeScanner(makeVideo(), { onScan, scanIntervalMs: 50 });
      cam.isScanning = true;
      cam.detector = new window.BarcodeDetector();
      await cam.scan();
      expect(onScan).not.toHaveBeenCalled();
      expect(cam.isScanning).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('stop clears timer and stops stream tracks', async () => {
    vi.useFakeTimers();
    try {
      const stop = vi.fn();
      const stream = { getTracks: () => [{ stop }] };
      const { CameraBarcodeScanner } = await importScanner();
      const cam = new CameraBarcodeScanner(makeVideo());
      cam.isScanning = true;
      cam.stream = stream;
      cam._timer = setTimeout(() => {}, 1000);
      const video = makeVideo();
      video.srcObject = stream;
      cam.video = video;
      cam.stop();
      expect(stop).toHaveBeenCalled();
      expect(cam._timer).toBeNull();
      expect(cam.stream).toBeNull();
      expect(cam.video.srcObject).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('setupCameraScanUI', () => {
  function installSupport({ result = [{ rawValue: '1234567890123' }], getUserMedia, fail = false } = {}) {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] };
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: getUserMedia || vi.fn(async () => stream),
      },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    if (fail) {
      window.BarcodeDetector = class {
        static getSupportedFormats = vi.fn(async () => { throw new Error('boom'); });
      };
    } else {
      window.BarcodeDetector = class {
        static getSupportedFormats = vi.fn(async () => ['ean_13', 'code_128']);
        constructor() {}
        async detect() {
          return result;
        }
      };
    }
    Object.defineProperty(HTMLMediaElement.prototype, 'readyState', {
      configurable: true,
      get: () => 4,
    });
  }

  it('returns null and hides button when unsupported', async () => {
    const button = document.createElement('button');
    document.body.appendChild(button);
    const { setupCameraScanUI } = await importScanner();
    const ui = setupCameraScanUI({ button, onScan: vi.fn() });
    expect(ui).toBeNull();
    expect(button.classList.contains('d-none')).toBe(true);
  });

  it('builds overlay and reports scanned code', async () => {
    vi.useFakeTimers();
    try {
      installSupport();
      const button = document.createElement('button');
      document.body.appendChild(button);
      const onScan = vi.fn();
      const { setupCameraScanUI } = await importScanner();
      const ui = setupCameraScanUI({ button, onScan, onError: vi.fn() });
      expect(ui).not.toBeNull();
      button.click();
      await vi.advanceTimersByTimeAsync(100);
      expect(document.getElementById('cameraScanOverlay')).toBeTruthy();
      await vi.advanceTimersByTimeAsync(500);
      expect(onScan).toHaveBeenCalledWith('1234567890123');
      expect(document.getElementById('cameraScanOverlay').style.display).toBe('none');
    } finally {
      vi.useRealTimers();
    }
  });

  it('calls onError and closes overlay when camera fails', async () => {
    vi.useFakeTimers();
    try {
      installSupport({ fail: true });
      const button = document.createElement('button');
      document.body.appendChild(button);
      const onError = vi.fn();
      const { setupCameraScanUI } = await importScanner();
      setupCameraScanUI({ button, onScan: vi.fn(), onError });
      button.click();
      await vi.advanceTimersByTimeAsync(50);
      expect(onError).toHaveBeenCalled();
      expect(document.getElementById('cameraScanOverlay').style.display).toBe('none');
    } finally {
      vi.useRealTimers();
    }
  });
});
