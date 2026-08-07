import { describe, it, expect } from 'vitest';

describe('escpos-printer.js', () => {
  let buildReceiptBytes;
  let EscposPrinter;

  beforeAll(async () => {
    const mod = await import('../../static/js/pos/escpos-printer.js');
    buildReceiptBytes = mod.buildReceiptBytes;
    EscposPrinter = mod.EscposPrinter;
  });

  it('buildReceiptBytes starts with init command', () => {
    const out = buildReceiptBytes({ lines: [] });
    expect([out[0], out[1]]).toEqual([0x1b, 0x40]);
  });

  it('centered bold line has alignment and emphasis bytes', () => {
    const out = buildReceiptBytes({ lines: [{ text: 'Hi', align: 'center', bold: true }] });
    const arr = [...out];
    expect(arr).toContain(0x1b);
    // ESC a 01 center
    expect(arr.join(',')).toContain([0x1b, 0x61, 0x01].join(','));
    // ESC E 01 bold on
    expect(arr.join(',')).toContain([0x1b, 0x45, 0x01].join(','));
  });

  it('double size emits GS ! 0x11', () => {
    const out = buildReceiptBytes({ lines: [{ text: 'Big', double: true }] });
    expect([...out].join(',')).toContain([0x1d, 0x21, 0x11].join(','));
  });

  it('separator line renders dashes', () => {
    const out = buildReceiptBytes({ lines: [{ separator: true }] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('--------------------------------');
  });

  it('adds feed lines', () => {
    const out = buildReceiptBytes({ lines: [], feed: 3 });
    const arr = [...out];
    const feedLines = arr.filter(b => b === 0x0a).length;
    expect(feedLines).toBeGreaterThanOrEqual(3);
  });

  it('adds open_drawer command when requested', () => {
    const out = buildReceiptBytes({ lines: [], open_drawer: true });
    const arr = [...out];
    expect(arr.join(',')).toContain([0x1b, 0x70, 0x00, 0x19, 0xfa].join(','));
  });

  it('adds cut command by default', () => {
    const out = buildReceiptBytes({ lines: [] });
    const arr = [...out];
    // GS V 0x00 cut
    expect(arr.includes(0x1d)).toBe(true);
    expect(arr.includes(0x56)).toBe(true);
  });

  it('can disable cut', () => {
    const withCut = buildReceiptBytes({ lines: [] });
    const withoutCut = buildReceiptBytes({ lines: [], cut: false });
    expect(withoutCut.length).toBeLessThan(withCut.length);
  });

  it('handles string lines', () => {
    const out = buildReceiptBytes({ lines: ['Hello', 'World'] });
    const text = new TextDecoder().decode(out);
    expect(text).toContain('Hello');
    expect(text).toContain('World');
  });
});
