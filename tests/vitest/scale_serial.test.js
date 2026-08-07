import { describe, it, expect } from 'vitest';

describe('scale-serial.js', () => {
  let parseScaleFrame;

  beforeAll(async () => {
    const mod = await import('../../static/js/pos/scale-serial.js');
    parseScaleFrame = mod.parseScaleFrame;
  });

  it('returns null for null/empty input', () => {
    expect(parseScaleFrame(null)).toBeNull();
    expect(parseScaleFrame('')).toBeNull();
    expect(parseScaleFrame('   ')).toBeNull();
  });

  it('parses plain numeric weight', () => {
    const result = parseScaleFrame('1.234');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(1.234, 3);
    expect(result.stable).toBe(true);
  });

  it('parses A&D-style stable header', () => {
    const result = parseScaleFrame('ST,GS,+  1.234kg');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(1.234, 3);
    expect(result.stable).toBe(true);
  });

  it('parses A&D-style unstable header', () => {
    const result = parseScaleFrame('US,NT,- 0.500kg');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(0.5, 3);
    expect(result.stable).toBe(false);
  });

  it('parses gram-denominated frames', () => {
    const result = parseScaleFrame('500g');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(0.5, 3);
  });

  it('handles comma decimal separator', () => {
    const result = parseScaleFrame('1,234');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(1.234, 3);
  });

  it('returns null for non-numeric input', () => {
    expect(parseScaleFrame('abc')).toBeNull();
    expect(parseScaleFrame('ST,GS,abc')).toBeNull();
  });

  it('returns null for negative values', () => {
    expect(parseScaleFrame('-1.5')).toBeNull();
  });

  it('rounds to 3 decimal places', () => {
    const result = parseScaleFrame('1.234567');
    expect(result).not.toBeNull();
    expect(result.weightKg).toBeCloseTo(1.235, 3);
  });
});
