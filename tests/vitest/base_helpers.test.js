import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('base-helpers.js (azad object)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.azad;
    delete window.AzadHelpers;
    document.body.innerHTML = '';
  });

  async function loadModule() {
    await import('../../static/js/base-helpers.js');
    expect(window.azad).toBeDefined();
    return window.AzadHelpers;
  }

  it('exposes azad global with expected methods', async () => {
    const helpers = await loadModule();
    expect(helpers.azad).toBeDefined();
    expect(typeof helpers.azad.showLoading).toBe('function');
    expect(typeof helpers.azad.hideLoading).toBe('function');
    expect(typeof helpers.azad.formatNumber).toBe('function');
    expect(typeof helpers.azad.showError).toBe('function');
    expect(typeof helpers.azad.showSuccess).toBe('function');
    expect(typeof helpers.azad.showWarning).toBe('function');
    expect(typeof helpers.azad.showInfo).toBe('function');
  });

  it('formatNumber formats with 2 decimal places', async () => {
    const helpers = await loadModule();
    expect(helpers.azad.formatNumber(1234.5)).toBe('1,234.50');
    expect(helpers.azad.formatNumber('99.9')).toBe('99.90');
    expect(helpers.azad.formatNumber(0)).toBe('0.00');
    expect(helpers.azad.formatNumber(-100)).toBe('-100.00');
    expect(helpers.azad.formatNumber('invalid')).toBe('0.00');
  });

  it('showLoading/hideLoading toggle overlay', async () => {
    vi.useFakeTimers();
    try {
      await loadModule();
      window.azad.showLoading();
      const overlay = document.getElementById('azadLoadingOverlay');
      expect(overlay).toBeTruthy();
      expect(overlay.style.display).toBe('flex');

      window.azad.hideLoading();
      expect(overlay.style.opacity).toBe('0');
      vi.advanceTimersByTime(301);
      expect(overlay.style.display).toBe('none');
    } finally {
      vi.useRealTimers();
    }
  });

  it('showLoading increments counter, hideLoading decrements', async () => {
    vi.useFakeTimers();
    try {
      await loadModule();
      window.azad.showLoading();
      window.azad.showLoading();
      window.azad.hideLoading();
      const overlay = document.getElementById('azadLoadingOverlay');
      expect(overlay.style.display).toBe('flex');
      window.azad.hideLoading();
      expect(overlay.style.opacity).toBe('0');
      vi.advanceTimersByTime(301);
      expect(overlay.style.display).toBe('none');
    } finally {
      vi.useRealTimers();
    }
  });

  it('toast methods create toast elements', async () => {
    await loadModule();
    window.azad.showSuccess('Operation succeeded');
    window.azad.showError('Operation failed');
    const texts = [...document.body.querySelectorAll('div')].map((el) => el.textContent);
    expect(texts).toContain('Operation succeeded');
    expect(texts).toContain('Operation failed');
  });

  it('safeEval evaluates arithmetic and rejects unsafe input', async () => {
    const helpers = await loadModule();
    expect(helpers.safeEval('2+3')).toBe('5');
    expect(helpers.safeEval('10/4')).toBe('2.5');
    expect(helpers.safeEval('foo();')).toBe('ERR');
  });

  it('formatFxRate formats with adaptive precision', async () => {
    const helpers = await loadModule();
    expect(helpers.formatFxRate(null)).toBe('--');
    expect(helpers.formatFxRate(100)).toBe('100.00');
    expect(helpers.formatFxRate(3.672)).toBe('3.672');
    expect(helpers.formatFxRate(0.1234)).toBe('0.1234');
  });

  it('getFallbackFx returns static fallback rates', async () => {
    const helpers = await loadModule();
    const fallback = helpers.getFallbackFx();
    expect(fallback.ok).toBe(false);
    expect(fallback.source).toBe('fallback_static');
    expect(fallback.rates.AED).toBe(3.67);
    expect(fallback.rates.USD).toBe(1.0);
  });

  it('populateFxDisplay renders rates into tbody', async () => {
    const helpers = await loadModule();
    // Create DOM elements manually to avoid innerHTML clearing issues
    const tbody = document.createElement('tbody');
    tbody.id = 'fx-rates-body';
    document.body.appendChild(tbody);
    helpers.populateFxDisplay({
      ok: true,
      base: 'USD',
      rates: { AED: 3.67, EUR: 0.92 },
      source: 'api',
      stale: false,
      last_updated: '2026-01-01T12:00:00Z',
    });
    expect(tbody.innerHTML).toContain('3.67');
  });

  it('updateDateTime updates time and date displays', async () => {
    document.body.innerHTML = '<span id="time-display"></span><span id="date-display"></span>';
    const helpers = await loadModule();
    helpers.updateDateTime();
    const timeDisplay = document.getElementById('time-display');
    const dateDisplay = document.getElementById('date-display');
    expect(timeDisplay.textContent).not.toBe('');
    expect(dateDisplay.textContent).not.toBe('');
  });
});

describe('base-helpers.js - page-load safeguards', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  it('prefetches ordinary internal links but never the logout link', async () => {
    document.body.innerHTML = `
      <a href="/sales/" id="normal">Sales</a>
      <a href="/logout" id="logout">Logout</a>
      <a href="/pos/grid" id="pos">POS</a>
    `;
    await import('../../static/js/base-helpers.js');
    document.getElementById('normal').dispatchEvent(new MouseEvent('mouseenter'));
    document.getElementById('logout').dispatchEvent(new MouseEvent('mouseenter'));
    document.getElementById('pos').dispatchEvent(new MouseEvent('mouseenter'));
    const prefetched = [...document.querySelectorAll('link[rel="prefetch"]')].map((link) =>
      link.getAttribute('href'),
    );
    expect(prefetched).toContain('/sales/');
    expect(prefetched).toContain('/pos/grid');
    expect(prefetched).not.toContain('/logout');
  });

  it('does not start the clock interval when no clock element exists', async () => {
    const original = global.setInterval;
    const spy = vi.spyOn(global, 'setInterval').mockImplementation(original);
    try {
      document.body.innerHTML = '<div id="app"></div>';
      await import('../../static/js/base-helpers.js');
      expect(spy).not.toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it('starts the clock interval only when a clock element exists', async () => {
    const original = global.setInterval;
    const spy = vi.spyOn(global, 'setInterval').mockImplementation(original);
    try {
      document.body.innerHTML = '<span id="time-display"></span>';
      await import('../../static/js/base-helpers.js');
      expect(spy).toHaveBeenCalledWith(window.AzadHelpers.updateDateTime, 1000);
    } finally {
      spy.mockRestore();
    }
  });
});
