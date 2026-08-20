with open('tests/vitest/pos_index.test.js', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Move exchangeRate from select to input
old_select = 'for (const id of ["orderType", "tableSelect", "paymentMethod", "warehouseId", "currency", "exchangeRate"]) { const el = document.createElement("select"); el.id = id; document.body.appendChild(el); }'
new_select = 'for (const id of ["orderType", "tableSelect", "paymentMethod", "warehouseId", "currency"]) { const el = document.createElement("select"); el.id = id; document.body.appendChild(el); }'
content = content.replace(old_select, new_select)

old_input = 'for (const id of ["taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber", "orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes"]) { const el = document.createElement("input"); el.id = id; document.body.appendChild(el); }'
new_input = 'for (const id of ["taxRate", "shippingCost", "discountAmount", "paidAmount", "referenceNumber", "orderNote", "openSessionBalance", "openSessionNotes", "closeSessionBalance", "closeSessionNotes", "exchangeRate"]) { const el = document.createElement("input"); el.id = id; document.body.appendChild(el); }'
content = content.replace(old_input, new_input)

# Fix 2: Make mockFetch merge handlers
old_mock = '''function mockFetch(map) {
  const spy = vi.fn((url) => {
    const handler = map[url] || map[url.split("?")[0]];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
    globalThis.fetch = spy; window.fetch = spy; console.log("FETCH_SET", typeof globalThis.fetch);
  
  return spy;
}'''
new_mock = '''function mockFetch(map) {
  const existing = globalThis.fetch?._map || {};
  const merged = { ...existing, ...map };
  const spy = vi.fn((url) => {
    const handler = merged[url] || merged[url.split("?")[0]];
    if (handler) return handler(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
  });
  spy._map = merged;
  globalThis.fetch = spy; window.fetch = spy;
  return spy;
}'''
content = content.replace(old_mock, new_mock)

with open('tests/vitest/pos_index.test.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed test file")
