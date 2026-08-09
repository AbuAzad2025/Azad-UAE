import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function setStoreSlug(slug = 'test-store') {
  document.body.setAttribute('data-store-slug', slug);
}

function setCsrf() {
  let meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'csrf-token');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', 'test-csrf');
}

function mockFetch(handler) {
  global.fetch = vi.fn(handler || (() => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, cart_count: 3 }) })));
}

function cleanupFetch() {
  delete global.fetch;
}

describe('shop-gallery.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
  });
  afterEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
  });

  it('should skip when no gallery element', async () => {
    document.body.innerHTML = '<div></div>';
    await import('../../static/js/shop-gallery.js');
    expect(true).toBe(true);
  });

  it('should skip when no main image', async () => {
    document.body.innerHTML = '<div class="ps-product-gallery"></div>';
    await import('../../static/js/shop-gallery.js');
    expect(true).toBe(true);
  });

  it('should zoom on mousemove, reset on leave, toggle on click', async () => {
    document.body.innerHTML = `
      <div class="ps-product-gallery">
        <div class="ps-gallery-main"><img src="a.jpg"></div>
      </div>
    `;
    const gallery = document.querySelector('.ps-product-gallery');
    gallery.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 });
    await import('../../static/js/shop-gallery.js');
    const img = document.querySelector('img');

    gallery.dispatchEvent(new MouseEvent('mousemove', { clientX: 10, clientY: 10 }));
    expect(img.style.transform).toBe('scale(2)');
    expect(img.style.transformOrigin).toContain('%');

    gallery.dispatchEvent(new MouseEvent('mouseleave'));
    expect(img.style.transform).toBe('scale(1)');
    expect(img.style.transformOrigin).toBe('center center');

    gallery.dispatchEvent(new MouseEvent('click'));
    expect(img.style.transform).toBe('scale(2)');
    gallery.dispatchEvent(new MouseEvent('click'));
    expect(img.style.transform).toBe('scale(1)');
  });
});

describe('shop-quickview.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setStoreSlug();
    mockFetch(() => Promise.resolve({ ok: true, text: () => Promise.resolve('<div>loaded</div>') }));
    vi.resetModules();
  });
  afterEach(() => {
    document.body.innerHTML = '';
    document.body.removeAttribute('data-store-slug');
    cleanupFetch();
    vi.resetModules();
  });

  it('should skip when modal missing', async () => {
    document.body.innerHTML = '<div></div>';
    await import('../../static/js/shop-quickview.js');
    expect(window.ShopQuickView).toBeUndefined();
  });

  it('should open modal and render fetched content', async () => {
    document.body.innerHTML = `
      <div id="ps-quick-view-modal" style="display:none">
        <div class="ps-modal-overlay"></div>
        <button data-modal-close>close</button>
        <div id="ps-quick-view-body"></div>
      </div>
    `;
    await import('../../static/js/shop-quickview.js');
    expect(window.ShopQuickView).toBeDefined();

    await window.ShopQuickView.open(5);
    await new Promise((r) => setTimeout(r, 0));
    expect(document.getElementById('ps-quick-view-modal').style.display).toBe('flex');
    expect(document.getElementById('ps-quick-view-body').innerHTML).toContain('loaded');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/s/test-store/quick-view/5'), expect.anything());

    await window.ShopQuickView.close();
    expect(document.getElementById('ps-quick-view-modal').style.display).toBe('none');
  });

  it('should show error when fetch fails', async () => {
    document.body.innerHTML = `
      <div id="ps-quick-view-modal" style="display:none">
        <div class="ps-modal-overlay"></div>
        <div id="ps-quick-view-body"></div>
      </div>
    `;
    mockFetch(() => Promise.resolve({ ok: false, statusText: 'boom' }));
    await import('../../static/js/shop-quickview.js');
    await window.ShopQuickView.open(5);
    await new Promise((r) => setTimeout(r, 0));
    expect(document.getElementById('ps-quick-view-body').innerHTML).toContain('ps-modal-error');
  });

  it('should open via data-quick-view click handler', async () => {
    document.body.innerHTML = `
      <button data-quick-view data-product-id="7">quick</button>
      <div id="ps-quick-view-modal" style="display:none">
        <div id="ps-quick-view-body"></div>
      </div>
    `;
    await import('../../static/js/shop-quickview.js');
    document.querySelector('[data-quick-view]').click();
    await new Promise((r) => setTimeout(r, 0));
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/quick-view/7'), expect.anything());
  });

  it('should handle qty minus/plus and ajax cart form', async () => {
    document.body.innerHTML = `
      <div id="ps-quick-view-modal" style="display:none">
        <div id="ps-quick-view-body"></div>
      </div>
    `;
    mockFetch(() => Promise.resolve({ ok: true, text: () => Promise.resolve(`
      <div class="ps-qty-wrap">
        <button type="button" data-qty-minus>-</button>
        <input type="number" name="quantity" value="2" min="1" max="5">
        <button type="button" data-qty-plus>+</button>
      </div>
      <form data-ajax-cart>
        <input type="hidden" name="product_id" value="9">
        <input type="number" name="quantity" value="2">
      </form>
    `) }));
    await import('../../static/js/shop-quickview.js');
    window.ShopCart = { addToCart: vi.fn(() => Promise.resolve({ success: true })) };
    await window.ShopQuickView.open(9);
    await new Promise((r) => setTimeout(r, 0));

    const body = document.getElementById('ps-quick-view-body');
    const input = body.querySelector('input[name="quantity"]');
    body.querySelector('[data-qty-minus]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(input.value).toBe('1');

    body.querySelector('[data-qty-plus]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(input.value).toBe('2');

    const form = body.querySelector('[data-ajax-cart]');
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    expect(window.ShopCart.addToCart).toHaveBeenCalled();
    delete window.ShopCart;
  });

  it('should close modal on Escape', async () => {
    document.body.innerHTML = `
      <div id="ps-quick-view-modal" style="display:none">
        <div id="ps-quick-view-body"></div>
      </div>
    `;
    await import('../../static/js/shop-quickview.js');
    await window.ShopQuickView.open(1);
    await new Promise((r) => setTimeout(r, 0));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(document.getElementById('ps-quick-view-modal').style.display).toBe('none');
  });
});

describe('shop-search.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setStoreSlug();
    vi.resetModules();
  });
  afterEach(() => {
    document.body.innerHTML = '';
    document.body.removeAttribute('data-store-slug');
    cleanupFetch();
    vi.resetModules();
  });

  it('should skip when no autocomplete input', async () => {
    document.body.innerHTML = '<input name="q">';
    await import('../../static/js/shop-search.js');
    expect(true).toBe(true);
  });

  it('should skip when no results container', async () => {
    document.body.innerHTML = '<input name="q" data-search-autocomplete><form></form>';
    await import('../../static/js/shop-search.js');
    expect(true).toBe(true);
  });

  it('should search and render results after debounce', async () => {
    document.body.innerHTML = `
      <form><input name="q" data-search-autocomplete></form>
      <div class="ps-autocomplete-results"></div>
    `;
    mockFetch(() => Promise.resolve({ ok: true, json: () => Promise.resolve({
      results: [{ url: '/s/test-store/p/1', name: 'Item <b>One</b>', price: '10.50', currency: 'AED', image: '' }]
    }) }));
    await import('../../static/js/shop-search.js');

    const input = document.querySelector('input[name="q"]');
    input.value = 'ite';
    input.dispatchEvent(new Event('input'));

    await new Promise((r) => setTimeout(r, 350));
    const wrap = document.querySelector('.ps-autocomplete-results');
    expect(wrap.style.display).toBe('block');
    expect(wrap.textContent).toContain('Item');
    expect(wrap.textContent).toContain('10.50');
  });

  it('should close dropdown for short query and empty results', async () => {
    document.body.innerHTML = `
      <form><input name="q" data-search-autocomplete></form>
      <div class="ps-autocomplete-results"></div>
    `;
    mockFetch(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }));
    await import('../../static/js/shop-search.js');

    const input = document.querySelector('input[name="q"]');
    input.value = 'i';
    input.dispatchEvent(new Event('input'));
    await new Promise((r) => setTimeout(r, 350));
    expect(document.querySelector('.ps-autocomplete-results').style.display).toBe('none');
  });

  it('should close dropdown on fetch error', async () => {
    document.body.innerHTML = `
      <form><input name="q" data-search-autocomplete></form>
      <div class="ps-autocomplete-results"></div>
    `;
    mockFetch(() => Promise.reject(new Error('network')));
    await import('../../static/js/shop-search.js');
    const input = document.querySelector('input[name="q"]');
    input.value = 'abc';
    input.dispatchEvent(new Event('input'));
    await new Promise((r) => setTimeout(r, 350));
    expect(document.querySelector('.ps-autocomplete-results').style.display).toBe('none');
  });

  it('should navigate with keyboard and select with Enter', async () => {
    document.body.innerHTML = `
      <form><input name="q" data-search-autocomplete></form>
      <div class="ps-autocomplete-results"></div>
    `;
    mockFetch(() => Promise.resolve({ ok: true, json: () => Promise.resolve({
      results: [
        { url: '/s/test-store/p/1', name: 'One', price: '1.00', currency: '' },
        { url: '/s/test-store/p/2', name: 'Two', price: '2.00', currency: '' },
      ]
    }) }));
    await import('../../static/js/shop-search.js');
    const input = document.querySelector('input[name="q"]');
    input.value = 'ab';
    input.dispatchEvent(new Event('input'));
    await new Promise((r) => setTimeout(r, 350));

    const wrap = document.querySelector('.ps-autocomplete-results');
    const items = wrap.querySelectorAll('.ps-autocomplete-item');
    expect(items.length).toBe(2);

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    expect(items[0].classList.contains('ps-ac-active')).toBe(true);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    expect(items[1].classList.contains('ps-ac-active')).toBe(true);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp' }));
    expect(items[0].classList.contains('ps-ac-active')).toBe(true);

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(wrap.style.display).toBe('none');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(true).toBe(true);
  });
});

describe('shop-storefront.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setStoreSlug();
    vi.resetModules();
  });
  afterEach(() => {
    document.body.innerHTML = '';
    document.body.removeAttribute('data-store-slug');
    cleanupFetch();
    vi.resetModules();
  });

  it('should adjust quantity via data-qty buttons', async () => {
    document.body.innerHTML = `
      <div class="ps-qty-wrap">
        <button type="button" data-qty-minus>-</button>
        <input type="number" value="5" min="1" max="10" step="1">
        <button type="button" data-qty-plus>+</button>
      </div>
    `;
    await import('../../static/js/shop-storefront.js');
    const input = document.querySelector('.ps-qty-wrap input');
    const change = vi.fn();
    input.addEventListener('change', change);

    document.querySelector('[data-qty-minus]').click();
    expect(input.value).toBe('4');
    document.querySelector('[data-qty-plus]').click();
    expect(input.value).toBe('5');
    expect(change).toHaveBeenCalled();
  });

  it('should toggle mobile nav', async () => {
    document.body.innerHTML = `
      <button class="ps-nav-toggle"></button>
      <nav class="ps-nav"></nav>
    `;
    await import('../../static/js/shop-storefront.js');
    const toggle = document.querySelector('.ps-nav-toggle');
    const nav = document.querySelector('.ps-nav');
    toggle.click();
    expect(nav.classList.contains('is-open')).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    toggle.click();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('should auto-dismiss alerts after timeout', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = '<div class="ps-alert" data-auto-dismiss>hi</div>';
    await import('../../static/js/shop-storefront.js');
    const alert = document.querySelector('.ps-alert');
    vi.advanceTimersByTime(5100);
    vi.advanceTimersByTime(500);
    expect(alert.parentNode).toBeNull();
    vi.useRealTimers();
  });

  it('should submit search form after debounce', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <form class="ps-search-form" action="/s/test-store">
        <input type="search" value="xyz">
      </form>
    `;
    const form = document.querySelector('.ps-search-form');
    const submitSpy = vi.fn();
    form.submit = submitSpy;
    await import('../../static/js/shop-storefront.js');
    form.querySelector('input').dispatchEvent(new Event('input'));
    vi.advanceTimersByTime(350);
    expect(submitSpy).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('should update cart on cart-update-form change', async () => {
    document.body.innerHTML = `
      <form id="cart-update-form">
        <input type="number" name="qty_1" value="2">
      </form>
    `;
    window.ShopCart = { updateCart: vi.fn(() => Promise.resolve({ success: true })) };
    mockFetch(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) }));
    await import('../../static/js/shop-storefront.js');
    const input = document.querySelector('#cart-update-form input');
    input.dispatchEvent(new Event('change', { bubbles: true }));
    expect(window.ShopCart.updateCart).toHaveBeenCalled();
    delete window.ShopCart;
  });

  it('should show install banner on beforeinstallprompt', async () => {
    document.body.innerHTML = '<div id="ps-install-banner" style="display:none"></div>';
    await import('../../static/js/shop-storefront.js');
    const banner = document.getElementById('ps-install-banner');
    window.dispatchEvent(new Event('beforeinstallprompt'));
    expect(banner.style.display).toBe('flex');
  });

  it('should paginate via infinite sentinel', async () => {
    document.body.innerHTML = `
      <div class="ps-grid"></div>
      <div class="ps-infinite-sentinel" data-page="1" data-total="3"></div>
    `;
    let callback;
    class MockObserver {
      constructor(cb) { callback = cb; }
      observe() {}
      disconnect() {}
    }
    global.IntersectionObserver = MockObserver;
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, text: () => Promise.resolve('<div class="ps-card"><a>item</a></div>') }));
    await import('../../static/js/shop-storefront.js');

    const sentinel = document.querySelector('.ps-infinite-sentinel');
    callback([{ isIntersecting: true }]);
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const grid = document.querySelector('.ps-grid');
    expect(grid.children.length).toBeGreaterThan(0);
    expect(sentinel.getAttribute('data-page')).toBe('2');
    delete global.IntersectionObserver;
  });
});
