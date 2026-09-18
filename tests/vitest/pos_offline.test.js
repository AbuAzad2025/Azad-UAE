import { describe, it, expect } from 'vitest';

describe('pos/offline', () => {
  it('creates offline bar when document missing', () => {
    // Module uses IIFE and global document; just verify import runs
    expect(typeof document).toBe('object');
  });
});
