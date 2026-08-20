import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const MOD_PATH = "../../static/js/sales.js";

function buildDom() {
  document.body.innerHTML = "";
  document.head.innerHTML = "";

  const form = document.createElement("form");
  form.id = "saleForm";

  const lines = document.createElement("div");
  lines.id = "saleLines";

  // One initial sale line (template)
  const row = document.createElement("div");
  row.className = "sale-line";
  row.dataset.index = "0";
  row.innerHTML = `
    <input type="number" name="lines-0-quantity" class="quantity-input" value="1">
    <input type="number" name="lines-0-unit_price" class="price-input" value="10">
    <input type="number" name="lines-0-discount_rate" class="discount-input" value="0">
    <input type="number" name="lines-0-tax" class="tax-input" value="0">
    <button type="button" class="remove-line">Remove</button>
    <span class="stock-badge"></span>
  `;
  lines.appendChild(row);

  form.appendChild(lines);
  document.body.appendChild(form);

  const addBtn = document.createElement("button");
  addBtn.id = "addLine";
  addBtn.type = "button";
  document.body.appendChild(addBtn);

  for (const id of ["subtotal", "taxAmount", "shippingCostDisplay", "totalAmount", "discountTotalDisplay", "totalDiscount"]) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }

  const taxRate = document.createElement("input");
  taxRate.id = "taxRate";
  taxRate.value = "0";
  document.body.appendChild(taxRate);

  const shipping = document.createElement("input");
  shipping.id = "shippingCost";
  shipping.value = "0";
  document.body.appendChild(shipping);

  const discountTotal = document.createElement("input");
  discountTotal.id = "discountTotal";
  discountTotal.value = "0";
  document.body.appendChild(discountTotal);

  const currency = document.createElement("select");
  currency.name = "currency";
  currency.innerHTML = '<option value="USD">USD</option>';
  document.body.appendChild(currency);
}

function mockFetch(map) {
  const existing = globalThis.fetch?._map || {};
  const merged = { ...existing, ...map };
  const spy = vi.fn((url) => {
    const handler = merged[url] || merged[url.split("?")[0]];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  spy._map = merged;
  globalThis.fetch = spy;
  window.fetch = spy;
  return spy;
}

beforeEach(() => {
  buildDom();
  mockFetch({});
  window.alert = vi.fn();
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

async function loadModule() {
  await import(MOD_PATH + String.fromCharCode(63) + Date.now());
  await new Promise((r) => setTimeout(r, 50));
}

describe("sales.js extended", () => {
  it("recalc computes totals correctly", async () => {
    await loadModule();
    window._salesRecalc();
    expect(document.getElementById("subtotal").textContent).toBe("10.00 USD");
    expect(document.getElementById("totalAmount").textContent).toBe("10.00 USD");
  });

  it("recalc applies discount", async () => {
    await loadModule();
    document.querySelector('[name="lines-0-discount_rate"]').value = "10";
    window._salesRecalc();
    expect(document.getElementById("subtotal").textContent).toBe("9.00 USD");
    expect(document.getElementById("totalDiscount").textContent).toBe("1.00");
  });

  it("recalc applies tax and shipping", async () => {
    await loadModule();
    document.getElementById("taxRate").value = "10";
    document.getElementById("shippingCost").value = "5";
    window._salesRecalc();
    expect(document.getElementById("taxAmount").textContent).toBe("1.00 USD");
    expect(document.getElementById("totalAmount").textContent).toBe("16.00 USD");
  });

  it("addLine clones a row and clears values", async () => {
    await loadModule();
    const before = document.querySelectorAll(".sale-line").length;
    window._salesAddLine();
    const after = document.querySelectorAll(".sale-line").length;
    expect(after).toBe(before + 1);
    const newRow = document.querySelectorAll(".sale-line")[after - 1];
    expect(newRow.querySelector('[name$="-quantity"]').value).toBe("");
    expect(newRow.querySelector('[name$="-unit_price"]').value).toBe("");
  });

  it("removeLine removes row and renumbers", async () => {
    await loadModule();
    window._salesAddLine();
    expect(document.querySelectorAll(".sale-line").length).toBe(2);
    const row = document.querySelectorAll(".sale-line")[1];
    window._salesRemoveLine(row);
    expect(document.querySelectorAll(".sale-line").length).toBe(1);
  });

  it("removeLine prevents removing last row", async () => {
    await loadModule();
    const row = document.querySelector(".sale-line");
    window._salesRemoveLine(row);
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("بند"));
    expect(document.querySelectorAll(".sale-line").length).toBe(1);
  });

  it("currentMaxIndex returns highest index", async () => {
    await loadModule();
    expect(window._salesCurrentMaxIndex()).toBe(0);
    window._salesAddLine();
    expect(window._salesCurrentMaxIndex()).toBe(1);
  });

  it("renumberRow updates names and ids", async () => {
    await loadModule();
    const row = document.querySelector(".sale-line");
    window._salesRenumberRow(row, 5);
    expect(row.dataset.index).toBe("5");
    expect(row.querySelector('[name$="-quantity"]').name).toBe("lines-5-quantity");
  });

  it("clearRow clears inputs and selects", async () => {
    await loadModule();
    const row = document.querySelector(".sale-line");
    row.querySelector('[name$="-quantity"]').value = "99";
    window._salesClearRow(row);
    expect(row.querySelector('[name$="-quantity"]').value).toBe("");
  });

  it("fetchProductInfo returns data on success", async () => {
    mockFetch({
      "/api/products/1/info": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 1, price: 25, stock: 10 }) }),
    });
    await loadModule();
    const data = await window._salesFetchProductInfo(1, 2);
    expect(data.price).toBe(25);
  });

  it("fetchProductInfo returns empty on missing params", async () => {
    await loadModule();
    const data = await window._salesFetchProductInfo(0, 0);
    expect(data).toEqual({});
  });

  it("fetchProductInfo returns empty on network error", async () => {
    mockFetch({
      "/api/products/1/info": () => Promise.reject(new Error("network")),
    });
    await loadModule();
    const data = await window._salesFetchProductInfo(1, 2);
    expect(data).toEqual({});
  });

  it("updateAvailability shows stock badge", async () => {
    mockFetch({
      "/api/products/1/info": () =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ stock: 42 }) }),
    });
    await loadModule();
    const row = document.querySelector(".sale-line");
    await window._salesUpdateAvailability(1, 2, row);
    expect(row.querySelector(".stock-badge").textContent).toBe("متاح: 42");
  });

  it("updateAvailability clears badge when missing pid or wid", async () => {
    await loadModule();
    const row = document.querySelector(".sale-line");
    row.querySelector(".stock-badge").textContent = "old";
    await window._salesUpdateAvailability(0, 2, row);
    expect(row.querySelector(".stock-badge").textContent).toBe("");
  });
});
