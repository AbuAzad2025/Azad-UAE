with open('static/js/purchases/create.js', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = """function calculateTotalsClientSide() {

  let subtotal = 0;

  

  $('.product-line').each(function() {

    const lineId = $(this).attr('id');

    const lineNumber = lineId.split('_')[1];

    

    const qty = parseFloat($('.line-quantity[data-line="' + lineNumber + '"]').val()) || 0;

    const cost = parseFloat($('.line-cost[data-line="' + lineNumber + '"]').val()) || 0;

    const discount = parseFloat($('.line-discount[data-line="' + lineNumber + '"]').val()) || 0;

    

    const lineSubtotal = qty * cost;

    const lineDiscountAmount = lineSubtotal * (discount / 100);

    const lineTotal = lineSubtotal - lineDiscountAmount;

    

    $('#line_total_' + lineNumber).val(lineTotal.toFixed(2));

    subtotal += lineTotal;

  });

  

  const taxRate = parseFloat($('#tax_rate').val()) || 0;

  const taxAmount = subtotal * (taxRate / 100);



  const freight = parseFloat($('#freight').val()) || 0;

  const insurance = parseFloat($('#insurance').val()) || 0;

  const customsDuty = parseFloat($('#customs_duty').val()) || 0;

  const otherLanded = parseFloat($('#other_landed_cost').val()) || 0;

  const landedTotal = freight + insurance + customsDuty + otherLanded;



  const total = subtotal + taxAmount + landedTotal;



  $('#summary_subtotal').text(subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_tax').text(taxAmount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_landed_cost').text(landedTotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_total').text(total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

}"""

new_func = """async function calculateTotalsClientSide() {

  let subtotal = 0;

  

  $('.product-line').each(function() {

    const lineId = $(this).attr('id');

    const lineNumber = lineId.split('_')[1];

    

    const qty = parseFloat($('.line-quantity[data-line="' + lineNumber + '"]').val()) || 0;

    const cost = parseFloat($('.line-cost[data-line="' + lineNumber + '"]').val()) || 0;

    const discount = parseFloat($('.line-discount[data-line="' + lineNumber + '"]').val()) || 0;

    

    const lineSubtotal = qty * cost;

    const lineDiscountAmount = lineSubtotal * (discount / 100);

    const lineTotal = lineSubtotal - lineDiscountAmount;

    

    $('#line_total_' + lineNumber).val(lineTotal.toFixed(2));

    subtotal += lineTotal;

  });

  

  const taxRate = parseFloat($('#tax_rate').val()) || 0;

  const freight = parseFloat($('#freight').val()) || 0;

  const insurance = parseFloat($('#insurance').val()) || 0;

  const customsDuty = parseFloat($('#customs_duty').val()) || 0;

  const otherLanded = parseFloat($('#other_landed_cost').val()) || 0;

  const landedTotal = freight + insurance + customsDuty + otherLanded;



  // Backend API for exact calculation (handles prices_include_vat correctly)

  const pricesIncludeVat = window._PRICES_INCLUDE_VAT || false;

  const lines = [];

  $('.product-line').each(function() {

    const lineId = $(this).attr('id');

    const lineNumber = lineId.split('_')[1];

    const qty = parseFloat($('.line-quantity[data-line="' + lineNumber + '"]').val()) || 0;

    const cost = parseFloat($('.line-cost[data-line="' + lineNumber + '"]').val()) || 0;

    const discount = parseFloat($('.line-discount[data-line="' + lineNumber + '"]').val()) || 0;

    if (qty > 0 && cost > 0) {

      lines.push({ quantity: qty, unit_cost: cost, discount_percent: discount });

    }

  });

  

  try {

    const r = await fetch('/purchases/api/calculate-totals', {

      method: 'POST',

      headers: { 'Content-Type': 'application/json' },

      credentials: 'same-origin',

      body: JSON.stringify({

        lines: lines,

        tax_rate: taxRate,

        freight: freight,

        insurance: insurance,

        customs_duty: customsDuty,

        other_landed_cost: otherLanded,

        prices_include_vat: pricesIncludeVat

      })

    });

    const data = await r.json();

    if (data.success) {

      $('#summary_subtotal').text(data.subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      $('#summary_tax').text(data.tax_amount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      $('#summary_landed_cost').text(data.landed_cost.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      $('#summary_total').text(data.total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      return;

    }

  } catch (_) {}

  

  // Fallback: local calculation (exclusive only)

  const taxAmount = subtotal * (taxRate / 100);

  const total = subtotal + taxAmount + landedTotal;

  $('#summary_subtotal').text(subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_tax').text(taxAmount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_landed_cost').text(landedTotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

  $('#summary_total').text(total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

}"""

if old_func in content:
    content = content.replace(old_func, new_func)
    print('Fixed calculateTotalsClientSide')
else:
    print('calculateTotalsClientSide not found')

with open('static/js/purchases/create.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
