import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('api.js central client', () => {
  beforeEach(() => {
    document.head.innerHTML =
      '<meta name="csrf-token" content="csrf-123">';
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function loadClient() {
    await import('../../static/js/api.js');
    return window.api;
  }

  it('passes the fetch Response through untouched', async () => {
    const response = { ok: true, json: () => Promise.resolve({ ok: 1 }) };
    global.fetch = vi.fn(() => Promise.resolve(response));
    const api = await loadClient();
    await expect(api.fetch('/x')).resolves.toBe(response);
    expect(global.fetch).toHaveBeenCalledWith('/x', undefined);
  });

  it('rejects a second request while one is in flight (double-submit guard)', async () => {
    let release;
    global.fetch = vi.fn(
      () => new Promise((resolve) => { release = () => resolve({ ok: true }); }),
    );
    const api = await loadClient();
    const inflight = api.fetch('/slow');
    await expect(api.fetch('/second')).rejects.toThrow('already in progress');
    release();
    await inflight;
    await expect(api.isSubmitting()).toBe(false);
  });

  it('releases the submit lock even when fetch throws', async () => {
    global.fetch = vi.fn(() => Promise.reject(new TypeError('network down')));
    const api = await loadClient();
    await expect(api.fetch('/boom')).rejects.toThrow('network down');
    expect(api.isSubmitting()).toBe(false);
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    await expect(api.fetch('/retry')).resolves.toEqual({ ok: true });
  });

  it('post() sends CSRF + XHR headers and JSON body', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    const api = await loadClient();
    await api.post('/submit', { qty: 2 });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/submit');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBe(JSON.stringify({ qty: 2 }));
    expect(opts.headers['X-CSRFToken']).toBe('csrf-123');
    expect(opts.headers['X-Requested-With']).toBe('XMLHttpRequest');
  });

  it('documents that options with a headers key REPLACE the security headers (bug footgun)', async () => {
    // Known issue: `...options` spreads AFTER the merged headers object, so
    // passing { headers: {...} } drops X-CSRFToken / X-Requested-With.
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    const api = await loadClient();
    await api.post('/submit', {}, { headers: { 'X-Extra': '1' } });
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['X-Extra']).toBe('1');
    expect(opts.headers['X-CSRFToken']).toBeUndefined();
    expect(opts.headers['X-Requested-With']).toBeUndefined();
  });

  it('get() sends GET with CSRF headers', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    const api = await loadClient();
    await api.get('/data');
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.method).toBe('GET');
    expect(opts.headers['X-CSRFToken']).toBe('csrf-123');
    expect(opts.headers['X-Requested-With']).toBe('XMLHttpRequest');
  });

  it('falls back to empty CSRF token when meta tag is absent', async () => {
    document.head.innerHTML = '';
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    const api = await loadClient();
    await api.get('/data');
    expect(global.fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('');
  });

  it('lets option properties such as signal ride along', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    const api = await loadClient();
    const controller = new AbortController();
    await api.get('/abortable', { signal: controller.signal });
    expect(global.fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
