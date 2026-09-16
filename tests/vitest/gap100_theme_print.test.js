import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

function setReadyState(state) {
  Object.defineProperty(document, "readyState", { configurable: true, value: state });
}

function restoreReadyState() {
  // @ts-ignore shadowing accessor with own property
  delete document.readyState;
}

// ---------- ui-theme ----------

describe("ui-theme.js gaps", () => {
  let matchMediaHandlers;

  beforeEach(() => {
    matchMediaHandlers = [];
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    document.documentElement.removeAttribute("data-ui-mode");
    document.documentElement.removeAttribute("data-ui-variant");
    delete document.body.dataset.sidebarSide;
    localStorage.clear();
    delete window.toggleSidebarDirection;
    vi.resetModules();
  });

  afterEach(() => {
    // @ts-ignore jsdom override cleanup — restore first so later lines see a body
    if (Object.prototype.hasOwnProperty.call(document, "body")) delete document.body;
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    localStorage.clear();
    delete window.toggleSidebarDirection;
    if (window.matchMedia && window.matchMedia.isMock) window.matchMedia.mockRestore();
    restoreReadyState();
    vi.resetModules();
    vi.restoreAllMocks();
  });

  async function load() {
    await import("../../static/js/ui-theme.js");
  }

  it("restores a stored sidebar side", async () => {
    localStorage.setItem("sidebarLayout", "left");
    localStorage.setItem("sidebarLayoutDir", "rtl");
    await load();
    expect(document.body.dataset.sidebarSide).toBe("left");
  });

  it("no-ops sidebar application without a body", async () => {
    Object.defineProperty(document, "body", { configurable: true, get: () => null });
    await load();
    expect(window.toggleSidebarDirection).toBeTypeOf("function");
    expect(() => window.toggleSidebarDirection()).not.toThrow();
  });

  it("skips flash messages already scheduled elsewhere", async () => {
    const el = document.createElement("div");
    el.className = "flash-message alert-success";
    el.dataset.flashDismissScheduled = "1";
    document.body.appendChild(el);
    await load();
    expect(document.body.contains(el)).toBe(true);
  });

  it("follows system dark-mode changes when the user has no stored mode", async () => {
    window.matchMedia = vi.fn(() => ({
      matches: false,
      addEventListener: (evt, fn) => matchMediaHandlers.push({ evt, fn }),
      removeEventListener: () => {},
    }));
    await load();
    expect(matchMediaHandlers.length).toBe(1);
    localStorage.clear();
    matchMediaHandlers[0].fn({ matches: true });
    expect(document.documentElement.dataset.uiMode).toBe("dark");
  });

  it("defers boot until DOMContentLoaded while loading", async () => {
    setReadyState("loading");
    await load();
    expect(document.documentElement.dataset.uiMode || "").toBe("");
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(document.documentElement.dataset.uiMode).toMatch(/light|dark/);
  });
});

// ---------- smart-print ----------

const spHandlers = new Map();
const spData = new Map();
const spVals = new Map();
const spModalSpy = vi.fn(() => undefined);
const spWarnSpy = vi.fn();

function makeSmartJQuery() {
  const chain = (sel) => {
    const api = {
      length: (() => {
        if (typeof sel !== "string") return sel ? 1 : 0;
        try {
          return document.querySelectorAll(sel).length;
        } catch {
          return 0;
        }
      })(),
      on: (types, fn) => {
        String(types)
          .split(" ")
          .forEach((t) => {
            const key = String(sel) + "|" + t;
            if (!spHandlers.has(key)) spHandlers.set(key, []);
            spHandlers.get(key).push(fn);
          });
        return api;
      },
      off: () => api,
      data: (k, v) => {
        const s = "data:" + String(sel);
        if (!spData.has(s)) spData.set(s, {});
        if (v !== undefined) {
          spData.get(s)[k] = v;
          return api;
        }
        return spData.get(s)[k];
      },
      val: (v) => {
        if (v !== undefined) {
          spVals.set("val:" + String(sel), v);
          return api;
        }
        return spVals.get("val:" + String(sel)) ?? "";
      },
      prop: (k, v) => {
        if (v !== undefined) {
          spVals.set("prop:" + String(sel) + ":" + k, v);
          return api;
        }
        return spVals.get("prop:" + String(sel) + ":" + k);
      },
      addClass: () => api,
      removeClass: () => api,
      text: (t) => {
        if (t !== undefined) {
          spVals.set("text:" + String(sel), t);
          return api;
        }
        return spVals.get("text:" + String(sel)) ?? "";
      },
      modal: spModalSpy,
      each: (fn) => {
        if (fn) fn.call(api, 0, null);
        return api;
      },
      find: () => chain(".inner"),
      first: () => api,
      css: () => api,
      remove: () => api,
      prepend: () => api,
      append: (html) => {
        if (typeof sel === "string" && (sel === "body" || sel === document.body)) {
          document.body.insertAdjacentHTML("beforeend", String(html));
        }
        return api;
      },
    };
    return api;
  };
  const $ = (sel) => chain(sel);
  $.fn = {};
  $.extend = (...args) => {
    let deep = false;
    let target = args[0];
    let i = 1;
    if (typeof args[0] === "boolean") {
      deep = args[0];
      target = args[1];
      i = 2;
    }
    for (; i < args.length; i += 1) {
      const src = args[i];
      if (!src) continue;
      Object.keys(src).forEach((k) => {
        const v = src[k];
        if (deep && v && typeof v === "object" && !Array.isArray(v)) {
          const prev = target[k];
          target[k] = $.extend(true, prev && typeof prev === "object" && !Array.isArray(prev) ? prev : {}, v);
        } else {
          target[k] = v;
        }
      });
    }
    return target;
  };
  $.Event = function (type) {
    this.type = type;
  };
  return $;
}

function fireSp(sel, type, ctx) {
  const key = sel + "|" + type;
  (spHandlers.get(key) || []).slice().forEach((fn) => fn.call(ctx || {}, { preventDefault() {} }));
}

function makeManualTable() {
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>H1</th></tr>";
  const tfoot = document.createElement("tfoot");
  tfoot.innerHTML = "<tr><th>F1</th></tr>";
  const btnNode = document.createElement("button");
  document.body.appendChild(btnNode);
  return {
    rows: () => ({
      indexes: () => ({ toArray: () => [0, 1, 2, 3] }),
      nodes: () => [],
      data: () => [
        ["a", "b"],
        ["c", "d"],
      ],
    }),
    page: { info: () => ({ page: 0, pages: 2, length: 2, recordsTotal: 4, recordsDisplay: 4 }) },
    button: () => ({ length: 1, node: () => btnNode }),
    buttons: () => ({ count: () => 0 }),
    table: () => ({ header: () => thead, footer: () => tfoot }),
  };
}

describe("smart-print.js gaps", () => {
  let origConsoleWarn;
  let origAlert;
  let origOpen;

  beforeEach(() => {
    spHandlers.clear();
    spData.clear();
    spVals.clear();
    document.body.innerHTML = "";
    const $ = makeSmartJQuery();
    window.$ = $;
    window.jQuery = $;
    origConsoleWarn = console.warn;
    console.warn = spWarnSpy;
    origAlert = window.alert;
    window.alert = vi.fn();
    origOpen = window.open;
    window.open = vi.fn(() => null);
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    console.warn = origConsoleWarn;
    window.alert = origAlert;
    window.open = origOpen;
    delete window.SmartPrint;
    delete window.$;
    delete window.jQuery;
    global.$ = undefined;
    vi.resetModules();
    vi.restoreAllMocks();
  });

  async function load() {
    await import("../../static/js/smart-print.js");
    return window.SmartPrint;
  }

  it("toggles range inputs on radio change", async () => {
    const sp = await load();
    sp.attachTrigger(makeManualTable(), "#spBtn");
    fireSp('input[name="smartPrintRange"]', "change", { value: "rows" });
    expect(spVals.get("prop:#smartPrintRowStart, #smartPrintRowEnd:disabled")).toBe(false);
    fireSp('input[name="smartPrintRange"]', "change", { value: "pages" });
    expect(spVals.get("prop:#smartPrintPageStart, #smartPrintPageEnd:disabled")).toBe(false);
  });

  it("ignores confirm with no table state", async () => {
    await load();
    fireSp("#smartPrintModalConfirm", "click");
    expect(spModalSpy).not.toHaveBeenCalledWith("hide");
  });

  it("rejects unknown print ranges on confirm", async () => {
    const sp = await load();
    const table = makeManualTable();
    sp.attachTrigger(table, "#spBtn");
    sp.trigger(table, { title: "t" });
    spVals.set('val:input[name="smartPrintRange"]:checked', "");
    fireSp("#smartPrintModalConfirm", "click");
    expect(spVals.get("text:#smartPrintError")).toContain("لم يتم التعرف");
  });

  it("falls back to manual DOM extraction with footer", async () => {
    const sp = await load();
    const table = makeManualTable();
    sp.attachTrigger(table, "#spBtn");
    sp.trigger(table, { title: "t" });
    spVals.set('val:input[name="smartPrintRange"]:checked', "all");
    fireSp("#smartPrintModalConfirm", "click");
    expect(window.alert).toHaveBeenCalledWith("يرجى السماح بالنوافذ المنبثقة لطباعة التقرير.");
  });

  it("applies print styles through the button customize hook", async () => {
    const sp = await load();
    const buttons = sp.buildButtons({ title: "R", headerColor: "#198754" });
    const printBtn = buttons.find((b) => b.extend === "print");
    printBtn.customize({ document });
    expect(document.head.querySelectorAll("style").length).toBeGreaterThan(0);
    expect(printBtn.init).toBeTypeOf("function");
    const node = document.createElement("button");
    printBtn.init({}, node, { smartPrintOptions: { title: "R" } });
  });

  it("warns and bails out for a missing trigger", async () => {
    const sp = await load();
    sp.attachTrigger(makeManualTable(), "#definitely-missing");
    expect(spWarnSpy).toHaveBeenCalledWith(
      "SmartPrint: trigger button not found for selector",
      "#definitely-missing"
    );
  });
});
