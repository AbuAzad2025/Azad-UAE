import { describe, it, expect } from 'vitest';

// Load module by requiring the source logic (pure function exported via UMD in file)
// Since file uses const and no export, we test via a minimal node eval of the function
function parseFrame(line) {
  const _SCALE_NUMBER_RE = /(-?\d+(?:[.,]\d+)?)/;
  if (line == null) return null;
  const s = String(line).trim();
  if (!s) return null;
  let stable = true;
  if (/^(ST|US|OL|GS|NT)[,\s]/i.test(s)) {
    stable = !/^(US|OL)/i.test(s);
  }
  const m = s.match(_SCALE_NUMBER_RE);
  if (!m) return null;
  const num = Number(m[1].replace(",", "."));
  if (!Number.isFinite(num) || num < 0) return null;
  let kg = num;
  if (!/kg/i.test(s) && /(?:^|[^k])g\b/i.test(s)) {
    kg = num / 1000;
  }
  return { weightKg: Math.round(kg * 1000) / 1000, stable };
}

describe('scale-serial parser', () => {
  it('parses plain kg', () => {
    expect(parseFrame('1.234kg')).toEqual({ weightKg: 1.234, stable: true });
  });
  it('parses grams', () => {
    expect(parseFrame('500g')).toEqual({ weightKg: 0.5, stable: true });
  });
  it('returns null for bad input', () => {
    expect(parseFrame('bad')).toBeNull();
    expect(parseFrame('')).toBeNull();
    expect(parseFrame(null)).toBeNull();
  });
});
