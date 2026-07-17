/**
 * Sales Module - Enhanced Features
 * تحسينات خاصة بالمبيعات
 */

let lineIndex = 0;

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

/**
 * Add Product Line
 */
function addLine() {
    const html = `
        <div class="product-line mb-3 p-3" id="line_${lineIndex}" style="background: #f8f9fa; border-radius: 8px; border-right: 4px solid #667eea;">
            <div class="row">
                <div class="col-md-5">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-box text-primary"></i> المنتج
                        <span class="text-danger">*</span>
                    </label>
                    <select name="lines[${lineIndex}][product_id]" class="form-control product-select" required 
                            data-index="${lineIndex}" onchange="loadProductPrice(${lineIndex})">
                        <option value="">بلا</option>
                    </select>
                    <small class="text-muted">ابحث بالاسم أو رقم القطعة</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-sort-numeric-up text-info"></i> الكمية
                        <span class="text-danger">*</span>
                    </label>
                    <input type="number" name="lines[${lineIndex}][quantity]" class="form-control quantity-input" 
                           placeholder="الكمية" value="1" step="0.01" min="0.01" required 
                           onchange="calculateTotals()" onkeyup="calculateTotals()">
                    <small class="text-muted">عدد الوحدات</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-money-bill text-success"></i> السعر
                        <span class="text-danger">*</span>
                    </label>
                    <input type="number" name="lines[${lineIndex}][unit_price]" class="form-control price-input" 
                           placeholder="السعر" step="0.01" min="0" required 
                           id="price_${lineIndex}" onchange="calculateTotals()" onkeyup="calculateTotals()"
                           title="سعر الوحدة بالعملة الأساسية">
                    <small class="text-muted">${window._CURRENCY_SYMBOL || 'AED'}/وحدة</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-percent text-warning"></i> خصم
                    </label>
                    <input type="number" name="lines[${lineIndex}][discount_percent]" class="form-control discount-input" 
                           placeholder="خصم%" value="0" step="0.01" min="0" max="100" 
                           onchange="calculateTotals()" onkeyup="calculateTotals()">
                    <small class="text-muted">نسبة الخصم %</small>
                </div>
                <div class="col-md-2 text-center" id="serial_btn_container_${lineIndex}" style="display:none;">
                    <label class="font-weight-bold mb-1">&nbsp;</label>
                    <button type="button" class="btn btn-warning btn-sm btn-block" id="serial_btn_${lineIndex}" 
                            onclick="triggerSerialModal(${lineIndex})">
                        <i class="fas fa-fingerprint"></i> سيريال
                    </button>
                    <small class="text-muted">مطلوب إدخال السيريال</small>
                </div>
                <div class="col-md-1">
                    <label class="font-weight-bold mb-1">&nbsp;</label>
                    <button type="button" class="btn btn-danger btn-sm btn-block" onclick="removeLine(${lineIndex})" title="حذف الصنف">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="row mt-2" id="line_info_${lineIndex}" style="display:none;">
                <div class="col-12">
                    <small class="text-muted">
                        <i class="fas fa-box mr-1"></i>المخزون: <span id="stock_${lineIndex}">-</span> |
                        <i class="fas fa-dollar-sign mr-1"></i>التكلفة: <span id="cost_${lineIndex}">-</span>
                    </small>
                </div>
            </div>
        </div>
    `;
    
    $('#linesContainer').append(html);
    
    const newSelect = $(`select[name="lines[${lineIndex}][product_id]"]`);
    
    // استخدام الفلتر الذكي الموحد
    if (window.SmartSelectors) {
        window.SmartSelectors.initProducts(newSelect[0]);
    } else {
        // Fallback: استخدام API موحد
        newSelect.select2({
            ajax: {
                url: '/api/search',
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        q: params.term || '',
                        type: 'products',
                        page: params.page || 1
                    };
                },
                processResults: function(data) {
                    return {
                        results: (data.results || []).map(p => ({
                            id: p.id,
                            text: p.name || p.text,
                            price: p.default_price || p.regular_price || p.unit_price || 0,
                            stock: p.current_stock || 0,
                            cost: p.cost_price || 0,
                            unit: p.unit || 'قطعة',
                            sku: p.sku
                        })),
                        pagination: { more: data.has_more || false }
                    };
                }
            },
            language: 'ar',
            dir: 'rtl',
            placeholder: 'ابحث عن منتج...',
            minimumInputLength: 0,
            width: '100%'
        });
    }
    
    newSelect.on('select2:select', function(e) {
        // تحميل السعر والمخزون عند اختيار منتج
        const selectedData = e.params.data;
        const currentIndex = $(this).data('index');
        const customerId = $('#customer_id').val();
        
        // Load price based on customer type
        if (customerId && selectedData.id) {
            $.ajax({
                url: '/sales/api/get-price',
                data: {
                    product_id: selectedData.id,
                    customer_id: customerId
                },
                success: function(data) {
                    if (data.price) {
                        $(`#price_${currentIndex}`).val(parseFloat(data.price).toFixed(2));
                    }
                    if (data.current_stock !== undefined) {
                        $(`#stock_${currentIndex}`).text(data.current_stock + ' ' + (data.unit || ''));
                        $(`#line_info_${currentIndex}`).show();
                        
                        if (data.current_stock < 1) {
                            $(`#stock_${currentIndex}`).addClass('text-danger font-weight-bold');
                            if (typeof azad !== 'undefined') {
                                azad.showWarning('⚠️ تنبيه: المخزون منخفض للمنتج');
                            }
                        }
                    }
                    if (data.cost_price) {
                        $(`#cost_${currentIndex}`).text(parseFloat(data.cost_price).toFixed(2) + ' ' + (window._CURRENCY_SYMBOL || 'AED'));
                    }
                    void calculateTotals();
                },
                error: function() {
                    // Fallback to selected data
                    if (selectedData.price) {
                        $(`#price_${currentIndex}`).val(parseFloat(selectedData.price).toFixed(2));
                    }
                    void calculateTotals();
                }
            });
        } else {
            // Use default price from search result
            if (selectedData.price) {
                $(`#price_${currentIndex}`).val(parseFloat(selectedData.price).toFixed(2));
            }
        }
        
        if (selectedData.stock !== undefined) {
            $(`#stock_${currentIndex}`).text(selectedData.stock + ' ' + (selectedData.unit || ''));
            $(`#line_info_${currentIndex}`).show();
        }
        
        if (selectedData.cost) {
            $(`#cost_${currentIndex}`).text(parseFloat(selectedData.cost).toFixed(2) + ' ' + (window._CURRENCY_SYMBOL || 'AED'));
        }
        
        // حساب الإجماليات
        void calculateTotals();
    });
    
    lineIndex++;
    $('#line_count').val(lineIndex);
}

/**
 * Remove Product Line
 */
function removeLine(index) {
    $(`#line_${index}`).remove();
    void calculateTotals();
}

/**
 * Load Product Price based on Customer Type
 */
function loadProductPrice(index) {
    const customerId = $('#customer_id').val();
    const productId = $(`select[name="lines[${index}][product_id]"]`).val();
    
    if (!customerId || !productId) {
        return;
    }
    
    azad.showLoading();
    
    $.ajax({
        url: '/sales/api/get-price',
        data: { 
            product_id: productId, 
            customer_id: customerId 
        },
        success: function(data) {
            // Store base price in base currency
            $(`#price_${index}`).data('base-price', data.price);
            
            // Calculate price based on current currency
            const rate = parseFloat($('#exchange_rate').val()) || 1;
            const currency = $('#currency').val();
            
            let finalPrice = data.price;
            if (currency !== (window._FX_FALLBACK_BASE || 'AED') && rate > 0) {
                finalPrice = data.price / rate;
            }
            
            $(`#price_${index}`).val(finalPrice.toFixed(2));
            
            if (data.current_stock !== undefined) {
                $(`#stock_${index}`).text(data.current_stock + ' ' + (data.unit || ''));
                
                if (data.current_stock < 1) {
                    $(`#stock_${index}`).addClass('text-danger font-weight-bold');
                    azad.showError(`⚠️ تنبيه: المخزون منخفض للمنتج`);
                }
            }
            
            if (data.cost_price && data.cost_price > 0) {
                $(`#cost_${index}`).text(data.cost_price.toFixed(2) + ' ' + (window._CURRENCY_SYMBOL || 'AED'));
            }
            
            // Check Serial Number Requirement (Outside cost check, always check product data)
            if (data.has_serial_number) {
                $(`#serial_btn_container_${index}`).show();
                $(`#serial_btn_${index}`).data('product-name', data.name);
                $(`#serial_btn_${index}`).data('needed', true);
                
                // Adjust column width to fit button
                $(`#serial_btn_container_${index}`).prev().removeClass('col-md-2').addClass('col-md-1'); // Discount
                // $(`#serial_btn_container_${index}`).prev().prev().removeClass('col-md-2').addClass('col-md-2'); // Price
            } else {
                $(`#serial_btn_container_${index}`).hide();
                $(`#serial_btn_${index}`).data('needed', false);
                $(`#serial_btn_container_${index}`).prev().removeClass('col-md-1').addClass('col-md-2'); // Restore Discount
            }

            $(`#line_info_${index}`).show();
            
            void calculateTotals();
            azad.hideLoading();
        },
        error: function() {
            azad.hideLoading();
            azad.showError('فشل تحميل السعر');
        }
    });
}

/**
 * Trigger Serial Modal
 */
function triggerSerialModal(lineIndex) {
    const btn = $(`#serial_btn_${lineIndex}`);
    if (!btn.data('needed')) return;
    
    const productName = btn.data('product-name');
    const qty = $(`input[name="lines[${lineIndex}][quantity]"]`).val();
    
    if (typeof openSerialModal === 'function') {
        openSerialModal(lineIndex, productName, qty);
    }
}

/**
 * Update all line prices based on exchange rate
 */
function updateLinePrices() {
    const $exchangeRate = $('#exchange_rate');
    const $currency = $('#currency');
    const rate = parseFloat($exchangeRate.val()) || 1;
    const currency = $currency.val();
    
    $('.product-line').each(function() {
        const index = $(this).find('.product-select').data('index');
        const $priceInput = $(`#price_${index}`);
        const basePrice = parseFloat($priceInput.data('base-price'));
        
        if (!isNaN(basePrice)) {
            let finalPrice = basePrice;
            if (currency !== (window._FX_FALLBACK_BASE || 'AED') && rate > 0) {
                finalPrice = basePrice / rate;
            }
            $priceInput.val(finalPrice.toFixed(2));
        }
    });
    
    updateCurrencyLabels();
    void calculateTotals();
}

function updateCurrencyLabels() {
    const $currency = $('#currency');
    const currency = $currency.val();
    $('#discount_currency').text(currency);
    $('#shipping_currency').text(currency);
    $('#total_currency_label').text(currency);
}

/**
 * Calculate All Totals
 */
// حساب الإجماليات - Backend Calculation
async function calculateTotals() {
    try {
        // جمع البيانات من الفورم
        const lines = [];
        $('[name^="lines"][name$="[quantity]"]').each(function() {
            const $line = $(this).closest('.product-line');
            const qty = parseFloat($(this).val()) || 0;
            const price = parseFloat($line.find('[name$="[unit_price]"]').val()) || 0;
            const discount = parseFloat($line.find('[name$="[discount_percent]"]').val()) || 0;
            
            if (qty > 0 || price > 0) {
                lines.push({
                    quantity: qty,
                    unit_price: price,
                    discount_percent: discount
                });
            }
        });
        
        const discount_amount = parseFloat($('[name="discount_amount"]').val()) || 0;
        const shipping_cost = parseFloat($('[name="shipping_cost"]').val()) || 0;
        const tax_rate = parseFloat($('[name="tax_rate"]').val()) || 0;
        
        // إرسال للـ backend
        const response = await fetch('/sales/api/calculate-totals', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                lines: lines,
                discount_amount: discount_amount,
                shipping_cost: shipping_cost,
                tax_rate: tax_rate
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // تحديث الواجهة
            $('#subtotal').text(azad.formatNumber(result.subtotal));
            $('#total').text(azad.formatNumber(result.total));
            $('#line_count_display').text(result.line_count);
            
            return {
                subtotal: result.subtotal,
                discount: result.discount,
                shipping: result.shipping,
                tax: result.tax_amount,
                total: result.total,
                lineCount: result.line_count
            };
        } else {            // Fallback to client-side calculation
            return calculateTotalsClientSide();
        }
    } catch (error) {        // Fallback to client-side calculation
        return calculateTotalsClientSide();
    }
}

// Fallback: حساب محلي في حالة فشل الـ backend
function calculateTotalsClientSide() {
    let subtotal = 0;
    let lineCount = 0;
    
    $('[name^="lines"][name$="[quantity]"]').each(function() {
        const qty = parseFloat($(this).val()) || 0;
        const price = parseFloat($(this).closest('.product-line').find('[name$="[unit_price]"]').val()) || 0;
        const discount = parseFloat($(this).closest('.product-line').find('[name$="[discount_percent]"]').val()) || 0;
        
        if (qty > 0 && price > 0) {
            const lineTotal = qty * price * (1 - discount/100);
            subtotal += lineTotal;
            lineCount++;
        }
    });
    
    const discount = parseFloat($('[name="discount_amount"]').val()) || 0;
    const shipping = parseFloat($('[name="shipping_cost"]').val()) || 0;
    const taxRate = parseFloat($('[name="tax_rate"]').val()) || 0;
    
    const afterDiscount = subtotal - discount + shipping;
    const tax = afterDiscount * (taxRate / 100);
    const total = afterDiscount + tax;
    
    $('#subtotal').text(azad.formatNumber(subtotal));
    $('#total').text(azad.formatNumber(total));
    $('#line_count_display').text(lineCount);
    
    return {
        subtotal: subtotal,
        discount: discount,
        shipping: shipping,
        tax: tax,
        total: total,
        lineCount: lineCount
    };
}

/**
 * Load Exchange Rate when Currency Changes
 * Allows manual editing with audit trail
 */
let serverExchangeRate = null;  // Store server rate for comparison

$('#currency').on('change', function() {
    const currency = $(this).val();
    const $rateInput = $('#exchange_rate');
    
    // Update payment currency display
    $('#payment_currency_display').text(currency);
    
    if (currency === (window._FX_FALLBACK_BASE || 'AED')) {
        $rateInput.val('1.000000');
        $rateInput.data('server-rate', 1);
        serverExchangeRate = 1;
        $rateInput.prop('readonly', false);
        $rateInput.css('background-color', '#e9ecef');
        azad.showInfo(`💡 العملة: ${window._CURRENCY_NAME_AR || 'درهم'} - الأسعار والمدفوع بالـ${window._CURRENCY_NAME_AR || 'درهم'}`);
        return;
    }
    
    $rateInput.val('...').css('background-color', '#fff8dc');
    
    $.ajax({
        url: `/api/currency-rate/${currency}/${window._FX_FALLBACK_BASE || 'AED'}`,
        success: function(data) {
            if (data.rate) {
                serverExchangeRate = data.rate;
                $rateInput.val(data.rate.toFixed(6));
                $rateInput.data('server-rate', data.rate);
                $rateInput.prop('readonly', false);
                $rateInput.css('background-color', '#d4edda');
                azad.showSuccess(`✅ تم جلب سعر الصرف: 1 ${currency} = ${data.rate.toFixed(3)} ${window._FX_FALLBACK_BASE || 'AED'}`);
                updateLinePrices();
            } else if (data.manual_input_required) {
                serverExchangeRate = null;
                $rateInput.val('');
                $rateInput.prop('readonly', false);
                $rateInput.css('background-color', '#fff3cd');
                $rateInput.focus();
                azad.showError('⚠️ يرجى إدخال سعر الصرف يدوياً');
            }
        },
        error: function() {
            serverExchangeRate = null;
            $rateInput.val('');
            $rateInput.prop('readonly', false);
            $rateInput.css('background-color', '#f8d7da');
            azad.showError('⚠️ فشل تحميل سعر الصرف - يرجى الإدخال يدوياً');
        }
    });
});

// Audit manual exchange rate changes
$('#exchange_rate').on('change', function() {
    const manualRate = parseFloat($(this).val());
    const serverRate = parseFloat($(this).data('server-rate')) || serverExchangeRate;
    
    if (!manualRate || manualRate <= 0) {
        azad.showError('⚠️ سعر الصرف يجب أن يكون أكبر من صفر');
        if (serverRate) {
            $(this).val(serverRate.toFixed(6));
        }
        return;
    }
    
    if (serverRate && manualRate !== serverRate) {
        const diff = ((manualRate - serverRate) / serverRate * 100).toFixed(2);
        const diffText = diff > 0 ? `+${diff}%` : `${diff}%`;
        
        if (manualRate < serverRate) {
            // Manual rate is lower than server rate - requires documentation
            $(this).css('background-color', '#f8d7da');
            azad.showWarning(
                `⚠️ تحذير: سعر الصرف المدخل (${manualRate.toFixed(6)}) أقل من سعر السيرفر (${serverRate.toFixed(6)}) بنسبة ${diffText}` +
                `\nسيتم توثيق هذا التغيير في سجل العمليات`
            );
            
            // Add hidden field to track manual override
            const $saleForm = $('#saleForm');
            $saleForm.find('input[name="exchange_rate_manual"]').remove();
            $saleForm.append(`
                <input type="hidden" name="exchange_rate_manual" value="true">
                <input type="hidden" name="exchange_rate_server" value="${serverRate}">
                <input type="hidden" name="exchange_rate_difference" value="${diff}">
            `);
        } else if (manualRate > serverRate) {
            $(this).css('background-color', '#d1ecf1');
            azad.showInfo(`ℹ️ سعر الصرف المدخل أعلى من السيرفر بنسبة ${diffText}`);
        } else {
            $(this).css('background-color', '#d4edda');
        }
    } else if (!serverRate) {
        // Manual input without server rate
        $(this).css('background-color', '#fff3cd');
        const $saleForm = $('#saleForm');
        $saleForm.find('input[name="exchange_rate_manual"]').remove();
        $saleForm.append(`<input type="hidden" name="exchange_rate_manual" value="true">`);
    }
    
    updateLinePrices();
});

/**
 * Handle Payment Method Change - Show Dynamic Fields
 */
$('#payment_method').on('change', function() {
    const method = $(this).val();
    const $container = $('#payment_fields_container');
    const $amountGroup = $('#payment_amount_group');
    
    // Clear previous fields
    $container.empty();
    
    if (!method) {
        // No payment method selected (deferred payment)
        $amountGroup.hide();
        return;
    }
    
    // Show payment amount field
    $amountGroup.show();
    
    // Load dynamic fields from API
    $.ajax({
        url: `/api/payment-fields/${method}`,
        success: function(data) {
            if (data.fields && data.fields.length > 0) {
                let html = '<hr class="my-3">';
                html += `<h6 class="mb-3">${data.ar_title || 'تفاصيل الدفع'}</h6>`;
                
                data.fields.forEach(field => {
                    const label = field.label_ar || field.label || field.name;
                    const required = field.required ? 'required' : '';
                    const requiredStar = field.required ? ' *' : '';
                    
                    html += `
                        <div class="form-group">
                            <label class="font-weight-bold">${label}${requiredStar}</label>
                    `;
                    
                    if (field.type === 'select' && field.options) {
                        html += `<select name="${field.name}" class="form-control" ${required}>`;
                        html += '<option value="">اختر...</option>';
                        field.options.forEach(opt => {
                            html += `<option value="${opt.value}">${opt.label_ar || opt.label_en}</option>`;
                        });
                        html += '</select>';
                    } else {
                        html += `
                            <input 
                                type="${field.type || 'text'}" 
                                name="${field.name}" 
                                class="form-control" 
                                ${required}
                                placeholder="${label}">
                        `;
                    }
                    
                    html += '</div>';
                });
                
                $container.html(html);
            }
        },
        error: function() {
            azad.showError('⚠️ فشل تحميل حقول الدفع');
        }
    });
});

/**
 * Initialize on Document Ready
 */
$(document).ready(function() {
    $('#customer_id').select2({
        placeholder: 'ابحث عن زبون...',
        language: 'ar',
        dir: 'rtl',
        width: '100%',
        ajax: {
            url: '/api/search',
            dataType: 'json',
            delay: 250,
            data: function(params) {
                return {
                    q: params.term,
                    type: 'customers',
                    page: params.page || 1
                };
            },
            processResults: function(data) {
                return {
                    results: data.results,
                    pagination: {
                        more: data.has_more
                    }
                };
            },
            cache: true
        },
        minimumInputLength: 0,
        templateResult: function(customer) {
            if (customer.loading) return customer.text;
            return $('<span>' + customer.text + '</span>');
        },
        templateSelection: function(customer) {
            return customer.text;
        }
    });
    
    addLine();
    
    $('[name="discount_amount"], [name="shipping_cost"], [name="tax_rate"]').on('change keyup', function() {
        void calculateTotals();
    });
    
    $('#saleForm').on('submit', async function(e) {
        e.preventDefault();
        const totals = await calculateTotals();
        
        if (totals.lineCount === 0) {
            azad.showError('⚠️ يجب إضافة منتج واحد على الأقل');
            return false;
        }
        
        // Don't block if total is 0 - could be all free items
        if (totals.total < 0) {
            azad.showError('⚠️ الإجمالي لا يمكن أن يكون سالب');
            return false;
        }
        
        if (!$('#customer_id').val()) {
            azad.showError('⚠️ يجب اختيار زبون');
            return false;
        }
        
        azad.showLoading();
        this.submit();
    });

    $(document).on('click', '[data-action="add-line"]', function() {
        addLine();
    });
});

