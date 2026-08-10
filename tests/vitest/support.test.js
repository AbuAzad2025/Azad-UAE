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

function mockSwal() {
  const swal = vi.fn(() => Promise.resolve({ isConfirmed: true, value: undefined }));
  swal.fire = vi.fn(() =>
    Promise.resolve({ isConfirmed: true, value: { name: 'Ali', email: 'a@b.c', phone: '', extra: '' } })
  );
  swal.close = vi.fn();
  swal.DismissReason = { cancel: 'cancel', backdrop: 'backdrop' };
  globalThis.Swal = swal;
  return swal;
}

function mockFetch() {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true, purchase_id: 7, message: 'ok' }),
    })
  );
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function stubEnv() {
  window.spConfig = { whatsappLink: '971500000000', whatsappDisplay: 'Azad', email: 'dev@azad.ae', brand: 'Azad' };
  window.spI18n = {};
  mockSwal();
  mockFetch();
  window.open = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: new URL('http://localhost/support'),
  });
  globalThis.navigator.clipboard = { writeText: vi.fn(() => Promise.resolve()) };
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
}

describe('support.js', () => {
  let domListeners = [];

  beforeEach(() => {
    document.body.innerHTML = '';
    setupSupportFixture();
    stubEnv();
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

  it('should expose all public API functions', async () => {
    await import('../../static/js/support.js');
    expect(typeof window.openWhatsApp).toBe('function');
    expect(typeof window.openSupportEmail).toBe('function');
    expect(typeof window.selectPackage).toBe('function');
    expect(typeof window.updateProgress).toBe('function');
    expect(typeof window.selectMethod).toBe('function');
    expect(typeof window.selectAmount).toBe('function');
    expect(typeof window.switchTab).toBe('function');
    expect(typeof window.spGetCurrentTab).toBe('function');
    expect(typeof window.generateCryptoPayment).toBe('function');
    expect(typeof window.copyAddress).toBe('function');
    expect(typeof window.handlePayPalPayment).toBe('function');
  });

  it('updateProgress adds/removes status classes', async () => {
    await import('../../static/js/support.js');
    window.updateProgress('step-package', 'completed');
    const step = document.getElementById('step-package');
    expect(step.className).toContain('sp-step');
    expect(step.className).toContain('completed');
    window.updateProgress('step-package', 'active');
    expect(step.className).not.toContain('completed');
    expect(step.className).toContain('active');
    window.updateProgress('nonexistent', 'x');
  });

  it('selectPackage selects plan and reveals payment methods', async () => {
    await import('../../static/js/support.js');
    window.selectPackage('Plan A', 50);
    expect(document.getElementById('purchase-payment-methods').style.display).toBe('grid');
    expect(document.querySelector('.sp-package-card.active')).toBeNull();
    const cards = document.querySelectorAll('.sp-package-card');
    expect(cards[0].className).not.toContain('active');
    window.selectPackage('Plan B', 100, { currentTarget: cards[0] });
    expect(cards[0].className).toContain('active');
    expect(document.getElementById('step-package').className).toContain('completed');
  });

  it('selectAmount toggles buttons and clears custom input', async () => {
    await import('../../static/js/support.js');
    const btn = document.querySelector('.sp-amount-btn');
    window.selectAmount(25, { currentTarget: btn });
    expect(btn.className).toContain('active');
    expect(document.getElementById('customAmount').value).toBe('');
  });

  it('selectMethod activates form and syncs purchase amount', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    window.selectPackage('Plan A', 50);
    window.selectMethod('crypto', { currentTarget: document.getElementById('crypto-form') });
    expect(document.getElementById('crypto-form').className).toContain('active');
    expect(document.getElementById('customAmount').value).toBe('50');
    window.selectMethod('card', {});
    expect(document.getElementById('card-form').className).toContain('active');
    expect(document.getElementById('cardAmount').value).toBe('50');
  });

  it('selectMethod clears amounts on donation tab', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '99';
    window.selectMethod('crypto', {});
    expect(document.getElementById('customAmount').value).toBe('');
  });

  it('switchTab toggles content and hero icon', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    expect(window.spGetCurrentTab()).toBe('donation');
    expect(document.getElementById('donation-tab').className).toContain('active');
    expect(document.getElementById('purchase-tab').className).not.toContain('active');
    const icon = document.querySelector('.sp-hero-section .mb-4 i');
    expect(icon.className).toContain('fa-heart');
    expect(icon.style.color).toBe('rgb(231, 76, 60)');
    window.switchTab('purchase');
    expect(window.spGetCurrentTab()).toBe('purchase');
    expect(icon.className).toContain('fa-shopping-cart');
  });

  it('switchTab hides payment methods when leaving purchase', async () => {
    await import('../../static/js/support.js');
    window.selectPackage('Plan A', 50);
    document.getElementById('purchase-payment-methods').style.display = 'grid';
    window.switchTab('donation');
    expect(document.getElementById('purchase-payment-methods').style.display).toBe('none');
  });

  it('openWhatsApp opens wa.me link with encoded message', async () => {
    await import('../../static/js/support.js');
    window.openWhatsApp('buy_code', 50, 5);
    expect(window.open).toHaveBeenCalledTimes(1);
    const [url, target] = window.open.mock.calls[0];
    expect(url).toContain('https://wa.me/971500000000?text=');
    expect(target).toBe('_blank');
    expect(decodeURIComponent(url.split('text=')[1])).toContain('Azad');
  });

  it('openSupportEmail sets mailto location', async () => {
    await import('../../static/js/support.js');
    window.openSupportEmail('donation_help', 25);
    expect(window.location.href).toContain('mailto:dev@azad.ae?subject=');
    expect(window.location.href).toContain('&body=');
  });

  it('generateCryptoPayment rejects amount below minimum', async () => {
    await import('../../static/js/support.js');
    window.selectAmount(5, {});
    await window.generateCryptoPayment();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ icon: 'error', text: 'Minimum donation amount is $15' })
    );
  });

  it('generateCryptoPayment rejects junk-string amounts instead of parsing them', async () => {
    await import('../../static/js/support.js');
    window.selectAmount(0, {});
    document.getElementById('customAmount').value = '15abc';
    await window.generateCryptoPayment();
    expect(Swal.fire).toHaveBeenCalledWith(
      expect.objectContaining({ icon: 'error', text: 'Minimum donation amount is $15' })
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('generateCryptoPayment sends a numeric amount with a randomized transaction id', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Ali', email: 'a@b.c', phone: '123', extra: 'msg' } });
    await window.generateCryptoPayment();
    await flush();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.amount).toBe(50);
    expect(body.transaction_id).toMatch(/^DONATION_\d+_[a-z0-9]+_[a-z0-9]+$/);
  });

  it('generateCryptoPayment handles donation flow with fetch', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Ali', email: 'a@b.c', phone: '123', extra: 'msg' } });
    await window.generateCryptoPayment();
    await flush();
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/payment-vault/api/donation');
    const body = JSON.parse(opts.body);
    expect(body.amount).toBe(50);
    expect(body.payment_method).toBe('crypto');
    expect(body.donor_name).toBe('Ali');
    expect(body.donor_email).toBe('a@b.c');
    expect(Swal.close).toHaveBeenCalled();
  });

  it('generateCryptoPayment handles purchase flow', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    window.selectPackage('Plan A', 100, { currentTarget: document.querySelector('.sp-package-card') });
    document.getElementById('customAmount').value = '100';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Ali', email: 'a@b.c', phone: '', extra: '' } });
    await window.generateCryptoPayment();
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/payment-vault/api/purchase');
    const body = JSON.parse(opts.body);
    expect(body.package_id).toBe(1);
    expect(body.payment_method).toBe('crypto');
    expect(body.customer_name).toBe('Ali');
  });

  it('generateCryptoPayment warns when package missing on purchase', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    document.getElementById('customAmount').value = '50';
    await window.generateCryptoPayment();
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'warning' }));
  });

  it('generateCryptoPayment shows connection error on fetch failure', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '50';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Ali', email: 'a@b.c', phone: '', extra: '' } });
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network')));
    await window.generateCryptoPayment();
    await flush();
    expect(Swal.close).toHaveBeenCalled();
  });

  it('copyAddress copies wallet address', async () => {
    await import('../../static/js/support.js');
    await window.copyAddress();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('bc1qtest');
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'success' }));
  });

  it('handlePayPalPayment rejects below minimum', async () => {
    await import('../../static/js/support.js');
    document.getElementById('customAmount').value = '10';
    await window.handlePayPalPayment();
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ text: 'Minimum donation $15' }));
  });

  it('handlePayPalPayment submits donation order', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.getElementById('customAmount').value = '40';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Sara', email: 's@b.c', phone: '5', company: '' } });
    await window.handlePayPalPayment();
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/payment-vault/api/donation');
    const body = JSON.parse(opts.body);
    expect(body.payment_method).toBe('paypal');
    expect(body.donor_name).toBe('Sara');
  });

  it('handlePayPalPayment requires package on purchase tab', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    document.getElementById('customAmount').value = '40';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Sara', email: 's@b.c', phone: '', company: '' } });
    await window.handlePayPalPayment();
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ icon: 'error' }));
  });

  it('handlePayPalPayment handles purchase with active package', async () => {
    await import('../../static/js/support.js');
    window.switchTab('purchase');
    window.selectPackage('Plan A', 40, { currentTarget: document.querySelector('.sp-package-card') });
    document.getElementById('customAmount').value = '40';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Sara', email: 's@b.c', phone: '', company: 'ACME' } });
    await window.handlePayPalPayment();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.package_id).toBe(1);
    expect(body.company_name).toBe('ACME');
    expect(body.payment_method).toBe('paypal');
  });

  it('cardPaymentForm submit handler posts card donation', async () => {
    await import('../../static/js/support.js');
    window.switchTab('donation');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    document.getElementById('cardAmount').value = '60';
    Swal.fire.mockResolvedValueOnce({ value: { name: 'Z', email: 'z@b.c', phone: '', company: '' } });
    const form = document.getElementById('cardPaymentForm');
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/payment-vault/api/donation');
    const body = JSON.parse(opts.body);
    expect(body.payment_method).toBe('card');
  });

  it('cardPaymentForm submit rejects below minimum', async () => {
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    document.getElementById('cardAmount').value = '5';
    const form = document.getElementById('cardPaymentForm');
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(Swal.fire).toHaveBeenCalledWith(expect.objectContaining({ text: 'Minimum donation $15' }));
  });

  it('DOMContentLoaded with ?tab=donation activates donation tab', async () => {
    window.location.search = '?tab=donation';
    await import('../../static/js/support.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(window.spGetCurrentTab()).toBe('donation');
    expect(document.getElementById('donation-tab').className).toContain('active');
    const icon = document.querySelector('.sp-hero-section .mb-4 i');
    expect(icon.className).toContain('fa-heart');
  });
});
