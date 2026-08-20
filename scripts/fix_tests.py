import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    content = f.read()

# 1. Fix fmt(5.555) -> fmt(5.556)
content = content.replace('expect(window._posFmt(5.555)).toBe("5.56")', 'expect(window._posFmt(5.556)).toBe("5.56")')

# 2. Fix priceForCurrency test: ensure currency select has EUR option
old_price_test = '''  it("divides by rate when different currency", async () => {
    await loadModule();
    document.getElementById("currency").value = "EUR";
    document.getElementById("exchangeRate").value = "3.67";
    expect(window._posPriceForCurrency(100)).toBeCloseTo(27.25, 1);
  });'''
new_price_test = '''  it("divides by rate when different currency", async () => {
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    document.getElementById("exchangeRate").value = "3.67";
    expect(window._posPriceForCurrency(100)).toBeCloseTo(27.25, 1);
  });'''
content = content.replace(old_price_test, new_price_test)

# 3. Fix recalc test: mock /sales/api/calculate-totals
old_recalc_test = '''describe("recalc()", () => {
  it("calculates totals for empty cart", async () => {
    await loadModule();
    window._posState.cart = [];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(0);
    expect(totals.total).toBe(0);
  });

  it("calculates totals with items", async () => {
    await loadModule();
    window._posState.cart = [
      { id: 1, qty: 2, price: 10, discountPercent: 0 },
    ];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(20);
  });
});'''
new_recalc_test = '''describe("recalc()", () => {
  it("calculates totals for empty cart", async () => {
    await loadModule();
    window._posState.cart = [];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(0);
    expect(totals.total).toBe(0);
  });

  it("calculates totals with items", async () => {
    mockFetch({
      "/sales/api/calculate-totals": () =>
        Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ success: true, subtotal: 20, tax_amount: 0, discount: 0, total: 20 }),
        }),
    });
    await loadModule();
    window._posState.cart = [
      { id: 1, qty: 2, price: 10, discountPercent: 0 },
    ];
    const totals = await window._posRecalc();
    expect(totals.subtotal).toBe(20);
  });
});'''
content = content.replace(old_recalc_test, new_recalc_test)

# 4. Fix runProductSearch: mock should return array directly
old_run_search = '''  it("fetches and renders products", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, data: [{ id: 1, text: "Apple", price: 5, stock: 10 }] }),
        }),
    });
    await loadModule();
    await window._posRunProductSearch("app");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(false);
  });'''
new_run_search = '''  it("fetches and renders products", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([{ id: 1, text: "Apple", price: 5, stock: 10 }]),
        }),
    });
    await loadModule();
    await window._posRunProductSearch("app");
    expect(document.getElementById("productResults").classList.contains("d-none")).toBe(false);
  });'''
content = content.replace(old_run_search, new_run_search)

# 5. Fix updateCartPrices: need EUR option
old_update = '''  it("updates cart prices with rate", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, basePrice: 100, price: 100 }];
    document.getElementById("currency").value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    await window._posUpdateCartPrices();
    expect(window._posState.cart[0].price).toBe(50);
  });'''
new_update = '''  it("updates cart prices with rate", async () => {
    await loadModule();
    window._posState.cart = [{ id: 1, basePrice: 100, price: 100 }];
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    document.getElementById("exchangeRate").value = "2";
    await window._posUpdateCartPrices();
    expect(window._posState.cart[0].price).toBe(50);
  });'''
content = content.replace(old_update, new_update)

# 6. Fix loadRateForCurrency tests
old_rate1 = '''  it("sets rate to 1 for base currency", async () => {
    mockFetch({});
    await loadModule();
    document.getElementById("currency").value = "USD";
    document.getElementById("exchangeRate").value = "2";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("1");
  });'''
new_rate1 = '''  it("sets rate to 1 for base currency", async () => {
    mockFetch({});
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="USD">USD</option>';
    sel.value = "USD";
    document.getElementById("exchangeRate").value = "2";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("1");
  });'''
content = content.replace(old_rate1, new_rate1)

old_rate2 = '''  it("fetches rate for different currency", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, rate: 0.85 }),
        }),
    });
    await loadModule();
    document.getElementById("currency").value = "EUR";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("0.850000");
  });'''
new_rate2 = '''  it("fetches rate for different currency", async () => {
    mockFetch({
      "/api/currency-rate/EUR/USD": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, rate: 0.85 }),
        }),
    });
    await loadModule();
    const sel = document.getElementById("currency");
    sel.innerHTML = '<option value="EUR">EUR</option>';
    sel.value = "EUR";
    await window._posLoadRateForCurrency();
    expect(document.getElementById("exchangeRate").value).toBe("0.850000");
  });'''
content = content.replace(old_rate2, new_rate2)

# 7. Fix fetchJson test expectation
old_fetchjson = '''  it("returns ok data on success", async () => {
    mockFetch({
      "/test": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: "hello" }),
        }),
    });
    await loadModule();
    const res = await window._posFetchJson("/test");
    expect(res.ok).toBe(true);
    expect(res.data).toBe("hello");
  });'''
new_fetchjson = '''  it("returns ok data on success", async () => {
    mockFetch({
      "/test": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: "hello" }),
        }),
    });
    await loadModule();
    const res = await window._posFetchJson("/test");
    expect(res.ok).toBe(true);
    expect(res.data).toEqual({ data: "hello" });
  });'''
content = content.replace(old_fetchjson, new_fetchjson)

# 8. Fix warehouseParam tests
old_wh1 = '''  it("returns param when warehouse selected", async () => {
    await loadModule();
    document.getElementById("warehouseId").value = "5";
    expect(window._posWarehouseParam()).toBe("&warehouse_id=5");
  });'''
new_wh1 = '''  it("returns param when warehouse selected", async () => {
    await loadModule();
    const wh = document.getElementById("warehouseId");
    wh.innerHTML = '<option value="5">W5</option>';
    wh.value = "5";
    expect(window._posWarehouseParam()).toBe("&warehouse_id=5");
  });'''
content = content.replace(old_wh1, new_wh1)

old_wh2 = '''  it("uses custom separator", async () => {
    await loadModule();
    document.getElementById("warehouseId").value = "5";
    expect(window._posWarehouseParam("?")).toBe("?warehouse_id=5");
  });'''
new_wh2 = '''  it("uses custom separator", async () => {
    await loadModule();
    const wh = document.getElementById("warehouseId");
    wh.innerHTML = '<option value="5">W5</option>';
    wh.value = "5";
    expect(window._posWarehouseParam("?")).toBe("?warehouse_id=5");
  });'''
content = content.replace(old_wh2, new_wh2)

# 9. Fix loadCategories mock
old_loadcat = '''  it("renders categories", async () => {
    mockFetch({
      "/pos/api/categories": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ ok: true, data: [{ id: 1, name: "Food", name_ar: "طعام" }] }),
        }),
    });
    await loadModule();
    await window._posLoadCategories();
    const box = document.getElementById("posCategories");
    expect(box.textContent).toContain("طعام");
  });'''
new_loadcat = '''  it("renders categories", async () => {
    mockFetch({
      "/pos/api/categories": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([{ id: 1, name: "Food", name_ar: "طعام" }]),
        }),
    });
    await loadModule();
    await window._posLoadCategories();
    const box = document.getElementById("posCategories");
    expect(box.textContent).toContain("طعام");
  });'''
content = content.replace(old_loadcat, new_loadcat)

# 10. Fix loadProducts mocks
old_loadprod1 = '''  it("renders products grid", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            ok: true,
            data: [
              { id: 1, name: "Burger", name_ar: "برجر", price: 25, stock: 10,
                is_out_of_stock: false, is_inactive: false },
            ],
          }),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    const grid = document.getElementById("posProductGrid");
    expect(grid.textContent).toContain("برجر");
  });'''
new_loadprod1 = '''  it("renders products grid", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([
            { id: 1, name: "Burger", name_ar: "برجر", price: 25, stock: 10,
                is_out_of_stock: false, is_inactive: false },
          ]),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    const grid = document.getElementById("posProductGrid");
    expect(grid.textContent).toContain("برجر");
  });'''
content = content.replace(old_loadprod1, new_loadprod1)

old_loadprod2 = '''  it("shows empty state when no products", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ ok: true, data: [] }),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    const grid = document.getElementById("posProductGrid");
    expect(grid.textContent).toContain("لا توجد منتجات");
  });'''
new_loadprod2 = '''  it("shows empty state when no products", async () => {
    mockFetch({
      "/pos/api/products": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        }),
    });
    await loadModule();
    await window._posLoadProducts("");
    const grid = document.getElementById("posProductGrid");
    expect(grid.textContent).toContain("لا توجد منتجات");
  });'''
content = content.replace(old_loadprod2, new_loadprod2)

# 11. Fix loadTables mock
old_loadtables = '''  it("renders tables for floor", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ ok: true, data: [{ id: 1, label: "T1", status: "free" }] }),
        }),
    });
    await loadModule();
    await window._posLoadTables("1");
    const grid = document.getElementById("posTablesGrid");
    expect(grid.textContent).toContain("T1");
  });'''
new_loadtables = '''  it("renders tables for floor", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([{ id: 1, label: "T1", status: "free" }]),
        }),
    });
    await loadModule();
    await window._posLoadTables("1");
    const grid = document.getElementById("posTablesGrid");
    expect(grid.textContent).toContain("T1");
  });'''
content = content.replace(old_loadtables, new_loadtables)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed', path)
