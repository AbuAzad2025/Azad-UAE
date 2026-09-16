import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('notifications.js gaps', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    for (const el of document.head.querySelectorAll('#toast-styles')) el.remove();
    delete window.NotificationManager;
    delete window.initNotifications;
    delete window.notify;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.useRealTimers();
    vi.resetModules();
  });

  async function loadFresh() {
    await import('../../static/js/notifications.js');
    return window.initNotifications();
  }

  it('close button removes its toast', async () => {
    const manager = await loadFresh();
    const toast = manager.show({ type: 'info', title: 'T', message: 'hello' });
    expect(toast.isConnected).toBe(true);
    toast.querySelector('.toast-close').click();
    expect(toast.isConnected).toBe(false);
  });

  it('plays sounds and swallows blocked-autoplay rejections', async () => {
    const manager = await loadFresh();
    manager.sounds.success.play = vi.fn(() => Promise.resolve());
    manager.show({ type: 'success', title: 'T', message: 'M', sound: true });
    expect(manager.sounds.success.play).toHaveBeenCalledTimes(1);
    manager.sounds.error.play = vi.fn(() => Promise.reject(new Error('blocked')));
    manager.show({ type: 'error', message: 'E', sound: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(manager.sounds.error.play).toHaveBeenCalledTimes(1);
  });

  it('vibrates with per-type patterns after interaction', async () => {
    const manager = await loadFresh();
    const vib = vi.fn();
    Object.defineProperty(navigator, 'vibrate', { configurable: true, value: vib });
    manager.userHasInteracted = true;
    manager.show({ type: 'success', message: 'a', vibrate: true });
    manager.show({ type: 'error', message: 'b', vibrate: true });
    manager.show({ type: 'warning', message: 'c', vibrate: true });
    manager.show({ type: 'info', message: 'd', vibrate: true });
    manager.show({ type: 'mystery', message: 'e', vibrate: true });
    expect(vib).toHaveBeenCalledTimes(5);
    expect(vib).toHaveBeenNthCalledWith(1, [100]);
    expect(vib).toHaveBeenNthCalledWith(2, [100, 50, 100]);
    expect(vib).toHaveBeenNthCalledWith(3, [50, 50, 50]);
    expect(vib).toHaveBeenNthCalledWith(4, [50]);
    expect(vib).toHaveBeenNthCalledWith(5, [50]);
  });

  it('skips vibration before first user interaction', async () => {
    const manager = await loadFresh();
    const vib = vi.fn();
    Object.defineProperty(navigator, 'vibrate', { configurable: true, value: vib });
    expect(manager.userHasInteracted).toBe(false);
    manager.show({ type: 'success', message: 'a', vibrate: true });
    expect(vib).not.toHaveBeenCalled();
  });

  it('auto-removes toasts after the duration elapses', async () => {
    const manager = await loadFresh();
    vi.useFakeTimers();
    const toast = manager.show({ type: 'info', message: 'temp', duration: 1000 });
    expect(toast.isConnected).toBe(true);
    vi.advanceTimersByTime(1000);
    expect(toast.className).toContain('removing');
    vi.advanceTimersByTime(300);
    expect(toast.isConnected).toBe(false);
  });

  it('exposes a jQuery $.notify bridge', async () => {
    await loadFresh();
    globalThis.$.notify('jq-msg', 'success', 'JQ');
    const toast = document.querySelector('.toast');
    expect(toast).toBeTruthy();
    expect(toast.textContent).toContain('jq-msg');
  });
});

describe('landing.js flash auto-dismiss gaps', () => {
  let originalIO;

  beforeEach(() => {
    originalIO = global.IntersectionObserver;
    global.IntersectionObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    Element.prototype.scrollIntoView = vi.fn();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    if (originalIO === undefined) delete global.IntersectionObserver;
    else global.IntersectionObserver = originalIO;
    delete Element.prototype.scrollIntoView;
    vi.useRealTimers();
    vi.resetModules();
  });

  it('auto-dismisses flash items per severity and skips pre-marked ones', async () => {
    vi.useFakeTimers();
    const origRaf = global.requestAnimationFrame;
    global.requestAnimationFrame = (cb) => {
      cb(0);
      return 0;
    };
    document.body.innerHTML = `
      <a href="#pricing">Pricing</a>
      <section id="pricing"></section>
      <div class="feature-card" id="fc"></div>
      <button id="landingSidebarOpen"></button>
      <button id="landingSidebarClose"></button>
      <div id="landingSidebarBackdrop"></div>
      <aside id="landingSidebar"></aside>
      <a href="#nowhere" class="landing-scroll-link">X</a>
      <div class="azad-flash-item azad-flash-item--danger" id="fDanger">D</div>
      <div class="azad-flash-item azad-flash-item--warning" id="fWarn">W</div>
      <div class="azad-flash-item" id="fInfo">I</div>
      <div class="azad-flash-item" id="fDone" data-azad-flash-dismiss="1">done</div>
    `;
    await import('../../static/js/landing.js');

    const danger = document.getElementById('fDanger');
    const warn = document.getElementById('fWarn');
    const info = document.getElementById('fInfo');
    const done = document.getElementById('fDone');
    expect(danger.querySelector('span')).toBeTruthy();
    expect(warn.querySelector('span')).toBeTruthy();
    expect(info.querySelector('span')).toBeTruthy();
    expect(done.querySelector('span')).toBeNull();

    vi.advanceTimersByTime(0);
    expect(danger.querySelector('span').style.transform).toBe('scaleX(0.01)');
    global.requestAnimationFrame = origRaf;

    vi.advanceTimersByTime(3500);
    expect(document.getElementById('fInfo').style.opacity).toBe('0');
    vi.advanceTimersByTime(400);
    expect(document.getElementById('fInfo')).toBeNull();

    vi.advanceTimersByTime(7000 - 3900);
    expect(document.getElementById('fWarn').style.opacity).toBe('0');
    vi.advanceTimersByTime(400);
    expect(document.getElementById('fWarn')).toBeNull();

    vi.advanceTimersByTime(9000 - 7400);
    expect(document.getElementById('fDanger').style.opacity).toBe('0');
    vi.advanceTimersByTime(400);
    expect(document.getElementById('fDanger')).toBeNull();

    expect(document.getElementById('fDone')).not.toBeNull();
  });
});

describe('i18n.js translation lookup gaps', () => {
  let origDict;
  let origLang;

  beforeEach(() => {
    origDict = window.I18N_TRANSLATIONS;
    origLang = window.I18N_LANG;
    document.documentElement.lang = 'ar';
    delete window.t;
    delete window.getCurrentLanguage;
    vi.resetModules();
  });

  afterEach(() => {
    window.I18N_TRANSLATIONS = origDict;
    if (origLang === undefined) delete window.I18N_LANG;
    else window.I18N_LANG = origLang;
    document.documentElement.lang = 'ar';
    delete window.t;
    delete window.getCurrentLanguage;
    vi.resetModules();
  });

  it('returns translations with en and key fallbacks', async () => {
    window.I18N_TRANSLATIONS = {
      greeting: { ar: 'مرحبا', en: 'Hello' },
      only_en: { en: 'Only EN' },
      naked: {},
    };
    window.I18N_LANG = 'ar';
    await import('../../static/js/i18n.js');
    expect(window.t('greeting')).toBe('مرحبا');

    delete window.I18N_LANG;
    document.documentElement.lang = 'fr';
    expect(window.t('greeting')).toBe('Hello');
    expect(window.t('only_en')).toBe('Only EN');
    expect(window.t('naked')).toBe('naked');
    expect(window.t('missing')).toBe('missing');
  });
});

describe('print-handlers.js template-switch gaps', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new URL('http://localhost/print/receipt'),
    });
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
  });

  it('navigates with the template query param on change', async () => {
    await import('../../static/js/print-handlers.js');
    const sel = document.createElement('select');
    sel.dataset.action = 'template-switch';
    const opt = document.createElement('option');
    opt.value = 'fancy';
    opt.textContent = 'Fancy';
    sel.appendChild(opt);
    sel.value = 'fancy';
    document.body.appendChild(sel);
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    expect(window.location.href).toContain('template=fancy');
  });

  it('ignores change events without a template value', async () => {
    await import('../../static/js/print-handlers.js');
    const sel = document.createElement('select');
    sel.dataset.action = 'template-switch';
    document.body.appendChild(sel);
    expect(() => sel.dispatchEvent(new Event('change', { bubbles: true }))).not.toThrow();
    expect(window.location.href).not.toContain('template=');
    const plain = document.createElement('div');
    document.body.appendChild(plain);
    expect(() => plain.dispatchEvent(new Event('change', { bubbles: true }))).not.toThrow();
  });
});
