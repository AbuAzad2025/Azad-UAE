import os

with open('static/js/purchases/create.js', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('function calculateTotalsClientSide() {')
if start_idx == -1:
    print('function not found')
    exit(1)

brace_count = 1
i = start_idx + len('function calculateTotalsClientSide() {')
while i < len(content) and brace_count > 0:
    if content[i] == '{':
        brace_count += 1
    elif content[i] == '}':
        brace_count -= 1
    i += 1

# Build new function using chr(36) for $ to avoid shell issues
D = chr(36)
new_func = f"""async function calculateTotalsClientSide() {{
  let subtotal = 0;
  {D}('.product-line').each(function() {{
    const lineId = {D}(this).attr('id');
    const lineNumber = lineId.split('_')[1];
    const qty = parseFloat({D}('.line-quantity[data-line="' + lineNumber + '"]').val()) || 0;
    const cost = parseFloat({D}('.line-cost[data-line="' + lineNumber + '"]').val()) || 0;
    const discount = parseFloat({D}('.line-discount[data-line="' + lineNumber + '"]').val()) || 0;
    const lineSubtotal = qty * cost;
    const lineDiscountAmount = lineSubtotal * (discount / 100);
    const lineTotal = lineSubtotal - lineDiscountAmount;
    {D}('#line_total_' + lineNumber).val(lineTotal.toFixed(2));
    subtotal += lineTotal;
  }});
  const taxRate = parseFloat({D}('#tax_rate').val()) || 0;
  const freight = parseFloat({D}('#freight').val()) || 0;
  const insurance = parseFloat({D}('#insurance').val()) || 0;
  const customsDuty = parseFloat({D}('#customs_duty').val()) || 0;
  const otherLanded = parseFloat({D}('#other_landed_cost').val()) || 0;
  const landedTotal = freight + insurance + customsDuty + otherLanded;
  const pricesIncludeVat = window._PRICES_INCLUDE_VAT || false;
  const lines = [];
  {D}('.product-line').each(function() {{
    const lineId = {D}(this).attr('id');
    const lineNumber = lineId.split('_')[1];
    const qty = parseFloat({D}('.line-quantity[data-line="' + lineNumber + '"]').val()) || 0;
    const cost = parseFloat({D}('.line-cost[data-line="' + lineNumber + '"]').val()) || 0;
    const discount = parseFloat({D}('.line-discount[data-line="' + lineNumber + '"]').val()) || 0;
    if (qty > 0 && cost > 0) {{
      lines.push({{ quantity: qty, unit_cost: cost, discount_percent: discount }});
    }}
  }});
  try {{
    const r = await fetch('/purchases/api/calculate-totals', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      credentials: 'same-origin',
      body: JSON.stringify({{
        lines: lines,
        tax_rate: taxRate,
        freight: freight,
        insurance: insurance,
        customs_duty: customsDuty,
        other_landed_cost: otherLanded,
        prices_include_vat: pricesIncludeVat
      }})
    }});
    const data = await r.json();
    if (data.success) {{
      {D}('#summary_subtotal').text(data.subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
      {D}('#summary_tax').text(data.tax_amount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
      {D}('#summary_landed_cost').text(data.landed_cost.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
      {D}('#summary_total').text(data.total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
      return;
    }}
  }} catch (_) {{}}
  const taxAmount = subtotal * (taxRate / 100);
  const total = subtotal + taxAmount + landedTotal;
  {D}('#summary_subtotal').text(subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  {D}('#summary_tax').text(taxAmount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  {D}('#summary_landed_cost').text(landedTotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  {D}('#summary_total').text(total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
}}
"""

content = content[:start_idx] + new_func + content[i:]

with open('static/js/purchases/create.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed calculateTotalsClientSide')
