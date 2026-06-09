/**
 * Azad Garage System - Main JavaScript
 * نظام أزاد للكراج - الجافا سكريبت الرئيسي
 */

$(document).ready(function() {
    // Initialize all components
    initializeApp();
    
    // Initialize new features
    if (typeof initAutoSave === 'function') initAutoSave();
    if (typeof initProgressIndicators === 'function') initProgressIndicators();
    if (typeof initSmartDefaults === 'function') initSmartDefaults();

    // Ensure loading overlay never sticks on navigation or page restore
    $(window).on('load pageshow', function() { hideLoading(); });
    $(document).on('ajaxStop', function() { hideLoading(); });
});

/**
 * Initialize Application
 */
function initializeApp() {
    initializeSelect2();
    initializeDataTables();
    initializeTooltips();
    initializeAlerts();
    initializeFormValidation();
    initializeNumberFormatting();
    initializeAccessibility();
}

/**
 * Initialize Select2 for all select elements
 */
function initializeSelect2() {
    if (!$.fn.select2) return;
    $('.select2').not('.select2-hidden-accessible').each(function() {
        if ($(this).data('select2')) return;
        $(this).select2({
            theme: 'bootstrap4',
            language: 'ar',
            dir: 'rtl',
            width: '100%',
            placeholder: 'اختر...'
        });
    });
}

/**
 * Initialize DataTables with Arabic language
 */
function initializeDataTables() {
    if (!$.fn.DataTable) return;
    $('.datatable').each(function() {
        if ($.fn.DataTable.isDataTable(this)) return;
        $(this).DataTable({
            language: {
                url: '/static/datatables/Arabic.json'
            },
            responsive: true,
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "الكل"]],
            dom: 'Bfrtip',
            buttons: [
                {
                    extend: 'excel',
                    text: '<i class="fas fa-file-excel"></i> Excel',
                    className: 'btn btn-success btn-sm'
                },
                {
                    extend: 'pdf',
                    text: '<i class="fas fa-file-pdf"></i> PDF',
                    className: 'btn btn-danger btn-sm'
                },
                {
                    extend: 'print',
                    text: '<i class="fas fa-print"></i> طباعة',
                    className: 'btn btn-info btn-sm'
                }
            ]
        });
    }
}

/**
 * Initialize Bootstrap Tooltips
 */
function initializeTooltips() {
    $('[data-toggle="tooltip"]').tooltip();
}

/**
 * Auto-hide alerts after 5 seconds
 */
function initializeAlerts() {
    setTimeout(function() {
        $('.alert:not(.flash-message):not(.alert-permanent)').fadeOut('slow');
    }, 5000);
}

/**
 * Form Validation
 */
function initializeFormValidation() {
    $('form').on('submit', function(e) {
        const form = $(this);
        
        // If another handler already prevented default, ensure no overlay
        if (typeof e.isDefaultPrevented === 'function' && e.isDefaultPrevented()) {
            hideLoading();
            return false;
        }
        
        // Check required fields
        let isValid = true;
        form.find('[required]').each(function() {
            if (!$(this).val()) {
                isValid = false;
                $(this).addClass('is-invalid');
                showError('يرجى ملء جميع الحقول المطلوبة');
                return false;
            } else {
                $(this).removeClass('is-invalid');
            }
        });
        
        if (!isValid) {
            e.preventDefault();
            hideLoading();
            return false;
        }
        
        // Show loading
        showLoading();
        // Fallback: hide loading after 12s if navigation didn't happen
        setTimeout(hideLoading, 12000);
    });
}

/**
 * Number Formatting for Arabic
 */
function initializeNumberFormatting() {
    $('.number-format').each(function() {
        const value = parseFloat($(this).text());
        if (!isNaN(value)) {
            $(this).text(formatNumber(value));
        }
    });
}

/**
 * Format number with commas
 */
function formatNumber(num, decimals = 2) {
    return num.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Show Loading Spinner
 */
function showLoading() {
    const html = `
        <div class="loading-overlay" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 9999; display: flex; align-items: center; justify-content: center;">
            <div class="loading-spinner"></div>
        </div>
    `;
    $('body').append(html);
}

/**
 * Hide Loading Spinner
 */
function hideLoading() {
    $('.loading-overlay').remove();
}

/**
 * Show Info Message
 */
function showInfo(message) {
    showAlert(message, 'info');
}

/**
 * Show Warning Message
 */
function showWarning(message) {
    showAlert(message, 'warning');
}

/**
 * Show Success Message
 */
function showSuccess(message) {
    showAlert(message, 'success');
}

/**
 * Show Error Message
 */
function showError(message) {
    showAlert(message, 'danger');
}

/**
 * Show Alert
 */
function showAlert(message, type = 'info') {
    const normalized = type === 'danger' ? 'error' : type;
    if (window.notify && typeof window.notify.show === 'function') {
        window.notify.show({ type: normalized, title: '', message: String(message || '') });
        return;
    }

    const $container = $('#flash-messages-container');
    if ($container.length) {
        const cls = normalized === 'success' ? 'success' : normalized === 'error' ? 'danger' : normalized;
        const html = `
            <div class="alert alert-${cls} alert-dismissible fade show flash-message erp-flash" role="alert">
                <div class="erp-flash-body">${message}</div>
                <button type="button" class="close" data-dismiss="alert">&times;</button>
                <div class="progress mt-2 w-100">
                    <div class="progress-bar flash-timer" role="progressbar"></div>
                </div>
            </div>
        `;
        $container.prepend(html);
        return;
    }

    alert(message);
}

/**
 * Confirm Delete
 */
function confirmDelete(message = 'هل أنت متأكد من الحذف؟') {
    return confirm(message);
}

/**
 * Print Element
 */
function printElement(elementId) {
    const content = document.getElementById(elementId).innerHTML;
    const originalContent = document.body.innerHTML;
    document.body.innerHTML = content;
    window.print();
    document.body.innerHTML = originalContent;
    location.reload();
}

/**
 * Copy to Clipboard
 */
function copyToClipboard(text) {
    const temp = $('<input>');
    $('body').append(temp);
    temp.val(text).select();
    document.execCommand('copy');
    temp.remove();
    showSuccess('تم النسخ بنجاح');
}

/**
 * Calculate Totals (for sales/purchase forms)
 */
// حساب الإجماليات - Backend Calculation (used as fallback/legacy)
// NOTE: This is now replaced by sales-enhanced.js for modern pages
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

async function calculateTotals() {
    try {
        // Detect which type of form (sales or purchases)
        const isSalesForm = $('[name^="lines"][name$="[unit_price]"]').length > 0;
        const isPurchaseForm = $('[name^="lines"][name$="[unit_cost]"]').length > 0;
        
        if (isSalesForm) {
            // Use sales API
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
            
            const response = await fetch('/sales/api/calculate-totals', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    lines: lines,
                    discount_amount: parseFloat($('[name="discount_amount"]').val()) || 0,
                    shipping_cost: parseFloat($('[name="shipping_cost"]').val()) || 0,
                    tax_rate: parseFloat($('[name="tax_rate"]').val()) || 0
                })
            });
            
            const result = await response.json();
            if (result.success) {
                $('#subtotal').text(formatNumber(result.subtotal));
                $('#total').text(formatNumber(result.total));
                return {
                    subtotal: result.subtotal,
                    discount: result.discount,
                    shipping: result.shipping,
                    tax: result.tax_amount,
                    total: result.total
                };
            }
        }
        
        // Fallback to client-side
        return calculateTotalsClientSide();
    } catch (error) {        return calculateTotalsClientSide();
    }
}

// Client-side fallback calculation
function calculateTotalsClientSide() {
    let subtotal = 0;
    
    $('[name^="lines"][name$="[quantity]"]').each(function() {
        const qty = parseFloat($(this).val()) || 0;
        const price = parseFloat($(this).closest('.product-line').find('[name$="[unit_price]"]').val()) || 0;
        const discount = parseFloat($(this).closest('.product-line').find('[name$="[discount_percent]"]').val()) || 0;
        const lineTotal = qty * price * (1 - discount/100);
        subtotal += lineTotal;
    });
    
    const discount = parseFloat($('[name="discount_amount"]').val()) || 0;
    const shipping = parseFloat($('[name="shipping_cost"]').val()) || 0;
    const taxRate = parseFloat($('[name="tax_rate"]').val()) || 0;
    
    const afterDiscount = subtotal - discount + shipping;
    const tax = afterDiscount * (taxRate / 100);
    const total = afterDiscount + tax;
    
    $('#subtotal').text(formatNumber(subtotal));
    $('#total').text(formatNumber(total));
    
    return {
        subtotal: subtotal,
        discount: discount,
        shipping: shipping,
        tax: tax,
        total: total
    };
}

/**
 * Load Exchange Rate
 */
function loadExchangeRate(fromCurrency, toCurrency = 'AED') {
    if (fromCurrency === toCurrency) {
        $('#exchange_rate').val('1.00');
        return;
    }
    
    $.ajax({
        url: `/api/currency-rate/${fromCurrency}/${toCurrency}`,
        method: 'GET',
        success: function(data) {
            if (data.rate) {
                $('#exchange_rate').val(data.rate.toFixed(6));
            }
        },
        error: function() {
            showError('فشل تحميل سعر الصرف');
        }
    });
}

/**
 * Search Products (Autocomplete)
 */
function initializeProductSearch() {
    $('.product-search').autocomplete({
        source: function(request, response) {
            $.ajax({
                url: '/api/search',
                data: {
                    q: request.term,
                    type: 'products'
                },
                success: function(data) {
                    response(data.results.map(function(item) {
                        return {
                            label: item.name,
                            value: item.id,
                            price: item.regular_price
                        };
                    }));
                }
            });
        },
        minLength: 2,
        select: function(event, ui) {
            // Handle product selection
            $(this).data('product-id', ui.item.value);
            $(this).val(ui.item.label);
            return false;
        }
    });
}

/**
 * Search Customers (Autocomplete)
 */
function initializeCustomerSearch() {
    $('.customer-search').autocomplete({
        source: function(request, response) {
            $.ajax({
                url: '/api/search',
                data: {
                    q: request.term,
                    type: 'customers'
                },
                success: function(data) {
                    response(data.results.map(function(item) {
                        return {
                            label: item.name + ' - ' + item.phone,
                            value: item.id
                        };
                    }));
                }
            });
        },
        minLength: 2
    });
}

/**
 * Accessibility Features
 */
function initializeAccessibility() {
    // Keyboard shortcuts
    $(document).keydown(function(e) {
        // Alt + N = New Sale
        if (e.altKey && e.keyCode === 78) {
            window.location.href = '/sales/create';
        }
        
        // Alt + C = Customers
        if (e.altKey && e.keyCode === 67) {
            window.location.href = '/customers';
        }
        
        // Alt + P = Products
        if (e.altKey && e.keyCode === 80) {
            window.location.href = '/products';
        }
        
        // Ctrl + P = Print
        if (e.ctrlKey && e.keyCode === 80) {
            e.preventDefault();
            window.print();
        }
    });
    
    // Large text toggle
    $('#large-text-toggle').on('click', function() {
        $('body').toggleClass('large-text');
    });
    
    // High contrast toggle
    $('#high-contrast-toggle').on('click', function() {
        $('body').toggleClass('high-contrast');
    });
}

/**
 * WhatsApp Share
 */
function shareOnWhatsApp(text, phone = '') {
    const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
}

/**
 * Export to Excel
 */
function exportToExcel(tableId, filename = 'export') {
    const table = document.getElementById(tableId);
    const wb = XLSX.utils.table_to_book(table);
    XLSX.writeFile(wb, filename + '.xlsx');
}

/**
 * Check Internet Connection
 */
function checkConnection() {
    if (!navigator.onLine) {
        showError('لا يوجد اتصال بالإنترنت');
        return false;
    }
    return true;
}

// Global error handler
window.onerror = function(msg, url, lineNo, columnNo, error) {    showError('حدث خطأ غير متوقع');
    return false;
};

// Export functions for global use
window.azad = {
    showLoading: showLoading,
    hideLoading: hideLoading,
    showInfo: showInfo,
    showWarning: showWarning,
    showSuccess: showSuccess,
    showError: showError,
    showAlert: showAlert,
    confirmDelete: confirmDelete,
    printElement: printElement,
    copyToClipboard: copyToClipboard,
    calculateTotals: calculateTotals,
    loadExchangeRate: loadExchangeRate,
    shareOnWhatsApp: shareOnWhatsApp,
    formatNumber: formatNumber
};

/**
 * UI Helper Object - Provides toast notifications
 * Integrates with the existing notify system from notifications.js
 */
window.UI = {
    /**
     * Show toast notification
     * @param {string} message - The message to display
     * @param {string} type - Type of toast (success, error, warning, info)
     * @param {number} duration - Duration in milliseconds (default: 4000)
     */
    toast: function(message, type = 'info', duration = 4000) {
        // Check if the notify object exists (from notifications.js)
        if (typeof window.notify !== 'undefined') {
            return window.notify.show({ 
                type: type, 
                message: message, 
                duration: duration 
            });
        }
        // Fallback to SweetAlert2 if available
        else if (typeof Swal !== 'undefined') {
            const icons = {
                'success': 'success',
                'error': 'error',
                'warning': 'warning',
                'info': 'info'
            };
            Swal.fire({
                icon: icons[type] || 'info',
                text: message,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: duration,
                timerProgressBar: true
            });
        }
        // Final fallback to alert
        else {
            showAlert(message, type === 'error' ? 'danger' : type);
        }
    },
    
    /**
     * Show success toast
     */
    success: function(message, duration = 4000) {
        this.toast(message, 'success', duration);
    },
    
    /**
     * Show error toast
     */
    error: function(message, duration = 4000) {
        this.toast(message, 'error', duration);
    },
    
    /**
     * Show warning toast
     */
    warning: function(message, duration = 4000) {
        this.toast(message, 'warning', duration);
    },
    
    /**
     * Show info toast
     */
    info: function(message, duration = 4000) {
        this.toast(message, 'info', duration);
    }
};

// =====================================
// Auto-save + Progress + Smart Defaults
// =====================================
let autoSaveTimer;
window.initAutoSave = function() {
    $('form[data-autosave]').each(function() {
        const $form = $(this);
        $form.find('input, textarea').on('input', function() {
            clearTimeout(autoSaveTimer);
            autoSaveTimer = setTimeout(() => {
                sessionStorage.setItem('autosave_' + $form.attr('id'), $form.serialize());
                if (window.Swal) Swal.fire({toast:true, position:'top-end', icon:'success', title:'💾 محفوظ', timer:1000, showConfirmButton:false});
            }, 30000);
        });
    });
};

window.initProgressIndicators = function() {
    $('form[data-show-progress]').each(function() {
        const $form = $(this);
        const $required = $form.find('[required]');
        if ($required.length === 0) return;
        
        $form.prepend(`<div class="mb-3"><div class="progress" style="height:8px"><div class="progress-bar bg-success" id="prog-bar" style="width:0%"></div></div></div>`);
        
        function update() {
            const filled = $required.filter(function() { return $(this).val() !== ''; }).length;
            const pct = (filled / $required.length) * 100;
            $('#prog-bar').css('width', pct + '%');
        }
        $required.on('input change', update);
        update();
    });
};

window.initSmartDefaults = function() {
    $('form').on('submit', function() {
        const custId = $(this).find('[name="customer_id"]').val();
        if (custId) sessionStorage.setItem('last_customer_id', custId);
        
        const payMethod = $(this).find('[name="payment_method"]').val();
        if (payMethod) sessionStorage.setItem('last_payment_method', payMethod);
    });
};

// =====================================
// Keyboard Shortcuts
// =====================================
$(document).on('keydown', function(e) {
    // Ctrl+S = حفظ
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        $('form').first().submit();
        return false;
    }
    
    // Ctrl+N = جديد
    if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        const createBtn = $('a[href*="/create"]').first();
        if (createBtn.length) window.location = createBtn.attr('href');
    }
    
    // Ctrl+F = بحث
    if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        $('.dataTables_filter input').focus();
    }
    
    // Esc = إلغاء/رجوع
    if (e.key === 'Escape') {
        const cancelBtn = $('a:contains("إلغاء"), a:contains("العودة")').first();
        if (cancelBtn.length) window.location = cancelBtn.attr('href');
    }
});

// =====================================
// Lazy Loading للصور
// =====================================
if ('IntersectionObserver' in window) {
    const imgObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy');
                imgObserver.unobserve(img);
            }
        });
    });
    
    document.querySelectorAll('img[data-src]').forEach(img => imgObserver.observe(img));
}

// =====================================
// Graceful Degradation for AJAX
// =====================================
window.submitWithFallback = async function(url, data, method='POST') {
    try {
        const response = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        return await response.json();
    } catch (error) {        // Fallback: create form and submit
        const form = document.createElement('form');
        form.method = method;
        form.action = url;
        for (let key in data) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = key;
            input.value = data[key];
            form.appendChild(input);
        }
        document.body.appendChild(form);
        form.submit();
    }
};

// =====================================
// Retry Mechanism for AJAX
// =====================================
window.fetchWithRetry = async function(url, options = {}, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(url, options);
            if (response.ok) return response;
            
            if (i < retries - 1) {
                await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
            }
        } catch (error) {
            if (i === retries - 1) throw error;
            await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
        }
    }
};

// =====================================
// Undo/Redo System
// =====================================
const formHistory = [];
let historyIndex = -1;

window.saveFormState = function() {
    const state = $('form').first().serialize();
    formHistory.push(state);
    historyIndex++;
    if (formHistory.length > 50) formHistory.shift();
};

window.undoForm = function() {
    if (historyIndex > 0) {
        historyIndex--;
        restoreFormState(formHistory[historyIndex]);
    }
};

window.redoForm = function() {
    if (historyIndex < formHistory.length - 1) {
        historyIndex++;
        restoreFormState(formHistory[historyIndex]);
    }
};

function restoreFormState(serialized) {
    const data = new URLSearchParams(serialized);
    data.forEach((value, key) => {
        $(`[name="${key}"]`).val(value);
    });
}

// Ctrl+Z = Undo, Ctrl+Y = Redo
$(document).on('keydown', function(e) {
    if (e.ctrlKey && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        undoForm();
    }
    if (e.ctrlKey && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        redoForm();
    }
});

// =====================================
// Inline Editing
// =====================================
$(document).on('dblclick', '.editable', function() {
    if (window.APP_INLINE_EDIT_ENABLED !== true) {
        return;
    }
    const $this = $(this);
    const originalValue = $this.text();
    const entityType = $this.data('entity');
    const entityId = $this.data('id');
    const field = $this.data('field');
    const inlineEditEndpointTemplate = (window.APP_INLINE_EDIT_ENDPOINT_TEMPLATE || '').trim();
    if (!inlineEditEndpointTemplate) {
        $this.text(originalValue);
        return;
    }
    
    const input = $(`<input type="text" class="form-control form-control-sm" value="${originalValue}">`);
    $this.html(input);
    input.focus().select();
    
    input.on('blur', async function() {
        const newValue = $(this).val();
        if (newValue !== originalValue) {
            try {
                const endpoint = inlineEditEndpointTemplate
                    .replace('{entity}', encodeURIComponent(String(entityType)))
                    .replace('{id}', encodeURIComponent(String(entityId)));
                await fetch(endpoint, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({field: field, value: newValue})
                });
                $this.text(newValue);
            } catch {
                $this.text(originalValue);
            }
        } else {
            $this.text(originalValue);
        }
    });
    
    input.on('keydown', function(e) {
        if (e.key === 'Enter') $(this).blur();
        if (e.key === 'Escape') { $this.text(originalValue); }
    });
});

