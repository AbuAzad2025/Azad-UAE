(function () {
  'use strict';

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-qty-minus], [data-qty-plus]');
    if (!btn) return;
    var input = btn.closest('.ps-qty-wrap')?.querySelector('input[type="number"]');
    if (!input) return;
    var step = parseFloat(input.step || '1') || 1;
    var min = parseFloat(input.min || '1') || 1;
    var max = parseFloat(input.max || '9999') || 9999;
    var val = parseFloat(input.value || min) || min;
    if (btn.hasAttribute('data-qty-minus')) val = Math.max(min, val - step);
    else val = Math.min(max, val + step);
    input.value = val;
    var evt = new Event('change', { bubbles: true });
    input.dispatchEvent(evt);
  });

  var navToggle = document.querySelector('.ps-nav-toggle');
  var nav = document.querySelector('.ps-nav');
  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var isOpen = nav.classList.contains('is-open');
      if (isOpen) {
        nav.style.height = nav.scrollHeight + 'px';
        requestAnimationFrame(function () {
          nav.classList.remove('is-open');
          nav.style.height = '0';
        });
      } else {
        nav.classList.add('is-open');
        nav.style.height = nav.scrollHeight + 'px';
        nav.addEventListener('transitionend', function handler() {
          nav.style.height = '';
          nav.removeEventListener('transitionend', handler);
        });
      }
      navToggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
    });
  }

  var alerts = document.querySelectorAll('.ps-alert[data-auto-dismiss]');
  alerts.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity 0.4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 5000);
  });

  var searchInput = document.querySelector('.ps-search-form input[type="search"]');
  if (searchInput) {
    var searchForm = searchInput.closest('form');
    var searchTimer;
    searchInput.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        if (searchForm) searchForm.submit();
      }, 300);
    });
  }

  var cartUpdateForm = document.getElementById('cart-update-form');
  if (cartUpdateForm) {
    cartUpdateForm.querySelectorAll('input[type="number"]').forEach(function (input) {
      input.addEventListener('change', function () {
        var data = {};
        var formData = new FormData(cartUpdateForm);
        formData.forEach(function (value, key) {
          data[key] = value;
        });
        if (window.ShopCart && window.ShopCart.updateCart) {
          window.ShopCart.updateCart(data);
        }
      });
    });
  }
})();
