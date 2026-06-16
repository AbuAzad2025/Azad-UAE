// archive.js - Archive Functions
// Location: /garage_manager/static/js/archive.js
function archiveCustomer(customerId) {    
    const reason = prompt('أدخل سبب أرشفة هذا العميل:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذا العميل؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/customers/archive/${customerId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}
function archiveSale(saleId) {    
    const reason = prompt('أدخل سبب أرشفة هذه المبيعة:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذه المبيعة؟')) {        // إظهار رسالة تحميل
        const loadingMsg = document.createElement('div');
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-info';
        alertDiv.textContent = 'جاري أرشفة المبيعة...';
        loadingMsg.appendChild(alertDiv);
        document.body.appendChild(loadingMsg);
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/sales/${saleId}/archive`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// أرشفة النفقة
function archiveExpense(expenseId) {    
    const reason = prompt('أدخل سبب أرشفة هذه النفقة:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذه النفقة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/expenses/${expenseId}/archive`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// أرشفة طلب الصيانة
function archiveService(serviceId) {    
    const reason = prompt('أدخل سبب أرشفة هذا طلب الصيانة:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذا طلب الصيانة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/service/archive/${serviceId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// أرشفة المورد
function archiveSupplier(supplierId) {    
    const reason = prompt('أدخل سبب أرشفة هذا المورد:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذا المورد؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/suppliers/archive/${supplierId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// أرشفة الشريك
function archivePartner(partnerId) {    
    const reason = prompt('أدخل سبب أرشفة هذا الشريك:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذا الشريك؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/partners/archive/${partnerId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// وظيفة مساعدة للحصول على CSRF token
function getCSRFToken() {    
    // محاولة الحصول على الـ token من meta tag
    const metaToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (metaToken) {        return metaToken;
    }
    
    // محاولة الحصول من hidden input في النموذج
    const hiddenInput = document.querySelector('input[name="csrf_token"]');
    if (hiddenInput) {        return hiddenInput.value;
    }
    
    // إذا لم يتم العثور على token، إرجاع قيمة افتراضية    return '';
}

// إضافة event listeners عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {    
    // فحص CSRF token
    const csrfToken = getCSRFToken();    
    // إضافة console logs للأزرار
    const archiveButtons = document.querySelectorAll('button[onclick*="archive"]');    archiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة طلبات الصيانة تحديداً
    const serviceArchiveButtons = document.querySelectorAll('button[onclick*="archiveService"]');    serviceArchiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة العملاء
    const customerArchiveButtons = document.querySelectorAll('button[onclick*="archiveCustomer"]');    customerArchiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة المبيعات
    const saleArchiveButtons = document.querySelectorAll('button[onclick*="archiveSale"]');    saleArchiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة النفقات
    const expenseArchiveButtons = document.querySelectorAll('button[onclick*="archiveExpense"]');    expenseArchiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة الموردين
    const supplierArchiveButtons = document.querySelectorAll('button[onclick*="archiveSupplier"]');    supplierArchiveButtons.forEach((button, index) => {    });
    
    // فحص أزرار أرشفة الشركاء
    const partnerArchiveButtons = document.querySelectorAll('button[onclick*="archivePartner"]');    partnerArchiveButtons.forEach((button, index) => {    });
});

// أرشفة الدفعة
function archivePayment(paymentId) {    
    const reason = prompt('أدخل سبب أرشفة هذه الدفعة:');
    if (!reason) {        return;
    }    
    if (confirm('هل أنت متأكد من أرشفة هذه الدفعة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/payments/archive/${paymentId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);        
        document.body.appendChild(form);        
        form.addEventListener('submit', function(e) {        });
        
        form.submit();
    } else {    }
}

// ===== وظائف الاستعادة =====

// استعادة العميل
function restoreCustomer(customerId) {    
    if (confirm('هل أنت متأكد من استعادة هذا العميل؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/customers/restore/${customerId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}

// استعادة المبيعة
function restoreSale(saleId) {    
    if (confirm('هل أنت متأكد من استعادة هذه المبيعة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/sales/restore/${saleId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}

// استعادة النفقة
function restoreExpense(expenseId) {    
    if (confirm('هل أنت متأكد من استعادة هذه النفقة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/expenses/restore/${expenseId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}

// استعادة طلب الصيانة
function restoreService(serviceId) {    
    if (confirm('هل أنت متأكد من استعادة هذا طلب الصيانة؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/service/restore/${serviceId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}

// استعادة المورد
function restoreSupplier(supplierId) {    
    if (confirm('هل أنت متأكد من استعادة هذا المورد؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/suppliers/restore/${supplierId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}

// استعادة الشريك
function restorePartner(partnerId) {    
    if (confirm('هل أنت متأكد من استعادة هذا الشريك؟')) {        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/partners/restore/${partnerId}`;        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);        form.submit();
    } else {    }
}
