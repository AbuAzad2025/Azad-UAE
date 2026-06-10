(function () {
  'use strict';
  var modal = document.getElementById('ps-quick-view-modal');
  var body = document.getElementById('ps-quick-view-body');
  if (!modal || !body) return;
  var slug = document.body.getAttribute('data-store-slug');
  var closeBtn = modal.querySelector('[data-modal-close]');
  var overlay = modal.querySelector('.ps-modal-overlay');
  function openModal(productId) {
    body.innerHTML = '<div class="ps-modal-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    fetch('/s/' + slug + '/quick-view/' + productId, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        body.innerHTML = html;
        var minusBtns = body.querySelectorAll('[data-qty-minus]');
        var plusBtns = body.querySelectorAll('[data-qty-plus]');
        minusBtns.forEach(function (btn) {
          btn.addEventListener('click', function () {
            var input = btn.closest('.ps-qty-wrap')?.querySelector('input[type="number"]');
            if (!input) return;
            var val = parseFloat(input.value || '1');
            var min = parseFloat(input.min || '1');
            input.value = Math.max(min, val - 1);
          });
        });
        plusBtns.forEach(function (btn) {
          btn.addEventListener('click', function () {
            var input = btn.closest('.ps-qty-wrap')?.querySelector('input[type="number"]');
            if (!input) return;
            var val = parseFloat(input.value || '1');
            var max = parseFloat(input.max || '9999');
            input.value = Math.min(max, val + 1);
          });
        });
        var forms = body.querySelectorAll('[data-ajax-cart]');
        forms.forEach(function (f) {
          f.addEventListener('submit', function (e) {
            e.preventDefault();
            var pid = f.querySelector('[name="product_id"]')?.value;
            var qty = f.querySelector('[name="quantity"]')?.value || 1;
            if (window.ShopCart && window.ShopCart.addToCart) {
              window.ShopCart.addToCart(parseInt(pid), parseFloat(qty));
            }
          });
        });
      });
  }
  function closeModal() {
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (overlay) overlay.addEventListener('click', closeModal);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal();
  });
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-quick-view]');
    if (!btn) return;
    e.preventDefault();
    var pid = btn.getAttribute('data-product-id');
    if (pid) openModal(parseInt(pid));
  });
  window.ShopQuickView = { open: openModal, close: closeModal };
})();
