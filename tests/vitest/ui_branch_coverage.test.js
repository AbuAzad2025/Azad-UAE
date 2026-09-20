import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

async function loadModules() {
  vi.resetModules();
  window.t = (k) => k;
  window.$ = vi.fn((sel) => {
    const el = document.querySelector(sel);
    return el ? {
      show: vi.fn(),
      hide: vi.fn(),
      on: vi.fn(),
      modal: vi.fn(),
      focus: vi.fn(),
      val: vi.fn(),
      text: vi.fn(),
      html: vi.fn(),
      addClass: vi.fn(),
      removeClass: vi.fn(),
      click: vi.fn(),
      data: vi.fn(),
      attr: vi.fn(),
      removeAttr: vi.fn(),
      remove: vi.fn(),
      append: vi.fn(),
      appendChild: vi.fn(),
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      innerHTML: "",
      textContent: "",
      value: "",
      innerHTML: "",
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
      removeAttribute: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
      removeAttribute: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
    } : {
      show: vi.fn(),
      hide: vi.fn(),
      on: vi.fn(),
      modal: vi.fn(),
      focus: vi.fn(),
      val: vi.fn(),
      text: vi.fn(),
      html: vi.fn(),
      addClass: vi.fn(),
      removeClass: vi.fn(),
      click: vi.fn(),
      data: vi.fn(),
      attr: vi.fn(),
      removeAttr: vi.fn(),
      remove: vi.fn(),
      append: vi.fn(),
      appendChild: vi.fn(),
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(),
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn(), contains: vi.fn() },
      className: "",
      textContent: "",
      innerHTML: "",
      value: "",
      disabled: false,
    };
  });
  window.jQuery = window.$;
  global.$ = window.$;
  window.t = (k) => k;
  window.t = (k) => k;
  window.t = (k) => k;
  vi.resetModules();
  await import("../../static/js/pos/ui.js");
  await new Promise((r) => setTimeout(r, 50));
}

describe("pos/ui.js — branch coverage", () => {
  beforeEach(async () => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
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

  describe("showAlert", () => {
    beforeEach(async () => { await import("../../static/js/pos/ui.js"); });

    it("shows danger alert with correct duration", async () => {
      const { showAlert } = await import("../../static/js/pos/ui.js");
      document.body.innerHTML += '<div id="posAlert" class="d-none"></div>';
      showAlert("Error message", "danger");
      const el = document.getElementById("posAlert");
      expect(el.textContent).toBe("Error message");
      expect(el.className).toContain("alert-danger");
      expect(el.classList.contains("d-none")).toBe(false);
    });

    it("shows success alert with correct duration", async () => {
      const { showAlert } = await import("../../static/js/pos/ui.js");
      document.body.innerHTML += '<div id="posAlert" class="d-none"></div>';
      showAlert("Success!", "success");
      const el = document.getElementById("posAlert");
      expect(el.className).toContain("alert-success");
    });

    it("shows warning alert", async () => {
      const { showAlert } = await import("../../static/js/pos/ui.js");
      document.body.innerHTML += '<div id="posAlert" class="d-none"></div>';
      showAlert("Warning!", "warning");
      const el = document.getElementById("posAlert");
      expect(el.className).toContain("alert-warning");
    });
  });

  describe("showModalAlert", () => {
    it("shows modal alert with message", async () => {
      document.body.innerHTML += '<div id="modal1Alert" class="alert d-none"></div>';
      const { showModalAlert } = await import("../../static/js/pos/ui.js");
      showModalAlert("modal1", "Modal message", "warning");
      const el = document.getElementById("modal1Alert");
      expect(el.textContent).toBe("Modal message");
      expect(el.className).toContain("alert-warning");
    });

    it("falls back to showAlert when modal alert element missing", async () => {
      document.body.innerHTML += '<div id="posAlert" class="d-none"></div>';
      const { showModalAlert } = await import("../../static/js/pos/ui.js");
      showModalAlert("nonexistent", "Fallback message", "danger");
      const el = document.getElementById("posAlert");
      expect(el.textContent).toBe("Fallback message");
    });
  });

  describe("customerHint", () => {
    beforeEach(async () => {
      document.body.innerHTML += '<div id="customerSelectedHint"></div>';
    });

    it("shows customer name when customer selected", async () => {
      const { state } = await import("../../static/js/pos/core.js");
      state.customer = { text: "Test Customer" };
      const { customerHint } = await import("../../static/js/pos/ui.js");
      customerHint();
      const el = document.getElementById("customerSelectedHint");
      expect(el.textContent).toContain("Test Customer");
      expect(el.className).toContain("text-success");
    });

    it("shows placeholder when no customer", async () => {
      const { state } = await import("../../static/js/pos/core.js");
      state.customer = null;
      const { customerHint } = await import("../../static/js/pos/ui.js");
      customerHint();
      const el = document.getElementById("customerSelectedHint");
      expect(el.textContent).toContain("لم يتم اختيار عميل");
    });
  });

  describe("toggleTableField", () => {
    it("shows table field for dine_in", async () => {
      document.body.innerHTML += '<div id="tableField" class="d-none"></div><select id="orderType"><option value="dine_in">Dine In</option></select>';
      const { toggleTableField } = await import("../../static/js/pos/ui.js");
      toggleTableField();
      expect(document.getElementById("tableField").classList.contains("d-none")).toBe(false);
    });

    it("hides table field for takeaway", async () => {
      document.body.innerHTML += '<div id="tableField"></div><select id="orderType"><option value="takeaway">Takeaway</option></select>';
      const { toggleTableField } = await import("../../static/js/pos/ui.js");
      toggleTableField();
      expect(document.getElementById("tableField").classList.contains("d-none")).toBe(true);
    });
  });
});