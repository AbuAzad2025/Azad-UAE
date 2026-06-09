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
    var html = document.documentElement;
    if (!body) return;
    var normalized = normalizeSidebarSide(side) || getDefaultSidebarSide();
    body.dataset.sidebarSide = normalized;
    localStorage.setItem(STORAGE_SIDEBAR, normalized);
    localStorage.setItem(STORAGE_SIDEBAR_DIR, html.getAttribute('dir') || 'rtl');

    // Force inline styles so the switch actually moves elements regardless of CSS specificity
    var sidebar = document.querySelector('.main-sidebar');
    var content = document.querySelector('.content-wrapper');
    var header = document.querySelector('.main-header');
    var footer = document.querySelector('.main-footer');
    if (sidebar) {
      if (normalized === 'right') {
        sidebar.style.left = 'auto';
        sidebar.style.right = '0';
      } else {
        sidebar.style.left = '0';
        sidebar.style.right = 'auto';
      }
    }
    var marginProp = normalized === 'right' ? 'margin-right' : 'margin-left';
    var otherProp = normalized === 'right' ? 'margin-left' : 'margin-right';
    var width = body.classList.contains('sidebar-mini') && body.classList.contains('sidebar-collapse') ? '4.6rem' : '250px';
    [content, header, footer].forEach(function(el) {
      if (!el) return;
      el.style.setProperty(marginProp, width, 'important');
      el.style.setProperty(otherProp, '0px', 'important');
    });
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

  function updateThemeSwitcher(variant) {
    var buttons = document.querySelectorAll('.erp-theme-switcher .erp-theme-option');
    buttons.forEach(function(btn) {
      var btnVariant = btn.getAttribute('data-value');
      if (btnVariant === variant) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
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
    updateThemeSwitcher(variant);
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

    var variantButtons = document.querySelectorAll('.erp-theme-switcher .erp-theme-option[data-ui-action="set-variant"]');
    variantButtons.forEach(function(btn) {
      btn.addEventListener('click', function(ev) {
        ev.preventDefault();
        var variant = normalizeVariant(btn.getAttribute('data-value'));
        var mode = normalizeMode(document.documentElement.dataset.uiMode || 'light');
        applyTheme(mode, variant);
      });
    });

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
