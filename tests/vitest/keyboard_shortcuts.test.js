import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const modalSpy = vi.fn(() => undefined);
const triggerSpy = vi.fn(() => undefined);

function makeJQuery() {
  const chain = () => ({
    ready: (fn) => { if (typeof fn === 'function') fn(); return api; },
    on: () => api,
    off: () => api,
    trigger: triggerSpy,
    remove: () => api,
    appendTo: () => api,
    modal: modalSpy,
    data: () => undefined,
    val: () => '',
  });
  const api = chain();
  const $ = (sel) => (sel === document ? api : chain());
  $.fn = {};
  return $;
}

function fireKey(el, init) {
  el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }));
}

async function importShortcuts() {
  await import('../../static/js/keyboard-shortcuts.js');
  return window.shortcuts;
}

describe('keyboard-shortcuts.js', () => {
  let notify;
  let $;

  beforeEach(() => {
    localStorage.setItem('shortcuts-shown', 'true');
    document.body.innerHTML = '';
    notify = { info: vi.fn(), success: vi.fn() };
    global.notify = notify;
    window.notify = notify;
    $ = makeJQuery();
    global.$ = $;
    window.$ = $;
    global.jQuery = $;
    window.jQuery = $;
    delete window.shortcuts;
    modalSpy.mockClear();
    triggerSpy.mockClear();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    localStorage.clear();
    delete global.notify;
    delete window.notify;
    delete global.$;
    delete window.$;
    delete global.jQuery;
    delete window.jQuery;
    delete window.shortcuts;
    vi.resetModules();
  });

  it('creates window.shortcuts and help button', async () => {
    await importShortcuts();
    expect(window.shortcuts).toBeDefined();
    expect(document.getElementById('shortcuts-help-btn')).toBeTruthy();
    expect(modalSpy).not.toHaveBeenCalled();
  });

  it('ignores keydown inside input fields without modifiers', async () => {
    const s = await importShortcuts();
    const cb = vi.fn();
    s.register('ctrl+x', cb);
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireKey(input, { key: 'x' });
    expect(cb).not.toHaveBeenCalled();
    fireKey(input, { key: 'x', ctrlKey: true });
    expect(cb).toHaveBeenCalled();
  });

  it('register stores shortcut in lowercase', async () => {
    const s = await importShortcuts();
    const cb = vi.fn();
    s.register('CTRL+Z', cb);
    expect(s.shortcuts.has('ctrl+z')).toBe(true);
    fireKey(document, { key: 'z', ctrlKey: true });
    expect(cb).toHaveBeenCalled();
  });

  it('alt+h navigates home', async () => {
    const s = await importShortcuts();
    fireKey(document, { key: 'h', altKey: true });
    expect(window.location.href).toBe('http://localhost:3000/');
  });

  it('alt+s clicks sales link', async () => {
    const link = document.createElement('a');
    link.href = '/sales';
    link.setAttribute('data-id', 'sales-link');
    const clickSpy = vi.spyOn(link, 'click');
    document.body.appendChild(link);
    const s = await importShortcuts();
    fireKey(document, { key: 's', altKey: true });
    expect(clickSpy).toHaveBeenCalled();
  });

  it('ctrl+n notifies when no create button exists', async () => {
    const s = await importShortcuts();
    fireKey(document, { key: 'n', ctrlKey: true });
    expect(notify.info).toHaveBeenCalled();
  });

  it('ctrl+n clicks the create button when present', async () => {
    const btn = document.createElement('a');
    btn.className = 'btn-primary';
    btn.href = '/sales/create';
    document.body.appendChild(btn);
    const clickSpy = vi.spyOn(btn, 'click');
    const s = await importShortcuts();
    fireKey(document, { key: 'n', ctrlKey: true });
    expect(clickSpy).toHaveBeenCalled();
  });

  it('ctrl+s submits the form', async () => {
    const form = document.createElement('form');
    document.body.appendChild(form);
    const submitSpy = vi.spyOn(form, 'dispatchEvent');
    const s = await importShortcuts();
    fireKey(document, { key: 's', ctrlKey: true });
    expect(submitSpy).toHaveBeenCalled();
  });

  it('escape hides open modal', async () => {
    const modal = document.createElement('div');
    modal.className = 'modal show';
    document.body.appendChild(modal);
    const s = await importShortcuts();
    fireKey(document, { key: 'Escape' });
    expect(modalSpy).toHaveBeenCalledWith('hide');
  });

  it('escape removes toasts when no modal open', async () => {
    const toast = document.createElement('div');
    toast.className = 'toast';
    document.body.appendChild(toast);
    const s = await importShortcuts();
    fireKey(document, { key: 'Escape' });
    expect(document.querySelector('.toast')).toBeNull();
  });

  it('ctrl+k focuses search input', async () => {
    const input = document.createElement('input');
    input.type = 'search';
    document.body.appendChild(input);
    const focusSpy = vi.spyOn(input, 'focus');
    const selectSpy = vi.spyOn(input, 'select');
    const s = await importShortcuts();
    fireKey(document, { key: 'k', ctrlKey: true });
    expect(focusSpy).toHaveBeenCalled();
    expect(selectSpy).toHaveBeenCalled();
  });

  it('ctrl+e clicks export button and notifies', async () => {
    const btn = document.createElement('button');
    btn.className = 'buttons-excel';
    document.body.appendChild(btn);
    const clickSpy = vi.spyOn(btn, 'click');
    const s = await importShortcuts();
    fireKey(document, { key: 'e', ctrlKey: true });
    expect(clickSpy).toHaveBeenCalled();
    expect(notify.success).toHaveBeenCalled();
  });

  it('ctrl+p triggers window.print', async () => {
    global.print = vi.fn();
    const s = await importShortcuts();
    fireKey(document, { key: 'p', ctrlKey: true });
    expect(global.print).toHaveBeenCalled();
  });

  it('ctrl+b toggles pushmenu', async () => {
    const s = await importShortcuts();
    fireKey(document, { key: 'b', ctrlKey: true });
    expect(triggerSpy).toHaveBeenCalledWith('click');
  });

  it('question mark shows help modal', async () => {
    const s = await importShortcuts();
    fireKey(document, { key: '?' });
    expect(modalSpy).toHaveBeenCalledWith('show');
  });

  it('disable and enable gate shortcuts', async () => {
    const s = await importShortcuts();
    const cb = vi.fn();
    s.register('y', cb);
    s.disable();
    fireKey(document, { key: 'y' });
    expect(cb).not.toHaveBeenCalled();
    s.enable();
    fireKey(document, { key: 'y' });
    expect(cb).toHaveBeenCalled();
  });

  it('help button click shows the help modal', async () => {
    const s = await importShortcuts();
    document.getElementById('shortcuts-help-btn').click();
    expect(modalSpy).toHaveBeenCalledWith('show');
  });

  it('shows first-load tip when not seen before', async () => {
    vi.useFakeTimers();
    try {
      localStorage.removeItem('shortcuts-shown');
      await importShortcuts();
      vi.advanceTimersByTime(2100);
      expect(notify.info).toHaveBeenCalled();
      expect(localStorage.getItem('shortcuts-shown')).toBe('true');
    } finally {
      vi.useRealTimers();
    }
  });
});
