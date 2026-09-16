import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// tests/vitest/setup.js provides global.$ — restore it instead of deleting it.
const SETUP_DOLLAR = global.$;

function restoreDollar() {
  global.$ = SETUP_DOLLAR;
  window.$ = SETUP_DOLLAR;
  delete global.jQuery;
  delete window.jQuery;
}

function setReadyState(state) {
  Object.defineProperty(document, "readyState", { configurable: true, value: state });
}

function restoreReadyState() {
  // @ts-ignore shadowing accessor with own property
  delete document.readyState;
}

describe("form_validation.js gaps", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    restoreReadyState();
    vi.resetModules();
    vi.useRealTimers();
  });

  async function load() {
    await import("../../static/js/form_validation.js");
    return window.FormValidation;
  }

  function textInput(extra = {}) {
    const input = document.createElement("input");
    input.type = "text";
    input.name = "f";
    document.body.appendChild(input);
    Object.assign(input, extra);
    const wrap = document.createElement("div");
    wrap.appendChild(input);
    document.body.appendChild(wrap);
    return input;
  }

  it("rejects invalid url type", async () => {
    const fv = await load();
    const input = textInput();
    input.type = "url";
    input.value = "not a url at all";
    expect(fv.validateField(input)).toBe(false);
    expect(input.classList.contains("is-invalid")).toBe(true);
  });

  it("rejects NaN number type", async () => {
    const fv = await load();
    const input = textInput();
    input.type = "number";
    Object.defineProperty(input, "value", { value: "abc", configurable: true });
    expect(fv.validateField(input)).toBe(false);
  });

  it("rejects unparsable date type", async () => {
    const fv = await load();
    const input = textInput();
    input.type = "date";
    Object.defineProperty(input, "value", { value: "not-a-date", configurable: true });
    expect(fv.validateField(input)).toBe(false);
  });

  it("rejects overlong values via maxlength", async () => {
    const fv = await load();
    const input = textInput();
    input.maxLength = 2;
    input.value = "toolong";
    expect(fv.validateField(input)).toBe(false);
  });

  it("rejects pattern mismatches", async () => {
    const fv = await load();
    const input = textInput();
    input.pattern = "[0-9]+";
    input.value = "abc";
    expect(fv.validateField(input)).toBe(false);
  });

  it("rejects values below min and above max", async () => {
    const fv = await load();
    const lo = textInput();
    lo.min = "5";
    lo.value = "3";
    expect(fv.validateField(lo)).toBe(false);
    const hi = textInput();
    hi.max = "5";
    hi.value = "9";
    expect(fv.validateField(hi)).toBe(false);
  });

  it("rejects non-digit values when digits required", async () => {
    const fv = await load();
    const input = textInput();
    input.dataset.digits = "true";
    input.value = "12a";
    expect(fv.validateField(input)).toBe(false);
  });

  it("rejects oversized files", async () => {
    const fv = await load();
    const input = document.createElement("input");
    input.type = "file";
    input.name = "doc";
    input.dataset.maxSize = "1024";
    input.accept = ".pdf";
    Object.defineProperty(input, "value", { value: "C:\\fakepath\\big.pdf", configurable: true });
    Object.defineProperty(input, "files", {
      value: [{ name: "big.pdf", size: 10 * 1024 * 1024, type: "application/pdf" }],
      configurable: true,
    });
    const wrap = document.createElement("div");
    wrap.appendChild(input);
    document.body.appendChild(wrap);
    expect(fv.validateField(input)).toBe(false);
    expect(input.classList.contains("is-invalid")).toBe(true);
  });

  it("rejects disallowed file types", async () => {
    const fv = await load();
    const input = document.createElement("input");
    input.type = "file";
    input.name = "doc";
    input.accept = ".pdf";
    Object.defineProperty(input, "value", { value: "C:\\fakepath\\run.exe", configurable: true });
    Object.defineProperty(input, "files", {
      value: [{ name: "run.exe", size: 100, type: "application/x-msdownload" }],
      configurable: true,
    });
    const wrap = document.createElement("div");
    wrap.appendChild(input);
    document.body.appendChild(wrap);
    expect(fv.validateField(input)).toBe(false);
  });

  it("scrolls the first invalid field into view on validateForm", async () => {
    const fv = await load();
    document.body.innerHTML =
      '<form id="f"><div><input name="a" type="text" required></div></form>';
    const input = document.querySelector('input[name="a"]');
    input.scrollIntoView = vi.fn();
    expect(fv.validateForm(document.getElementById("f"))).toBe(false);
    expect(input.scrollIntoView).toHaveBeenCalled();
  });

  it("shakes an invalid form on submit and clears the shake", async () => {
    vi.useFakeTimers();
    await load();
    document.body.innerHTML =
      '<form class="needs-validation"><div><input name="a" type="text" required></div></form>';
    const form = document.querySelector("form");
    window.FormValidation.init();
    const ev = new Event("submit", { bubbles: true, cancelable: true });
    form.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(form.classList.contains("az-shake")).toBe(true);
    await vi.advanceTimersByTimeAsync(600);
    expect(form.classList.contains("az-shake")).toBe(false);
  });

  it("revalidates on input only when already invalid", async () => {
    await load();
    document.body.innerHTML =
      '<form class="needs-validation"><div><input name="email" type="email"></div></form>';
    const form = document.querySelector("form");
    window.FormValidation.init();
    const input = form.querySelector("input");
    input.value = "bad";
    input.dispatchEvent(new Event("change", { bubbles: true }));
    expect(input.classList.contains("is-invalid")).toBe(true);
    input.value = "good@test.com";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect(input.classList.contains("is-invalid")).toBe(false);
  });

  it("defers init until DOMContentLoaded while loading", async () => {
    setReadyState("loading");
    document.body.innerHTML = '<form class="needs-validation"></form>';
    await load();
    const form = document.querySelector("form");
    expect(form.hasAttribute("novalidate")).toBe(false);
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(form.getAttribute("novalidate")).toBe("");
  });
});

describe("draft-autosave.js gaps", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.resetModules();
  });

  async function load() {
    await import("../../static/js/draft-autosave.js");
    return window.DraftAutosave;
  }

  it("skips unknown or protected fields when loading", async () => {
    const da = await load();
    document.body.innerHTML = '<form id="f"><input name="title" value=""></form>';
    const form = document.getElementById("f");
    localStorage.setItem(
      "azad_draft_k1",
      JSON.stringify({ data: { ghost: "x", title: "hello" }, timestamp: Date.now() })
    );
    expect(da.load("k1", form)).toBe(true);
    expect(form.querySelector('[name="title"]').value).toBe("hello");
  });

  it("shows a restore banner when a draft exists", async () => {
    const da = await load();
    document.body.innerHTML = '<form id="f"><input name="title" value=""></form>';
    const form = document.getElementById("f");
    localStorage.setItem(
      "azad_draft_k2",
      JSON.stringify({ data: { title: "saved" }, timestamp: Date.now() })
    );
    da.init("k2", "#f");
    const banner = form.querySelector(".js-draft-restore");
    expect(banner).toBeTruthy();
    banner.click();
    expect(form.querySelector('[name="title"]').value).toBe("saved");
    expect(form.querySelector(".alert")).toBeNull();
  });

  it("discards the draft from the banner", async () => {
    const da = await load();
    document.body.innerHTML = '<form id="f"><input name="title" value=""></form>';
    localStorage.setItem(
      "azad_draft_k3",
      JSON.stringify({ data: { title: "saved" }, timestamp: Date.now() })
    );
    da.init("k3", "#f");
    document.querySelector(".js-draft-discard").click();
    expect(da.hasDraft("k3")).toBe(false);
  });
});

describe("payment-fields.js gaps", () => {
  function makeDOMJQuery() {
    const $ = (sel) => {
      const els = typeof sel === "string" ? Array.from(document.querySelectorAll(sel)) : [sel].filter(Boolean);
      return {
        length: els.length,
        empty: () => {
          els.forEach((el) => {
            el.innerHTML = "";
          });
          return $(sel);
        },
        html: (h) => {
          els.forEach((el) => {
            el.innerHTML = h;
          });
          return $(sel);
        },
      };
    };
    $.fn = {};
    return $;
  }

  beforeEach(() => {
    document.body.innerHTML = '<div id="pay-fields"></div>';
    global.$ = global.jQuery = makeDOMJQuery();
    window.$ = window.jQuery = global.$;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    restoreDollar();
    vi.resetModules();
  });

  it("renders textarea fields and value/max constrained inputs", async () => {
    await import("../../static/js/payment-fields.js");
    const pm = window.PaymentFieldsManager;
    const original = [...pm.methods.credit.fields];
    pm.methods.credit.fields = [
      ...original,
      { name: "notes", type: "textarea", label_ar: "ملاحظات", placeholder: "اكتب", required: true },
      { name: "limit", type: "number", label_ar: "حد", min: 1, max: 100, value: 5 },
    ];
    try {
      pm.render("credit", "#pay-fields");
      const root = document.getElementById("pay-fields");
      const area = root.querySelector('textarea[name="notes"]');
      expect(area).toBeTruthy();
      expect(area.getAttribute("placeholder")).toBe("اكتب");
      const limit = root.querySelector('input[name="limit"]');
      expect(limit.getAttribute("max")).toBe("100");
      expect(limit.getAttribute("value")).toBe("5");
    } finally {
      pm.methods.credit.fields = original;
    }
  });
});

describe("payments-receipts-page.js gaps", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    delete window.ActionHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    delete window.ActionHelpers;
    restoreReadyState();
    vi.resetModules();
  });

  it("defers init until DOMContentLoaded while loading", async () => {
    setReadyState("loading");
    window.ActionHelpers = { archivePaymentItem: vi.fn() };
    document.body.innerHTML =
      '<button class="js-archive-payment" data-item-type="payment" data-item-id="7" data-item-number="P-7"></button>';
    await import("../../static/js/payments-receipts-page.js");
    expect(window.ActionHelpers.archivePaymentItem).not.toHaveBeenCalled();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    document.querySelector(".js-archive-payment").click();
    expect(window.ActionHelpers.archivePaymentItem).toHaveBeenCalledWith("payment", "7", "P-7");
  });
});

describe("action-helpers.js gaps", () => {
  let origPrompt;
  let origConfirm;
  let origAlert;
  let origFetch;

  beforeEach(() => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    document.body.innerHTML = "";
    origPrompt = window.prompt;
    origConfirm = window.confirm;
    origAlert = window.alert;
    origFetch = global.fetch;
    window.prompt = vi.fn(() => "reason");
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();
    vi.resetModules();
  });

  afterEach(() => {
    window.prompt = origPrompt;
    window.confirm = origConfirm;
    window.alert = origAlert;
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.head.innerHTML = "";
    delete window.ActionHelpers;
    vi.resetModules();
  });

  it("alerts a non-JSON archive failure with the HTTP status", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, headers: { get: () => null } })
    );
    window.fetch = global.fetch;
    await import("../../static/js/action-helpers.js");
    window.ActionHelpers.archivePaymentItem("receipt", 42, "R-42");
    await new Promise((r) => setTimeout(r, 10));
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("500"));
  });

  it("alerts a JSON archive failure message", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve({ message: "bad" }),
      })
    );
    window.fetch = global.fetch;
    await import("../../static/js/action-helpers.js");
    window.ActionHelpers.archivePaymentItem("payment", 9, "");
    await new Promise((r) => setTimeout(r, 10));
    expect(window.alert).toHaveBeenCalled();
  });
});
