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
    expect(parseScaleFrame("invalid")).toBeNull();
    expect(parseScaleFrame(null)).toBeNull();
  });

  it("PosScaleSerial isSupported returns boolean", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    expect(typeof PosScaleSerial.isSupported()).toBe("boolean");
  });

  it("PosScaleSerial constructor initializes correctly", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale.baudRate).toBe(9600);
    expect(scale.connected).toBe(false);
    expect(scale.lastWeightKg).toBe(0);
  });

  it("PosScaleSerial getLastWeight returns last weight", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ baudRate: 9600 });
    expect(scale.getLastWeight()).toBe(0);
    scale.lastWeightKg = 1.5;
    expect(scale.getLastWeight()).toBe(1.5);
  });

  it("PosScaleSerial _ingest parses frames", async () => {
    const { PosScaleSerial } = await import("../../static/js/pos/scale-serial.js");
    const scale = new PosScaleSerial({ onStableWeight: vi.fn(), baudRate: 9600 });
    scale._ingest("ST,GS,+  1.000kg\r\n");
    expect(scale._pendingCount).toBe(1);
    expect(scale._pendingKg).toBe(1);
  });
});
