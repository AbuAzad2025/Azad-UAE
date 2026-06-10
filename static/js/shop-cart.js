(function () {
  'use strict';

  var CSRF_TOKEN = '';
  var SLUG = '';

  function showToast(message, type) {
    var colors = { success: '#007A3D', danger: '#CE1126', warning: '#D4AF37' };
    var bg = colors[type] || '#333';
    var toast = document.createElement('div');
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
    var badges = document.querySelectorAll('.ps-cart-badge');
    badges.forEach(function (el) {
      if (count > 0) {
        el.textContent = count;
        el.style.display = 'inline';
      } else {
        el.style.display = 'none';
      }
    });
    var counts = document.querySelectorAll('.ps-cart-count');
    counts.forEach(function (el) { el.textContent = count; });
  }

  function refreshCartBadge() {
    apiGet('/cart/count').then(function (data) {
      updateCartBadge(data.count || 0);
    });
  }

  function setupAddToCartButtons() {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form.hasAttribute('data-ajax-cart')) return;
      e.preventDefault();
      var productId = form.querySelector('[name="product_id"]');
      var qty = form.querySelector('[name="quantity"]');
      if (productId) addToCart(parseInt(productId.value), parseFloat((qty && qty.value) || 1));
    });
  }

  function setupRemoveButtons() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-ajax-remove]');
      if (!btn) return;
      e.preventDefault();
      var productId = btn.getAttribute('data-product-id');
      if (productId) removeFromCart(parseInt(productId));
    });
  }

  function wishlistToggle(productId) {
    var btn = document.querySelector('[data-wishlist-toggle][data-product-id="' + productId + '"]');
    var isOn = btn && btn.querySelector('.fas.fa-heart');
    var path = isOn ? '/wishlist/remove/' + productId : '/wishlist/add/' + productId;
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
      var btn = e.target.closest('[data-wishlist-toggle]');
      if (!btn) return;
      e.preventDefault();
      var productId = btn.getAttribute('data-product-id');
      if (productId) wishlistToggle(parseInt(productId));
    });
  }

  function setupAutoUpdateCart() {
    var form = document.getElementById('cart-update-form');
    if (!form) return;
    form.addEventListener('change', function (e) {
      if (e.target.name && e.target.name.indexOf('qty_') === 0) {
        var data = {};
        var fData = new FormData(form);
        fData.forEach(function (v, k) { data[k] = v; });
        updateCart(data).then(function (res) {
          if (res.success && res.totals) {
            var totalEl = document.querySelector('.ps-summary-row.total span:last-child');
            if (totalEl && res.totals.subtotal) {
              totalEl.textContent = parseFloat(res.totals.subtotal).toFixed(2) + ' ' + (res.totals.currency || 'AED');
            }
          }
        });
      }
    });
  }

  function init() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) CSRF_TOKEN = meta.getAttribute('content');
    var body = document.body;
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
    updateCartBadge: updateCartBadge
  };
})();
