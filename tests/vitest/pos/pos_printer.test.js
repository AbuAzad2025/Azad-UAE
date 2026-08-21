import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../../static/js/pos/printer.js";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
  delete window.printSaleTickets;
  delete window.printQueuedCartReceipt;
});

async function loadModule() {
  return import(MOD_PATH + "?" + Date.now());
}

describe("pos/printer.js — autoPrintSale", () => {
  it("calls window.printSaleTickets when present", async () => {
    window.printSaleTickets = vi.fn();
    const { autoPrintSale } = await loadModule();
    autoPrintSale(42);
    expect(window.printSaleTickets).toHaveBeenCalledWith(42);
  });

  it("no-ops when global function missing", async () => {
    const { autoPrintSale } = await loadModule();
    expect(() => autoPrintSale(42)).not.toThrow();
  });
});

describe("pos/printer.js — autoPrintQueuedReceipt", () => {
  it("calls window.printQueuedCartReceipt when present", async () => {
    window.printQueuedCartReceipt = vi.fn();
    const { autoPrintQueuedReceipt } = await loadModule();
    const cart = [{ id: 1 }];
    const totals = { total: 100 };
    const payload = { note: "x" };
    autoPrintQueuedReceipt(cart, totals, payload);
    expect(window.printQueuedCartReceipt).toHaveBeenCalledWith(cart, totals, payload);
  });

  it("no-ops when global function missing", async () => {
    const { autoPrintQueuedReceipt } = await loadModule();
    expect(() => autoPrintQueuedReceipt([], {}, {})).not.toThrow();
  });
});
