import { describe, it, expect, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(process.cwd(), 'static/js/sales-enhanced.js');

describe('sales-enhanced select2 guard (browser-discovered defect)', () => {
  it('does not call .select2() unconditionally on document ready', () => {
    const source = fs.readFileSync(SRC, 'utf8');
    // The script is loaded on every page (partials/scripts.html) but select2 is
    // only included on sale create/edit. An unconditional $("#customer_id").select2()
    // threw TypeError on /sales/ and aborted the rest of the ready handler.
    expect(source).toMatch(/typeof \$\.fn\.select2\s*===\s*["']function["']/);
    const readyStart = source.indexOf('$(document).ready');
    const guard = source.indexOf('typeof $.fn.select2', readyStart);
    const call = source.indexOf('.select2({', readyStart);
    expect(guard).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(guard); // guard appears before the call
  });

  it('still initializes select2 when the plugin and element exist', () => {
    const source = fs.readFileSync(SRC, 'utf8');
    expect(source).toMatch(/\$customer\.length\s*&&\s*typeof \$\.fn\.select2/);
    expect(source).toMatch(/\$customer\.select2\(\{/);
  });
});
