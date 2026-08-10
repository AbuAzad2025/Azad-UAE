import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('pos-permissions.js', () => {
  beforeEach(() => {
    delete window.CURRENT_USER_PERMISSIONS;
    vi.resetModules();
  });

  afterEach(() => {
    delete window.CURRENT_USER_PERMISSIONS;
    delete window.hasPermission;
    vi.resetModules();
  });

  it('exposes hasPermission on window', async () => {
    await import('../../static/js/pos-permissions.js');
    expect(typeof window.hasPermission).toBe('function');
  });

  it('returns false when permissions are missing', async () => {
    await import('../../static/js/pos-permissions.js');
    expect(window.hasPermission('pos.sell')).toBe(false);
  });

  it('returns false when permissions is not an array', async () => {
    window.CURRENT_USER_PERMISSIONS = 'nope';
    await import('../../static/js/pos-permissions.js');
    expect(window.hasPermission('pos.sell')).toBe(false);
  });

  it('returns true when the code is present', async () => {
    window.CURRENT_USER_PERMISSIONS = ['pos.sell', 'pos.hold'];
    await import('../../static/js/pos-permissions.js');
    expect(window.hasPermission('pos.hold')).toBe(true);
    expect(window.hasPermission('pos.delete')).toBe(false);
  });
});

describe('print-handlers.js', () => {
  let printSpy;
  let closeSpy;
  let backSpy;
  let origAdd;
  let registered;

  beforeEach(() => {
    registered = [];
    origAdd = document.addEventListener.bind(document);
    document.addEventListener = vi.fn((type, fn) => {
      registered.push({ type, fn });
      origAdd(type, fn);
    });
    printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});
    closeSpy = vi.spyOn(window, 'close').mockImplementation(() => {});
    backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    vi.resetModules();
  });

  afterEach(() => {
    registered.forEach(({ type, fn }) => document.removeEventListener(type, fn));
    registered = [];
    document.addEventListener = origAdd;
    printSpy.mockRestore();
    closeSpy.mockRestore();
    backSpy.mockRestore();
    vi.resetModules();
  });

  function click(target) {
    document.body.appendChild(target);
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  }

  it('calls window.print for data-action window-print', async () => {
    await import('../../static/js/print-handlers.js');
    const btn = document.createElement('button');
    btn.dataset.action = 'window-print';
    click(btn);
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it('calls window.close for data-action window-close', async () => {
    await import('../../static/js/print-handlers.js');
    const btn = document.createElement('button');
    btn.dataset.action = 'window-close';
    click(btn);
    expect(closeSpy).toHaveBeenCalledTimes(1);
  });

  it('goes back when history has entries', async () => {
    Object.defineProperty(window.history, 'length', { configurable: true, value: 5 });
    await import('../../static/js/print-handlers.js');
    const btn = document.createElement('button');
    btn.dataset.action = 'history-back';
    click(btn);
    expect(backSpy).toHaveBeenCalledTimes(1);
    expect(closeSpy).not.toHaveBeenCalled();
    delete window.history.length;
  });

  it('closes the window when history is empty', async () => {
    Object.defineProperty(window.history, 'length', { configurable: true, value: 1 });
    await import('../../static/js/print-handlers.js');
    const btn = document.createElement('button');
    btn.dataset.action = 'history-back';
    click(btn);
    expect(closeSpy).toHaveBeenCalledTimes(1);
    expect(backSpy).not.toHaveBeenCalled();
    delete window.history.length;
  });

  it('ignores clicks not matching a data-action', async () => {
    await import('../../static/js/print-handlers.js');
    const btn = document.createElement('button');
    click(btn);
    expect(printSpy).not.toHaveBeenCalled();
    expect(closeSpy).not.toHaveBeenCalled();
  });

  it('schedules an auto print when auto_print=true is present', async () => {
    vi.useFakeTimers();
    window.history.replaceState({}, '', '/print/receipt?auto_print=true');
    await import('../../static/js/print-handlers.js');
    document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true }));
    vi.advanceTimersByTime(300);
    expect(printSpy).toHaveBeenCalledTimes(1);
    window.history.replaceState({}, '', '/');
    vi.useRealTimers();
  });

  it('does not auto print without the auto_print param', async () => {
    await import('../../static/js/print-handlers.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(printSpy).not.toHaveBeenCalled();
  });
});
