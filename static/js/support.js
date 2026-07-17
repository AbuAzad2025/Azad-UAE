/* ============================================================
   Azadexa — Support / Donation / Purchase Page Logic
   ============================================================
   Depends on window.spConfig defined in scripts.html.
   ============================================================ */

(function () {
  'use strict';

  const cfg = window.spConfig || {};
  const i18n = window.spI18n || {};
  const t = function (key) { return i18n[key] || key; };

  let selectedAmount = 0;
  let selectedMethod = '';
  let selectedPackage = '';
  let currentTab = 'purchase';

  function buildSupportMessage(kind, amountOverride, recordId) {
    const amount = amountOverride || selectedAmount ||
      (document.getElementById('customAmount') ? document.getElementById('customAmount').value : '') ||
      (document.getElementById('cardAmount') ? document.getElementById('cardAmount').value : '') || '';
    const packageLabel = selectedPackage || t('not yet specified');
    const orderRef = recordId ? ' ' + t('reference number') + ': #' + recordId + '.' : '';

    const messages = {
      buy_code: t('Hello') + ' ' + cfg.brand + ', ' + t('I want') + ' ' + t('Purchase') + ' ' + t('Source Code') + ' ' + t('or') + ' ' + t('implement') + ' ' + t('customization') + ' ' + t('Specific') + ' ' + t('for the system') + '.' + orderRef,
      donation_help: t('Hello') + ' ' + cfg.brand + ', ' + t('I want') + ' ' + t('Donation') + ' ' + t('or') + ' ' + t('Sponsorship') + ' ' + t('development') + ' ' + t('feature') + ' ' + t('in') + ' ' + t('System') + '. ' + t('Amount') + ' ' + t('Expected') + ': ' + (amount || t('I will specify with you')) + ' ' + t('Dollar') + '.' + orderRef,
      payment_help: t('Hello') + ' ' + cfg.brand + ', ' + t('I need') + ' ' + t('help') + ' ' + t('in') + ' ' + t('completing') + ' ' + (currentTab === 'purchase' ? t('Purchase') + ' ' + t('System') : t('Donation')) + '.' + orderRef,
      refund_help: t('Hello') + ' ' + cfg.brand + ', ' + t('I want') + ' ' + t('inquiry') + ' ' + t('about') + ' ' + t('Status') + ' ' + t('Payment') + ' ' + t('or') + ' ' + t('refund') + '.' + orderRef
    };
    messages.buy_system = t('Hello') + ' ' + cfg.brand + ', ' + t('I want') + ' ' + t('Purchase') + ' ' + t('System') + (currentTab === 'purchase' ? ' ' + t('current package') + ': ' + packageLabel : '') + '. ' + t('Amount') + ' ' + t('Expected') + ': ' + (amount || t('I will specify with you')) + ' ' + t('Dollar') + '.' + orderRef;

    return messages[kind] || messages.buy_system;
  }

  function buildSupportEmail(kind, amountOverride, recordId) {
    const message = buildSupportMessage(kind, amountOverride, recordId);
    const subjects = {
      buy_system: t('Purchase System Request'),
      buy_code: t('Purchase Code or Customization Request'),
      donation_help: t('Donation or Sponsorship Inquiry'),
      payment_help: t('Help Completing Payment'),
      refund_help: t('Refund or Payment Status Inquiry')
    };
    const subject = (subjects[kind] || t('inquiry')) + ' - ' + cfg.brand;
    const body = message + '\n\n' + t('Contact Information') + ':\n' + t('WhatsApp') + ': ' + cfg.whatsappDisplay + '\n' + t('Email') + ': ' + cfg.email;
    return { subject: subject, body: body };
  }

  window.openWhatsApp = function (kind, amountOverride, recordId) {
    const message = buildSupportMessage(kind, amountOverride, recordId);
    window.open('https://wa.me/' + cfg.whatsappLink + '?text=' + encodeURIComponent(message), '_blank');
  };

  window.openSupportEmail = function (kind, amountOverride, recordId) {
    const payload = buildSupportEmail(kind, amountOverride, recordId);
    window.location.href = 'mailto:' + cfg.email + '?subject=' + encodeURIComponent(payload.subject) + '&body=' + encodeURIComponent(payload.body);
  };

  function buildSupportStatusHtml(recordId, paymentAmount, label) {
    return '' +
      '<div class="sp-status-box">' +
        '<p class="sp-status-box-label"><strong>' + t('Current Status') + ':</strong> ' + label + '</p>' +
        '<p class="sp-status-box-label"><strong>' + t('Reference') + ':</strong> #' + (recordId || '\u2014') + '</p>' +
        '<p class="sp-status-box-value"><strong>' + t('Amount') + ':</strong> $' + (paymentAmount || '\u2014') + '</p>' +
      '</div>' +
      '<div class="sp-status-details">' +
        '<div><i class="fas fa-check-circle sp-status-icon-success"></i> ' + t('On success you will receive clear details or direct payment address') + '.</div>' +
        '<div><i class="fas fa-hourglass-half sp-status-icon-warning"></i> ' + t('On manual review you can follow up immediately with Azad') + '.</div>' +
        '<div><i class="fas fa-undo-alt sp-status-icon-info"></i> ' + t('For any refund or reconciliation use WhatsApp or official email') + '.</div>' +
      '</div>';
  }

  function escapeHtml(value) {
    const div = document.createElement('div');
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
            '<p class="sp-status-box-label"><strong>' + t('Official contact with Azad') + ':</strong></p>' +
            '<p class="sp-status-box-label"><i class="fab fa-whatsapp sp-status-icon-success"></i> ' + cfg.whatsappDisplay + '</p>' +
            '<p class="sp-status-box-value"><i class="fas fa-envelope sp-text-primary"></i> ' + cfg.email + '</p>' +
          '</div>' +
        '</div>',
      confirmButtonText: t('Open Azad WhatsApp'),
      confirmButtonColor: '#25D366',
      showDenyButton: true,
      denyButtonText: t('Send Email'),
      showCancelButton: true,
      cancelButtonText: t('Close')
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
    const el = document.getElementById('purchase-payment-methods');
    if (el) {
      el.style.display = 'grid';
      setTimeout(function () { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
    }
  }
  window.selectPackage = selectPackage;

  function updateProgress(stepId, status) {
    const step = document.getElementById(stepId);
    if (!step) return;
    step.className = 'sp-step';
    if (status) step.classList.add(status);
  }
  window.updateProgress = updateProgress;

  function selectMethod(method, event) {
    document.querySelectorAll('.sp-donation-form').forEach(function (f) { f.classList.remove('active'); });
    document.querySelectorAll('.sp-payment-card').forEach(function (c) { c.classList.remove('active'); });
    const form = document.getElementById(method + '-form');
    if (form) {
      form.classList.add('active');
      if (currentTab === 'purchase' && selectedAmount > 0) {
        if (method === 'card') {
          const ci = document.getElementById('cardAmount');
          if (ci) ci.value = selectedAmount;
        } else if (method === 'crypto') {
          const ca = document.getElementById('customAmount');
          if (ca) ca.value = selectedAmount;
        }
      } else {
        if (method === 'card') {
          const ci2 = document.getElementById('cardAmount');
          if (ci2) ci2.value = '';
        } else if (method === 'crypto') {
          const ca2 = document.getElementById('customAmount');
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
    const ca = document.getElementById('customAmount');
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
    const tc = document.getElementById(tab + '-tab');
    if (tc) tc.classList.add('active');

    const ppm = document.getElementById('purchase-payment-methods');
    if (ppm && tab !== 'purchase') ppm.style.display = 'none';

    if (tab === 'donation') {
      document.querySelectorAll('.sp-package-card').forEach(function (c) { c.classList.remove('active'); });
      selectedPackage = null;
      selectedAmount = 0;
    }

    const hi = document.querySelector('.sp-hero-section .mb-4 i');
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
    const result = await Swal.fire({
      title: title,
      html: '' +
        '<input id="swal-name" class="swal2-input" placeholder="' + t('Full Name') + '">' +
        '<input id="swal-email" class="swal2-input" placeholder="' + t('Email address') + '" type="email">' +
        '<input id="swal-phone" class="swal2-input" placeholder="' + t('Mobile Number') + '" type="tel">' +
        '<textarea id="swal-message" class="swal2-textarea" placeholder="' + (currentTab === 'purchase' ? t('Company name or additional note (optional)') : t('Short message (optional)')) + '"></textarea>',
      focusConfirm: false,
      showCancelButton: true,
      cancelButtonText: t('Cancel'),
      confirmButtonText: t('Continue'),
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
      Swal.fire({ icon: 'error', title: t('Error'), text: t('Name and email required to purchase plan'), confirmButtonColor: '#667eea' });
      return null;
    }
    return result.value;
  }

  async function generateCryptoPayment() {
    const customAmount = document.getElementById('customAmount') ? document.getElementById('customAmount').value : '';
    const paymentAmount = customAmount || selectedAmount;
    if (!paymentAmount || paymentAmount < 15) {
      Swal.fire({ icon: 'error', title: t('Error'), text: t('Minimum donation amount is') + ' $15', confirmButtonColor: '#667eea' });
      return;
    }
    const cryptoType = document.getElementById('cryptoType') ? document.getElementById('cryptoType').value : 'btc';

    Swal.fire({ title: t('Creating payment address...'), html: '<i class="fas fa-spinner fa-spin fa-3x"></i>', showConfirmButton: false, allowOutsideClick: false });

    let apiEndpoint = '';
    let requestData = {};

    if (currentTab === 'purchase') {
      if (!selectedPackage) {
        Swal.close();
        Swal.fire({ icon: 'warning', title: t('Alert'), text: t('Please select a package first'), confirmButtonColor: '#667eea' });
        return;
      }
      const pcard = document.querySelector('.sp-package-card.active');
      const packageId = pcard ? pcard.getAttribute('data-package-id') : null;
      if (!packageId) {
        Swal.close();
        Swal.fire({ icon: 'error', title: t('Error'), text: t('Selected plan not recognized'), confirmButtonColor: '#667eea' });
        return;
      }
      const fv = await collectSupportContactData(t('Plan Purchase Details'));
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
      const fv2 = await collectSupportContactData(t('Donation Details'));
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
        const recordId = data.purchase_id || data.donation_id;
        const recordType = data.purchase_id ? t('Purchase') : t('Donation');
        const payBtn = data.payment_url
          ? '<a href="' + data.payment_url + '" target="_blank" rel="noopener noreferrer" class="btn btn-primary mt-2"><i class="fas fa-external-link-alt"></i> ' + t('Open Payment Page') + '</a>'
          : '';
        if (data.payment_address) {
          Swal.fire({
            icon: 'success',
            title: t('Created') + ' ' + recordType + ' ' + t('successfully'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-title">' + data.message + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('Order Number') + ':</strong> #' + recordId + '</p>' +
                  '<p><strong>' + t('Required Amount') + ':</strong> ' + (data.payment_amount || paymentAmount) + ' ' + (data.crypto_currency || cryptoType.toUpperCase()) + '</p>' +
                  '<hr>' +
                  '<p><strong>' + t('Payment Address') + ':</strong></p>' +
                  '<p class="sp-result-address">' + data.payment_address + '</p>' +
                  '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-outline-primary mt-2"><i class="fas fa-copy"></i> ' + t('Copy Address') + '</button>' +
                  payBtn +
                '</div>' +
                '<p class="sp-result-hint"><i class="fas fa-info-circle"></i> ' + t('Send the amount to the address above and the status will be confirmed automatically') + '.</p>' +
                buildSupportStatusHtml(recordId, paymentAmount, t('Waiting for your transfer to payment address')) +
              '</div>',
            confirmButtonText: t('Done, I will pay now'),
            confirmButtonColor: '#28a745',
            showDenyButton: true,
            denyButtonText: t('Azad WhatsApp'),
            showCancelButton: true,
            cancelButtonText: t('Email us'),
            width: 650,
            allowOutsideClick: false
          }).then(function (r) {
            if (r.isDenied) window.openWhatsApp('payment_help', paymentAmount, recordId);
            else if (r.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, recordId);
          });
        } else {
          Swal.fire({
            icon: 'success',
            title: t('Order saved successfully'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-amount">' + data.message + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('Order Number') + ':</strong> #' + recordId + '</p>' +
                  '<p><strong>' + t('Amount') + ':</strong> $' + paymentAmount + '</p>' +
                  '<p><strong>' + t('Payment Method') + ':</strong> ' + (data.payment_method_display || cryptoType.toUpperCase()) + '</p>' +
                '</div>' +
                buildSupportStatusHtml(recordId, paymentAmount, t('Order registered pending follow-up or confirmation')) +
              '</div>',
            confirmButtonText: t('Azad WhatsApp'),
            confirmButtonColor: '#28a745',
            showDenyButton: true,
            denyButtonText: t('Email us'),
            allowOutsideClick: false
          }).then(function (r) {
            if (r.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, recordId);
            else if (r.isDenied) window.openSupportEmail('payment_help', paymentAmount, recordId);
          });
        }
      } else {
        showSupportAssistanceModal(
          t('Could not create order'),
          '<p>' + escapeHtml(data.error || t('Error occurred while creating the order')) + '.</p><p>' + t('You can retry or complete the process directly with Azad Company') + '.</p>',
          'payment_help', paymentAmount
        );
      }
    })
    .catch(function () {
      Swal.close();
      showSupportAssistanceModal(
        t('Could not connect to server'),
        '<p>' + t('We could not create') + ' ' + (currentTab === 'purchase' ? t('Purchase order') : t('Donation order')) + ' ' + t('now') + '.</p><p>' + t('You can follow up directly with Azad via WhatsApp or email for the same amount') + ': <strong>$' + paymentAmount + '</strong>.</p>',
        'payment_help', paymentAmount
      );
    });
  }
  window.generateCryptoPayment = generateCryptoPayment;

  function copyAddress() {
    const addr = document.getElementById('walletAddress').textContent;
    navigator.clipboard.writeText(addr).then(function () {
      Swal.fire({ icon: 'success', title: t('Copied!'), text: t('Address copied to clipboard'), timer: 2000, showConfirmButton: false });
    });
  }
  window.copyAddress = copyAddress;

  async function handlePayPalPayment() {
    const ca = document.getElementById('customAmount') ? document.getElementById('customAmount').value : '';
    const paymentAmount = ca || selectedAmount || 0;
    if (!paymentAmount || paymentAmount < 15) {
      Swal.fire({ icon: 'error', title: t('Error'), text: t('Minimum donation') + ' $15', confirmButtonColor: '#667eea' });
      return;
    }
    const r = await Swal.fire({
      title: t('Payment Details') + ' - PayPal',
      html: '' +
        '<input id="swal-name" class="swal2-input" placeholder="' + t('Full Name') + '" required>' +
        '<input id="swal-email" class="swal2-input" placeholder="' + t('Email address') + '" type="email" required>' +
        '<input id="swal-phone" class="swal2-input" placeholder="' + t('Mobile Number') + '" type="tel">' +
        (currentTab === 'purchase' ? '<input id="swal-company" class="swal2-input" placeholder="' + t('Company Name') + ' (' + t('Optional') + ')">' : ''),
      focusConfirm: false,
      showCancelButton: true,
      cancelButtonText: t('Cancel'),
      confirmButtonText: t('Continue'),
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

    const apiEndpoint = currentTab === 'purchase' ? '/payment-vault/api/purchase' : '/payment-vault/api/donation';
    let requestData = {};
    if (currentTab === 'purchase') {
      const pcard = document.querySelector('.sp-package-card.active');
      const packageId = pcard ? pcard.getAttribute('data-package-id') : null;
      if (!packageId) {
        Swal.fire({ icon: 'error', title: t('Error'), text: t('Please select a package') });
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
      const resp = await fetch(apiEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestData) });
      const data = await resp.json();
      if (data.success) {
        if (data.payment_address) {
          Swal.fire({
            icon: 'success',
            title: t('Payment Details'),
            html: '' +
              '<div class="sp-result-center">' +
                '<p class="sp-result-title"><i class="fab fa-paypal sp-result-paypal-icon"></i> <strong>' + t('Payment via PayPal') + '</strong></p>' +
                '<p>' + t('Order Number') + ': #' + (data.purchase_id || data.donation_id) + '</p>' +
                '<div class="sp-result-box">' +
                  '<p><strong>' + t('Amount') + ':</strong> $' + paymentAmount + '</p>' +
                  '<p class="sp-result-contact"><i class="fas fa-exchange-alt"></i> ' + t('Transfer is automatically sent to Bitcoin') + '</p><hr>' +
                  '<p class="sp-result-wallet">' + data.payment_address + '</p>' +
                  '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-primary"><i class="fas fa-copy"></i> ' + t('Copy') + '</button>' +
                '</div>' +
                '<p class="sp-result-confirmed">\u2705 ' + t('Your order has been saved successfully') + '</p>' +
                buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('Pending payment completion or contact')) +
              '</div>',
            confirmButtonText: t('Follow up Payment'),
            confirmButtonColor: '#0070ba',
            showDenyButton: true,
            denyButtonText: t('Azad WhatsApp'),
            showCancelButton: true,
            cancelButtonText: t('Email us'),
            width: 600
          }).then(function (r2) {
            const rid = data.purchase_id || data.donation_id;
            if (r2.isDenied) window.openWhatsApp('payment_help', paymentAmount, rid);
            else if (r2.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, rid);
          });
        } else {
          Swal.fire({
            icon: 'success',
            title: t('Order saved'),
            html: '' +
              buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('Pending coordination with Azad team')) +
              '<p class="sp-result-actions">' + t('You can now choose WhatsApp or email to complete payment or inquire') + '.</p>',
            confirmButtonText: t('Azad WhatsApp'),
            confirmButtonColor: '#25D366',
            showDenyButton: true,
            denyButtonText: t('Email us')
          }).then(function (r2) {
            const rid = data.purchase_id || data.donation_id;
            if (r2.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, rid);
            else if (r2.isDenied) window.openSupportEmail('payment_help', paymentAmount, rid);
          });
        }
      } else {
        showSupportAssistanceModal(t('Could not complete PayPal order'), '<p>' + escapeHtml(data.error || t('Could not save PayPal order currently')) + '.</p><p>' + t('You can follow up directly with Azad via WhatsApp or email') + '.</p>', 'payment_help', paymentAmount);
      }
    } catch (e) {
      showSupportAssistanceModal(t('Connection failed during PayPal'), '<p>' + t('Could not connect to server while preparing the order') + '.</p><p>' + t('Use WhatsApp or email to complete the purchase or donation with the same details') + '.</p>', 'payment_help', paymentAmount);
    }
  }
  window.handlePayPalPayment = handlePayPalPayment;

  document.addEventListener('DOMContentLoaded', function () {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'donation') {
      document.querySelectorAll('.sp-tab-btn').forEach(function (b, i) {
        b.classList.toggle('active', i === 1);
      });
      document.querySelectorAll('.sp-tab-content').forEach(function (c) { c.classList.remove('active'); });
      const dt = document.getElementById('donation-tab');
      if (dt) dt.classList.add('active');
      const hi = document.querySelector('.sp-hero-section .mb-4 i');
      if (hi) { hi.className = 'fas fa-heart'; hi.style.color = '#e74c3c'; }
      currentTab = 'donation';
    }

    const cardForm = document.getElementById('cardPaymentForm');
    if (cardForm) {
      cardForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const ci = document.getElementById('cardAmount');
        const paymentAmount = parseFloat(ci ? ci.value : '') || selectedAmount || 0;
        if (!paymentAmount || paymentAmount < 15) {
          Swal.fire({ icon: 'error', title: t('Error'), text: t('Minimum donation') + ' $15', confirmButtonColor: '#667eea' });
          return;
        }
        const r = await Swal.fire({
          title: t('Payment Details'),
          html: '' +
            '<input id="swal-name" class="swal2-input" placeholder="' + t('Full Name') + '" required>' +
            '<input id="swal-email" class="swal2-input" placeholder="' + t('Email address') + '" type="email" required>' +
            '<input id="swal-phone" class="swal2-input" placeholder="' + t('Mobile Number') + '" type="tel">' +
            (currentTab === 'purchase' ? '<input id="swal-company" class="swal2-input" placeholder="' + t('Company Name') + ' (' + t('Optional') + ')">' : ''),
          focusConfirm: false,
          showCancelButton: true,
          cancelButtonText: t('Cancel'),
          confirmButtonText: t('Continue'),
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

        const apiEndpoint = currentTab === 'purchase' ? '/payment-vault/api/purchase' : '/payment-vault/api/donation';
        let requestData = {};
        if (currentTab === 'purchase') {
          const pcard = document.querySelector('.sp-package-card.active');
          const packageId = pcard ? pcard.getAttribute('data-package-id') : null;
          if (!packageId) {
            Swal.fire({ icon: 'error', title: t('Error'), text: t('Please select a package') });
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
          const resp = await fetch(apiEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestData) });
          const data = await resp.json();
          if (data.success) {
            if (data.payment_address) {
              Swal.fire({
                icon: 'success',
                title: t('Payment address created!'),
                html: '' +
                  '<div class="sp-result-center">' +
                    '<p class="sp-result-amount"><strong>' + t('Order Number') + ': #' + (data.purchase_id || data.donation_id) + '</strong></p>' +
                    '<div class="sp-result-box">' +
                      '<p><strong>' + t('Required Amount') + ':</strong></p>' +
                      '<p class="sp-result-cta">' + (data.payment_amount || paymentAmount) + ' ' + (data.crypto_currency || 'BTC') + '</p><hr>' +
                      '<p><strong>' + t('Saved Address') + ':</strong></p>' +
                      '<p class="sp-result-mono">' + data.payment_address + '</p>' +
                      '<button onclick="navigator.clipboard.writeText(\'' + data.payment_address + '\')" class="btn btn-primary mt-2"><i class="fas fa-copy"></i> ' + t('Copy Address') + '</button>' +
                    '</div>' +
                    '<p class="sp-result-highlight"><i class="fas fa-check-circle"></i> ' + t('Send the specified amount to the address above') + '</p>' +
                    buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('Pending payment completion or follow-up with Azad')) +
                  '</div>',
                confirmButtonText: t('Follow up Payment'),
                confirmButtonColor: '#28a745',
                showDenyButton: true,
                denyButtonText: t('Azad WhatsApp'),
                showCancelButton: true,
                cancelButtonText: t('Email us'),
                width: 600,
                allowOutsideClick: false
              }).then(function (r2) {
                const rid = data.purchase_id || data.donation_id;
                if (r2.isDenied) window.openWhatsApp('payment_help', paymentAmount, rid);
                else if (r2.dismiss === Swal.DismissReason.cancel) window.openSupportEmail('payment_help', paymentAmount, rid);
              });
            } else {
              Swal.fire({
                icon: 'success',
                title: t('Order saved'),
                html: '' +
                  buildSupportStatusHtml(data.purchase_id || data.donation_id, paymentAmount, t('Order registered pending confirmation or manual follow-up')) +
                  '<p class="sp-result-actions">' + t('You can follow up directly with Azad Company via WhatsApp or email') + '.</p>',
                confirmButtonText: t('Azad WhatsApp'),
                confirmButtonColor: '#25D366',
                showDenyButton: true,
                denyButtonText: t('Email us')
              }).then(function (r2) {
                const rid = data.purchase_id || data.donation_id;
                if (r2.isConfirmed) window.openWhatsApp('payment_help', paymentAmount, rid);
                else if (r2.isDenied) window.openSupportEmail('payment_help', paymentAmount, rid);
              });
            }
          } else {
            showSupportAssistanceModal(t('Could not prepare card order'), '<p>' + escapeHtml(data.error || t('Could not save card order currently')) + '.</p><p>' + t('You can complete the process directly with Azad via WhatsApp or email') + '.</p>', 'payment_help', paymentAmount);
          }
        } catch (e) {
          showSupportAssistanceModal(t('Connection failed during payment'), '<p>' + t('Could not reach server while processing the order') + '.</p><p>' + t("Don't worry, you can follow up directly with Azad Company") + '.</p>', 'payment_help', paymentAmount);
        }
      });
    }
  });

})();
