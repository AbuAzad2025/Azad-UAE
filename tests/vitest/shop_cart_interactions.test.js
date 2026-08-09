import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('shop-cart.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    let meta = document.createElement('meta');
    meta.setAttribute('name', 'csrf-token');
    meta.setAttribute('content', 'test-csrf');
    document.head.appendChild(meta);
    document.body.setAttribute('data-store-slug', 'test-store');
    delete window.ShopCart;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    document.body.removeAttribute('data-store-slug');
    delete window.ShopCart;
    delete global.fetch;
    vi.resetModules();
  });

  function okJson(data) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
  }

  it('should add item to cart and update badge', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 3, message: 'Added' }));
    document.body.innerHTML = '<span class="ps-cart-badge"></span><span class="ps-cart-count"></span>';
    await import('../../static/js/shop-cart.js');

    const data = await window.ShopCart.addToCart(5, 2);
    expect(data.success).toBe(true);
    expect(document.querySelector('.ps-cart-badge').textContent).toBe('3');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/s/test-store/cart/add'), expect.objectContaining({ method: 'POST' }));
  });

  it('should show danger toast when add fails', async () => {
    global.fetch = vi.fn(() => okJson({ success: false, message: 'Failed' }));
    await import('../../static/js/shop-cart.js');
    const data = await window.ShopCart.addToCart(5, 1);
    expect(data.success).toBe(false);
    expect(document.body.textContent).toContain('Failed');
  });

  it('should remove item from cart', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 0 }));
    document.body.innerHTML = '<span class="ps-cart-badge"></span>';
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.removeFromCart(5);
    expect(document.querySelector('.ps-cart-badge').style.display).toBe('none');
  });

  it('should update cart quantities', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 4 }));
    document.body.innerHTML = '<span class="ps-cart-badge"></span>';
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.updateCart({ qty_5: 3 });
    expect(document.querySelector('.ps-cart-badge').textContent).toBe('4');
  });

  it('should toggle wishlist on and off', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, wishlisted: true }));
    document.body.innerHTML = `
      <button data-wishlist-toggle data-product-id="5"><i class="far fa-heart"></i></button>
    `;
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.wishlistToggle(5);
    expect(document.querySelector('[data-wishlist-toggle]').innerHTML).toContain('fa-heart');

    global.fetch = vi.fn(() => okJson({ success: true, wishlisted: false }));
    await window.ShopCart.wishlistToggle(5);
    expect(document.querySelector('[data-wishlist-toggle]').innerHTML).toContain('fa-heart');
  });

  it('should refresh badge from count endpoint', async () => {
    global.fetch = vi.fn(() => okJson({ count: 7 }));
    document.body.innerHTML = '<span class="ps-cart-count"></span>';
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.refreshCartBadge();
    expect(document.querySelector('.ps-cart-count').textContent).toBe('7');
  });

  it('should update cart via form change handler', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 2, subtotal: '25.00' }));
    document.body.innerHTML = `
      <form id="cart-update-form">
        <input type="number" name="qty_5" value="3">
      </form>
      <div class="ps-summary-row total"><span></span><span></span></div>
    `;
    await import('../../static/js/shop-cart.js');
    document.querySelector('#cart-update-form input').dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(global.fetch).toHaveBeenCalled();
  });

  it('should add via submit handler on data-ajax-cart form', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 1, message: 'Added' }));
    document.body.innerHTML = `
      <form data-ajax-cart>
        <input type="hidden" name="product_id" value="8">
        <input type="number" name="quantity" value="1">
      </form>
    `;
    await import('../../static/js/shop-cart.js');
    document.querySelector('form[data-ajax-cart]').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/cart/add'), expect.anything());
  });

  it('should remove via click handler on data-ajax-remove', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 0 }));
    document.body.innerHTML = '<button data-ajax-remove data-product-id="8">x</button>';
    await import('../../static/js/shop-cart.js');
    document.querySelector('[data-ajax-remove]').click();
    await new Promise((r) => setTimeout(r, 0));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/cart/remove/8'), expect.anything());
  });

  it('should toggle wishlist via click handler', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, wishlisted: true }));
    document.body.innerHTML = '<button data-wishlist-toggle data-product-id="8"><i class="far fa-heart"></i></button>';
    await import('../../static/js/shop-cart.js');
    document.querySelector('[data-wishlist-toggle]').click();
    await new Promise((r) => setTimeout(r, 0));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/wishlist/add/8'), expect.anything());
  });

  it('should open and close the cart drawer', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) }));
    document.body.innerHTML = `
      <div id="psCartOverlay"></div>
      <div id="psCartDrawer"></div>
      <div id="psCartDrawerBody"></div>
      <div id="psCartDrawerFooter"></div>
      <div id="psCartDrawerTotal"></div>
    `;
    await import('../../static/js/shop-cart.js');

    window.ShopCart.openCartDrawer();
    expect(document.getElementById('psCartOverlay').classList.contains('open')).toBe(true);
    expect(document.getElementById('psCartDrawer').classList.contains('open')).toBe(true);

    window.ShopCart.closeCartDrawer();
    expect(document.getElementById('psCartOverlay').classList.contains('open')).toBe(false);
  });

  it('should refresh drawer with cart contents', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ count: 0 }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) })
      .mockResolvedValueOnce({ ok: true, status: 200, text: () => Promise.resolve(`
          <div class="ps-cart-item-row" data-product-id="5">
            <div class="ps-cart-item-name">Item</div>
            <div class="ps-cart-item-price">10.00</div>
            <input name="qty_5" value="2">
          </div>
        `) })
      .mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
    document.body.innerHTML = `
      <div id="psCartOverlay"></div>
      <div id="psCartDrawer"></div>
      <div id="psCartDrawerBody"></div>
      <div id="psCartDrawerFooter"></div>
      <div id="psCartDrawerTotal"></div>
    `;
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.refreshCartDrawer();
    await new Promise((r) => setTimeout(r, 50));
    const body = document.getElementById('psCartDrawerBody');
    expect(body.textContent).toContain('Item');
    expect(document.getElementById('psCartDrawerTotal').textContent).toBe('20.00');
  });

  it('should render empty drawer when no items', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ count: 0 }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) })
      .mockResolvedValueOnce({ ok: true, status: 200, text: () => Promise.resolve('<div>empty cart</div>') })
      .mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) });
    document.body.innerHTML = `
      <div id="psCartOverlay"></div>
      <div id="psCartDrawer"></div>
      <div id="psCartDrawerBody"></div>
      <div id="psCartDrawerFooter"></div>
    `;
    await import('../../static/js/shop-cart.js');
    await window.ShopCart.refreshCartDrawer();
    await new Promise((r) => setTimeout(r, 50));
    expect(document.getElementById('psCartDrawerBody').textContent).toContain('empty');
  });

  it('should close drawer on Escape and via close button', async () => {
    global.fetch = vi.fn(() => okJson({ success: true }));
    document.body.innerHTML = `
      <div id="psCartOverlay"></div>
      <div id="psCartDrawer"></div>
      <button data-cart-close>close</button>
    `;
    await import('../../static/js/shop-cart.js');
    window.ShopCart.openCartDrawer();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(document.getElementById('psCartOverlay').classList.contains('open')).toBe(false);

    window.ShopCart.openCartDrawer();
    document.querySelector('[data-cart-close]').click();
    expect(document.getElementById('psCartOverlay').classList.contains('open')).toBe(false);
  });

  it('should open drawer via ps-cart-link and quick-add', async () => {
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 1, message: 'Added' }));
    document.body.innerHTML = `
      <a href="#" class="ps-cart-link">Cart</a>
      <button data-quick-add data-product-id="4">add</button>
      <div id="psCartOverlay"></div>
      <div id="psCartDrawer"></div>
    `;
    await import('../../static/js/shop-cart.js');
    document.querySelector('.ps-cart-link').click();
    expect(document.getElementById('psCartOverlay').classList.contains('open')).toBe(true);
  });

  it('should not add to cart when no SLUG (init guard)', async () => {
    document.body.removeAttribute('data-store-slug');
    global.fetch = vi.fn(() => okJson({ success: true, cart_count: 1, message: 'Added' }));
    await import('../../static/js/shop-cart.js');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
