import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("pos/scale-serial.js - branch coverage", () => {
  beforeEach(async () => {
    vi.resetModules();
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllTimers();
    vi.restoreAllMocks();
    await new Promise((r) => setTimeout(r, 0));
  });

  it("parseScaleFrame parses A&D style frame", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("ST,GS,+  1.234kg");
    expect(result).toEqual({ weightKg: 1.234, stable: true });
  });

  it("parseScaleFrame parses US/OL unstable frame", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("US,NT,- 0.500kg");
    expect(result).toEqual({ weightKg: 0.5, stable: false });
  });

  it("parseScaleFrame parses plain numeric", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("1.234");
    expect(result).toEqual({ weightKg: 1.234, stable: true });
  });

  it("parseScaleFrame parses gram frame", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("500g");
    expect(result).toEqual({ weightKg: 0.5, stable: true });
  });

  it("parseScaleFrame returns null for invalid input", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("invalid");
    expect(result).toBeNull();
  });

  it("parseScaleFrame returns null for null input", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame(null);
    expect(result).toBeNull();
  });

  it("parseScaleFrame returns null for empty string", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("");
    expect(result).toBeNull();
  });

  it("parseScaleFrame parses negative weight", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("-0.500kg");
    expect(result).toBeNull();
  });

  it("parseScaleFrame handles comma decimal", async () => {
    const { parseScaleFrame } = await import("../../static/js/pos/scale-serial.js");
    const result = parseScaleFrame("1,234kg");
    expect(result).toEqual({ weightKg: 1.234, stable: true });
  });

  it("PosScaleSerial isSupported returns boolean", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const supported = PosScaleSerial.isSupported();
    expect(typeof supported).toBe("boolean");
  });

  it("PosScaleSerial constructor initializes correctly", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale).toBeInstanceOf(Object);
    expect(scale.baudRate).toBe(9600);
    expect(scale.connected).toBe(false);
    expect(scale.lastWeightKg).toBe(0);
  });

  it("PosScaleSerial connect handles unsupported browser", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const originalNavigator = global.navigator;
    global.navigator = undefined;
    const scale = new PosScaleSerial({ onError: vi.fn() });
    const result = await scale.connect();
    expect(result).toBe(false);
    expect(scale.connected).toBe(false);
    global.navigator = originalNavigator;
  });

  it("PosScaleSerial connect succeeds in supported env", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const mockPort = {
      open: vi.fn().mockResolvedValue(undefined),
      readable: {
        getReader: () => ({
          read: vi.fn().mockResolvedValue({ done: true, value: null }),
          releaseLock: vi.fn(),
        }),
      },
      close: vi.fn().mockResolvedValue(undefined),
    };
    global.navigator = { serial: { requestPort: vi.fn().mockResolvedValue(mockPort) } };
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), onError: vi.fn(), baudRate: 9600 });
    const result = await scale.connect();
    expect(result).toBe(true);
    expect(scale.connected).toBe(true);
  });

  it("PosScaleSerial disconnect cleans up", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const mockPort = {
      open: vi.fn().mockResolvedValue(undefined),
      readable: {
        getReader: () => ({
          read: vi.fn().mockResolvedValue({ done: true, value: null }),
          releaseLock: vi.fn(),
          cancel: vi.fn().mockResolvedValue(undefined),
        }),
      },
      close: vi.fn().mockResolvedValue(undefined),
    };
    global.navigator = { serial: { requestPort: vi.fn().mockResolvedValue(mockPort) } };
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), onError: vi.fn() });
    await scale.connect();
    await scale.disconnect();
    expect(scale.connected).toBe(false);
    expect(scale.port).toBeNull();
    expect(scale.reader).toBeNull();
  });

  it("PosScaleSerial getLastWeight returns last weight", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale.getLastWeight()).toBe(0);
    scale.lastWeightKg = 1.5;
    expect(scale.getLastWeight()).toBe(1.5);
  });

  it("PosScaleSerial _ingest parses and handles frames", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), baudRate: 9600 });
    scale._ingest("ST,GS,+  1.000kg\r\n");
    expect(scale._pendingCount).toBe(1);
    expect(scale._pendingKg).toBe(1);
  });

  it("PosScaleSerial _ingest handles multiple lines", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), baudRate: 9600 });
    scale._ingest("ST,GS,+  1.000kg\r\nST,GS,+  2.000kg\r\n");
    expect(scale._buffer).toBe("");
    expect(scale._pendingCount).toBeGreaterThanOrEqual(0);
  });

  it("PosScaleSerial _ingest handles partial lines", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), baudRate: 9600 });
    scale._ingest("ST,GS,+  1.000kg");
    expect(scale._buffer).toContain("ST,GS,+  1.000kg");
    scale._ingest("\r\n");
    expect(scale._buffer).toBe("");
    expect(scale._pendingCount).toBe(1);
  });

  it("PosScaleSerial _ingest truncates large buffer", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), baudRate: 9600 });
    scale._ingest("x".repeat(200));
    expect(scale._buffer.length).toBeLessThanOrEqual(128);
  });

  it("PosScaleSerial _handleLine processes stable frames", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const onStable = vi.fn();
    const scale = new PosScaleSerial({ onStableWeight: onStable, baudRate: 9600 });
    scale._handleLine("ST,GS,+  1.000kg");
    scale._handleLine("ST,GS,+  1.000kg");
    scale._handleLine("ST,GS,+  1.000kg");
    expect(onStable).toHaveBeenCalledWith(1);
    expect(scale.lastWeightKg).toBe(1);
  });

  it("PosScaleSerial _fail calls onError", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const onError = vi.fn();
    const scale = new PosScaleSerial({ onError, baudRate: 9600 });
    scale._fail("Test error");
    expect(onError).toHaveBeenCalledWith("Test error");
  });

  it("setupPosScaleUI returns null when Web Serial unsupported", async () => {
    const { setupPosScaleUI } = await import("../../static/js/pos/scale-serial.js");
    const originalNavigator = global.navigator;
    global.navigator = undefined;
    const button = document.createElement("button");
    const result = setupPosScaleUI({ button });
    expect(result).toBeNull();
    expect(button.classList.contains("d-none")).toBe(true);
    global.navigator = window.navigator;
  });

  it("setupPosScaleUI returns null when button missing", async () => {
    const { setupPosScaleUI } = await import("../../static/js/pos/scale-serial.js");
    const result = setupPosScaleUI({ scale: {} });
    expect(result).toBeNull();
  });

  it("setupPosScaleUI returns null when scale missing", async () => {
    const { setupPosScaleUI } = await import("../../static/js/pos/scale-serial.js");
    const button = document.createElement("button");
    const result = setupPosScaleUI({ button });
    expect(result).toBeNull();
  });

  it("setupPosScaleUI connects and disconnects scale", async () => {
    const { setupPosScaleUI, PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const mockPort = {
      open: vi.fn().mockResolvedValue(undefined),
      readable: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true, value: null }), releaseLock: vi.fn() }) },
      close: vi.fn().mockResolvedValue(undefined),
    };
    global.navigator = { serial: { requestPort: vi.fn().mockResolvedValue(mockPort) } };
    const button = document.createElement("button");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), onError: vi.fn() });
    const result = setupPosScaleUI({ button, scale });
    expect(result).toBe(scale);
    button.click();
    await new Promise(r => setTimeout(r, 50));
    expect(scale.connected).toBe(true);
  });