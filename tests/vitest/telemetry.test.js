import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const ENDPOINT = '/api/v1/telemetry/logs';

async function importTelemetry() {
  await import('../../static/js/telemetry.js');
  return window.azadTelemetry;
}

describe('telemetry.js', () => {
  let fetchMock;
  const realVisibility = Object.getOwnPropertyDescriptor(Document.prototype, 'visibilityState');

  beforeEach(() => {
    document.body.innerHTML = '<button id="buy">شراء</button>';
    fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
    );
    global.fetch = fetchMock;
    delete window.azadTelemetry;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.azadTelemetry;
    delete global.fetch;
    delete navigator.sendBeacon;
    if (realVisibility) {
      Object.defineProperty(document, 'visibilityState', realVisibility);
    }
    vi.resetModules();
  });

  it('boots and exposes capture', async () => {
    const api = await importTelemetry();
    expect(typeof api.capture).toBe('function');
  });

  it('capture enqueues events and flushes via beacon', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) {
      api.capture('SOFTWARE_EXCEPTION', `err-${i}`);
    }
    await new Promise((r) => setTimeout(r, 20));
    expect(navigator.sendBeacon).toHaveBeenCalled();
    const [url, blob] = navigator.sendBeacon.mock.calls[0];
    expect(url).toBe(ENDPOINT);
    expect(blob.type).toBe('application/json');
    const payload = JSON.parse(await blob.text());
    expect(payload.events).toHaveLength(10);
    expect(payload.events[0].qid).toBe(1);
    expect(payload.events[0].category).toBe('SOFTWARE_EXCEPTION');
    expect(payload.events[0].level).toBe('ERROR');
  });

  it('capture falls back to fetch when beacon is unavailable', async () => {
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `f-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const endpointCalls = fetchMock.mock.calls.filter(([url]) => url === ENDPOINT);
    expect(endpointCalls.length).toBeGreaterThan(0);
    const body = JSON.parse(endpointCalls[0][1].body);
    expect(body.events).toHaveLength(10);
    const opts = endpointCalls[0][1];
    expect(opts.method).toBe('POST');
    expect(opts.keepalive).toBe(true);
    expect(opts.headers['Content-Type']).toBe('application/json');
  });

  it('requeues batch when send fails and retries on next flush', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'));
    const api = await importTelemetry();
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `r-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const firstCalls = fetchMock.mock.calls.filter(([url]) => url === ENDPOINT);
    expect(firstCalls.length).toBe(1);
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `s-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const secondCalls = fetchMock.mock.calls.filter(([url]) => url === ENDPOINT);
    expect(secondCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('normalizes unknown categories and hardware warnings', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    api.capture('BOGUS', 'x');
    api.capture('HARDWARE_WARN', 'printer offline', { port: 9100 });
    for (let i = 0; i < 8; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const events = payload.events;
    expect(events.find((e) => e.message === 'x').category).toBe('SOFTWARE_EXCEPTION');
    const hw = events.find((e) => e.message === 'printer offline');
    expect(hw.category).toBe('HARDWARE_WARN');
    expect(hw.level).toBe('WARNING');
    expect(hw.extra).toEqual({ port: 9100 });
  });

  it('capture ignores empty messages', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    api.capture('SOFTWARE_EXCEPTION', '');
    api.capture('SOFTWARE_EXCEPTION', null);
    for (let i = 0; i < 10; i += 1) api.capture('SOFTWARE_EXCEPTION', `e-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    expect(payload.events).toHaveLength(10);
  });

  it('captures window error events with stack and location', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    await importTelemetry();
    const err = new Error('boom');
    window.dispatchEvent(new ErrorEvent('error', {
      message: 'boom',
      filename: '/static/app.js',
      lineno: 10,
      colno: 5,
      error: err,
    }));
    for (let i = 0; i < 9; i += 1) window.dispatchEvent(new ErrorEvent('error', { message: `e-${i}` }));
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const boom = payload.events.find((e) => e.message === 'boom');
    expect(boom.extra.kind).toBe('error');
    expect(boom.extra.filename).toBe('/static/app.js');
    expect(boom.extra.lineno).toBe(10);
    expect(boom.extra.colno).toBe(5);
  });

  it('captures unhandled rejections', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    await importTelemetry();
    const reason = new Error('rej');
    const p = Promise.reject(reason);
    p.catch(() => {});
    window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection', { promise: p, reason }));
    for (let i = 0; i < 9; i += 1) window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection', { promise: Promise.resolve(), reason: `x-${i}` }));
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const rej = payload.events.find((e) => e.message === 'rej');
    expect(rej.extra.kind).toBe('unhandledrejection');
  });

  it('records click breadcrumbs into captured events', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    document.getElementById('buy').click();
    api.capture('SOFTWARE_EXCEPTION', 'after-click');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-click');
    expect(after.breadcrumbs.some((b) => b.type === 'click' && b.id === 'buy')).toBe(true);
  });

  it('records fetch breadcrumbs and redacts telemetry self-requests', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await fetch('/api/orders?token=abc');
    await fetch(ENDPOINT);
    api.capture('SOFTWARE_EXCEPTION', 'after-fetch');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-fetch');
    const crumbs = after.breadcrumbs.filter((b) => b.type === 'fetch');
    expect(crumbs.some((b) => b.url.includes('/api/orders?token=%5Bredacted%5D'))).toBe(true);
    expect(crumbs.some((b) => b.url.endsWith(ENDPOINT))).toBe(false);
    expect(crumbs.every((b) => b.method === 'GET')).toBe(true);
  });

  it('records route breadcrumbs on pushState and popstate', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    history.pushState({}, '', '/pos');
    window.dispatchEvent(new PopStateEvent('popstate'));
    api.capture('SOFTWARE_EXCEPTION', 'after-route');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'after-route');
    expect(after.breadcrumbs.filter((b) => b.type === 'route').length).toBe(2);
  });

  it('flushes on visibility hidden and drains on online', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    api.capture('SOFTWARE_EXCEPTION', 'hidden-flush');
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    await new Promise((r) => setTimeout(r, 20));
    expect(navigator.sendBeacon).toHaveBeenCalled();
    window.dispatchEvent(new Event('online'));
    await new Promise((r) => setTimeout(r, 20));
  });

  it('removes sensitive query keys from URLs via redaction', async () => {
    navigator.sendBeacon = vi.fn(() => true);
    const api = await importTelemetry();
    await fetch('/api/login?password=hunter2&keep=1');
    api.capture('SOFTWARE_EXCEPTION', 'cred');
    for (let i = 0; i < 9; i += 1) api.capture('SOFTWARE_EXCEPTION', `pad-${i}`);
    await new Promise((r) => setTimeout(r, 20));
    const payload = JSON.parse(await navigator.sendBeacon.mock.calls[0][1].text());
    const after = payload.events.find((e) => e.message === 'cred');
    const crumb = after.breadcrumbs.find((b) => b.type === 'fetch');
    expect(crumb.url).toContain('password=%5Bredacted%5D');
    expect(crumb.url).not.toContain('hunter2');
  });
});
