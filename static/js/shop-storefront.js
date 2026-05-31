(function () {
  'use strict';

  document.querySelectorAll('[data-qty-minus], [data-qty-plus]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = btn.closest('.ps-qty-wrap')?.querySelector('input[type="number"]');
      if (!input) return;
      var step = parseFloat(input.step || '1') || 1;
      var min = parseFloat(input.min || '1') || 1;
      var max = parseFloat(input.max || '9999') || 9999;
      var val = parseFloat(input.value || min) || min;
      if (btn.hasAttribute('data-qty-minus')) val = Math.max(min, val - step);
      else val = Math.min(max, val + step);
      input.value = val;
    });
  });

  var alerts = document.querySelectorAll('.ps-alert[data-auto-dismiss]');
  alerts.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity 0.4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 5000);
  });
})();
