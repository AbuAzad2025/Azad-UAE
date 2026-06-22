// Tenant currency config for unified display

const TENANT_BASE_CURRENCY = {{ tenant_default_currency|tojson }} || window._FX_FALLBACK_BASE || 'AED';

const TENANT_CURRENCY_SYMBOL = {{ tenant_currency_symbol|tojson }} || window._CURRENCY_SYMBOL || 'AED';



let lineIndex = 0;



// =====================================

// إضافة سطر منتج جديد

// =====================================

function addLine() {

  const html = `

    <div class="product-line mb-3 p-3 ic-1" id="line_${lineIndex}">

      <div class="row align-items-end">

        

        <div class="col-md-4">

          <label class="small" for="line_${lineIndex}_product_id"><i class="fas fa-box"></i> المنتج</label>

          <select name="lines[${lineIndex}][product_id]" 

                  id="line_${lineIndex}_product_id"

                  class="form-control product-select line-product" 

                  data-line="${lineIndex}" required aria-label="lines[${lineIndex}][product id]">

            <option value="">بلا</option>

          </select>

        </div>

        

        

        <div class="col-md-2">

          <label class="small" for="line_${lineIndex}_quantity"><i class="fas fa-sort-numeric-up"></i> الكمية</label>

          <input type="number" name="lines[${lineIndex}][quantity]" 

                 id="line_${lineIndex}_quantity"

                 class="form-control line-quantity" data-line="${lineIndex}"

                 placeholder="{{ t('Quantity') }}" value="1" step="0.01" min="0.01" required>

        </div>

        

        

        <div class="col-md-2">

          <label class="small" for="line_${lineIndex}_unit_cost"><i class="fas fa-dollar-sign"></i> التكلفة</label>

          <input type="number" name="lines[${lineIndex}][unit_cost]" 

                 id="line_${lineIndex}_unit_cost"

                 class="form-control line-cost" data-line="${lineIndex}"

                 placeholder="0.00" step="0.01" min="0" required>

        </div>

        

        

        <div class="col-md-2">

          <label class="small" for="line_${lineIndex}_discount"><i class="fas fa-percentage"></i> خصم%</label>

          <input type="number" name="lines[${lineIndex}][discount_percent]" 

                 id="line_${lineIndex}_discount"

                 class="form-control line-discount" data-line="${lineIndex}"

                 placeholder="0" value="0" step="0.01" min="0" max="100">

        </div>

        

        

        <div class="col-md-1">

          <label class="small" for="line_total_${lineIndex}"><i class="fas fa-equals"></i> المجموع</label>

          <input type="text" class="form-control line-total bg-light" 

                 id="line_total_${lineIndex}" data-line="${lineIndex}" value="0.00" readonly aria-label="line total ${lineIndex}">

        </div>

        

        

        <div class="col-md-1">

          <button type="button" class="btn btn-danger btn-block" 

                  onclick="removeLine(${lineIndex})" title="{{ t('Delete') }}">

            <i class="fas fa-trash"></i>

          </button>

        </div>

      </div>

      <div class="row mt-2 serial-row" id="serial_row_${lineIndex}" style="display:none;">

        <div class="col-md-12">

          <label class="small"><i class="fas fa-barcode"></i> أرقام السيريال / IMEI <small class="text-muted">(واحد لكل سطر)</small></label>

          <textarea name="lines[${lineIndex}][serials]" id="line_${lineIndex}_serials"

                    class="form-control serial-textarea" rows="2"

                    placeholder="SN001&#10;SN002" data-line="${lineIndex}"></textarea>

        </div>

      </div>

    </div>

  `;

  

  $('#linesContainer').append(html);

  

  // تفعيل Select2 للمنتج باستخدام الفلتر الذكي

  const $productSelect = $(`select[name="lines[${lineIndex}][product_id]"]`);

  

  // استخدام نفس التكوين من customer-select.js

  if (window.SmartSelectors) {

    window.SmartSelectors.initProducts($productSelect[0]);

  } else {

    // Fallback: تكوين يدوي

    $productSelect.select2({

      ajax: {

        {% if current_user.has_permission('view_reports') %}
        url: "{{ url_for('api.api_search') }}",
        {% endif %}

        dataType: 'json',

        delay: 250,

        data: function(params) {

          return {

            q: params.term || '',

            type: 'products',

            purpose: 'purchase',

            warehouse_id: $('#warehouse_id').val() || '',

            page: params.page || 1

          };

        },

        processResults: function(data) {

          return {

            results: data.results.map(p => ({

              id: p.id,

              text: p.name,

              name: p.name,

              sku: p.sku,

              cost_price: p.cost_price || 0,

              current_stock: p.current_stock || 0

            })),

            pagination: { more: data.has_more || false }

          };

        },

        cache: true

      },

      placeholder: 'ابحث عن منتج...',

      allowClear: true,

      minimumInputLength: 0,

      dir: 'rtl',

      width: '100%',

      language: 'ar',

      templateResult: function(p) {

        if (p.loading) return 'جاري البحث...';

        if (!p.id) return p.text;

        

        const stockIcon = (p.current_stock || 0) > 0 ? '✅' : '❌';

        const stockClass = (p.current_stock || 0) > 0 ? 'text-success' : 'text-danger';

        

        return $(`

          <div class="ic-2">

            <div class="d-flex justify-content-between">

              <div>

                <strong>📦 ${p.text}</strong>

                <br><small class="text-muted">SKU: ${p.sku || '-'}</small>

              </div>

              <div class="text-left">

                <small><strong>${(p.cost_price || 0).toFixed(2)} ${TENANT_CURRENCY_SYMBOL}</strong></small>

                <br><small class="${stockClass}">${stockIcon} ${p.current_stock || 0}</small>

              </div>

            </div>

          </div>

        `);

      },

      templateSelection: function(p) {

        return p.id ? `📦 ${p.text}` : p.text;

      },

      escapeMarkup: function(m) { return m; }

    });

  }

  

  // حساب الإجمالي عند التغيير - استخدام setTimeout للتأكد من التحميل

  setTimeout(function() {

    $(`.line-quantity[data-line="${lineIndex}"], .line-cost[data-line="${lineIndex}"], .line-discount[data-line="${lineIndex}"]`)

      .on('input change keyup', function() {

        if ($(this).hasClass('line-cost')) {

          const enteredCost = parseFloat($(this).val()) || 0;

          const rate = parseFloat($('#exchange_rate').val()) || 1;

          const currency = $('#currency').val();

          $(this).data('base-cost', currency !== TENANT_BASE_CURRENCY && rate > 0 ? enteredCost * rate : enteredCost);

        }

        calculateLineTotal(lineIndex);

        calculateTotals();

      });

  }, 100);

  

  $productSelect.on('select2:select', function(e) {

    const data = e.params.data;

    if (data && data.cost_price) {

      $(`.line-cost[data-line="${lineIndex}"]`).data('base-cost', parseFloat(data.cost_price) || 0);

      updateLineCosts();

    }

    if (data && data.has_serial_number) {

      $(`#serial_row_${lineIndex}`).show();

    } else {

      $(`#serial_row_${lineIndex}`).hide();

    }

  });

  

  lineIndex++;

  $('#line_count').val(lineIndex);

}



// =====================================

// حذف سطر

// =====================================

function removeLine(index) {

  $(`#line_${index}`).remove();

  calculateTotals();

}



// =====================================

// حساب إجمالي السطر

// =====================================

function calculateLineTotal(index) {

  const qty = parseFloat($(`.line-quantity[data-line="${index}"]`).val()) || 0;

  const cost = parseFloat($(`.line-cost[data-line="${index}"]`).val()) || 0;

  const discount = parseFloat($(`.line-discount[data-line="${index}"]`).val()) || 0;

  

  const subtotal = qty * cost;

  const discountAmount = subtotal * (discount / 100);

  const total = subtotal - discountAmount;

  

  $(`#line_total_${index}`).val(total.toFixed(2));

}



// =====================================

// حساب إجمالي الفاتورة - Backend Calculation

// =====================================

async function calculateTotals() {

  try {

    // جمع البيانات من الفورم

    const lines = [];

    $('.product-line').each(function() {

      const lineId = $(this).attr('id');

      const lineNumber = lineId.split('_')[1];

      

      const qty = parseFloat($(`.line-quantity[data-line="${lineNumber}"]`).val()) || 0;

      const cost = parseFloat($(`.line-cost[data-line="${lineNumber}"]`).val()) || 0;

      const discount = parseFloat($(`.line-discount[data-line="${lineNumber}"]`).val()) || 0;

      

      if (qty > 0 || cost > 0) {

        lines.push({

          quantity: qty,

          unit_cost: cost,

          discount_percent: discount

        });

      }

    });

    

    const tax_rate = parseFloat($('#tax_rate').val()) || 0;

    

    // إرسال للـ backend

    const response = await fetch('{{ url_for("purchases.api_calculate_purchase_totals") }}', {

      method: 'POST',

      headers: {

        'Content-Type': 'application/json'

      },

      body: JSON.stringify({

        lines: lines,

        tax_rate: tax_rate,

        freight: parseFloat($('#freight').val()) || 0,

        insurance: parseFloat($('#insurance').val()) || 0,

        customs_duty: parseFloat($('#customs_duty').val()) || 0,

        other_landed_cost: parseFloat($('#other_landed_cost').val()) || 0

      })

    });

    

    const result = await response.json();

    

    if (result.success) {

      // تحديث الواجهة

      $('#summary_subtotal').text(result.subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      $('#summary_tax').text(result.tax_amount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      if (result.landed_cost !== undefined) {

        $('#summary_landed_cost').text(result.landed_cost.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);

      }

      $('#summary_total').text(result.total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);    } else {      // Fallback to client-side

      await calculateTotalsClientSide();

    }

  } catch (error) {    // Fallback to client-side

    await calculateTotalsClientSide();

  }

}



// Fallback: حساب محلي

async function calculateTotalsClientSide() {
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
  const taxAmount = subtotal * (taxRate / 100);
  const total = subtotal + taxAmount + landedTotal;
  $('#summary_subtotal').text(subtotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  $('#summary_tax').text(taxAmount.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  $('#summary_landed_cost').text(landedTotal.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
  $('#summary_total').text(total.toFixed(2) + ' ' + TENANT_CURRENCY_SYMBOL);
}







// =====================================

// تحديث أسعار التكلفة عند تغيير العملة

// =====================================

function updateLineCosts() {

    const currency = $('#currency').val();

    const rate = parseFloat($('#exchange_rate').val()) || 1;

    

    $('.line-cost').each(function() {

        const baseCost = parseFloat($(this).data('base-cost'));

        if (!isNaN(baseCost)) {

            let finalCost = baseCost;

            if (currency !== TENANT_BASE_CURRENCY && rate > 0) {

                finalCost = baseCost / rate;

            }

            $(this).val(finalCost.toFixed(2));

            

            // Recalculate line total

            const lineId = $(this).data('line');

            calculateLineTotal(lineId);

        }

    });

    calculateTotals();

}



// =====================================

// تغيير العملة - جلب سعر الصرف

// =====================================

$('#currency').on('change', function() {

  const currency = $(this).val();

  

  if (currency !== TENANT_BASE_CURRENCY) {

    $.ajax({

      url: `/api/currency-rate/${currency}/${TENANT_BASE_CURRENCY}`,

      success: function(data) {

        if (data.rate) {

          $('#exchange_rate').val(data.rate.toFixed(6));

          updateLineCosts();

        } else {

          toastr.warning('يرجى إدخال سعر الصرف يدوياً');

        }

      },

      error: function() {

        toastr.warning('يرجى إدخال سعر الصرف يدوياً');

      }

    });

  } else {

    $('#exchange_rate').val('1.000000');

    updateLineCosts();

  }

});



$('#exchange_rate').on('input change', function() {

    updateLineCosts();

});



// =====================================

// اختيار المورد - تعبئة البيانات

// =====================================

$('#supplier_id').on('change', function() {

  const selectedData = $(this).select2('data')[0];

  

  if (selectedData) {

    $('#supplier_phone').val(selectedData.phone || '');

    $('#supplier_email').val(selectedData.email || '');

    

    // عرض معلومات المورد

    if (selectedData.is_verified) {

      toastr.success(`✅ مورد موثوق: ${selectedData.name}`);

    }

  }

});



// =====================================

// Event Delegation - للتعامل مع العناصر المضافة ديناميكياً

// =====================================

$(document).on('input change keyup', '.line-quantity, .line-cost, .line-discount', function() {  const lineNumber = $(this).data('line');

  if (lineNumber !== undefined) {

    calculateLineTotal(lineNumber);

    calculateTotals();

  }

});



// =====================================

// التهيئة عند تحميل الصفحة

// =====================================

$(document).ready(function() {  

  // إضافة أول سطر

  addLine();

  

  // حساب عند تغيير الضريبة

  $('#tax_rate').on('input change', function() {    calculateTotals();

  });

  

  // زر إعادة الحساب اليدوي

  $('#recalcTotalsBtn').on('click', function() {    calculateTotals();

  });

  

  // زر إضافة سطر منتج

  $('#addLineBtn').on('click', function() {    addLine();

  });

  

  // التحقق قبل الإرسال

  $('#purchaseForm').on('submit', function(e) {    

    const lineCount = $('.product-line').length;    

    if (lineCount === 0) {

      e.preventDefault();

      toastr.error('يجب إضافة منتج واحد على الأقل');

      return false;

    }

    

    // التحقق من اختيار المورد

    if (!$('#supplier_id').val()) {

      e.preventDefault();

      toastr.error('يجب اختيار المورد');

      return false;

    }

    

    // طباعة جميع البيانات قبل الإرسال    

    // طباعة بيانات كل سطر

    $('.product-line').each(function(index) {

      const lineId = $(this).attr('id');

      const lineNumber = lineId.split('_')[1];

      

      const productId = $(`.line-product[data-line="${lineNumber}"]`).val();

      const quantity = $(`.line-quantity[data-line="${lineNumber}"]`).val();

      const cost = $(`.line-cost[data-line="${lineNumber}"]`).val();

      const discount = $(`.line-discount[data-line="${lineNumber}"]`).val();    });  });

});
