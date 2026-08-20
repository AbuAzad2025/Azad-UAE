with open('tests/vitest/sales_js_extended.test.js', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''  row.innerHTML = `
    <input name="lines-0-quantity" class="quantity-input" value="1">
    <input name="lines-0-unit_price" class="price-input" value="10">
    <input name="lines-0-discount_rate" class="discount-input" value="0">
    <input name="lines-0-tax" class="tax-input" value="0">
    <button type="button" class="remove-line">Remove</button>
    <span class="stock-badge"></span>
  `;'''

new = '''  row.innerHTML = `
    <input type="number" name="lines-0-quantity" class="quantity-input" value="1">
    <input type="number" name="lines-0-unit_price" class="price-input" value="10">
    <input type="number" name="lines-0-discount_rate" class="discount-input" value="0">
    <input type="number" name="lines-0-tax" class="tax-input" value="0">
    <button type="button" class="remove-line">Remove</button>
    <span class="stock-badge"></span>
  `;'''

if old not in content:
    print("Old not found")
    exit(1)

content = content.replace(old, new)

with open('tests/vitest/sales_js_extended.test.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
