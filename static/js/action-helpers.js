/**
 * Shared action helpers (archive/delete/print helpers)
 * Reusable across templates to reduce inline JS duplication.
 */
(function () {
  'use strict';

  function getCsrfToken() {
    return (
      document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      ''
    );
  }

  function archivePaymentItem(type, id, number) {
    const normalizedType = type === 'receipt' ? 'receipt' : 'payment';
    const baseEndpoint = normalizedType === 'receipt' ? '/payments/receipts/' : '/payments/payments/';
    const reason = window.prompt(`أدخل سبب أرشفة السند ${number || ('#' + id)}:`);
    if (!reason) return;
    if (!window.confirm(`هل أنت متأكد من أرشفة السند ${number || ('#' + id)}؟`)) return;

    fetch(`${baseEndpoint}${id}/archive`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'X-CSRFToken': getCsrfToken(),
      },
      body: new URLSearchParams({ reason }).toString(),
      credentials: 'same-origin',
    })
      .then((resp) => {
        if (!resp.ok) {
          return resp
            .json()
            .then((j) => Promise.reject(j?.message || j?.error || 'فشلت عملية الأرشفة'))
            .catch(() => Promise.reject('فشلت عملية الأرشفة'));
        }
        window.location.reload();
      })
      .catch((err) => window.alert(String(err || 'فشلت عملية الأرشفة')));
  }

  function openPrintWindow(url) {
    if (!url) return;
    window.open(url, '_blank');
  }

  window.ActionHelpers = {
    getCsrfToken,
    archivePaymentItem,
    openPrintWindow,
  };
})();

