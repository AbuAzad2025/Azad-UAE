/* ============================================================
   Azadexa — Support / Donation / Purchase Page Logic
   ============================================================
   Depends on window.spConfig defined in scripts.html.
   ============================================================ */

(function () {
  'use strict';

  var cfg = window.spConfig || {};
  var i18n = window.spI18n || {};
  var t = function (key) { return i18n[key] || key; };

  var selectedAmount = 0;
  var selectedMethod = '';
  var selectedCrypto = 'btc';
  var selectedPackage = '';
  var currentTab = 'purchase';

  function buildSupportMessage(kind, amountOverride, recordId) {
    var amount = amountOverride || selectedAmount ||
      (document.getElementById('customAmount') ? document.getElementById('customAmount').value : '') ||
      (document.getElementById('cardAmount') ? document.getElementById('cardAmount').value : '') || '';
    var packageLabel = selectedPackage || t('غير محددة بعد');
    var orderRef = recordId ? ' ' + t('رقم المرجع') + ': #' + recordId + '.' : '';

    var messages = {
      buy_code: t('مرحباً') + ' ' + cfg.brand + '، ' + t('أريد') + ' ' + t('Purchase') + ' ' + t('Code') + ' ' + t('المصدري') + ' ' + t('أو') + ' ' + t('تنفيذ') + ' ' + t('تخصيص') + ' ' + t('Specific_2') + ' ' + t('للنظام') + '.' + orderRef,
      donation_help: t('مرحباً') + ' ' + cfg.brand + '، ' + t('أريد') + ' ' + t('التبرع') + ' ' + t('أو') + ' ' + t('رعاية') + ' ' + t('تطوير') + ' ' + t('ميزة') + ' ' + t('في') + ' ' + t('System') + '. ' + t('Amount') + ' ' + t('Expected') + ': ' + (amount || t('سأحدده معكم')) + ' ' + t('Dollar') + '.' + orderRef,
      payment_help: t('مرحباً') + ' ' + cfg.brand + '، ' + t('أحتاج') + ' ' + t('مساعدة') + ' ' + t('في') + ' ' + t('إتمام') + ' ' + (currentTab === 'purchase' ? t('Purchase') + ' ' + t('System') : t('التبرع')) + '.' + orderRef,
      refund_help: t('مرحباً') + ' ' + cfg.brand + '، ' + t('أريد') + ' ' + t('الاستفسار') + ' ' + t('عن') + ' ' + t('Status_2') + ' ' + t('Payment') + ' ' + t('أو') + ' ' + t('استرداد') + '.' + orderRef
    };
    messages.buy_system = t('مرحباً') + ' ' + cfg.brand + '، ' + t('أريد') + ' ' + t('Purchase') + ' ' + t('System') + (currentTab === 'purchase' ? ' ' + t('والباقة الحالية') + ': ' + packageLabel : '') + '. ' + t('Amount') + ' ' + t('Expected') + ': ' + (amount || t('سأحدده معكم')) + ' ' + t('Dollar') + '.' + orderRef;

    return messages[kind] || messages.buy_system;
  }

  function buildSupportEmail(kind, amountOverride, recordId) {
    var message = buildSupportMessage(kind, amountOverride, recordId);
    var subjects = {
      buy_system: t('طلب Purchase System'),
      buy_code: t('طلب Purchase Code أو تخصيص'),
      donation_help: t('استفسار تبرع أو رعاية'),
      payment_help: t('مساعدة في إتمام Payment'),
      refund_help: t('استفسار استرداد أو Status Payment')
    };
    var subject = (subjects[kind] || t('استفسار')) + ' - ' + cfg.brand;
    var body = message + '\n\n' + t('بيانات التواصل') + ':\n' + t('واتساب') + ': ' + cfg.whatsappDisplay + '\n' + t('بريد') + ': ' + cfg.email;
    return { subject: subject, body: body };
  }

  window.openWhatsApp = function (kind, amountOverride, recordId) {
    var message = buildSupportMessage(kind, amountOverride, recordId);
    window.open('https://wa.me/' + cfg.whatsappLink + '?text=' + encodeURIComponent(message), '_blank');
  };

  window.openSupportEmail = function (kind, amountOverride, recordId) {
    var payload = buildSupportEmail(kind, amountOverride, recordId);
    window.location.href = 'mailto:' + cfg.email + '?subject=' + encodeURIComponent(payload.subject) + '&body=' + encodeURIComponent(payload.body);
  };

  function buildSupportStatusHtml(recordId, paymentAmount, label) {
    return '' +
      '<div class="sp-status-box">' +
        '<p class="sp-status-box-label"><strong>' + t('Status الحالية') + ':</strong> ' + label + '</p>' +
        '<p class="sp-status-box-label"><strong>' + t('المرجع') + ':</strong> #' + (recordId || '\u2014') + '</p>' +
        '<p class="sp-status-box-value"><strong>' + t('Amount') + ':</strong> $' + (paymentAmount || '\u2014') + '</p>' +
      '</div>' +
      '<div class="sp-status-details">' +
        '<div><i class="fas fa-check-circle sp-status-icon-success"></i> ' + t('عند النجاح ستصلك Details واضحة أو Address Payment مباشر') + '.</div>' +
        '<div><i class="fas fa-hourglass-half sp-status-icon-warning"></i> ' + t('عند Review يدوية يمكنك المتابعة فوراً مع أزاد') + '.</div>' +
        '<div><i class="fas fa-undo-alt sp-status-icon-info"></i> ' + t('لأي استرداد أو Reconciliation استخدم واتساب أو بريد الرسمي') + '.</div>' +
      '</div>';
  }

  function escapeHtml(value) {
    var div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
  }

  function showSupportAssistanceModal(title, introHtml, kind, amountOverride, recordId) {
    Swal.fire({
      icon: 'info',
      title: title,
      html: '' +
        '<div class="sp-result-rtl">' +
          introHtml +
          '<div class="sp-result-bg">' +
            '<p class="sp-status-box-label"><strong>' + t('التواصل الرسمي مع أزاد') + ':</strong></p>' +
            '<p class="sp-status-box-label"><i class="fab fa-whatsapp sp-status-icon-success"></i> ' + cfg.whatsappDisplay + '</p>' +
            '<p class="sp-status-box-value"><i class="fas fa-envelope sp-text-primary"></i> ' + cfg.email + '</p>' +
          '</div>' +
        '</div>',
      confirmButtonText: t('فتح واتساب أزاد'),
      confirmButtonColor: '#25D366',
      showDenyButton: true,
      denyButtonText: t('إرسال بريد'),
      showCancelButton: true,
      cancelButtonText: t('إغلاق')
    }).then(function (result) {
      if (result.isConfirmed) {
        window.openWhatsApp(kind, amountOverride, recordId);
      } else if (result.isDenied) {
        window.openSupportEmail(kind, amountOverride, recordId);
      }
    });
  }

  function selectPackage(packageName, price, event) {
    selectedPackage = packageName;
    selectedAmount = price;
    document.querySelectorAll('.sp-package-card').forEach(function (c) { c.classList.remove('active'); });
    if (event && event.currentTarget) event.currentTarget.classList.add('active');
    updateProgress('step-package', 'completed');
    updateProgress('step-payment', 'active');
    updateProgress('step-complete', '');
    var el = document.getElementById('purchase-payment-methods');
    if (el) {
      el.style.display = 'grid';
      setTimeout(function () { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
    }
  }
  window.selectPackage = selectPackage;

  function updateProgress(stepId, status) {
    var step = document.getElementById(stepId);
    if (!step) return;
    step.className = 'sp-step';
    if (status) step.classList.add(status);
  }
  window.updateProgress = updateProgress;

  function selectMethod(method, event) {
    document.querySelectorAll('.sp-donation-form').forEach(function (f) { f.classList.remove('active'); });
    document.querySelectorAll('.sp-payment-card').forEach(function (c) { c.classList.remove('active'); });
    var form = document.getElementById(method + '-form');
    if (form) {
      form.classList.add('active');
      if (currentTab === 'purchase' && selectedAmount > 0) {
        if (method === 'card') {
          var ci = document.getElementById('cardAmount');
          if (ci) ci.value = selectedAmount;
        } else if (method === 'crypto') {
          var ca = document.getElementById('customAmount');
          if (ca) ca.value = selectedAmount;
        }
      } else {
        if (method === 'card') {
          var ci2 = document.getElementById('cardAmount');
          if (ci2) ci2.value = '';
        } else if (method === 'crypto') {
          var ca2 = document.getElementById('customAmount');
          if (ca2) ca2.value = '';
        }
      }
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (event && event.currentTarget) event.currentTarget.classList.add('active');
    selectedMethod = method;
  }
  window.selectMethod = selectMethod;

  function selectAmount(amount, event) {
    selectedAmount = amount;
    document.querySelectorAll('.sp-amount-btn').forEach(function (b) { b.classList.remove('active'); });
    if (event && event.currentTarget) event.currentTarget.classList.add('active');
    var ca = document.getElementById('customAmount');
    if (ca) ca.value = '';
  }
  window.selectAmount = selectAmount;

  function switchTab(tab, event) {
    currentTab = tab;
    document.querySelectorAll('.sp-tab-btn').forEach(function (b) { b.classList.remove('active'); });
    if (event && event.target) {
      event.target.classList.add('active');
    } else {
      document.querySelectorAll('.sp-tab-btn').forEach(function (b, idx) {
        if ((tab === 'purchase' && idx === 0) || (tab === 'donation' && idx === 1)) b.classList.add('active');
      });
    }
    document.querySelectorAll('.sp-tab-content').forEach(function (c) { c.classList.remove('active'); });
    var tc = document.getElementById(tab + '-tab');
    if (tc) tc.classList.add('active');

    var ppm = document.getElementById('purchase-payment-methods');
    if (ppm && tab !== 'purchase') ppm.style.display = 'none';

    if (tab === 'donation') {
      document.querySelectorAll('.sp-package-card').forEach(function (c) { c.classList.remove('active'); });
      selectedPackage = null;
      selectedAmount = 0;
    }

    var hi = document.querySelector('.sp-hero-section .mb-4 i');
    if (hi) {
      if (tab === 'purchase') {
        hi.className = 'fas fa-shopping-cart';
        hi.style.color = '#667eea';
      } else {
        hi.className = 'fas fa-heart';
        hi.style.color = '#e74c3c';
      }
    }
  }
  window.switchTab = switchTab;

  async function collectSupportContactData(title) {
    var result = await Swal.fire({
      title: title,
      html: '' +
        '<input id="swal-name" class="swal2-input" placeholder="' + t('Name الكامل') + '">' +
        '<input id="swal-email" class="swal2-input" placeholder="' + t('بريد إلكتروني') + '" type="email">' +
        '<input id="swal-phone" class="swal2-input" placeholder="' + t('رقم Mobile') + '" type="tel">' +
        '<textarea id="swal-message" class="swal2-textarea" placeholder="' + (currentTab === 'purchase' ? t('Name Company أو Note Additional (Optional)') : t('رسالة قصيرة (Optional)')) + '"></textarea>',
      focusConfirm: false,
      showCancelButton: true,
      cancelButtonText: t('Cancel'),
      confirmButtonText: t('متابعة'),
      preConfirm: function () {
        return {
          name: document.getElementById('swal-name').value.trim(),
          email: document.getElementById('swal-email').value.trim(),
          phone: document.getElementById('swal-phone').value.trim(),
          extra: document.getElementById('swal-message').value.trim()
        };
      }
    });
    if (!result.value) return null;
    if (currentTab === 'purchase' && (!result.value.name || !result.value.email)) {
      Swal.fire({ icon: 'error', title: t('Error'), text: t('Name وبريد إلكتروني مطلوبان لشراء Plan'), confirmButtonColor: '#667eea' });
      return null;
    }
    return result.value;
  }

  async function generateCryptoPayment() {
    var customAmount = document.getElementById('customAmount') ? document.getElementById('customAmount').value : '';
    var paymentAmount = customAmount || selectedAmount;
    if (!paymentAmount || paymentAmount < 15) {
      Swal.fire({ icon: 'error', title: t('Error'), text: t('الحد الأدنى للتبرع هو') + ' $15', confirmButtonColor: '#667eea' });
      return;
    }
    var cryptoType = document.getElementById('cryptoType') ? document.getElementById('cryptoType').value : 'btc';

    Swal.fire({ title: t('جاري إنشاء Address Payment...'), html: '<i class="fas fa-spinner fa-spin fa-3x"></i>', showConfirmButton: false, allowOutsideClick: false });

    var apiEndpoint = '';
    var requestData = {};

    if (currentTab === 'purchase') {
      if (!selectedPackage) {
        Swal.close();
        Swal.fire({ icon: 'warning', title: t('Alert'), text: t('الرجاء اختيار باقة أولاً'), confirmButtonColor: '#667eea' });
        return;
      }
      var pcard = document.querySelector('.sp-package-card.active');
      var packageId = pcard ? pcard.getAttribute('data-package-id') : null;
      if (!packageId) {
        Swal.close();
        Swal.fire({ icon: 'error', title: t('Error'), text: t('لم يتم التعرف على Plan المحددة'), confirmButtonColor: '#667eea' });
        return;
      }
      var fv = await collectSupportContactData(t('بيانات شراء Plan'));
      if (!fv) { Swal.close(); return; }
      apiEndpoint = '/payment-vault/api/purchase';
      requestData = {
        package_id: parseInt(packageId),
        customer_name: fv.name,
        customer_email: fv.email,
        customer_phone: fv.phone || '',
        company_name: fv.extra || '',
        payment_method: 'crypto',
        amount_paid: paymentAmount,
        currency: 'USD',
        crypto_currency: cryptoType,
        transaction_id: 'CRYPTO_' + Date.now(),
        payment_details: { crypto_type: cryptoType, amount: paymentAmount }
      };
    } else {
      var fv2 = await collectSupportContactData(t('بيانات التبرع'));
      if (!fv2) { Swal.close(); return; }
      apiEndpoint = '/payment-vault/api/donation';
      requestData = {
        amount: paymentAmount,
        payment_method: 'crypto',
        crypto_type: cryptoType,
        crypto_currency: cryptoType,
        donor_name: fv2.name || null,
        donor_email: fv2.email || null,
        message: fv2.extra || null,
        transaction_id: 'DONATION_' + Date.now()
      };
    }

    fetch(apiEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      Swal.close();
      if (data.success) {
        var recordId = data.purchase_id || data.donation_id;
        var recordType = data.purchase_id ? t('Purchase') : t('تبرع');
        var payBtn = data.payment_url
          ? '<a href="' + data.payment_url + '" target="_blank" rel="noopener noreferrer" class="btn btn-primary mt-2"><i class="fas fa-external-link-alt"></i> ' + t('فتح صفحة Payment') + '</a>'
          : '';
        if (data.payment_address) {
          Swal.fire({
            icon: 'success',
            title: t('تم إنشاء') + ' ' + recordType + ' ' + t('بنجاح'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-title">' + data.message + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('رقم الطلب') + ':</strong> #' + recordId + '</p>' +
                  '<p><strong>' + t('Amount المطلوب') + ':</strong> ' + (data.payment_amount || paymentAmount) + ' ' + (data.crypto_currency || cryptoType.toUpperCase()) + '</p>' +
                  '<hr>' +
                  '<p><strong>' + t('Address Payment') + ':</strong></p>' +
                  '<p class="sp-result-address">' + data.payment_address + '</p>' +
                  '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-outline-primary mt-2"><i class="fas fa-copy"></i> ' + t('نسخ Address') + '</button>' +
                  payBtn +
                '</div>' +
                '<p class="sp-result-hint"><i class="fas fa-info-circle"></i> ' + t('أرسل Amount إلى Address أعلاه وسيتم Confirm Status تلقائياً') + '.</p>' +
                buildSupportStatusHtml(recordId, paymentAmount, t('بانتظار تحويلك إلى Address Payment')) +
              '</div>',
            confirmButtonText: t('تم، سأدفع الآن'),
            confirmButtonColor: '#28a745',
            showDenyButton: true,
            denyButtonText: t('واتساب أزاد'),
            showCancelButton: true,
            cancelButtonText: t('راسلنا ببريد'),
            width: 650,
            allowOutsideClick: false
          }).then(function (r) {
            if (r.isDenied) window.openWhatsApp('payment_help', paymentAmount, recordId);
            else if (r.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, recordId);
          });
        } else {
          Swal.fire({
            icon: 'success',
            title: t('تم حفظ الطلب بنجاح'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-amount">' + data.message + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('رقم الطلب') + ':</strong> #' + recordId + '</p>' +
                  '<p><strong>' + t('Amount') + ':</strong> $' + paymentAmount + '</p>' +
                  '<p><strong>' + t('طريقة Payment') + ':</strong> ' + (data.payment_method_display || cryptoType.toUpperCase()) + '</p>' +
                '</div>' +
                buildSupportStatusHtml(recordId, paymentAmount, t('تم تسجيل الطلب بانتظار المتابعة أو التأكيد')) +
              '</div>',
            confirmButtonText: t('واتساب أزاد'),
            confirmButtonColor: '#28a745',
            showDenyButton: true,
            denyButtonText: t('راسلنا ببريد'),
            allowOutsideClick: false
          }).then(function (r) {
            if (r.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, recordId);
            else if (r.isDenied) window.openSupportEmail('payment_help', paymentAmount, recordId);
          });
        }
      } else {
        showSupportAssistanceModal(
          t('تعذر إنشاء الطلب'),
          '<p>' + escapeHtml(data.error || t('حدث Error أثناء إنشاء الطلب')) + '.</p><p>' + t('يمكنك إعادة المحاولة أو إكمال العملية مباشرة مع Company أزاد') + '.</p>',
          'payment_help', paymentAmount
        );
      }
    })
    .catch(function () {
      Swal.close();
      showSupportAssistanceModal(
        t('تعذر الاتصال بالخادم'),
        '<p>' + t('لم نتمكن من إنشاء') + ' ' + (currentTab === 'purchase' ? t('طلب شراء') : t('طلب تبرع')) + ' ' + t('الآن') + '.</p><p>' + t('يمكنك المتابعة مباشرة مع أزاد عبر واتساب أو بريد بنفس المبلغ') + ': <strong>$' + paymentAmount + '</strong>.</p>',
        'payment_help', paymentAmount
      );
    });
  }
  window.generateCryptoPayment = generateCryptoPayment;

  function copyAddress() {
    var addr = document.getElementById('walletAddress').textContent;
    navigator.clipboard.writeText(addr).then(function () {
      Swal.fire({ icon: 'success', title: t('تم النسخ!'), text: t('تم نسخ Address إلى الحافظة'), timer: 2000, showConfirmButton: false });
    });
  }
  window.copyAddress = copyAddress;

  async function handlePayPalPayment() {
    var ca = document.getElementById('customAmount') ? document.getElementById('customAmount').value : '';
    var paymentAmount = ca || selectedAmount || 0;
    if (!paymentAmount || paymentAmount < 15) {
      Swal.fire({ icon: 'error', title: t('Error'), text: t('الحد الأدنى للتبرع') + ' $15', confirmButtonColor: '#667eea' });
      return;
    }
    var r = await Swal.fire({
      title: t('بيانات Payment') + ' - PayPal',
      html: '' +
        '<input id="swal-name" class="swal2-input" placeholder="' + t('Name الكامل') + '" required>' +
        '<input id="swal-email" class="swal2-input" placeholder="' + t('بريد إلكتروني') + '" type="email" required>' +
        '<input id="swal-phone" class="swal2-input" placeholder="' + t('رقم Mobile') + '" type="tel">' +
        (currentTab === 'purchase' ? '<input id="swal-company" class="swal2-input" placeholder="' + t('Name Company') + ' (' + t('Optional') + ')">' : ''),
      focusConfirm: false,
      showCancelButton: true,
      cancelButtonText: t('Cancel'),
      confirmButtonText: t('متابعة'),
      preConfirm: function () {
        return {
          name: document.getElementById('swal-name').value,
          email: document.getElementById('swal-email').value,
          phone: document.getElementById('swal-phone').value,
          company: currentTab === 'purchase' ? (document.getElementById('swal-company') ? document.getElementById('swal-company').value : '') : ''
        };
      }
    });
    if (!r.value || !r.value.name || !r.value.email) return;

    var apiEndpoint = currentTab === 'purchase' ? '/payment-vault/api/purchase' : '/payment-vault/api/donation';
    var requestData = {};
    if (currentTab === 'purchase') {
      var pcard = document.querySelector('.sp-package-card.active');
      var packageId = pcard ? pcard.getAttribute('data-package-id') : null;
      if (!packageId) {
        Swal.fire({ icon: 'error', title: t('Error'), text: t('الرجاء اختيار باقة') });
        return;
      }
      requestData = {
        package_id: parseInt(packageId),
        customer_name: r.value.name,
        customer_email: r.value.email,
        customer_phone: r.value.phone,
        company_name: r.value.company,
        payment_method: 'paypal',
        amount_paid: paymentAmount,
        currency: 'USD',
        transaction_id: 'PAYPAL_PENDING_' + Date.now()
      };
    } else {
      requestData = {
        amount: paymentAmount,
        payment_method: 'paypal',
        donor_name: r.value.name,
        donor_email: r.value.email,
        transaction_id: 'PAYPAL_DONATION_' + Date.now()
      };
    }

    try {
      var resp = await fetch(apiEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestData) });
      var data = await resp.json();
      if (data.success) {
        if (data.payment_address) {
          Swal.fire({
            icon: 'success',
            title: t('بيانات Payment'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-title"><i class="fab fa-paypal sp-result-paypal-icon"></i> <strong>' + t('Payment عبر PayPal') + '</strong></p>' +
                '<p>' + t('رقم الطلب') + ': #' + (data.purchase_id || data.donation_id) + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('Amount') + ':</strong> $' + paymentAmount + '</p>' +
                  '<p class="sp-result-contact"><i class="fas fa-exchange-alt"></i> ' + t('يتم التحويل تلقائياً إلى Bitcoin') + '</p><hr>' +
                  '<p class="sp-result-wallet">' + data.payment_address + '</p>' +
                  '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-primary"><i class="fas fa-copy"></i> ' + t('نسخ') + '</button>' +
                '</div>' +
                '<p class="sp-result-confirmed">\u2705 ' + t('تم حفظ طلبك بنجاح') + '</p>' +
                buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('قيد انتظار إتمام Payment أو التواصل')) +
              '</div>',
            confirmButtonText: t('متابعة Payment'),
            confirmButtonColor: '#0070ba',
            showDenyButton: true,
            denyButtonText: t('واتساب أزاد'),
            showCancelButton: true,
            cancelButtonText: t('راسلنا ببريد'),
            width: 600
          }).then(function (r2) {
            var rid = data.purchase_id || data.donation_id;
            if (r2.isDenied) window.openWhatsApp('payment_help', paymentAmount, rid);
            else if (r2.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, rid);
          });
        } else {
          Swal.fire({
            icon: 'success',
            title: t('تم حفظ الطلب'),
            html: '' +
              buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('بانتظار التنسيق مع فريق أزاد')) +
              '<p class="sp-result-actions">' + t('يمكنك الآن اختيار واتساب أو بريد لإكمال Payment أو الاستفسار') + '.</p>',
            confirmButtonText: t('واتساب أزاد'),
            confirmButtonColor: '#25D366',
            showDenyButton: true,
            denyButtonText: t('راسلنا ببريد')
          }).then(function (r2) {
            var rid = data.purchase_id || data.donation_id;
            if (r2.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, rid);
            else if (r2.isDenied) window.openSupportEmail('payment_help', paymentAmount, rid);
          });
        }
      } else {
        showSupportAssistanceModal(t('تعذر إكمال طلب PayPal'), '<p>' + escapeHtml(data.error || t('تعذر حفظ طلب PayPal حالياً')) + '.</p><p>' + t('يمكنك المتابعة مباشرة مع أزاد عبر واتساب أو بريد') + '.</p>', 'payment_help', paymentAmount);
      }
    } catch (e) {
      showSupportAssistanceModal(t('فشل الاتصال أثناء PayPal'), '<p>' + t('تعذر التواصل مع الخادم أثناء تجهيز الطلب') + '.</p><p>' + t('استخدم واتساب أو بريد لإتمام الشراء أو التبرع بنفس التفاصيل') + '.</p>', 'payment_help', paymentAmount);
    }
  }
  window.handlePayPalPayment = handlePayPalPayment;

  document.addEventListener('DOMContentLoaded', function () {
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'donation') {
      document.querySelectorAll('.sp-tab-btn').forEach(function (b, i) {
        b.classList.toggle('active', i === 1);
      });
      document.querySelectorAll('.sp-tab-content').forEach(function (c) { c.classList.remove('active'); });
      var dt = document.getElementById('donation-tab');
      if (dt) dt.classList.add('active');
      var hi = document.querySelector('.sp-hero-section .mb-4 i');
      if (hi) { hi.className = 'fas fa-heart'; hi.style.color = '#e74c3c'; }
      currentTab = 'donation';
    }

    var cardForm = document.getElementById('cardPaymentForm');
    if (cardForm) {
      cardForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        var ci = document.getElementById('cardAmount');
        var paymentAmount = parseFloat(ci ? ci.value : '') || selectedAmount || 0;
        if (!paymentAmount || paymentAmount < 15) {
          Swal.fire({ icon: 'error', title: t('Error'), text: t('الحد الأدنى للتبرع') + ' $15', confirmButtonColor: '#667eea' });
          return;
        }
        var r = await Swal.fire({
          title: t('بيانات Payment'),
          html: '' +
            '<input id="swal-name" class="swal2-input" placeholder="' + t('Name الكامل') + '" required>' +
            '<input id="swal-email" class="swal2-input" placeholder="' + t('بريد إلكتروني') + '" type="email" required>' +
            '<input id="swal-phone" class="swal2-input" placeholder="' + t('رقم Mobile') + '" type="tel">' +
            (currentTab === 'purchase' ? '<input id="swal-company" class="swal2-input" placeholder="' + t('Name Company') + ' (' + t('Optional') + ')">' : ''),
          focusConfirm: false,
          showCancelButton: true,
          cancelButtonText: t('Cancel'),
          confirmButtonText: t('متابعة'),
          preConfirm: function () {
            return {
              name: document.getElementById('swal-name').value,
              email: document.getElementById('swal-email').value,
              phone: document.getElementById('swal-phone').value,
              company: currentTab === 'purchase' ? (document.getElementById('swal-company') ? document.getElementById('swal-company').value : '') : ''
            };
          }
        });
        if (!r.value || !r.value.name || !r.value.email) return;

        var apiEndpoint = currentTab === 'purchase' ? '/payment-vault/api/purchase' : '/payment-vault/api/donation';
        var requestData = {};
        if (currentTab === 'purchase') {
          var pcard = document.querySelector('.sp-package-card.active');
          var packageId = pcard ? pcard.getAttribute('data-package-id') : null;
          if (!packageId) {
            Swal.fire({ icon: 'error', title: t('Error'), text: t('الرجاء اختيار باقة') });
            return;
          }
          requestData = {
            package_id: parseInt(packageId),
            customer_name: r.value.name,
            customer_email: r.value.email,
            customer_phone: r.value.phone,
            company_name: r.value.company,
            payment_method: 'card',
            amount_paid: paymentAmount,
            currency: 'USD',
            transaction_id: 'CARD_PENDING_' + Date.now()
          };
        } else {
          requestData = {
            amount: paymentAmount,
            payment_method: 'card',
            donor_name: r.value.name,
            donor_email: r.value.email,
            transaction_id: 'CARD_DONATION_' + Date.now()
          };
        }

        try {
          var resp = await fetch(apiEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestData) });
          var data = await resp.json();
          if (data.success) {
            if (data.payment_address) {
              Swal.fire({
                icon: 'success',
                title: t('تم إنشاء Address Payment!'),
                html: '' +
                  '<div class="sp-result-center">' +
                    '<p class="sp-result-amount"><strong>' + t('رقم الطلب') + ': #' + (data.purchase_id || data.donation_id) + '</strong></p>' +
                    '<div class="sp-result-box">' +
                      '<p><strong>' + t('Amount المطلوب') + ':</strong></p>' +
                      '<p class="sp-result-cta">' + (data.payment_amount || paymentAmount) + ' ' + (data.crypto_currency || 'BTC') + '</p><hr>' +
                      '<p><strong>' + t('Address المحفوظة') + ':</strong></p>' +
                      '<p class="sp-result-mono">' + data.payment_address + '</p>' +
                      '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-primary mt-2"><i class="fas fa-copy"></i> ' + t('نسخ Address') + '</button>' +
                    '</div>' +
                    '<p class="sp-result-highlight"><i class="fas fa-check-circle"></i> ' + t('أرسل Amount المحدد إلى Address أعلاه') + '</p>' +
                    buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('بانتظار إتمام Payment أو المتابعة مع أزاد')) +
                  '</div>',
                confirmButtonText: t('متابعة Payment'),
                confirmButtonColor: '#28a745',
                showDenyButton: true,
                denyButtonText: t('واتساب أزاد'),
                showCancelButton: true,
                cancelButtonText: t('راسلنا ببريد'),
                width: 600,
                allowOutsideClick: false
              }).then(function (r2) {
                var rid = data.purchase_id || data.donation_id;
                if (r2.isDenied) window.openWhatsApp('payment_help', paymentAmount, rid);
                else if (r2.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, rid);
              });
            } else {
              Swal.fire({
                icon: 'success',
                title: t('تم حفظ الطلب'),
                html: '' +
                  buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('تم تسجيل الطلب بانتظار التأكيد أو متابعة يدوية')) +
                  '<p class="sp-result-actions">' + t('يمكنك المتابعة مباشرة مع Company أزاد عبر واتساب أو بريد') + '.</p>',
                confirmButtonText: t('واتساب أزاد'),
                confirmButtonColor: '#25D366',
                showDenyButton: true,
                denyButtonText: t('راسلنا ببريد')
              }).then(function (r2) {
                var rid = data.purchase_id || data.donation_id;
                if (r2.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, rid);
                else if (r2.isDenied) window.openSupportEmail('payment_help', paymentAmount, rid);
              });
            }
          } else {
            showSupportAssistanceModal(t('تعذر تجهيز طلب Card'), '<p>' + escapeHtml(data.error || t('تعذر حفظ طلب Card حالياً')) + '.</p><p>' + t('يمكنك إكمال العملية مباشرة مع أزاد عبر واتساب أو بريد') + '.</p>', 'payment_help', paymentAmount);
          }
        } catch (e) {
          showSupportAssistanceModal(t('فشل الاتصال أثناء Payment'), '<p>' + t('تعذر الوصول إلى الخادم أثناء معالجة الطلب') + '.</p><p>' + t('لا تقلق، يمكنك المتابعة الآن مباشرة مع Company أزاد') + '.</p>', 'payment_help', paymentAmount);
        }
      });
    }
  });

})();
