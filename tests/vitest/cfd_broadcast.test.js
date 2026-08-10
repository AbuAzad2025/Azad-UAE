import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let posted;
let OrigBC;

function defineBroadcastChannel() {
  OrigBC = global.BroadcastChannel;
  posted = [];
  global.BroadcastChannel = class {
    constructor(name) {
      this.name = name;
    }
    postMessage(msg) {
      posted.push(msg);
    }
    close() {}
  };
}

function undefineBroadcastChannel() {
  delete global.BroadcastChannel;
}

describe('pos/cfd-broadcast.js', () => {
  beforeEach(() => {
    delete window.cfdBroadcast;
    posted = [];
    vi.resetModules();
  });

  afterEach(() => {
    delete window.cfdBroadcast;
    if (OrigBC === undefined) delete global.BroadcastChannel;
    else global.BroadcastChannel = OrigBC;
    OrigBC = undefined;
    vi.resetModules();
  });

  it('exposes cfdBroadcast with setSession and sendCart', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    expect(typeof window.cfdBroadcast.setSession).toBe('function');
    expect(typeof window.cfdBroadcast.sendCart).toBe('function');
  });

  it('does not broadcast without a session id', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.sendCart([{ qty: 1, price: 5 }], {});
    expect(posted).toHaveLength(0);
  });

  it('posts a waiting message for an empty cart', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-1');
    window.cfdBroadcast.sendCart([], {});
    expect(posted).toHaveLength(1);
    expect(posted[0]).toEqual({ type: 'waiting', session_id: 'sess-1' });
  });

  it('posts a waiting message for a non-array cart', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-1');
    window.cfdBroadcast.sendCart(undefined, {});
    expect(posted[0]).toEqual({ type: 'waiting', session_id: 'sess-1' });
  });

  it('broadcasts a fully computed order_update payload', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-2');
    window.cfdBroadcast.sendCart(
      [
        { name: 'Cola', qty: 2, price: 3.5, discountPercent: 10 },
        { name: '', qty: '1', price: '2.0000', discountPercent: '0' },
      ],
      { discountAmount: 1, tax: 0.75, taxRate: 5, total: 8 }
    );
    expect(posted).toHaveLength(1);
    const msg = posted[0];
    expect(msg.type).toBe('order_update');
    expect(msg.live).toBe(true);
    expect(msg.session_id).toBe('sess-2');
    expect(msg.items).toHaveLength(2);
    expect(msg.items[0]).toEqual({
      name: 'Cola',
      quantity: 2,
      unit_price: 3.5,
      discount_percent: 10,
      discount_amount: 0.7,
      total: 6.3,
    });
    expect(msg.items[1]).toEqual({
      name: '—',
      quantity: 1,
      unit_price: 2,
      discount_percent: 0,
      discount_amount: 0,
      total: 2,
    });
    expect(msg.subtotal).toBe(9);
    expect(msg.discount_amount).toBe(1.7);
    expect(msg.taxable_amount).toBe(7.25);
    expect(msg.tax_breakdown.standard).toEqual({ base: 7.25, rate: 5, tax: 0.75 });
    expect(msg.tax_breakdown.zero_rated.base).toBe(0);
    expect(msg.total).toBe(8);
  });

  it('uses zero-rated breakdown when tax rate is zero', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-3');
    window.cfdBroadcast.sendCart(
      [{ name: 'Bread', qty: 1, price: 10, discountPercent: 0 }],
      { discountAmount: 2, tax: 0, taxRate: 0, subtotal: 10, total: 8 }
    );
    const msg = posted[0];
    expect(msg.tax_breakdown.standard).toEqual({ base: 0, rate: 0, tax: 0 });
    expect(msg.tax_breakdown.zero_rated).toEqual({ base: 8, tax: 0 });
    expect(msg.taxable_amount).toBe(8);
  });

  it('sanitises invalid numeric inputs to zero', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-4');
    window.cfdBroadcast.sendCart(
      [{ name: 'X', qty: 'abc', price: NaN, discountPercent: 'nope' }],
      { taxRate: 'x', total: Infinity }
    );
    const msg = posted[0];
    expect(msg.items[0].quantity).toBe(0);
    expect(msg.items[0].unit_price).toBe(0);
    expect(msg.items[0].discount_percent).toBe(0);
    expect(msg.total).toBe(0);
    expect(msg.tax_breakdown.standard.tax).toBe(0);
  });

  it('tolerates a missing BroadcastChannel', async () => {
    undefineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-5');
    expect(() => window.cfdBroadcast.sendCart([{ qty: 1, price: 2 }], {})).not.toThrow();
  });

  it('falls back to null when BroadcastChannel construction throws', async () => {
    global.BroadcastChannel = class {
      constructor() {
        throw new Error('no channel');
      }
    };
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-6');
    expect(() => window.cfdBroadcast.sendCart([{ qty: 1, price: 2 }], {})).not.toThrow();
    expect(posted).toHaveLength(0);
  });

  it('survives a crashing BroadcastChannel and disables the channel', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    global.BroadcastChannel.prototype.postMessage = function crash() {
      throw new Error('crashed tab');
    };
    window.cfdBroadcast.setSession('sess-7');
    // First send hits the throw and must not break the register.
    expect(() => window.cfdBroadcast.sendCart([{ qty: 1, price: 2 }], {})).not.toThrow();
    // Channel is now dropped — the second send is a no-op (would throw again otherwise).
    expect(() => window.cfdBroadcast.sendCart([{ qty: 1, price: 2 }], {})).not.toThrow();
  });

  it('derives zero-rated taxable from line discounts plus header discount', async () => {
    defineBroadcastChannel();
    await import('../../static/js/pos/cfd-broadcast.js');
    window.cfdBroadcast.setSession('sess-z');
    window.cfdBroadcast.sendCart(
      [{ name: 'Bread', qty: 2, price: 10, discountPercent: 10 }],
      { discountAmount: 1, tax: 0, taxRate: 0, total: 17 }
    );
    const msg = posted[0];
    // gross = 20, line discount = 2, header discount = 1 → taxable = 17
    expect(msg.taxable_amount).toBe(17);
    expect(msg.subtotal).toBe(20);
    expect(msg.discount_amount).toBe(3);
  });
});
