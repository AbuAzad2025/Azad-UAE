import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('base-helpers.js - calculator pad', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  async function loadWithCalcDOM() {
    document.body.innerHTML = `
      <input id="calcDisplayClassic" value="0" />
      <div id="calcClassicButtons"></div>
      <input id="calcDisplayScientific" value="0" />
      <div id="calcScientificButtons"></div>
      <button id="btnLoanCalc"></button>
      <input id="loanPrincipal" value="10000" />
      <input id="loanRate" value="5" />
      <input id="loanMonths" value="12" />
      <div id="loanResult"></div>
      <button id="btnMarginCalc"></button>
      <input id="costValue" value="80" />
      <input id="sellValue" value="100" />
      <div id="marginResult"></div>
    `;
    await import('../../static/js/base-helpers.js');
    return window.AzadHelpers;
  }

  function clickCalc(container, label) {
    const btn = container.querySelector(`[data-calc="${label}"]`);
    if (!btn) throw new Error(`Button ${label} not found`);
    btn.click();
  }

  it('wires classic calculator buttons and evaluates expressions', async () => {
    await loadWithCalcDOM();
    const display = document.getElementById('calcDisplayClassic');
    const container = document.getElementById('calcClassicButtons');

    clickCalc(container, '7');
    clickCalc(container, '+');
    clickCalc(container, '3');
    expect(display.value).toBe('7+3');

    clickCalc(container, '=');
    expect(display.value).toBe('10');
  });

  it('calculator C clears display to 0', async () => {
    await loadWithCalcDOM();
    const display = document.getElementById('calcDisplayClassic');
    const container = document.getElementById('calcClassicButtons');

    clickCalc(container, '9');
    expect(display.value).toBe('9');
    clickCalc(container, 'C');
    expect(display.value).toBe('0');
  });

  it('calculator DEL removes last character', async () => {
    await loadWithCalcDOM();
    const display = document.getElementById('calcDisplayClassic');
    const container = document.getElementById('calcClassicButtons');

    clickCalc(container, '1');
    clickCalc(container, '2');
    clickCalc(container, '3');
    expect(display.value).toBe('123');

    clickCalc(container, 'DEL');
    expect(display.value).toBe('12');

    clickCalc(container, 'C');
    clickCalc(container, 'DEL');
    expect(display.value).toBe('0');
  });

  it('scientific calculator supports functions and constants', async () => {
    await loadWithCalcDOM();
    const display = document.getElementById('calcDisplayScientific');
    const container = document.getElementById('calcScientificButtons');

    clickCalc(container, 'sin(');
    clickCalc(container, '0');
    clickCalc(container, ')');
    clickCalc(container, '=');
    expect(display.value).toBe('0');
  });

  it('loan calculator shows warning for invalid inputs', async () => {
    await loadWithCalcDOM();
    document.getElementById('loanPrincipal').value = '0';
    document.getElementById('loanMonths').value = '0';
    document.getElementById('btnLoanCalc').click();

    const result = document.getElementById('loanResult');
    expect(result.className).toContain('alert-warning');
    expect(result.textContent).toContain('أدخل قيم صحيحة');
  });

  it('loan calculator computes EMI for valid inputs', async () => {
    await loadWithCalcDOM();
    document.getElementById('loanPrincipal').value = '12000';
    document.getElementById('loanRate').value = '6';
    document.getElementById('loanMonths').value = '12';
    document.getElementById('btnLoanCalc').click();

    const result = document.getElementById('loanResult');
    expect(result.className).toContain('alert-info');
    expect(result.textContent).toContain('القسط:');
    expect(result.textContent).toContain('الفائدة:');
    expect(result.textContent).toContain('الإجمالي:');
  });

  it('loan calculator handles zero interest rate', async () => {
    await loadWithCalcDOM();
    document.getElementById('loanPrincipal').value = '12000';
    document.getElementById('loanRate').value = '0';
    document.getElementById('loanMonths').value = '12';
    document.getElementById('btnLoanCalc').click();

    const result = document.getElementById('loanResult');
    expect(result.className).toContain('alert-info');
    expect(result.textContent).toContain('1000');
  });

  it('margin calculator shows warning for invalid inputs', async () => {
    await loadWithCalcDOM();
    document.getElementById('costValue').value = '-10';
    document.getElementById('sellValue').value = '0';
    document.getElementById('btnMarginCalc').click();

    const result = document.getElementById('marginResult');
    expect(result.className).toContain('alert-warning');
    expect(result.textContent).toContain('أدخل قيم صحيحة');
  });

  it('margin calculator computes profit, margin and markup', async () => {
    await loadWithCalcDOM();
    document.getElementById('costValue').value = '80';
    document.getElementById('sellValue').value = '100';
    document.getElementById('btnMarginCalc').click();

    const result = document.getElementById('marginResult');
    expect(result.className).toContain('alert-success');
    expect(result.textContent).toContain('20.00');
    expect(result.textContent).toContain('Margin:');
    expect(result.textContent).toContain('Markup:');
  });

  it('margin calculator handles zero cost (markup = 0)', async () => {
    await loadWithCalcDOM();
    document.getElementById('costValue').value = '0';
    document.getElementById('sellValue').value = '100';
    document.getElementById('btnMarginCalc').click();

    const result = document.getElementById('marginResult');
    expect(result.className).toContain('alert-success');
    expect(result.textContent).toContain('Markup: 0.00%');
  });

  it('wirePad is a no-op when container or display missing', async () => {
    document.body.innerHTML = `
      <input id="calcDisplayClassic" value="0" />
      <div id="calcClassicButtons"></div>
    `;
    await import('../../static/js/base-helpers.js');
    expect(window.AzadHelpers).toBeDefined();
  });
});

describe('base-helpers.js - view mode system', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.className = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.body.className = '';
    delete window.azad;
    delete window.AzadHelpers;
    vi.resetModules();
  });

  async function loadWithViewDOM() {
    document.body.innerHTML = `
      <button data-ui-action="toggle-viewmode">
        <i data-ui-role="viewmode-icon" class="fas fa-desktop"></i>
        <span data-ui-role="viewmode-label">تلقائي</span>
      </button>
    `;
    await import('../../static/js/base-helpers.js');
    return window.AzadHelpers;
  }

  it('getSavedViewMode reads from localStorage', async () => {
    const store = {};
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k) => store[k] || null,
        setItem: (k, v) => { store[k] = v; },
        removeItem: (k) => { delete store[k]; },
      },
      writable: true,
      configurable: true,
    });
    store['azad_view_mode'] = 'mobile';

    const helpers = await loadWithViewDOM();
    expect(helpers.getSavedViewMode()).toBe('mobile');
  });

  it('getSavedViewMode defaults to auto when localStorage empty', async () => {
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
      writable: true,
      configurable: true,
    });

    const helpers = await loadWithViewDOM();
    expect(helpers.getSavedViewMode()).toBe('auto');
  });

  it('setViewMode updates body classes and localStorage', async () => {
    const store = {};
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k) => store[k] || null,
        setItem: (k, v) => { store[k] = v; },
        removeItem: (k) => { delete store[k]; },
      },
      writable: true,
      configurable: true,
    });

    const helpers = await loadWithViewDOM();
    helpers.setViewMode('mobile');

    expect(document.body.classList.contains('view-mobile')).toBe(true);
    expect(document.body.classList.contains('view-desktop')).toBe(false);
    expect(store['azad_view_mode']).toBe('mobile');
  });

  it('setViewMode falls back to auto for invalid mode', async () => {
    const store = {};
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k) => store[k] || null,
        setItem: (k, v) => { store[k] = v; },
        removeItem: (k) => { delete store[k]; },
      },
      writable: true,
      configurable: true,
    });

    const helpers = await loadWithViewDOM();
    helpers.setViewMode('invalid');

    expect(document.body.classList.contains('view-mobile')).toBe(false);
    expect(document.body.classList.contains('view-desktop')).toBe(false);
    expect(store['azad_view_mode']).toBe('auto');
  });

  it('setViewMode updates button icon and label', async () => {
    const helpers = await loadWithViewDOM();
    helpers.setViewMode('mobile');

    const icon = document.querySelector('[data-ui-role="viewmode-icon"]');
    const label = document.querySelector('[data-ui-role="viewmode-label"]');
    expect(icon.classList.contains('fa-mobile-alt')).toBe(true);
    expect(label.textContent).toBe('جوال');
  });

  it('cycleViewMode cycles through auto -> desktop -> mobile -> auto', async () => {
    const store = { 'azad_view_mode': 'auto' };
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k) => store[k] || null,
        setItem: (k, v) => { store[k] = v; },
        removeItem: (k) => { delete store[k]; },
      },
      writable: true,
      configurable: true,
    });

    const helpers = await loadWithViewDOM();
    helpers.cycleViewMode();
    expect(store['azad_view_mode']).toBe('desktop');

    helpers.cycleViewMode();
    expect(store['azad_view_mode']).toBe('mobile');

    helpers.cycleViewMode();
    expect(store['azad_view_mode']).toBe('auto');
  });
});

describe('base-helpers.js - telemetry', () => {
  let originalFetch;

  beforeEach(() => {
    document.body.innerHTML = '<meta name="csrf-token" content="test-csrf">';
    document.documentElement.dataset.uiMode = 'light';
    document.documentElement.dataset.uiVariant = 'palestinian';
    delete window.azad;
    delete window.AzadHelpers;
    originalFetch = vi.fn(() => Promise.resolve({ ok: true }));
    window._LOG_ENDPOINT = 'http://localhost/log';
    window.fetch = originalFetch;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete document.documentElement.dataset.uiMode;
    delete document.documentElement.dataset.uiVariant;
    delete window.azad;
    delete window.AzadHelpers;
    delete window._LOG_ENDPOINT;
    vi.resetModules();
  });

  async function loadWithTelemetry() {
    await import('../../static/js/base-helpers.js');
    return window.AzadHelpers;
  }

  function getFetchCalls() {
    return originalFetch.mock.calls;
  }

  it('sendError posts to _LOG_ENDPOINT', async () => {
    await loadWithTelemetry();
    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Test error',
      filename: 'test.js',
      lineno: 10,
      colno: 5,
    }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    expect(calls.length).toBeGreaterThanOrEqual(1);
    const [url, options] = calls[0];
    expect(url).toBe('http://localhost/log');
    expect(options.method).toBe('POST');
    const body = JSON.parse(options.body);
    expect(body.type).toBe('runtime');
    expect(body.message).toBe('Test error');
    expect(body.source).toBe('test.js');
    expect(body.lineno).toBe(10);
  });

  it('sendError deduplicates repeated errors within window', async () => {
    await loadWithTelemetry();

    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Duplicate error',
      filename: 'test.js',
      lineno: 1,
    }));
    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Duplicate error',
      filename: 'test.js',
      lineno: 1,
    }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  it('sendError skips opaque script errors', async () => {
    await loadWithTelemetry();

    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Script error.',
      filename: '',
      lineno: 0,
      colno: 0,
    }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    const runtimeCalls = calls.filter(([, opts]) => {
      try {
        const body = JSON.parse(opts.body);
        return body.type === 'runtime';
      } catch (_) { return false; }
    });
    expect(runtimeCalls.length).toBe(0);
  });

  it('fetch wrapper reports failed fetch requests', async () => {
    const failingFetch = vi.fn(() => Promise.resolve({ ok: false, status: 500, headers: { get: () => '' } }));
    window.fetch = failingFetch;
    await loadWithTelemetry();

    await window.fetch('/api/test');

    await new Promise((r) => setTimeout(r, 10));

    expect(failingFetch.mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('fetch wrapper reports slow requests', async () => {
    const slowFetch = vi.fn(() => new Promise((resolve) => {
      setTimeout(() => resolve({ ok: true, status: 200, headers: { get: () => '' } }), 10);
    }));
    window.fetch = slowFetch;

    const origPerf = window.performance;
    window.performance = {
      now: vi.fn(() => 6000),
    };

    await loadWithTelemetry();
    await window.fetch('/api/slow');

    window.performance = origPerf;
    await new Promise((r) => setTimeout(r, 10));

    expect(slowFetch.mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('resource load errors send resource type telemetry', async () => {
    await loadWithTelemetry();

    const img = document.createElement('img');
    img.src = '/broken.png';
    document.body.appendChild(img);

    img.dispatchEvent(new Event('error', { bubbles: true }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    const resourceCalls = calls.filter(([, opts]) => {
      try {
        const body = JSON.parse(opts.body);
        return body.type === 'resource';
      } catch (_) { return false; }
    });
    expect(resourceCalls.length).toBeGreaterThanOrEqual(1);
  });

  it('unhandledrejection sends promise type telemetry', async () => {
    await loadWithTelemetry();

    const reason = new Error('Promise rejected');
    window.dispatchEvent(new Event('unhandledrejection', {
      reason,
    }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    const promiseCalls = calls.filter(([, opts]) => {
      try {
        const body = JSON.parse(opts.body);
        return body.type === 'promise';
      } catch (_) { return false; }
    });
    expect(promiseCalls.length).toBeGreaterThanOrEqual(1);
  });

  it('sendError includes client context', async () => {
    await loadWithTelemetry();

    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Context test',
      filename: 'ctx.js',
      lineno: 5,
    }));

    await new Promise((r) => setTimeout(r, 10));

    const calls = getFetchCalls();
    expect(calls.length).toBeGreaterThanOrEqual(1);
    const [, options] = calls[0];
    const body = JSON.parse(options.body);
    expect(body.client).toBeDefined();
    expect(body.client.online).toBe(true);
    expect(body.client.active_requests).toBe(0);
  });
});
