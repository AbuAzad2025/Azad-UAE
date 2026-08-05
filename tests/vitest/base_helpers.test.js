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
    await loadModule();
    window.azad.showLoading();
    const overlay = document.getElementById('azadLoadingOverlay');
    expect(overlay).toBeTruthy();
    expect(overlay.style.display).toBe('flex');

    window.azad.hideLoading();
    expect(overlay.style.display).toBe('none');
  });

  it('showLoading increments counter, hideLoading decrements', async () => {
    await loadModule();
    window.azad.showLoading();
    window.azad.showLoading();
    window.azad.hideLoading();
    const overlay = document.getElementById('azadLoadingOverlay');
    expect(overlay.style.display).toBe('flex');
    window.azad.hideLoading();
    expect(overlay.style.display).toBe('none');
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
});
