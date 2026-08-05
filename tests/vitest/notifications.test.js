import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('jquery', () => import('./__mocks__/jquery.js'));

describe('notifications.js (NotificationManager)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.NotificationManager;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.NotificationManager;
    document.body.innerHTML = '';
  });

  it('creates toast container on init', async () => {
    await import('../../static/js/notifications.js');
    const manager = new window.NotificationManager();
    expect(document.getElementById('toast-container')).toBeTruthy();
    expect(manager.container).toBe(document.getElementById('toast-container'));
  });

  it('injects styles once', async () => {
    await import('../../static/js/notifications.js');
    new window.NotificationManager();
    const styles1 = document.getElementById('toast-styles');
    expect(styles1).toBeTruthy();
    
    new window.NotificationManager();
    const styles2 = document.getElementById('toast-styles');
    expect(styles2).toBe(styles1);
  });

  it('tracks user interaction for vibration API', async () => {
    await import('../../static/js/notifications.js');
    const manager = new window.NotificationManager();
    expect(manager.userHasInteracted).toBe(false);
    
    document.dispatchEvent(new Event('click'));
    expect(manager.userHasInteracted).toBe(true);
  });

  it('has sound objects for different types', async () => {
    await import('../../static/js/notifications.js');
    const manager = new window.NotificationManager();
    expect(manager.sounds.success).toBeInstanceOf(Audio);
    expect(manager.sounds.error).toBeInstanceOf(Audio);
    expect(manager.sounds.warning).toBeInstanceOf(Audio);
  });
});