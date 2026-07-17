(function () {
  'use strict';

  let CSRF_TOKEN = '';
  let SLUG = '';

  function showToast(message, type) {
    const colors = { success: '#007A3D', danger: '#CE1126', warning: '#D4AF37' };
    const bg = colors[type] || '#333';
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;background:' + bg + ';color:#fff;padding:12px 20px;border-radius:12px;font-weight:600;font-size:0.9rem;box-shadow:0 8px 32px rgba(0,0,0,0.2);opacity:0;transform:translateY(16px);transition:opacity 0.3s,transform 0.3s;max-width:360px;direction:ltr';
    document.body.appendChild(toast);
    requestAnimationFrame(function () {
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';
    });
    setTimeout(function () {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(16px)';
      setTimeout(function () { toast.remove(); }, 300);
    }, 4000);
  }

  function apiPost(path, data) {
    return fetch('/s/' + SLUG + path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': CSRF_TOKEN
      },
      body: JSON.stringify(data)
    }).then(function (r) { return r.json(); });
  }

  function apiGet(path) {
    return fetch('/s/' + SLUG + path, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (r) { return r.json(); });
  }

  function addToCart(productId, quantity) {
    quantity = quantity || 1;
    return apiPost('/cart/add', { product_id: productId, quantity: quantity })
      .then(function (data) {
        if (data.success) {
          updateCartBadge(data.cart_count);
          showToast(data.message || 'Added to cart', 'success');
        } else {
          showToast(data.message || 'Error adding to cart', 'danger');
        }
        return data;
      });
  }

  function removeFromCart(productId) {
    return apiPost('/cart/remove/' + productId, {})
      .then(function (data) {
        if (data.success) {
          updateCartBadge(data.cart_count);
          showToast('Removed from cart', 'success');
        } else {
          showToast('Error removing item', 'danger');
        }
        return data;
      });
  }

  function updateCart(updates) {
    return apiPost('/cart/update', updates)
      .then(function (data) {
        if (data.success) {
          updateCartBadge(data.cart_count);
        }
        return data;
      });
  }

  function updateCartBadge(count) {
    const badges = document.querySelectorAll('.ps-cart-badge');
    badges.forEach(function (el) {
      if (count > 0) {
        el.textContent = count;
        el.style.display = 'inline';
      } else {
        el.style.display = 'none';
      }
    });
    const counts = document.querySelectorAll('.ps-cart-count');
    counts.forEach(function (el) { el.textContent = count; });
  }

  function refreshCartBadge() {
    apiGet('/cart/count').then(function (data) {
      updateCartBadge(data.count || 0);
    });
  }

  function setupAddToCartButtons() {
    document.addEventListener('submit', function (e) {
      const form = e.target;
      if (!form.hasAttribute('data-ajax-cart')) return;
      e.preventDefault();
      const productId = form.querySelector('[name="product_id"]');
      const qty = form.querySelector('[name="quantity"]');
      if (productId) addToCart(parseInt(productId.value), parseFloat((qty && qty.value) || 1));
    });
  }

  function setupRemoveButtons() {
    document.addEventListener('click', function (e) {
      const btn = e.target.closest('[data-ajax-remove]');
      if (!btn) return;
      e.preventDefault();
      const productId = btn.getAttribute('data-product-id');
      if (productId) removeFromCart(parseInt(productId));
    });
  }

  function wishlistToggle(productId) {
    const btn = document.querySelector('[data-wishlist-toggle][data-product-id="' + productId + '"]');
    const isOn = btn && btn.querySelector('.fas.fa-heart');
    const path = isOn ? '/wishlist/remove/' + productId : '/wishlist/add/' + productId;
    return apiPost(path, { product_id: productId }).then(function (data) {
      if (data.success) {
        if (data.wishlisted) {
          if (btn) btn.innerHTML = '<i class="fas fa-heart"></i>';
          showToast('Added to wishlist', 'success');
        } else {
          if (btn) btn.innerHTML = '<i class="far fa-heart"></i>';
          showToast('Removed from wishlist', 'success');
        }
      }
      return data;
    });
  }

  function setupWishlistToggle() {
    document.addEventListener('click', function (e) {
      const btn = e.target.closest('[data-wishlist-toggle]');
      if (!btn) return;
      e.preventDefault();
      const productId = btn.getAttribute('data-product-id');
      if (productId) wishlistToggle(parseInt(productId));
    });
  }

  function setupAutoUpdateCart() {
    const form = document.getElementById('cart-update-form');
    if (!form) return;
    form.addEventListener('change', function (e) {
      if (e.target.name && e.target.name.indexOf('qty_') === 0) {
        const data = {};
        const fData = new FormData(form);
        fData.forEach(function (v, k) { data[k] = v; });
        updateCart(data).then(function (res) {
          if (res.success && res.totals) {
            const totalEl = document.querySelector('.ps-summary-row.total span:last-child');
            if (totalEl && res.totals.subtotal) {
              totalEl.textContent = parseFloat(res.totals.subtotal).toFixed(2) + ' ' + (res.totals.currency || window._CURRENCY_SYMBOL || 'AED');
            }
          }
        });
      }
    });
  }

  function init() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) CSRF_TOKEN = meta.getAttribute('content');
    const body = document.body;
    SLUG = body.getAttribute('data-store-slug') || '';
    if (!SLUG) return;
    setupAddToCartButtons();
    setupRemoveButtons();
    setupWishlistToggle();
    setupAutoUpdateCart();
    refreshCartBadge();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.ShopCart = {
    addToCart: addToCart,
    removeFromCart: removeFromCart,
    wishlistToggle: wishlistToggle,
    updateCart: updateCart,
    refreshCartBadge: refreshCartBadge,
    showToast: showToast,
    updateCartBadge: updateCartBadge,
    openCartDrawer: openCartDrawer,
    closeCartDrawer: closeCartDrawer,
    refreshCartDrawer: refreshCartDrawer
  };

  // ── Cart Drawer ──
  function openCartDrawer() {
    const overlay = document.getElementById('psCartOverlay');
    const drawer = document.getElementById('psCartDrawer');
    if (!overlay || !drawer) return;
    overlay.classList.add('open');
    drawer.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    drawer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    refreshCartDrawer();
  }

  function closeCartDrawer() {
    const overlay = document.getElementById('psCartOverlay');
    const drawer = document.getElementById('psCartDrawer');
    if (!overlay || !drawer) return;
    overlay.classList.remove('open');
    drawer.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function refreshCartDrawer() {
    const body = document.getElementById('psCartDrawerBody');
    const footer = document.getElementById('psCartDrawerFooter');
    const totalEl = document.getElementById('psCartDrawerTotal');
    if (!body) return;

    body.innerHTML = '<div class="ps-cart-drawer-loading"><i class="fas fa-spinner fa-spin"></i></div>';
    if (footer) footer.style.display = 'none';

    apiGet('/cart').then(function () {
      // Fallback: fetch cart page HTML and extract items OR use /cart/count + separate fetch
      // The cart/count endpoint returns count only; we need the cart contents.
      // Fetch the cart page HTML and parse items from it.
      return fetch('/s/' + SLUG + '/cart', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, 'text/html');
          const rows = doc.querySelectorAll('.ps-cart-item-row, tr[data-product-id]');
          const items = [];
          rows.forEach(function (row) {
            const pid = row.getAttribute('data-product-id') || row.getAttribute('data-product-id');
            const name = row.querySelector('.ps-cart-item-name, td:nth-child(2)') || row.querySelector('a');
            const price = row.querySelector('.ps-cart-item-price, td:nth-child(4)');
            const qtyInput = row.querySelector('input[name^="qty_"]');
            items.push({ el: row, pid: pid, name: name ? name.textContent.trim() : '', price: price ? price.textContent.trim() : '', qty: qtyInput ? qtyInput.value : 1 });
          });
          renderCartDrawerItems(items, doc);
        })
        .catch(function () {
          body.innerHTML = '<div class="ps-cart-drawer-empty"><i class="fas fa-shopping-basket"></i><p>Unable to load cart</p></div>';
        });
    });
  }

  function renderCartDrawerItems(items, doc) {
    const body = document.getElementById('psCartDrawerBody');
    const footer = document.getElementById('psCartDrawerFooter');
    const totalEl = document.getElementById('psCartDrawerTotal');
    if (!body) return;

    if (!items || items.length === 0) {
      body.innerHTML = '<div class="ps-cart-drawer-empty"><i class="fas fa-shopping-basket"></i><p>' + (window._EMPTY_CART_TEXT || 'Cart is empty') + '</p></div>';
      if (footer) footer.style.display = 'none';
      return;
    }

    let html = '';
    let total = 0;
    items.forEach(function (item) {
      const priceNum = parseFloat(item.price.replace(/[^0-9.]/g, '')) || 0;
      const qty = parseFloat(item.qty) || 1;
      total += priceNum * qty;
      html += '<div class="ps-cart-item" data-product-id="' + item.pid + '">'
        + '<button class="ps-cart-item-remove" data-cart-remove="' + item.pid + '"><i class="fas fa-times"></i></button>'
        + '<div class="ps-cart-item-info">'
        + '<div class="ps-cart-item-name">' + item.name + '</div>'
        + '<div class="ps-cart-item-price">' + item.price + '</div>'
        + '<div class="ps-cart-item-qty">'
        + '<button data-cart-dec="' + item.pid + '">−</button>'
        + '<span>' + qty + '</span>'
        + '<button data-cart-inc="' + item.pid + '">+</button>'
        + '</div></div></div>';
    });
    body.innerHTML = html;
    if (totalEl) totalEl.textContent = total.toFixed(2);
    if (footer) footer.style.display = 'block';

    // Wire up drawer item buttons
    body.querySelectorAll('[data-cart-remove]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const pid = this.getAttribute('data-cart-remove');
        const itemEl = this.closest('.ps-cart-item');
        if (itemEl) itemEl.classList.add('removing');
        removeFromCart(parseInt(pid)).then(function () { refreshCartDrawer(); });
      });
    });
    body.querySelectorAll('[data-cart-inc]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const pid = parseInt(this.getAttribute('data-cart-inc'));
        const updates = {}; updates['qty_' + pid] = (parseFloat(this.previousElementSibling.textContent) || 1) + 1;
        updateCart(updates).then(function () { refreshCartDrawer(); });
      });
    });
    body.querySelectorAll('[data-cart-dec]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const pid = parseInt(this.getAttribute('data-cart-dec'));
        const qtyEl = this.nextElementSibling;
        const newQty = (parseFloat(qtyEl.textContent) || 1) - 1;
        const updates = {}; updates['qty_' + pid] = newQty;
        updateCart(updates).then(function () { refreshCartDrawer(); });
      });
    });
  }

  // Hook into addToCart to open drawer
  const _origAddToCart = addToCart;
  addToCart = function (productId, quantity) {
    return _origAddToCart(productId, quantity).then(function (data) {
      if (data.success) openCartDrawer();
      return data;
    });
  };
  // Re-export overridden function
  window.ShopCart.addToCart = addToCart;

  // Wire up drawer open/close buttons
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-cart-close]')) { e.preventDefault(); closeCartDrawer(); }
    if (e.target.closest('.ps-cart-link')) { e.preventDefault(); openCartDrawer(); }
    const quickAdd = e.target.closest('[data-quick-add]');
    if (quickAdd) {
      e.preventDefault();
      const pid = parseInt(quickAdd.getAttribute('data-product-id'));
      if (pid) addToCart(pid, 1);
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeCartDrawer();
  });
})();
