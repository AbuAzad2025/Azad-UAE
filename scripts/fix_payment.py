with open('tests/vitest/pos_index_extended.test.js', encoding='utf-8') as f:
    content = f.read()

old = '''  for (const id of ["orderType", "tableSelect", "paymentMethod", "warehouseId", "currency"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }'''

new = '''  for (const id of ["orderType", "tableSelect", "warehouseId", "currency"]) {
    const el = document.createElement("select");
    el.id = id;
    document.body.appendChild(el);
  }
  const pmSel = document.createElement("select");
  pmSel.id = "paymentMethod";
  pmSel.innerHTML = '<option value="cash">Cash</option><option value="card">Card</option>';
  document.body.appendChild(pmSel);'''

if old not in content:
    print("Old string not found")
    exit(1)

content = content.replace(old, new)

with open('tests/vitest/pos_index_extended.test.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
