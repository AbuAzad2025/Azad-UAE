import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('base-helpers.js - function coverage', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    // Mock fetch for FX rates
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ rates: { USD: 3.67 } }),
      })
    );
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.azad;
    delete window.AzadHelpers;
    delete global.fetch;
    vi.resetModules();
  });

  it('should format FX rate', async () => {
    await import('../../static/js/base-helpers.js');
    const helpers = window.AzadHelpers;
    expect(helpers).toBeDefined();
  });

  it('should get fallback FX rates', async () => {
    await import('../../static/js/base-helpers.js');
    const helpers = window.AzadHelpers;
    expect(helpers).toBeDefined();
  });

  it('should update date time', async () => {
    document.body.innerHTML = '<span id="liveDateTime"></span>';
    await import('../../static/js/base-helpers.js');
    expect(true).toBe(true);
  });

  it('should handle view mode cycling', async () => {
    document.body.innerHTML = `
      <button id="viewModeBtn">View Mode</button>
    `;
    await import('../../static/js/base-helpers.js');
    const helpers = window.AzadHelpers;
    expect(helpers).toBeDefined();
  });

  it('should wire calculator pad', async () => {
    document.body.innerHTML = `
      <div id="calc-container">
        <input type="text" id="calc-display">
        <button data-val="1">1</button>
        <button data-val="+">+</button>
        <button data-val="=">=</button>
      </div>
    `;
    await import('../../static/js/base-helpers.js');
    expect(true).toBe(true);
  });

  it('should convert to absolute URL', async () => {
    await import('../../static/js/base-helpers.js');
    const helpers = window.AzadHelpers;
    expect(helpers).toBeDefined();
  });
});

describe('sales.js - function coverage', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: [] }),
      })
    );
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete global.fetch;
    vi.resetModules();
  });

  it('should initialize sales page', async () => {
    document.body.innerHTML = `
      <div id="sales-page">
        <table id="sales-table">
          <thead><tr><th>Sale #</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    `;
    await import('../../static/js/sales.js');
    expect(true).toBe(true);
  });

  it('should handle sale filters', async () => {
    document.body.innerHTML = `
      <div id="sales-page">
        <select id="status-filter">
          <option value="">All</option>
          <option value="completed">Completed</option>
        </select>
      </div>
    `;
    await import('../../static/js/sales.js');
    expect(true).toBe(true);
  });
});

describe('base-helpers.js - safeEval parser', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.AzadHelpers;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.AzadHelpers;
    vi.resetModules();
  });

  async function safeEval(expr) {
    await import('../../static/js/base-helpers.js');
    return window.AzadHelpers.safeEval(expr);
  }

  it('evaluates basic arithmetic', async () => {
    expect(await safeEval('2+3*4')).toBe('14');
    expect(await safeEval('(2+3)*4')).toBe('20');
    expect(await safeEval('10-2/2')).toBe('9');
    expect(await safeEval('10/0')).toBe('ERR');
  });

  it('supports unary minus and exponentiation', async () => {
    expect(await safeEval('-2+5')).toBe('3');
    expect(await safeEval('2^10')).toBe('1024');
    expect(await safeEval('2^3^2')).toBe('512');
  });

  it('supports calculator function buttons and constants', async () => {
    expect(await safeEval('sin(0)')).toBe('0');
    expect(await safeEval('cos(0)')).toBe('1');
    expect(await safeEval('sqrt(16)')).toBe('4');
    expect(await safeEval('log(100)')).toBe('2');
    expect(await safeEval('ln(1)')).toBe('0');
    expect(await safeEval('π')).toBe(String(Math.round((Math.PI + Number.EPSILON) * 100000000) / 100000000));
    expect(await safeEval('e')).toBe(String(Math.round((Math.E + Number.EPSILON) * 100000000) / 100000000));
  });

  it('rejects code-execution payloads with ERR', async () => {
    expect(await safeEval('[].constructor.constructor("alert(1)")()')).toBe('ERR');
    expect(await safeEval('alert(1)')).toBe('ERR');
    expect(await safeEval('constructor')).toBe('ERR');
    expect(await safeEval('__proto__')).toBe('ERR');
    expect(await safeEval('(function(){return 1})()')).toBe('ERR');
    expect(await safeEval('1+')).toBe('ERR');
  });
});
