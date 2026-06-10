/**
 * 🗑️ Delete Manager - نظام حذف موحد واحترافي
 * إدارة عمليات الحذف في كل النظام مع تأكيد وأرشفة
 */

(function($) {
  'use strict';

  const ENDPOINTS = {
    customers: {
      method: 'POST',
      delete: (id) => `/customers/${id}/delete`,
      restore: null
    },
    suppliers: {
      method: 'POST',
      delete: (id) => `/suppliers/${id}/delete`,
      restore: null
    },
    products: {
      method: 'POST',
      delete: (id) => `/products/${id}/delete`,
      restore: null
    },
    sales: {
      method: 'POST',
      delete: (id) => `/sales/${id}/delete`,
      restore: (id) => `/sales/${id}/restore`
    },
    purchases: {
      method: 'POST',
      delete: (id) => `/purchases/${id}/delete`,
      restore: null
    },
    receipts: {
      method: 'POST',
      delete: (id) => `/payments/receipts/${id}/delete`,
      restore: (id) => `/payments/receipts/${id}/restore`
    },
    payments: {
      method: 'POST',
      delete: (id) => `/payments/payments/${id}/delete`,
      restore: (id) => `/payments/payments/${id}/restore`
    },
    expenses: {
      method: 'POST',
      delete: (id) => `/expenses/${id}/delete`,
      restore: (id) => `/expenses/${id}/restore`
    },
    cheques: {
      method: 'POST',
      delete: (id) => `/cheques/${id}/delete`,
      restore: (id) => `/cheques/${id}/restore`
    },
    users: {
      method: 'POST',
      delete: (id) => `/users/${id}/delete`,
      restore: null
    },
    warehouses: {
      method: 'POST',
      delete: (id) => `/warehouse/${id}/delete`,
      restore: null
    }
  };

  function normalizeType(itemType) {
    const raw = String(itemType || '').trim().toLowerCase();
    if (!raw) return '';
    if (ENDPOINTS[raw]) return raw;
    const singularToPlural = {
      customer: 'customers',
      supplier: 'suppliers',
      product: 'products',
      sale: 'sales',
      purchase: 'purchases',
      receipt: 'receipts',
      payment: 'payments',
      expense: 'expenses',
      cheque: 'cheques',
      user: 'users',
      warehouse: 'warehouses'
    };
    return singularToPlural[raw] || raw;
  }

  function csrfToken() {
    return $('input[name="csrf_token"]').val() || $('meta[name="csrf-token"]').attr('content') || '';
  }

  function isSupportedAction(itemType, action) {
    const normalized = normalizeType(itemType);
    return Boolean(ENDPOINTS[normalized] && typeof ENDPOINTS[normalized][action] === 'function');
  }

  function resolveActionUrl(itemType, itemId, action) {
    const normalized = normalizeType(itemType);
    if (!isSupportedAction(normalized, action)) return null;
    return ENDPOINTS[normalized][action](itemId);
  }
  
  // =====================================
  // حذف عنصر عام
  // =====================================
  window.deleteItem = function(itemType, itemId, itemName, redirectUrl) {
    const normalizedType = normalizeType(itemType);
    const deleteUrl = resolveActionUrl(normalizedType, itemId, 'delete');
    if (!deleteUrl) {
      Swal.fire({
        icon: 'info',
        title: 'عملية غير مدعومة',
        text: 'هذا النوع لا يدعم الحذف من هذه الشاشة حالياً.'
      });
      return;
    }

    // رسائل مخصصة حسب نوع العنصر
    const messages = {
      customers: { title: 'حذف زبون', text: 'تنبيه: سيتم أرشفة الزبون إذا كان له سجلات مالية، أو حذفه نهائياً إذا كان جديداً.' },
      suppliers: { title: 'حذف مورد', text: 'تنبيه: سيتم أرشفة المورد إذا كان له سجلات مالية، أو حذفه نهائياً إذا كان جديداً.' },
      products: { title: 'حذف منتج', text: 'تنبيه: سيتم أرشفة المنتج إذا كان مرتبطاً بعمليات بيع/شراء، أو حذفه نهائياً إذا كان غير مرتبط.' },
      sales: { title: 'حذف فاتورة مبيعات', text: 'تنبيه: سيتم أرشفة الفاتورة إذا كان لها ارتباطات مالية (دفعات/شيكات)، أو حذفها نهائياً إذا كانت غير مرتبطة.' },
      purchases: { title: 'حذف فاتورة شراء', text: 'تنبيه: سيتم أرشفة الفاتورة إذا كان لها ارتباطات مالية، أو حذفها نهائياً إذا كانت غير مرتبطة.' },
      receipts: { title: 'حذف سند قبض', text: 'تنبيه: سيتم أرشفة السند إذا كان مرتبطاً بشيكات، أو حذفه نهائياً إذا كان غير مرتبط.' },
      payments: { title: 'حذف سند صرف', text: 'تنبيه: سيتم أرشفة السند إذا كان مرتبطاً بعمليات أخرى، أو حذفه نهائياً إذا كان غير مرتبط.' },
      expenses: { title: 'حذف مصروف', text: 'تنبيه: سيتم أرشفة المصروف وعكس القيد المحاسبي.' },
      cheques: { title: 'حذف شيك', text: 'تنبيه: سيتم أرشفة الشيك إذا كان مرتبطاً بسندات، أو حذفه نهائياً إذا كان غير مرتبط.' },
      users: { title: 'حذف مستخدم', text: 'سيتم إلغاء تفعيل المستخدم وليس حذفه نهائياً.' },
      warehouses: { title: 'حذف مستودع', text: 'تنبيه: سيتم أرشفة المستودع إذا كان يحتوي على حركات مخزنية، أو حذفه نهائياً إذا كان فارغاً.' }
    };
    
    const msg = messages[normalizedType] || { title: 'حذف', text: 'هل أنت متأكد من الحذف؟' };
    
    Swal.fire({
      title: msg.title,
      html: `
        <p><strong>${itemName}</strong></p>
        <p class="text-muted">${msg.text}</p>
      `,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#6c757d',
      confirmButtonText: '<i class="fas fa-trash mr-2"></i>نعم، احذف',
      cancelButtonText: '<i class="fas fa-times mr-2"></i>إلغاء',
      reverseButtons: true,
      showLoaderOnConfirm: true,
      preConfirm: function() {
        // إنشاء form وإرساله
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = deleteUrl;
        
        // إضافة CSRF token
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = csrfToken();
        form.appendChild(csrfInput);
        
        document.body.appendChild(form);
        form.submit();
        
        // منع إغلاق التنبيه
        return new Promise(() => {});
      },
      allowOutsideClick: () => !Swal.isLoading()
    });
  };
  
  // =====================================
  // حذف عدة عناصر
  // =====================================
  window.deleteMultiple = function(itemIds, itemType, redirectUrl) {
    if (!itemIds || itemIds.length === 0) {
      toastr.warning('⚠️ يجب اختيار عنصر واحد على الأقل');
      return;
    }
    
    Swal.fire({
      title: 'حذف متعدد',
      html: `
        <p>سيتم حذف <strong>${itemIds.length}</strong> عنصر</p>
        <p class="text-muted">سيتم تنفيذ حذف آمن لكل عنصر حسب نوعه</p>
      `,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#6c757d',
      confirmButtonText: '<i class="fas fa-trash mr-2"></i>نعم، احذف الكل',
      cancelButtonText: '<i class="fas fa-times mr-2"></i>إلغاء',
      reverseButtons: true,
      showLoaderOnConfirm: true,
      preConfirm: async function() {
        const normalizedType = normalizeType(itemType);
        if (!isSupportedAction(normalizedType, 'delete')) {
          Swal.showValidationMessage('هذا النوع لا يدعم الحذف المتعدد من هذه الشاشة.');
          return false;
        }

        const token = csrfToken();
        for (const id of itemIds) {
          const url = resolveActionUrl(normalizedType, id, 'delete');
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'X-CSRFToken': token
            },
            credentials: 'same-origin'
          });
          if (!response.ok) {
            Swal.showValidationMessage(`فشل حذف العنصر رقم ${id}`);
            return false;
          }
        }
        return true;
      },
      allowOutsideClick: () => !Swal.isLoading()
    }).then(function(result) {
      if (result.isConfirmed) {
        Swal.fire({
          icon: 'success',
          title: 'تم الحذف بنجاح',
          text: `تم حذف ${itemIds.length} عنصر بنجاح`,
          timer: 2000,
          showConfirmButton: false
        }).then(function() {
          if (redirectUrl) {
            window.location.href = redirectUrl;
          } else {
            location.reload();
          }
        });
      }
    });
  };
  
  // =====================================
  // حذف سطر (في الجداول)
  // =====================================
  window.deleteTableRow = function(rowElement, confirmMessage = 'هل أنت متأكد من الحذف؟') {
    Swal.fire({
      title: 'تأكيد الحذف',
      text: confirmMessage,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#6c757d',
      confirmButtonText: '<i class="fas fa-trash mr-2"></i>نعم',
      cancelButtonText: '<i class="fas fa-times mr-2"></i>إلغاء',
      reverseButtons: true
    }).then(function(result) {
      if (result.isConfirmed) {
        $(rowElement).fadeOut(300, function() {
          $(this).remove();
          toastr.success('✅ تم الحذف');
        });
      }
    });
  };
  
  // =====================================
  // استعادة عنصر محذوف
  // =====================================
  window.restoreItem = function(itemId, itemType, itemName) {
    const normalizedType = normalizeType(itemType);
    const restoreUrl = resolveActionUrl(normalizedType, itemId, 'restore');
    if (!restoreUrl) {
      Swal.fire({
        icon: 'info',
        title: 'الاستعادة غير متاحة',
        text: 'هذا النوع لا يملك مسار استعادة في النظام الحالي.'
      });
      return;
    }

    Swal.fire({
      title: 'استعادة العنصر',
      html: `<p>هل تريد استعادة: <strong>${itemName}</strong>؟</p>`,
      icon: 'question',
      showCancelButton: true,
      confirmButtonColor: '#28a745',
      cancelButtonColor: '#6c757d',
      confirmButtonText: '<i class="fas fa-undo mr-2"></i>نعم، استعد',
      cancelButtonText: '<i class="fas fa-times mr-2"></i>إلغاء',
      reverseButtons: true,
      showLoaderOnConfirm: true,
      preConfirm: function() {
        return $.ajax({
          url: restoreUrl,
          method: 'POST',
          headers: {
            'X-CSRFToken': csrfToken()
          }
        }).then(function(response) {
          return response;
        }).catch(function(error) {
          Swal.showValidationMessage(`حدث خطأ: ${error.responseJSON?.message || 'خطأ غير معروف'}`);
        });
      },
      allowOutsideClick: () => !Swal.isLoading()
    }).then(function(result) {
      if (result.isConfirmed) {
        Swal.fire({
          icon: 'success',
          title: 'تمت الاستعادة',
          text: 'تم استعادة العنصر بنجاح',
          timer: 2000,
          showConfirmButton: false
        }).then(function() {
          location.reload();
        });
      }
    });
  };
  
  // =====================================
  // تهيئة أزرار الحذف التلقائية
  // =====================================
  $(document).on('click', '[data-delete-item]', function(e) {
    e.preventDefault();
    const $btn = $(this);
    const itemId = $btn.data('delete-item');
    const itemType = $btn.data('item-type');
    const itemName = $btn.data('item-name') || 'هذا العنصر';
    const redirectUrl = $btn.data('redirect-url');
    
    deleteItem(itemType, itemId, itemName, redirectUrl);
  });
  
  $(document).on('click', '[data-delete-row]', function(e) {
    e.preventDefault();
    const $btn = $(this);
    const rowElement = $btn.closest('tr, .product-line, [data-row]');
    const confirmMessage = $btn.data('confirm-message') || 'هل أنت متأكد من حذف هذا السطر؟';
    
    deleteTableRow(rowElement, confirmMessage);
  });
  
  $(document).on('click', '[data-restore-item]', function(e) {
    e.preventDefault();
    const $btn = $(this);
    const itemId = $btn.data('restore-item');
    const itemType = $btn.data('item-type');
    const itemName = $btn.data('item-name') || 'هذا العنصر';
    
    restoreItem(itemId, itemType, itemName);
  });
  
})(jQuery);

