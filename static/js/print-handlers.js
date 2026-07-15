(function() {
  document.addEventListener('click', function(e) {
    let btn = e.target.closest('[data-action="window-print"]');
    if (btn) { e.preventDefault(); window.print(); }
    let closeBtn = e.target.closest('[data-action="window-close"]');
    if (closeBtn) { e.preventDefault(); window.close(); }
  });
  if (new URLSearchParams(window.location.search).get('auto_print') === 'true') {
    window.addEventListener('DOMContentLoaded', function() {
      setTimeout(function() { window.print(); }, 300);
    });
  }
})();
