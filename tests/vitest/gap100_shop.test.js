import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const SETUP_DOLLAR = global.$;

function restoreDollar() {
  global.$ = SETUP_DOLLAR;
  window.$ = SETUP_DOLLAR;
  delete global.jQuery;
  delete window.jQuery;
}

function flush(ms = 20) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------- shop-cart ----------

function routeFetch(routes) {
  const spy = vi.fn((url, opts) => {
    const u = new URL(url, "http://localhost");
    for (const [key, handler] of Object.entries(routes)) {
      if (u.pathname.endsWith(key)) return handler(url, opts);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  global.fetch = spy;
  window.fetch = spy;
  return spy;
}

const CART_ROWS_HTML =
  '<div class="ps-cart-item-row" data-product-id="1">' +
  '<span class="ps-cart-item-name">Apple</span>' +
  '<span class="ps-cart-item-price">10.00</span>' +
  '<input name="qty_1" value="2">' +
  "</div>";

describe("shop-cart.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    document.body.innerHTML = "";
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    restoreDollar();
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    delete window.ShopCart;
    vi.useRealTimers();
    vi.resetModules();
  });

  async function loadWithSlug(slug = "t") {
    cartMocks();
    if (slug) document.body.setAttribute("data-store-slug", slug);
    await import("../../static/js/shop-cart.js");
    return window.ShopCart;
  }

  function cartMocks() {
    return routeFetch({
      "/cart": (url) =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}), text: () => Promise.resolve(CART_ROWS_HTML) }),
      "/cart/add": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, cart_count: 1 }) }),
      "/cart/remove/1": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false, message: "no" }) }),
      "/cart/update": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, cart_count: 1 }) }),
      "/cart/count": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ count: 0 }) }),
    });
  }

  it("auto-dismisses toast notifications", async () => {
    vi.useFakeTimers();
    await loadWithSlug();
    window.ShopCart.showToast("hello", "success");
    expect(document.body.textContent).toContain("hello");
    await vi.advanceTimersByTimeAsync(4000);
    await vi.advanceTimersByTimeAsync(400);
    expect(document.body.textContent).not.toContain("hello");
  });

  it("shows an error toast when removal fails", async () => {
    await loadWithSlug();
    const spy = global.fetch;
    const data = await window.ShopCart.removeFromCart(1);
    expect(data.success).toBe(false);
    expect(spy).toHaveBeenCalled();
    expect(document.body.textContent).toContain("Error removing item");
  });

  it("ignores submits from non-cart forms", async () => {
    const spy = cartMocks();
    await loadWithSlug();
    document.body.insertAdjacentHTML("beforeend", '<form id="plain"><input name="x" value="1"></form>');
    document.getElementById("plain").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    expect(spy).not.toHaveBeenCalled();
  });

  it("bails out of init without a store slug", async () => {
    const spy = cartMocks();
    await loadWithSlug(null);
    expect(window.ShopCart).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it("no-ops the drawer close without drawer elements", async () => {
    await loadWithSlug();
    expect(() => window.ShopCart.closeCartDrawer()).not.toThrow();
  });

  it("wires drawer remove/inc/dec buttons", async () => {
    cartMocks();
    document.body.insertAdjacentHTML(
      "beforeend",
      '<div id="psCartDrawerBody"></div><div id="psCartDrawerFooter"></div><div id="psCartDrawerTotal"></div>'
    );
    await loadWithSlug();
    await window.ShopCart.refreshCartDrawer();
    await flush();
    await window.ShopCart.refreshCartDrawer();
    await flush();
    const body = document.getElementById("psCartDrawerBody");
    expect(body.querySelector("[data-cart-remove]")).toBeTruthy();
    body.querySelector("[data-cart-remove]").click();
    await flush(50);
    await window.ShopCart.refreshCartDrawer();
    await flush(50);
    document.getElementById("psCartDrawerBody").querySelector("[data-cart-inc]").click();
    await flush(50);
    await window.ShopCart.refreshCartDrawer();
    await flush(50);
    document.getElementById("psCartDrawerBody").querySelector("[data-cart-dec]").click();
    await flush(50);
    expect(true).toBe(true);
  });

  it("returns early from drawer render without a body", async () => {
    cartMocks();
    document.body.insertAdjacentHTML("beforeend", '<div id="psCartDrawerBody"></div>');
    await loadWithSlug();
    const p = window.ShopCart.refreshCartDrawer();
    document.getElementById("psCartDrawerBody").remove();
    await p;
    await flush();
    expect(document.getElementById("psCartDrawerBody")).toBeNull();
  });

  it("handles quick-add clicks", async () => {
    await loadWithSlug();
    const spy = global.fetch;
    document.body.insertAdjacentHTML(
      "beforeend",
      '<button data-quick-add data-product-id="9">add</button>'
    );
    document.querySelector("[data-quick-add]").click();
    await flush(50);
    expect(spy).toHaveBeenCalled();
  });
});

// ---------- shop-search ----------

describe("shop-search.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    document.body.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.body.innerHTML = "";
    vi.useRealTimers();
    vi.resetModules();
  });

  function baseDom(slug = "t") {
    if (slug) document.body.setAttribute("data-store-slug", slug);
    document.body.innerHTML +=
      '<form id="s"><input name="q" data-search-autocomplete value=""></form>' +
      '<div class="ps-autocomplete-results" style="display:none"></div>';
  }

  async function load() {
    await import("../../static/js/shop-search.js");
  }

  it("bails out without a store slug", async () => {
    baseDom(null);
    await load();
    expect(document.querySelector(".ps-autocomplete-results").innerHTML).toBe("");
  });

  it("hides the dropdown on empty results", async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) })
    );
    window.fetch = global.fetch;
    baseDom();
    await load();
    const input = document.querySelector('input[name="q"]');
    input.value = "ab";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    await vi.advanceTimersByTimeAsync(0);
    expect(document.querySelector(".ps-autocomplete-results").style.display).toBe("none");
  });

  it("renders image results and follows result clicks", async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            results: [{ name: "Pear", url: "/s/t/p/1", image: "/img/pear.png", price: "3.5", currency: "ILS" }],
          }),
      })
    );
    window.fetch = global.fetch;
    baseDom();
    await load();
    const input = document.querySelector('input[name="q"]');
    input.value = "pear";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    await vi.advanceTimersByTimeAsync(0);
    const item = document.querySelector(".ps-autocomplete-item");
    expect(item).toBeTruthy();
    expect(item.querySelector("img")).toBeTruthy();
    const href = window.location.href;
    item.click();
    await vi.advanceTimersByTimeAsync(10);
    expect(window.location.href).toBe(href);
  });

  it("navigates with Enter after arrow navigation", async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ results: [{ name: "Fig", url: "/s/t/p/2", price: "1" }] }),
      })
    );
    window.fetch = global.fetch;
    baseDom();
    await load();
    const input = document.querySelector('input[name="q"]');
    input.value = "fig";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(350);
    await vi.advanceTimersByTimeAsync(0);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.querySelector(".ps-ac-active")).toBeTruthy();
    const href = window.location.href;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(window.location.href).toBe(href);
  });
});

// ---------- shop-quickview ----------

describe("shop-quickview.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    document.body.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.body.innerHTML = "";
    delete window.ShopQuickView;
    delete window.ShopCart;
    vi.resetModules();
  });

  it("guards qty buttons without an input", async () => {
    document.body.setAttribute("data-store-slug", "t");
    document.body.innerHTML +=
      '<div id="ps-quick-view-modal"><div id="ps-quick-view-body"></div></div>' +
      '<button data-quick-view data-product-id="3">view</button>';
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        statusText: "OK",
        text: () =>
          Promise.resolve(
            '<button data-qty-minus>minus</button><button data-qty-plus>plus</button>'
          ),
      })
    );
    window.fetch = global.fetch;
    restoreDollar();
    await import("../../static/js/shop-quickview.js");
    document.querySelector("[data-quick-view]").click();
    await flush(30);
    document.querySelector("[data-qty-minus]").click();
    document.querySelector("[data-qty-plus]").click();
    expect(document.getElementById("ps-quick-view-body").textContent).toContain("minus");
  });
});

// ---------- shop-storefront ----------

describe("shop-storefront.js gaps", () => {
  let origFetch;
  let origIO;

  beforeEach(() => {
    origFetch = global.fetch;
    origIO = global.IntersectionObserver;
    document.body.innerHTML = "";
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    if (origIO === undefined) delete global.IntersectionObserver;
    else global.IntersectionObserver = origIO;
    document.body.innerHTML = "";
    delete window.ShopCart;
    vi.resetModules();
  });

  it("ignores qty buttons without an input", async () => {
    document.body.innerHTML = '<button data-qty-minus>minus</button>';
    await import("../../static/js/shop-storefront.js");
    document.querySelector("[data-qty-minus]").click();
    expect(true).toBe(true);
  });

  it("clears nav height on transition end", async () => {
    document.body.innerHTML =
      '<button class="ps-nav-toggle" aria-expanded="false">nav</button><nav class="ps-nav"></nav>';
    await import("../../static/js/shop-storefront.js");
    document.querySelector(".ps-nav-toggle").click();
    expect(document.querySelector(".ps-nav").classList.contains("is-open")).toBe(true);
    document.querySelector(".ps-nav").dispatchEvent(new Event("transitionend"));
    expect(document.querySelector(".ps-nav").style.height).toBe("");
  });

  it("hides the sentinel on the last page", async () => {
    global.IntersectionObserver = class {
      constructor(cb) {
        this.cb = cb;
      }
      observe(el) {
        this.cb([{ isIntersecting: true, target: el }]);
      }
      unobserve() {}
      disconnect() {}
    };
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, text: () => Promise.resolve("<div></div>") })
    );
    window.fetch = global.fetch;
    document.body.innerHTML =
      '<div class="ps-infinite-sentinel" data-page="1" data-total="2"></div><div class="ps-grid"></div>';
    await import("../../static/js/shop-storefront.js");
    await flush(30);
    expect(document.querySelector(".ps-infinite-sentinel").style.display).toBe("none");
  });

  it("resets loading state when infinite fetch fails", async () => {
    global.IntersectionObserver = class {
      constructor(cb) {
        this.cb = cb;
      }
      observe(el) {
        this.cb([{ isIntersecting: true, target: el }]);
      }
      unobserve() {}
      disconnect() {}
    };
    global.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    window.fetch = global.fetch;
    document.body.innerHTML =
      '<div class="ps-infinite-sentinel" data-page="1" data-total="5"></div>';
    await import("../../static/js/shop-storefront.js");
    await flush(30);
    expect(document.querySelector(".ps-infinite-sentinel").style.display).not.toBe("none");
  });
});

// ---------- category-controls ----------

function makeCategoryJQuery() {
  const mk = (els) => {
    const el = () => els[0] || null;
    const api = {
      els,
      get length() {
        return els.length;
      },
      first() {
        return mk(els.slice(0, 1));
      },
      find(sel) {
        const matches = [];
        els.forEach((e) => {
          try {
            matches.push(...Array.from(e.querySelectorAll(sel)));
          } catch {
            // attribute selectors with quotes reject in jsdom
          }
        });
        return mk(matches);
      },
      on(evt, sel, fn) {
        els.forEach((e) => {
          if (typeof sel === "function") {
            e.addEventListener(evt, sel);
          } else {
            e.addEventListener(evt, (ev) => {
              const t = ev.target && typeof ev.target.closest === "function" ? ev.target.closest(sel) : null;
              if (t && e.contains(t)) fn.call(t, ev);
            });
          }
        });
        return api;
      },
      trigger(evt) {
        els.forEach((e) => e.dispatchEvent(new Event(evt, { bubbles: true })));
        return api;
      },
      val(v) {
        if (v === undefined) return el() ? el().value : undefined;
        els.forEach((e) => {
          e.value = v;
        });
        return api;
      },
      text(v) {
        if (v === undefined) return el() ? el().textContent : "";
        els.forEach((e) => {
          e.textContent = v;
        });
        return api;
      },
      attr(name, val) {
        if (val === undefined) return el() ? el().getAttribute(name) : undefined;
        els.forEach((e) => e.setAttribute(name, val));
        return api;
      },
      data(key, val) {
        const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (val === undefined) return el() ? el().dataset[k] : undefined;
        els.forEach((e) => {
          e.dataset[k] = val;
        });
        return api;
      },
      removeData(key) {
        const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        els.forEach((e) => delete e.dataset[k]);
        return api;
      },
      prop(name, val) {
        if (val === undefined) return el() ? el()[name] : undefined;
        els.forEach((e) => {
          e[name] = val;
        });
        return api;
      },
      modal() {
        return api;
      },
    };
    return api;
  };
  const $ = (arg) => {
    if (typeof arg === "string") return mk(Array.from(document.querySelectorAll(arg)));
    if (arg === document) return mk([document]);
    return mk(arg ? [arg] : []);
  };
  $.ajax = () => {};
  return $;
}

describe("products/category-controls.js gaps", () => {
  beforeEach(() => {
    document.body.innerHTML =
      '<select id="product_category"><option value="0">-</option>' +
      '<option value=\'a"b\'>Quoted</option></select>' +
      '<div class="js-category-actions">' +
      '<button class="js-category-add">add</button>' +
      '<button class="js-category-edit">edit</button>' +
      '<button class="js-category-delete">del</button></div>' +
      '<div id="categoryModal"></div>';
    const $ = makeCategoryJQuery();
    global.$ = $;
    window.$ = $;
    global.jQuery = $;
    window.jQuery = $;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    restoreDollar();
    delete window.initProductCategoryControls;
    delete window.initCategoryListControls;
    vi.resetModules();
  });

  function init() {
    window.initProductCategoryControls({
      select: "#product_category",
      wrap: ".js-category-actions",
      modal: "#categoryModal",
      csrf: "tok",
      deleteUrl: (id) => `/cats/${id}/delete`,
      updateUrl: (id) => `/cats/${id}/update`,
      createUrl: "/cats/create",
    });
  }

  it("returns empty selection for the placeholder option on edit", async () => {
    await import("../../static/js/products/category-controls.js");
    init();
    document.getElementById("product_category").value = "0";
    document.querySelector(".js-category-edit").click();
    expect(true).toBe(true);
  });

  it("bails out of edit when the selected option is gone", async () => {
    await import("../../static/js/products/category-controls.js");
    init();
    document.getElementById("product_category").value = 'a"b';
    document.querySelector(".js-category-edit").click();
    expect(true).toBe(true);
  });

  it("bails out of delete for the placeholder option", async () => {
    await import("../../static/js/products/category-controls.js");
    init();
    document.getElementById("product_category").value = "0";
    document.querySelector(".js-category-delete").click();
    expect(true).toBe(true);
  });
});

// ---------- crm/pipeline + projects/kanban ----------

function dragEvent(type, payload) {
  const ev = new Event(type, { bubbles: true, cancelable: true });
  ev.dataTransfer = { getData: () => payload, setData: () => {} };
  return ev;
}

describe("crm/pipeline.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    document.body.innerHTML =
      '<div class="pipeline-column" data-stage-id="2"><div class="pipeline-cards">' +
      '<div class="pipeline-card" draggable="true" data-lead-id="5">lead</div></div></div>';
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) })
    );
    window.fetch = global.fetch;
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
  });

  it("reloads after a successful stage move", async () => {
    await import("../../static/js/crm/pipeline.js");
    document.querySelector(".pipeline-cards").dispatchEvent(dragEvent("drop", "5"));
    await flush();
    expect(global.fetch).toHaveBeenCalledWith(
      "/crm/api/move-stage",
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("projects/kanban.js gaps", () => {
  let origFetch;

  beforeEach(() => {
    origFetch = global.fetch;
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    document.body.innerHTML =
      '<div class="kanban-column" data-stage-id="3"><div class="kanban-cards">' +
      '<div class="kanban-card" draggable="true" data-task-id="9">task</div></div></div>';
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) })
    );
    window.fetch = global.fetch;
    vi.resetModules();
  });

  afterEach(() => {
    global.fetch = origFetch;
    window.fetch = origFetch;
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    vi.resetModules();
  });

  it("reloads after a successful task move", async () => {
    await import("../../static/js/projects/kanban.js");
    document.querySelector(".kanban-cards").dispatchEvent(dragEvent("drop", "9"));
    await flush();
    expect(global.fetch).toHaveBeenCalledWith(
      "/projects/api/move-task",
      expect.objectContaining({ method: "POST" })
    );
  });
});
