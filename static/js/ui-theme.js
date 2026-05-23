(function() {
  function normalizeMode(v) {
    return v === 'dark' ? 'dark' : 'light';
  }

  function normalizeVariant(v) {
    return v === 'gulf' ? 'gulf' : 'palestinian';
  }

  function getInitialMode() {
    const stored = localStorage.getItem('ui_mode');
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
    const stored = localStorage.getItem('ui_variant');
    if (stored) {
      return normalizeVariant(stored);
    }
    return 'palestinian';
  }

  function applyTheme(mode, variant) {
    const el = document.documentElement;
    el.dataset.uiMode = mode;
    el.dataset.uiVariant = variant;
    localStorage.setItem('ui_mode', mode);
    localStorage.setItem('ui_variant', variant);

    const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
    if (toggle) {
      toggle.setAttribute('data-ui-mode', mode);
      toggle.setAttribute('aria-pressed', mode === 'dark' ? 'true' : 'false');
      const label = toggle.querySelector('[data-ui-role="mode-label"]');
      if (label) {
        label.textContent = mode === 'dark' ? 'داكن' : 'فاتح';
      }
      const icon = toggle.querySelector('[data-ui-role="mode-icon"]');
      if (icon) {
        icon.className = mode === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
      }
    }

    const variantSelect = document.querySelector('[data-ui-action="set-variant"]');
    if (variantSelect && variantSelect.value !== variant) {
      variantSelect.value = variant;
    }
  }

  function boot() {
    const initialMode = getInitialMode();
    const initialVariant = getInitialVariant();
    applyTheme(initialMode, initialVariant);

    const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
    if (toggle) {
      toggle.addEventListener('click', function(ev) {
        ev.preventDefault();
        const current = normalizeMode(document.documentElement.dataset.uiMode || 'light');
        const next = current === 'dark' ? 'light' : 'dark';
        const variant = normalizeVariant(document.documentElement.dataset.uiVariant || 'palestinian');
        applyTheme(next, variant);
      });
    }

    const variantSelect = document.querySelector('[data-ui-action="set-variant"]');
    if (variantSelect) {
      variantSelect.addEventListener('change', function() {
        const variant = normalizeVariant(this.value);
        const mode = normalizeMode(document.documentElement.dataset.uiMode || 'light');
        applyTheme(mode, variant);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

