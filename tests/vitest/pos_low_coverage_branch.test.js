import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

function getExport(mod, name, fallbackName) {
  if (mod[name] !== undefined) return mod[name];
  if (mod.default && mod.default[name] !== undefined) return mod.default[name];
  if (window[name] !== undefined) return window[name];
  if (fallbackName && window[fallbackName] !== undefined) return window[fallbackName];
  return undefined;
}

describe("pos/scale-serial.js - branch coverage", () => {
  beforeEach(async () => {
    vi.resetModules();
    window.t = (k) => k;
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllTimers();
    vi.restoreAllMocks();
    await new Promise((r) => setTimeout(r, 0));
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("loads scale-serial module", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const parseScaleFrame = getExport(mod, "parseScaleFrame", "parseScaleFrame");
    expect(typeof parseScaleFrame).toBe("function");
  });

  it("parses stable A&D frame", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const parseScaleFrame = getExport(mod, "parseScaleFrame", "parseScaleFrame");
    const result = parseScaleFrame("ST,GS,+  1.234kg");
    expect(result).toEqual({ weightKg: 1.234, stable: true });
  });

  it("parses unstable frame", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const parseScaleFrame = getExport(mod, "parseScaleFrame", "parseScaleFrame");
    const result = parseScaleFrame("US,NT,- 0.500kg");
    expect(result).toEqual({ weightKg: 0.5, stable: false });
  });

  it("returns null for invalid input", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const parseScaleFrame = getExport(mod, "parseScaleFrame", "parseScaleFrame");
    expect(parseScaleFrame("invalid")).toBeNull();
    expect(parseScaleFrame(null)).toBeNull();
  });

  it("PosScaleSerial isSupported returns boolean", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const PosScaleSerial = getExport(mod, "PosScaleSerial", "PosScaleSerial");
    expect(typeof PosScaleSerial.isSupported()).toBe("boolean");
  });

  it("PosScaleSerial constructor initializes", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const PosScaleSerial = getExport(mod, "PosScaleSerial", "PosScaleSerial");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale.baudRate).toBe(9600);
    expect(scale.connected).toBe(false);
    expect(scale.lastWeightKg).toBe(0);
  });

  it("setupPosScaleUI returns null when unsupported", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const setupPosScaleUI = getExport(mod, "setupPosScaleUI", "setupPosScaleUI");
    const button = document.createElement("button");
    const originalNavigator = global.navigator;
    global.navigator = undefined;
    const result = setupPosScaleUI({ button });
    expect(result).toBeNull();
    global.navigator = originalNavigator;
  });

  it("getLastWeight returns current weight", async () => {
    const mod = await import("../../static/js/pos/scale-serial.js");
    const PosScaleSerial = getExport(mod, "PosScaleSerial", "PosScaleSerial");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale.getLastWeight()).toBe(0);
    scale.lastWeightKg = 2.5;
    expect(scale.getLastWeight()).toBe(2.5);
  });
});
