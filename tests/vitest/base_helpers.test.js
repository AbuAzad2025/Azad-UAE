import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('jquery', () => import('./__mocks__/jquery.js'));

describe('base-helpers.js (azad object)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.azad;
    document.body.innerHTML = '';
  });

  it('exposes azad global with expected methods', async () => {
    await import('../../static/js/base-helpers.js');
    expect(window.azad).toBeDefined();
    expect(typeof window.azad.showLoading).toBe('function');
    expect(typeof window.azad.hideLoading).toBe('function');
    expect(typeof window.azad.formatNumber).toBe('function');
    expect(typeof window.azad.showError).toBe('function');
    expect(typeof window.azad.showSuccess).toBe('function');
    expect(typeof window.azad.showWarning).toBe('function');
    expect(typeof window.azad.showInfo).toBe('function');
  });

  it('formatNumber formats with 2 decimal places', async () => {
    await import('../../static/js/base-helpers.js');
    expect(window.azad.formatNumber(1234.5)).toBe('1,234.50');
    expect(window.azad.formatNumber('99.9')).toBe('99.90');
    expect(window.azad.formatNumber(0)).toBe('0.00');
    expect(window.azad.formatNumber(-100)).toBe('-100.00');
    expect(window.azad.formatNumber('invalid')).toBe('0.00');
  });

  it('showLoading/hideLoading toggle overlay', async () => {
    await import('../../static/js/base-helpers.js');
    window.azad.showLoading();
    const overlay = document.getElementById('azadLoadingOverlay');
    expect(overlay).toBeTruthy();
    expect(overlay.style.display).toBe('flex');
    
    window.azad.hideLoading();
    expect(overlay.style.display).toBe('none');
  });

  it('showLoading increments counter, hideLoading decrements', async () => {
    await import('../../static/js/base-helpers.js');
    window.azad.showLoading();
    window.azad.showLoading();
    window.azad.hideLoading();
    const overlay = document.getElementById('azadLoadingOverlay');
    expect(overlay.style.display).toBe('flex');
    window.azad.hideLoading();
    expect(overlay.style.display).toBe('none');
  });

  it('toast methods create toast elements', async () => {
    await import('../../static/js/base-helpers.js');
    window.azad.showSuccess('Operation succeeded');
    window.azad.showError('Operation failed');
    window.azad.showWarning('Warning message');
    window.azad.showInfo('Info message');
    
    const toasts = document.body.querySelectorAll('[style*="position:fixed"][style*="z-index:20001"]');
    expect(toasts.length).toBeGreaterThanOrEqual(1);
  });
});