import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('notifications.js (NotificationManager)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.NotificationManager;
    delete window.initNotifications;
    delete window.notify;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.NotificationManager;
    delete window.initNotifications;
    delete window.notify;
    document.body.innerHTML = '';
  });

  async function loadModule() {
    await import('../../static/js/notifications.js');
    expect(window.NotificationManager).toBeDefined();
    expect(typeof window.initNotifications).toBe('function');
  }

  it('creates toast container on init', async () => {
    await loadModule();
    const manager = window.initNotifications();
    expect(document.getElementById('toast-container')).toBeTruthy();
    expect(manager.container).toBe(document.getElementById('toast-container'));
  });

  it('injects styles once', async () => {
    await loadModule();
    window.initNotifications();
    const styles1 = document.getElementById('toast-styles');
    expect(styles1).toBeTruthy();

    window.initNotifications();
    const styles2 = document.getElementById('toast-styles');
    expect(styles2).toBe(styles1);
  });

  it('tracks user interaction for vibration API', async () => {
    await loadModule();
    const manager = window.initNotifications();
    expect(manager.userHasInteracted).toBe(false);

    document.dispatchEvent(new Event('click'));
    expect(manager.userHasInteracted).toBe(true);
  });

  it('has sound objects for different types', async () => {
    await loadModule();
    const manager = window.initNotifications();
    expect(manager.sounds.success).toBeInstanceOf(Audio);
    expect(manager.sounds.error).toBeInstanceOf(Audio);
    expect(manager.sounds.warning).toBeInstanceOf(Audio);
  });

  it('show() creates a toast element with content', async () => {
    await loadModule();
    const manager = window.initNotifications();
    const toast = manager.show({ type: 'success', title: 'Done', message: 'Saved', sound: false });
    expect(toast).toBeTruthy();
    expect(toast.className).toContain('toast-success');
    expect(toast.textContent).toContain('Saved');
    expect(document.getElementById('toast-container').children.length).toBeGreaterThan(0);
  });

  it('success/error/warning/info helpers build toasts', async () => {
    await loadModule();
    const manager = window.initNotifications();
    manager.success('OK');
    manager.error('Bad');
    manager.warning('Careful');
    manager.info('FYI');
    const toasts = document.getElementById('toast-container').querySelectorAll('.toast');
    expect(toasts.length).toBe(4);
  });
});
