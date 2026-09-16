import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const ENDPOINT = '/api/v1/telemetry/logs';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function importTelemetry() {
  await import('../../static/js/telemetry.js');
  return window.azadTelemetry;
}

function installIdb(hooks = {}) {
  const state = { deleted: [], puts: [], cleared: 0 };
  const store = {
    put: (record) => {
      state.puts.push(record);
    },
    delete: (qid) => {
      state.deleted.push(qid);
    },
    clear: () => {
      state.cleared += 1;
    },
    getAllKeys: () => {
      const req = { result: hooks.keys || [] };
      setTimeout(() => {
        if (req.onsuccess) req.onsuccess();
      }, 0);
      return req;
    },
    getAll: () => {
      const req = { result: hooks.records || [] };
      setTimeout(() => {
        if (hooks.getAllError) {
          if (req.onerror) req.onerror();
        } else if (req.onsuccess) {
          req.onsuccess();
        }
      }, 0);
      return req;
    },
  };
  const result = {
    createObjectStore: () => {
      if (hooks.createStoreThrow) throw new Error('exists');
    },
    transaction: () => {
      if (hooks.txThrow) throw new Error('tx down');
      return { objectStore: () => store };
    },
  };
  globalThis.indexedDB = {
    open: () => {
      const req = { result };
      setTimeout(() => {
        if (hooks.fire === 'error') {
          if (req.onerror) req.onerror();
        } else if (hooks.fire === 'blocked') {
          if (req.onblocked) req.onblocked();
        } else {
          if (req.onupgradeneeded) req.onupgradeneeded();
          if (req.onsuccess) req.onsuccess();
        }
      }, 0);
      return req;
    },
  };
  return state;
}

describe('telemetry.js gaps', () => {
  let fetchMock;

  beforeEach(() => {
    document.body.innerHTML = '<button id="buy">buy</button>';
    fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
    );
    global.fetch = fetchMock;
    globalThis.indexedDB = undefined;
    delete window.azadTelemetry;
    delete window.CURRENT_USER;
    delete window.CURRENT_USERNAME;
    delete window._LOG_ENDPOINT;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.azadTelemetry;
    delete global.fetch;
    delete globalThis.indexedDB;
    delete navigator.sendBeacon;
    delete window.CURRENT_USER;
    delete window.CURRENT_USERNAME;
    delete window._LOG_ENDPOINT;
    if (Date.prototype.toISOString.restore) Date.prototype.toISOString.restore();
    vi.useRealTimers();
    vi.resetModules();
  });

  it('safe() swallows accessor errors during capture', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    let reads = 0;
    Object.defineProperty(window, 'CURRENT_USER', {
      configurable: true,
      get() {
        reads += 1;
        if (reads === 1) throw new Error('nope');
        return undefined;
      },
    });
    api.capture('SOFTWARE_EXCEPTION', 'dropped-event');
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    expect(payload.events).toHaveLength(10);
    expect(payload.events.some((e) => e.message === 'dropped-event')).toBe(false);
  });

  it('nowIso() falls back to empty string when the clock throws', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    vi.spyOn(Date.prototype, 'toISOString').mockImplementation(() => {
      throw new Error('clock broken');
    });
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `t-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    expect(payload.events[0].client_ts).toBe('');
  });

  it('redactUrl/isTelemetryUrl survive malformed urls', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await fetch('http://exa mple.com/bad?token=abc');
    api.capture('SOFTWARE_EXCEPTION', 'after-bad-url');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-bad-url');
    const crumb = after.breadcrumbs.find((b) => b.type === 'fetch');
    expect(crumb.url).toBe('http://exa mple.com/bad?token=abc');
  });

  it('trims breadcrumbs past the cap', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 25; i += 1) document.getElementById('buy').click();
    api.capture('SOFTWARE_EXCEPTION', 'after-clicks');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-clicks');
    expect(after.breadcrumbs).toHaveLength(20);
  });

  it('persists to the idb outbox and removes shipped records', async () => {
    const state = installIdb();
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `p-${i}`);
    await sleep(60);
    expect(state.puts).toHaveLength(10);
    expect(state.deleted).toHaveLength(10);
  });

  it('tolerates an existing object store on upgrade', async () => {
    installIdb({ createStoreThrow: true });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await sleep(30);
    expect(typeof api.capture).toBe('function');
    expect(navigator.sendBeacon).not.toHaveBeenCalled();
  });

  it('resolves a null db when open errors', async () => {
    installIdb({ fire: 'error' });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `e-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
  });

  it('resolves a null db when open is blocked', async () => {
    installIdb({ fire: 'blocked' });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `b-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
  });

  it('swallows idb transaction failures on put and trim', async () => {
    installIdb({ txThrow: true });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `t-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
  });

  it('trims the stored outbox on overflow', async () => {
    const keys = Array.from({ length: 105 }, (_, i) => i + 1);
    const state = installIdb({ keys });
    const api = await importTelemetry();
    api.capture('SOFTWARE_EXCEPTION', 'trim-me');
    await sleep(40);
    // 105 stored keys overflow by 5 (trim) + the boot flush ships 1 queued event (remove).
    expect(state.deleted.length).toBe(6);
  });

  it('restores persisted records on boot', async () => {
    installIdb({ records: [{ qid: 99, message: 'old' }] });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await sleep(40);
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `n-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    expect(payload.events.some((e) => e.qid === 99)).toBe(true);
  });

  it('boots with an empty outbox when drain errors', async () => {
    installIdb({ getAllError: true });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await sleep(40);
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `g-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
  });

  it('boots with an empty outbox when drain transactions fail', async () => {
    installIdb({ txThrow: true });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await sleep(40);
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `d-${i}`);
    await sleep(30);
    expect(navigator.sendBeacon).toHaveBeenCalled();
  });

  it('requeues when fetch throws synchronously', async () => {
    const throwing = vi.fn(() => {
      throw new Error('sync down');
    });
    global.fetch = throwing;
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `s-${i}`);
    await sleep(30);
    expect(throwing).toHaveBeenCalled();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `t-${i}`);
    await sleep(30);
    expect(throwing.mock.calls.length).toBeGreaterThan(1);
  });

  it('requeues with overflow trim when the outbox is full', async () => {
    let release;
    const hanging = vi.fn(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    global.fetch = hanging;
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `a-${i}`);
    for (let i = 0; i < 105; i += 1) api.capture('SOFTWARE_EXCEPTION', `o-${i}`);
    expect(hanging).toHaveBeenCalledTimes(1);
    release({ ok: false, status: 500 });
    await sleep(30);
    api.capture('SOFTWARE_EXCEPTION', 'one-more');
    await sleep(30);
    expect(hanging).toHaveBeenCalledTimes(2);
  });

  it('requeues when the shipper promise rejects', async () => {
    let calls = 0;
    const flaky = vi.fn(() => {
      calls += 1;
      if (calls === 1) {
        return { then: () => ({ catch: () => Promise.reject(new Error('ship failed')) }) };
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    global.fetch = flaky;
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `f-${i}`);
    await sleep(30);
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `g-${i}`);
    await sleep(30);
    expect(flaky.mock.calls.length).toBeGreaterThan(1);
    // The rejected batch must have been requeued: the next shipment carries
    // the 10 failed events plus the first new one.
    const secondBody = JSON.parse(flaky.mock.calls[1][1].body);
    expect(secondBody.events).toHaveLength(11);
    expect(secondBody.events.some((e) => e.message === 'f-0')).toBe(true);
    expect(secondBody.events.some((e) => e.message === 'g-0')).toBe(true);
  });

  it('ignores error events without a message', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    await importTelemetry();
    window.dispatchEvent(new ErrorEvent('error', { message: '' }));
    window.dispatchEvent(new Event('error'));
    for (let i = 0; i < 10; i += 1) window.dispatchEvent(new ErrorEvent('error', { message: `z-${i}` }));
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    expect(payload.events).toHaveLength(10);
  });

  it('ignores clicks on targets without a tag name', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    api.capture('SOFTWARE_EXCEPTION', 'after-bare-click');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-bare-click');
    expect(after.breadcrumbs.filter((b) => b.type === 'click')).toHaveLength(0);
  });

  it('skips history wrapping when the method is missing', async () => {
    const origPush = history.pushState;
    history.pushState = null;
    try {
      const api = await importTelemetry();
      expect(typeof api.capture).toBe('function');
    } finally {
      history.pushState = origPush;
    }
  });

  it('boots without fetch available', async () => {
    const realFetch = global.fetch;
    global.fetch = undefined;
    window.fetch = undefined;
    try {
      const api = await importTelemetry();
      api.capture('SOFTWARE_EXCEPTION', 'no-fetch');
      await sleep(20);
    } finally {
      global.fetch = realFetch;
      window.fetch = realFetch;
    }
  });

  it('records fetch breadcrumbs for Request objects and init methods', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await fetch(new Request('http://localhost/api/x', { method: 'POST' }));
    await fetch('http://localhost/api/y', { method: 'DELETE' });
    api.capture('SOFTWARE_EXCEPTION', 'after-req');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await sleep(30);
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-req');
    const methods = after.breadcrumbs.filter((b) => b.type === 'fetch').map((b) => b.method);
    expect(methods).toContain('POST');
    expect(methods).toContain('DELETE');
  });

  it('merges drained records on reconnect', async () => {
    installIdb({ records: [{ qid: 41, message: 'stale' }, 'junk'] });
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await sleep(40);
    api.capture('SOFTWARE_EXCEPTION', 'live');
    window.dispatchEvent(new Event('online'));
    await sleep(40);
    const bodies = await Promise.all(
      navigator.sendBeacon.mock.calls.map(([, blob]) => blob.text()),
    );
    const last = JSON.parse(bodies[bodies.length - 1]);
    expect(last.events.some((e) => e && e.message === 'live')).toBe(true);
  });

  it('flushes on the 30s interval', async () => {
    vi.useFakeTimers();
    global.fetch = fetchMock;
    const api = await importTelemetry();
    api.capture('SOFTWARE_EXCEPTION', 'tick');
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetchMock).toHaveBeenCalled();
  });
});
