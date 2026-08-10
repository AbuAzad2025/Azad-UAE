import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

async function importTheme() {
  await import('../../static/js/ui-theme.js');
}

describe('ui-theme.js', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('dir');
    document.documentElement.removeAttribute('data-ui-mode');
    document.documentElement.removeAttribute('data-ui-variant');
    document.body.innerHTML = '';
    vi.resetModules();
  });

  afterEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
    delete window.toggleSidebarDirection;
    vi.resetModules();
  });

  it('boots with light mode and palestinian variant by default', async () => {
    await importTheme();
    expect(document.documentElement.dataset.uiMode).toBe('light');
    expect(document.documentElement.dataset.uiVariant).toBe('palestinian');
    expect(localStorage.getItem('ui_mode')).toBe('light');
    expect(localStorage.getItem('ui_variant')).toBe('palestinian');
  });

  it('boots with stored dark mode and gulf variant', async () => {
    localStorage.setItem('ui_mode', 'dark');
    localStorage.setItem('ui_variant', 'gulf');
    await importTheme();
    expect(document.documentElement.dataset.uiMode).toBe('dark');
    expect(document.documentElement.dataset.uiVariant).toBe('gulf');
  });

  it('ignores invalid stored values', async () => {
    localStorage.setItem('ui_mode', 'neon');
    localStorage.setItem('ui_variant', 'sunset');
    await importTheme();
    expect(document.documentElement.dataset.uiMode).toBe('light');
    expect(document.documentElement.dataset.uiVariant).toBe('palestinian');
  });

  it('toggle-mode click flips dark to light', async () => {
    document.body.innerHTML =
      '<button data-ui-action="toggle-mode"><span data-ui-role="mode-label"></span><i data-ui-role="mode-icon"></i></button>';
    await importTheme();
    const toggle = document.querySelector('[data-ui-action="toggle-mode"]');
    toggle.click();
    expect(document.documentElement.dataset.uiMode).toBe('dark');
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    expect(toggle.getAttribute('data-ui-mode')).toBe('dark');
    expect(toggle.querySelector('[data-ui-role="mode-label"]').textContent).toBe('داكن');
    toggle.click();
    expect(document.documentElement.dataset.uiMode).toBe('light');
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
  });

  it('set-variant button applies variant and active class', async () => {
    document.body.innerHTML =
      '<div class="erp-theme-switcher">' +
      '<button class="erp-theme-option" data-ui-action="set-variant" data-value="gulf"></button>' +
      '<button class="erp-theme-option active" data-ui-action="set-variant" data-value="palestinian"></button>' +
      '</div>';
    await importTheme();
    const gulf = document.querySelector('[data-value="gulf"]');
    gulf.click();
    expect(document.documentElement.dataset.uiVariant).toBe('gulf');
    expect(gulf.classList.contains('active')).toBe(true);
    const palestinian = document.querySelector('[data-value="palestinian"]');
    expect(palestinian.classList.contains('active')).toBe(false);
  });

  it('applySidebarSide positions sidebar and margins based on dir', async () => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.body.innerHTML =
      '<div class="main-sidebar"></div>' +
      '<div class="content-wrapper"></div>' +
      '<div class="main-header"></div>' +
      '<div class="main-footer"></div>';
    await importTheme();
    const sidebar = document.querySelector('.main-sidebar');
    expect(sidebar.style.right).toBe('0px');
    expect(sidebar.style.left).toBe('auto');
    const content = document.querySelector('.content-wrapper');
    expect(content.style.getPropertyValue('margin-right')).toBe('250px');
    expect(document.body.dataset.sidebarSide).toBe('right');
  });

  it('toggleSidebarDirection flips between left and right', async () => {
    document.documentElement.setAttribute('dir', 'ltr');
    document.body.innerHTML = '<div class="main-sidebar"></div><div class="content-wrapper"></div>';
    await importTheme();
    window.toggleSidebarDirection();
    const sidebar = document.querySelector('.main-sidebar');
    expect(sidebar.style.left).toBe('auto');
    expect(document.body.dataset.sidebarSide).toBe('right');
    window.toggleSidebarDirection();
    expect(sidebar.style.left).toBe('0px');
    expect(document.body.dataset.sidebarSide).toBe('left');
  });

  it('collapsed sidebar uses narrow width', async () => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.body.classList.add('sidebar-mini', 'sidebar-collapse');
    document.body.innerHTML = '<div class="content-wrapper"></div>';
    await importTheme();
    const content = document.querySelector('.content-wrapper');
    expect(content.style.getPropertyValue('margin-right')).toBe('4.6rem');
  });

  it('falls back to light mode when matchMedia throws', async () => {
    window.matchMedia = () => {
      throw new Error('no media query');
    };
    try {
      await importTheme();
      expect(document.documentElement.dataset.uiMode).toBe('light');
    } finally {
      delete window.matchMedia;
    }
  });

  it('uses default sidebar side when stored dir differs from current', async () => {
    localStorage.setItem('sidebarLayout', 'left');
    localStorage.setItem('sidebarLayoutDir', 'ltr');
    document.documentElement.setAttribute('dir', 'rtl');
    document.body.innerHTML = '<div class="main-sidebar"></div><div class="content-wrapper"></div>';
    await importTheme();
    expect(document.body.dataset.sidebarSide).toBe('right');
  });

  it('removes flash messages without jQuery alert', async () => {
    vi.useFakeTimers();
    global.requestAnimationFrame = (cb) => cb();
    try {
      document.body.innerHTML = '<div class="flash-message"><div class="flash-timer"></div></div>';
      await importTheme();
      const flash = document.querySelector('.flash-message');
      const bar = flash.querySelector('.flash-timer');
      expect(bar.style.width).toBe('0%');
      vi.advanceTimersByTime(21000);
      expect(document.querySelector('.flash-message')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('closes flash messages via jQuery alert when available', async () => {
    const alertClose = vi.fn();
    const jq = vi.fn(() => ({ alert: alertClose }));
    jq.fn = { alert: vi.fn() };
    global.$ = global.jQuery = jq;
    vi.useFakeTimers();
    global.requestAnimationFrame = (cb) => cb();
    try {
      document.body.innerHTML = '<div class="flash-message"></div>';
      await importTheme();
      vi.advanceTimersByTime(21000);
      expect(alertClose).toHaveBeenCalledWith('close');
    } finally {
      vi.useRealTimers();
      delete global.$;
      delete global.jQuery;
    }
  });
});
