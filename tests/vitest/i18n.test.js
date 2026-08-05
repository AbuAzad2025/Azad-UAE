import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('i18n.js', () => {
  beforeEach(() => {
    document.documentElement.lang = 'ar';
    delete window.t;
    delete window.getCurrentLanguage;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.t;
    delete window.getCurrentLanguage;
    document.documentElement.lang = 'ar';
  });

  it('getCurrentLanguage returns document.documentElement.lang', async () => {
    document.documentElement.lang = 'en';
    await import('../../static/js/i18n.js');
    expect(window.getCurrentLanguage()).toBe('en');
    
    document.documentElement.lang = 'ar';
    expect(window.getCurrentLanguage()).toBe('ar');
    
    document.documentElement.lang = '';
    expect(window.getCurrentLanguage()).toBe('ar');
  });

  it('window.t passthrough returns key as-is', async () => {
    await import('../../static/js/i18n.js');
    expect(window.t('hello')).toBe('hello');
    expect(window.t('welcome_message')).toBe('welcome_message');
    expect(window.t('')).toBe('');
  });
});