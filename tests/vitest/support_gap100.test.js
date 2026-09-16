import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function setupSupportFixture() {
  document.body.innerHTML = `
    <div class="sp-hero-section"><div class="mb-4"><i class="fas fa-shopping-cart"></i></div></div>
    <div class="sp-tab-buttons">
      <button class="sp-tab-btn active" data-tab="purchase">Purchase</button>
      <button class="sp-tab-btn" data-tab="donation">Donation</button>
    </div>
    <div class="sp-tab-content active" id="purchase-tab">
      <div class="sp-step" id="step-package"></div>
      <div class="sp-step" id="step-payment"></div>
      <div class="sp-step" id="step-complete"></div>
      <div class="sp-package-card" data-package-id="1" data-price="50">Plan A</div>
      <div class="sp-package-card" data-package-id="2" data-price="100">Plan B</div>
      <div id="purchase-payment-methods"></div>
    </div>
    <div class="sp-tab-content" id="donation-tab">
      <div class="sp-amount-btn" data-amount="25">25</div>
      <div class="sp-amount-btn" data-amount="50">50</div>
    </div>
    <div id="crypto-form" class="sp-donation-form sp-payment-card">
      <input id="customAmount" value="">
      <select id="cryptoType"><option value="btc">BTC</option><option value="usdt">USDT</option></select>
      <span id="walletAddress">bc1qtest</span>
    </div>
    <div id="card-form" class="sp-donation-form sp-payment-card"><input id="cardAmount" value=""></div>
    <div id="paypal-form" class="sp-donation-form sp-payment-card"></div>
    <div id="bank-form" class="sp-donation-form sp-payment-card"></div>
    <form id="cardPaymentForm"></form>
  `;
}

const VALID_CONTACT = { name: 'Ali', email: 'a@b.c', phone: '5', extra: 'note' };

function ensureSwalInputs() {
  const seeds = [
    ['swal-name', 'Ali'],
    ['swal-email', 'a@b.c'],
    ['swal-phone', '5'],
    ['swal-message', 'note'],
    ['swal-company', 'ACME'],
  ];
  for (const [id, value] of seeds) {
    if (!document.getElementById(id)) {
      const el = document.createElement('input');
      el.id = id;
      el.value = value;
      document.body.appendChild(el);
    }
  }
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('support.js gaps', () => {
  let domListeners = [];
  let contactResponses;
  let modalResponses;
  let fetchImpl;
  let swalFire;

  beforeEach(() => {
    document.body.innerHTML = '';
    setupSupportFixture();
    contactResponses = [];
    modalResponses = [];
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, donation_id: 7, message: 'ok' }),
      });
    window.spConfig = {
      whatsappLink: '971500000000',
      whatsappDisplay: 'Azad',
      email: 'dev@azad.ae',
      brand: 'Azad',
    };
    window.spI18n = {};
    swalFire = vi.fn((opts) => {
      if (opts && typeof opts.preConfirm === 'function') {
        ensureSwalInputs();
        opts.preConfirm();
        if (contactResponses.length) return Promise.resolve(contactResponses.shift());
        return Promise.resolve({ value: { ...VALID_CONTACT } });
      }
      if (opts && opts.showDenyButton) {
        if (modalResponses.length) return Promise.resolve(modalResponses.shift());
        return Promise.resolve({});
      }
      return Promise.resolve({});
    });
    const swal = vi.fn();
    swal.fire = swalFire;
    swal.close = vi.fn();
    swal.DismissReason = { cancel: 'cancel', backdrop: 'backdrop' };
    globalThis.Swal = swal;
    globalThis.fetch = vi.fn((...args) => fetchImpl(...args));
    window.open = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new URL('http://localhost/support'),
    });
    globalThis.navigator.clipboard = { writeText: vi.fn(() => Promise.resolve()) };
    Element.prototype.scrollIntoView = vi.fn();
    domListeners = [];
    const origAdd = document.addEventListener.bind(document);
    document.addEventListener = vi.fn((type, fn, ...rest) => {
      if (type === 'DOMContentLoaded') domListeners.push(fn);
      return origAdd(type, fn, ...rest);
    });
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    for (const fn of domListeners) document.removeEventListener('DOMContentLoaded', fn);
    document.addEventListener = Document.prototype.addEventListener;
    delete globalThis.Swal;
    delete globalThis.fetch;
    delete window.spConfig;
    delete window.spI18n;
    delete window.openWhatsApp;
    delete window.openSupportEmail;
    delete window.selectPackage;
    delete window.updateProgress;
    delete window.selectMethod;
    delete window.selectAmount;
    delete window.switchTab;
    delete window.spGetCurrentTab;
    delete window.generateCryptoPayment;
    delete window.copyAddress;
    delete window.handlePayPalPayment;
    vi.resetModules();
  });

  function fireCallsWithDidOpen() {
    return swalFire.mock.calls.map((args) => args[0]).filter((opts) => opts && opts.didOpen);
  }

  function invokeDidOpenWithCopyButton(address) {
    const withDidOpen = fireCallsWithDidOpen();
    expect(withDidOpen.length).toBeGreaterThan(0);
    const btn = document.createElement('button');
    btn.id = 'spCopyAddressBtn';
    document.body.appendChild(btn);
    withDidOpen[withDidOpen.length - 1].didOpen();
    btn.click();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(address);
  }

  it('routes assistance modal deny to email and confirm to whatsapp', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false, error: 'nope' }) });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    modalResponses.push({ isDenied: true });
    await window.generateCryptoPayment();
    await flush();
    expect(window.location.href).toContain('mailto:dev@azad.ae');

    vi.resetModules();
    document.body.innerHTML = '';
    setupSupportFixture();
    contactResponses = [];
    modalResponses = [{ isConfirmed: true }];
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    await window.generateCryptoPayment();
    await flush();
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');
  });

  it('selectMethod clears the card input on the donation tab', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('cardAmount').value = '99';
    window.selectMethod('card', {});
    expect(document.getElementById('cardAmount').value).toBe('');
  });

  it('switchTab honours an explicit event target', async () => {
    await import('../../static/js/support.js');
    const buttons = document.querySelectorAll('.sp-tab-btn');
    window.switchTab('donation', { target: buttons[1] });
    expect(buttons[1].className).toContain('active');
    expect(window.spGetCurrentTab()).toBe('donation');
  });

  it('covers every support message kind and tab variant', async () => {
    await import('../../static/js/support.js');
    window.openWhatsApp('refund_help', 0, 12);
    window.openWhatsApp('buy_system', 0, 0);
    window.openSupportEmail('unknown_kind', 0, 0);
    window.switchTab('donation');
    window.openWhatsApp('payment_help', 0, 0);
    window.openSupportEmail('payment_help', 0, 0);
    expect(window.open).toHaveBeenCalled();
    expect(window.location.href).toContain('mailto:');
  });

  it('aborts crypto donation when contact details are dismissed', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    contactResponses.push({ value: undefined });
    await window.generateCryptoPayment();
    expect(fetch).not.toHaveBeenCalled();
    expect(Swal.close).toHaveBeenCalled();
  });

  it('rejects purchase contact data without name/email', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    window.selectPackage('Plan A', 100, {
      currentTarget: document.querySelector('.sp-package-card'),
    });
    document.getElementById('customAmount').value = '100';
    contactResponses.push({ value: { name: '', email: '', phone: '', extra: '' } });
    await window.generateCryptoPayment();
    expect(fetch).not.toHaveBeenCalled();
    expect(Swal.close).toHaveBeenCalled();
  });

  it('errors when the selected plan has no package id', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    window.selectPackage('Plan A', 50);
    document.getElementById('customAmount').value = '50';
    await window.generateCryptoPayment();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ icon: 'error', text: 'Selected plan not recognized' }),
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows the crypto payment-address modal with payment page (deny -> whatsapp)', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            donation_id: 11,
            message: 'sent',
            payment_address: 'bc1xyz',
            payment_amount: '0.001',
            crypto_currency: 'BTC',
            payment_url: 'https://pay.example/x',
          }),
      });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    modalResponses.push({ isDenied: true });
    await window.generateCryptoPayment();
    await flush();
    invokeDidOpenWithCopyButton('bc1xyz');
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');
  });

  it('shows the crypto payment-address modal without payment page (cancel -> email)', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            donation_id: 12,
            message: 'sent',
            payment_address: 'bc1abc',
          }),
      });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    modalResponses.push({ dismiss: 'cancel' });
    await window.generateCryptoPayment();
    await flush();
    invokeDidOpenWithCopyButton('bc1abc');
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('handles crypto purchase with a payment address', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            purchase_id: 21,
            message: 'created',
            payment_address: 'bc1pp',
            payment_amount: '100',
            crypto_currency: 'BTC',
          }),
      });
    window.switchTab('purchase');
    window.selectPackage('Plan A', 100, {
      currentTarget: document.querySelector('.sp-package-card'),
    });
    document.getElementById('customAmount').value = '100';
    modalResponses.push({ isConfirmed: true });
    await window.generateCryptoPayment();
    await flush();
    invokeDidOpenWithCopyButton('bc1pp');
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'success' }));
  });

  it('follows crypto no-address modal confirm and deny paths', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, donation_id: 5, message: 'ok' }),
      });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    modalResponses.push({ isConfirmed: true });
    await window.generateCryptoPayment();
    await flush();
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');

    modalResponses.push({ isDenied: true });
    await window.generateCryptoPayment();
    await flush();
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('submits paypal donation with address then follows deny to whatsapp', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ success: true, donation_id: 9, payment_address: 'pp-addr' }),
      });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '40';
    contactResponses.push({ value: { name: 'Sara', email: 's@b.c', phone: '5', company: '' } });
    modalResponses.push({ isDenied: true });
    await window.handlePayPalPayment();
    await flush();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.payment_method).toBe('paypal');
    invokeDidOpenWithCopyButton('pp-addr');
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');
  });

  it('submits paypal purchase with address then follows cancel to email', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ success: true, purchase_id: 30, payment_address: 'pp-biz' }),
      });
    window.switchTab('purchase');
    window.selectPackage('Plan A', 40, {
      currentTarget: document.querySelector('.sp-package-card'),
    });
    document.getElementById('customAmount').value = '40';
    contactResponses.push({ value: { name: 'Sara', email: 's@b.c', phone: '', company: 'ACME' } });
    modalResponses.push({ dismiss: 'cancel' });
    await window.handlePayPalPayment();
    await flush();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.company_name).toBe('ACME');
    invokeDidOpenWithCopyButton('pp-biz');
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('aborts paypal when contact details are missing', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '40';
    contactResponses.push({ value: { name: '', email: '' } });
    await window.handlePayPalPayment();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('follows paypal no-address modal confirm and deny paths', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, donation_id: 3, message: 'ok' }),
      });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '40';
    modalResponses.push({ isConfirmed: true });
    await window.handlePayPalPayment();
    await flush();
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');

    modalResponses.push({ isDenied: true });
    await window.handlePayPalPayment();
    await flush();
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('shows assistance when paypal order fails and when fetch throws', async () => {
    await import('../../static/js/support.js');
    fetchImpl = () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false, error: 'bad' }) });
    window.switchTab('donation');
    document.getElementById('customAmount').value = '40';
    modalResponses.push({ isDenied: true });
    await window.handlePayPalPayment();
    await flush();
    expect(window.location.href).toContain('mailto:dev@azad.ae');

    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network')));
    modalResponses.push({});
    await window.handlePayPalPayment();
    await flush();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Connection failed during PayPal' }),
    );
  });

  it('submits card purchase with address then follows deny to whatsapp', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            purchase_id: 7,
            message: 'ok',
            payment_address: 'card-addr',
            payment_amount: 60,
            crypto_currency: 'BTC',
          }),
      });
    window.switchTab('purchase');
    window.selectPackage('Plan A', 60, {
      currentTarget: document.querySelector('.sp-package-card'),
    });
    document.getElementById('cardAmount').value = '60';
    contactResponses.push({ value: { name: 'Zed', email: 'z@b.c', phone: '', company: 'ACME' } });
    modalResponses.push({ isDenied: true });
    document.getElementById('cardPaymentForm').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    await flush();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.payment_method).toBe('card');
    expect(body.package_id).toBe(1);
    invokeDidOpenWithCopyButton('card-addr');
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');
  });

  it('follows card address modal cancel to email', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            donation_id: 77,
            message: 'ok',
            payment_address: 'card-addr-2',
            payment_amount: 60,
            crypto_currency: 'BTC',
          }),
      });
    window.switchTab('donation');
    document.getElementById('cardAmount').value = '60';
    modalResponses.push({ dismiss: 'cancel' });
    document.getElementById('cardPaymentForm').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    await flush();
    invokeDidOpenWithCopyButton('card-addr-2');
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('follows card donation no-address modal confirm and deny paths', async () => {    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    fetchImpl = () =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, donation_id: 8, message: 'ok' }),
      });
    window.switchTab('donation');
    const submit = () => {
      document.getElementById('cardAmount').value = '60';
      contactResponses.push({ value: { name: 'Zed', email: 'z@b.c', phone: '', company: '' } });
      document
        .getElementById('cardPaymentForm')
        .dispatchEvent(new Event('submit', { cancelable: true }));
    };
    modalResponses.push({ isConfirmed: true });
    submit();
    await flush();
    await flush();
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('https://wa.me/'), '_blank');

    modalResponses.push({ isDenied: true });
    submit();
    await flush();
    await flush();
    expect(window.location.href).toContain('mailto:dev@azad.ae');
  });

  it('aborts card submit without contact details', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    window.switchTab('donation');
    document.getElementById('cardAmount').value = '60';
    contactResponses.push({ value: { name: '', email: '' } });
    document.getElementById('cardPaymentForm').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('aborts card purchase submit without a package', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    window.switchTab('purchase');
    document.getElementById('cardAmount').value = '60';
    document.getElementById('cardPaymentForm').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ icon: 'error', text: 'Please select a package' }),
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows assistance when card order fails and when fetch throws', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    window.switchTab('donation');
    const submit = () => {
      document.getElementById('cardAmount').value = '60';
      document.getElementById('cardPaymentForm').dispatchEvent(new Event('submit', { cancelable: true }));
    };
    fetchImpl = () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false, error: 'bad' }) });
    modalResponses.push({});
    submit();
    await flush();
    await flush();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Could not prepare card order' }),
    );

    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network')));
    modalResponses.push({});
    submit();
    await flush();
    await flush();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Connection failed during payment' }),
    );
  });
});
