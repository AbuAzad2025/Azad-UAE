(function() {
  var STORAGE_MODE = 'ui_mode';
  var STORAGE_VARIANT = 'ui_variant';
  var STORAGE_SIDEBAR = 'sidebarLayout';
  var STORAGE_SIDEBAR_DIR = 'sidebarLayoutDir';

  function normalizeMode(v) {
    return v === 'dark' ? 'dark' : 'light';
  }

  function normalizeVariant(v) {
    return v === 'gulf' ? 'gulf' : 'palestinian';
  }

  function normalizeSidebarSide(v) {
    return v === 'left' ? 'left' : v === 'right' ? 'right' : null;
  }

  function getDefaultSidebarSide() {
    return document.documentElement.getAttribute('dir') === 'rtl' ? 'right' : 'left';
  }

  function getInitialMode() {
    var stored = localStorage.getItem(STORAGE_MODE);
    if (stored) {
      return normalizeMode(stored);
    }
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch (e) {
      return 'light';
    }
  }

  function getInitialVariant() {
    var stored = localStorage.getItem(STORAGE_VARIANT);
    if (stored) {
      return normalizeVariant(stored);
    }
    return 'palestinian';
  }

  function getInitialSidebarSide() {
    var stored = normalizeSidebarSide(localStorage.getItem(STORAGE_SIDEBAR));
    var storedDir = localStorage.getItem(STORAGE_SIDEBAR_DIR);
    var currentDir = document.documentElement.getAttribute('dir') || 'rtl';

    if (!stored) {
      return getDefaultSidebarSide();
    }

    if (storedDir && storedDir !== currentDir) {
      return getDefaultSidebarSide();
    }

    return stored;
  }

  function applySidebarSide(side) {
    var body = document.body;
    if (!body) return;
    var normalized = normalizeSidebarSide(side) || getDefaultSidebarSide();
    body.dataset.sidebarSide = normalized;
    localStorage.setItem(STORAGE_SIDEBAR, normalized);
    localStorage.setItem(STORAGE_SIDEBAR_DIR, document.documentElement.getAttribute('dir') || 'rtl');
  }

  function updateModeToggle(mode) {
    var toggle = document.querySelector('[data-ui-action="toggle-mode"]');
    if (!toggle) return;

    toggle.setAttribute('data-ui-mode', mode);
    toggle.setAttribute('aria-pressed', mode === 'dark' ? 'true' : 'false');

    if (mode === 'dark') {
      toggle.setAttribute('aria-label', 'التبديل إلى الوضع الفاتح');
      toggle.setAttribute('title', 'التبديل إلى الوضع الفاتح');
    } else {
      toggle.setAttribute('aria-label', 'التبديل إلى الوضع الداكن');
      toggle.setAttribute('title', 'التبديل إلى الوضع الداكن');
    }

    var label = toggle.querySelector('[data-ui-role="mode-label"]');
    if (label) {
      label.textContent = mode === 'dark' ? 'داكن' : 'فاتح';
    }

    var icon = toggle.querySelector('[data-ui-role="mode-icon"]');
    if (icon) {
      icon.className = mode === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
    }
  }

  function applyTheme(mode, variant) {
    mode = normalizeMode(mode);
    variant = normalizeVariant(variant);

    var el = document.documentElement;
    el.dataset.uiMode = mode;
    el.dataset.uiVariant = variant;
    localStorage.setItem(STORAGE_MODE, mode);
    localStorage.setItem(STORAGE_VARIANT, variant);

    updateModeToggle(mode);

    var variantSelect = document.querySelector('[data-ui-action="set-variant"]');
    if (variantSelect && variantSelect.value !== variant) {
      variantSelect.value = variant;
    }
  }

  function boot() {
    applyTheme(getInitialMode(), getInitialVariant());
    applySidebarSide(getInitialSidebarSide());

    var toggle = document.querySelector('[data-ui-action="toggle-mode"]');
    if (toggle) {
      toggle.addEventListener('click', function(ev) {
        ev.preventDefault();
        var current = normalizeMode(document.documentElement.dataset.uiMode || 'light');
        var next = current === 'dark' ? 'light' : 'dark';
        var variant = normalizeVariant(document.documentElement.dataset.uiVariant || 'palestinian');
        applyTheme(next, variant);
      });
    }

    var variantSelect = document.querySelector('[data-ui-action="set-variant"]');
    if (variantSelect) {
      variantSelect.addEventListener('change', function() {
        var variant = normalizeVariant(this.value);
        var mode = normalizeMode(document.documentElement.dataset.uiMode || 'light');
        applyTheme(mode, variant);
      });
    }

    window.toggleSidebarDirection = function() {
      var body = document.body;
      if (!body) return;
      var current = body.dataset.sidebarSide === 'left' ? 'left' : 'right';
      var next = current === 'left' ? 'right' : 'left';
      applySidebarSide(next);
    };

    var flashes = document.querySelectorAll('.flash-message');
    flashes.forEach(function(el) {
      var bar = el.querySelector('.flash-timer');
      if (bar) {
        requestAnimationFrame(function() {
          bar.style.width = '0%';
        });
      }
      window.setTimeout(function() {
        try {
          if (window.jQuery && window.jQuery.fn && window.jQuery.fn.alert) {
            window.jQuery(el).alert('close');
          } else {
            el.remove();
          }
        } catch (e) {}
      }, 20000);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
