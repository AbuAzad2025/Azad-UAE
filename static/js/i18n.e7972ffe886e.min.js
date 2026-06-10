/**
 * 🌍 JavaScript Internationalization
 * نظام الترجمة في JavaScript
 */

// Get current language from session/cookie
function getCurrentLanguage() {
    // Try to get from body data attribute
    const lang = document.documentElement.lang || 'ar';
    return lang;
}

// Translation dictionary
const translations = {
    // Common
    'Save': { ar: 'حفظ', en: 'Save' },
    'Cancel': { ar: 'إلغاء', en: 'Cancel' },
    'Delete': { ar: 'حذف', en: 'Delete' },
    'Edit': { ar: 'تعديل', en: 'Edit' },
    'View': { ar: 'عرض', en: 'View' },
    'Back': { ar: 'رجوع', en: 'Back' },
    'Search': { ar: 'بحث', en: 'Search' },
    'Loading': { ar: 'جاري التحميل...', en: 'Loading...' },
    'Processing': { ar: 'جاري المعالجة...', en: 'Processing...' },
    
    // Messages
    'Success': { ar: 'نجاح', en: 'Success' },
    'Error': { ar: 'خطأ', en: 'Error' },
    'Warning': { ar: 'تحذير', en: 'Warning' },
    'Are you sure?': { ar: 'هل أنت متأكد؟', en: 'Are you sure?' },
    'This action cannot be undone': { ar: 'لا يمكن التراجع عن هذا الإجراء', en: 'This action cannot be undone' },
    'Saved successfully': { ar: 'تم الحفظ بنجاح', en: 'Saved successfully' },
    'Deleted successfully': { ar: 'تم الحذف بنجاح', en: 'Deleted successfully' },
    'Updated successfully': { ar: 'تم التحديث بنجاح', en: 'Updated successfully' },
    'An error occurred': { ar: 'حدث خطأ', en: 'An error occurred' },
    'Please try again': { ar: 'يرجى المحاولة مرة أخرى', en: 'Please try again' },
    
    // Actions
    'Confirm': { ar: 'تأكيد', en: 'Confirm' },
    'Yes': { ar: 'نعم', en: 'Yes' },
    'No': { ar: 'لا', en: 'No' },
    'OK': { ar: 'موافق', en: 'OK' },
    'Close': { ar: 'إغلاق', en: 'Close' },
    
    // Validation
    'This field is required': { ar: 'هذا الحقل مطلوب', en: 'This field is required' },
    'Please enter a valid email': { ar: 'يرجى إدخال بريد إلكتروني صحيح', en: 'Please enter a valid email' },
    'Please enter a valid phone number': { ar: 'يرجى إدخال رقم هاتف صحيح', en: 'Please enter a valid phone number' },
    'Please select an option': { ar: 'يرجى اختيار خيار', en: 'Please select an option' },
    
    // DataTables
    'Show': { ar: 'عرض', en: 'Show' },
    'entries': { ar: 'سجل', en: 'entries' },
    'Search:': { ar: 'بحث:', en: 'Search:' },
    'Showing': { ar: 'عرض', en: 'Showing' },
    'to': { ar: 'إلى', en: 'to' },
    'of': { ar: 'من', en: 'of' },
    'entries (filtered from': { ar: 'سجل (تمت فلترته من', en: 'entries (filtered from' },
    'total entries)': { ar: 'إجمالي السجلات)', en: 'total entries)' },
    'No data available': { ar: 'لا توجد بيانات', en: 'No data available' },
    'No records found': { ar: 'لم يتم العثور على سجلات', en: 'No records found' },
    'First': { ar: 'الأولى', en: 'First' },
    'Last': { ar: 'الأخيرة', en: 'Last' },
    'Next': { ar: 'التالي', en: 'Next' },
    'Previous': { ar: 'السابق', en: 'Previous' },
};

/**
 * Translate a key
 * @param {string} key - The translation key
 * @param {Object} params - Optional parameters for string interpolation
 * @returns {string} Translated text
 */
function t(key, params = {}) {
    const lang = getCurrentLanguage();
    const translation = translations[key];
    
    if (!translation) {        return key;
    }
    
    let text = translation[lang] || translation['ar'] || key;
    
    // Replace parameters {param}
    Object.keys(params).forEach(param => {
        text = text.replace(`{${param}}`, params[param]);
    });
    
    return text;
}

/**
 * Translate all elements with data-i18n attribute
 */
function translatePage() {
    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        element.textContent = t(key);
    });
}

/**
 * Get DataTables language configuration
 */
function getDataTablesLanguage() {
    const lang = getCurrentLanguage();
    
    if (lang === 'ar') {
        return {
            url: '/static/datatables/Arabic.json'
        };
    }
    
    return {
        "sEmptyTable": t("No data available"),
        "sInfo": `${t("Showing")} _START_ ${t("to")} _END_ ${t("of")} _TOTAL_ ${t("entries")}`,
        "sInfoEmpty": `${t("Showing")} 0 ${t("to")} 0 ${t("of")} 0 ${t("entries")}`,
        "sInfoFiltered": `(${t("entries (filtered from")} _MAX_ ${t("total entries)")})`,
        "sLengthMenu": `${t("Show")} _MENU_ ${t("entries")}`,
        "sLoadingRecords": t("Loading") + "...",
        "sProcessing": t("Processing") + "...",
        "sSearch": t("Search:"),
        "sZeroRecords": t("No records found"),
        "oPaginate": {
            "sFirst": t("First"),
            "sLast": t("Last"),
            "sNext": t("Next"),
            "sPrevious": t("Previous")
        }
    };
}

/**
 * Show SweetAlert with translation
 */
function showAlert(title, text, icon = 'info') {
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            title: t(title),
            text: t(text),
            icon: icon,
            confirmButtonText: t('OK')
        });
    } else {
        alert(`${t(title)}\n${t(text)}`);
    }
}

/**
 * Show confirmation dialog with translation
 */
function confirmAction(title, text, onConfirm) {
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            title: t(title),
            text: t(text),
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: t('Yes'),
            cancelButtonText: t('No'),
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6'
        }).then((result) => {
            if (result.isConfirmed && onConfirm) {
                onConfirm();
            }
        });
    } else {
        if (confirm(`${t(title)}\n${t(text)}`)) {
            if (onConfirm) onConfirm();
        }
    }
}

// Export functions
window.t = t;
window.translatePage = translatePage;
window.getDataTablesLanguage = getDataTablesLanguage;
window.showAlert = showAlert;
window.confirmAction = confirmAction;

// Auto-translate on page load
document.addEventListener('DOMContentLoaded', function() {
    translatePage();
});

