import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let serviceWorkerMock;
let origSW;
let origOnLine;
let origServiceWorkerInNavigator;
let origAdd;
let registered;

function dispatchContentLoaded() {
  document.dispatchEvent(new Event('DOMContentLoaded'));
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('pos/offline.js', () => {
  beforeEach(() => {
    registered = [];
    origAdd = document.addEventListener.bind(document);
    document.addEventListener = vi.fn((type, fn) => {
      registered.push({ type, fn });
      origAdd(type, fn);
    });
    serviceWorkerMock = {
      register: vi.fn(() => Promise.resolve({})),
    };
    origSW = navigator.serviceWorker;
    origOnLine = Object.getOwnPropertyDescriptor(navigator, 'onLine');
    vi.resetModules();
  });

  afterEach(() => {
    registered.forEach(({ type, fn }) => document.removeEventListener(type, fn));
    registered = [];
    document.addEventListener = origAdd;
    if (origSW === undefined) delete navigator.serviceWorker;
    else Object.defineProperty(navigator, 'serviceWorker', { value: origSW, configurable: true });
    if (origOnLine === undefined) delete navigator.onLine;
    else Object.defineProperty(navigator, 'onLine', origOnLine);
    document.getElementById('posOfflineBar')?.remove();
    document.getElementById('posSessionBar')?.remove();
    delete window.__posOffline;
    vi.resetModules();
  });

  it('exposes the retryQueue helper on window', async () => {
    await import('../../static/js/pos/offline.js');
    expect(typeof window.__posOffline.retryQueue).toBe('function');
  });

  it('creates the offline bar before the session bar on DOMContentLoaded', async () => {
    document.body.innerHTML = '<div id="posSessionBar"></div>';
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    const bar = document.getElementById('posOfflineBar');
    expect(bar).toBeTruthy();
    expect(bar.className).toContain('d-none');
    expect(bar.getAttribute('role')).toBe('alert');
    expect(bar.querySelector('#retryQueueBtn')).toBeTruthy();
    expect(bar.previousElementSibling).toBe(document.getElementById('posSessionBar'));
  });

  it('does not create a second offline bar', async () => {
    document.body.innerHTML = '<div id="posOfflineBar"></div><div id="posSessionBar"></div>';
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    const bars = document.querySelectorAll('#posOfflineBar');
    expect(bars).toHaveLength(1);
  });

  it('registers the service worker when supported', async () => {
    Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorkerMock, configurable: true });
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    expect(serviceWorkerMock.register).toHaveBeenCalledWith('/static/pos-sw.js', { scope: '/pos/' });
  });

  it('skips service worker registration when unsupported', async () => {
    delete navigator.serviceWorker;
    await import('../../static/js/pos/offline.js');
    expect(() => dispatchContentLoaded()).not.toThrow();
  });

  it('shows the bar when offline and hides it when online', async () => {
    document.body.innerHTML = '<div id="posSessionBar"></div>';
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    const bar = document.getElementById('posOfflineBar');
    expect(bar.classList.contains('d-none')).toBe(false);
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    window.dispatchEvent(new Event('online'));
    expect(bar.classList.contains('d-none')).toBe(true);
  });

  it('hides the bar when back online via offline event handling', async () => {
    document.body.innerHTML = '<div id="posSessionBar"></div>';
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    window.dispatchEvent(new Event('offline'));
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    window.dispatchEvent(new Event('offline'));
    const bar = document.getElementById('posOfflineBar');
    expect(bar.classList.contains('d-none')).toBe(false);
  });

  it('retries the queue via the exposed helper when a worker is active', async () => {
    const sync = { register: vi.fn(() => Promise.resolve()) };
    const active = { postMessage: vi.fn() };
    const reg = { active, sync };
    Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorkerMock, configurable: true });
    serviceWorkerMock.register.mockResolvedValue(reg);
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    await flush();
    window.__posOffline.retryQueue();
    expect(active.postMessage).toHaveBeenCalledWith('retry-queue');
    expect(sync.register).toHaveBeenCalledWith('pos-queue-retry');
  });

  it('retries the queue without sync support', async () => {
    const active = { postMessage: vi.fn() };
    const reg = { active };
    Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorkerMock, configurable: true });
    serviceWorkerMock.register.mockResolvedValue(reg);
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    await flush();
    window.__posOffline.retryQueue();
    expect(active.postMessage).toHaveBeenCalledWith('retry-queue');
  });

  it('is a no-op retry without a registered worker', async () => {
    await import('../../static/js/pos/offline.js');
    expect(() => window.__posOffline.retryQueue()).not.toThrow();
  });

  it('retries the queue when the retry button is clicked', async () => {
    const active = { postMessage: vi.fn() };
    const reg = { active };
    Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorkerMock, configurable: true });
    serviceWorkerMock.register.mockResolvedValue(reg);
    document.body.innerHTML = '<div id="posSessionBar"><button id="retryQueueBtn"></button></div>';
    await import('../../static/js/pos/offline.js');
    dispatchContentLoaded();
    await flush();
    document.getElementById('retryQueueBtn').click();
    expect(active.postMessage).toHaveBeenCalledWith('retry-queue');
  });
});
