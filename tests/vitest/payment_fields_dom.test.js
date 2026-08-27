import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Small DOM-backed jQuery seam: only the surface payment-fields.js uses
// (empty/html/val/on/length), wired against real jsdom elements.
function makeDOMJQuery() {
	const $ = (sel) => {
		const els =
			typeof sel === "string"
				? Array.from(document.querySelectorAll(sel))
				: [sel].filter(Boolean);
		return {
			length: els.length,
			empty: () => {
				els.forEach((el) => {
					el.innerHTML = "";
				});
				return $;
			},
			html: (h) => {
				els.forEach((el) => {
					el.innerHTML = h;
				});
				return $;
			},
			val: (v) => {
				if (v === undefined) return els[0] ? els[0].value : "";
				els.forEach((el) => {
					el.value = v;
				});
				return $;
			},
			on: (evt, handler) => {
				els.forEach((el) =>
					el.addEventListener(evt, function (...args) {
						handler.apply(this, args);
					}),
				);
				return $;
			},
		};
	};
	$.fn = {};
	return $;
}

describe('payment-fields.js (real DOM behavior)', () => {
	beforeEach(() => {
		document.body.innerHTML = `
      <div id="pay-fields"></div>
    `;
		global.$ = global.jQuery = makeDOMJQuery();
		vi.resetModules();
	});

	afterEach(() => {
		document.body.innerHTML = '';
		delete global.$;
		delete global.jQuery;
		vi.resetModules();
	});

	async function load() {
		await import('../../static/js/payment-fields.js');
		return window.PaymentFieldsManager;
	}

	it('exposes method catalogue with field metadata', async () => {
		const pm = await load();
		expect(Object.keys(pm.methods).sort()).toEqual([
			'bank_transfer',
			'card',
			'cash',
			'cheque',
			'credit',
			'e_wallet',
		]);
		expect(pm.methods.card.icon).toBe('fas fa-credit-card');
		expect(pm.methods.cheque.fields[0]).toMatchObject({
			name: 'cheque_number',
			required: true,
		});
	});

	it('getMethodInfo returns null for unknown methods', async () => {
		const pm = await load();
		expect(pm.getMethodInfo('nope')).toBeNull();
		expect(pm.getMethodInfo('card').color).toBe('primary');
	});

	it('render with empty/unknown method empties and leaves container blank', async () => {
		const pm = await load();
		document.getElementById('pay-fields').innerHTML = '<p>stale</p>';
		pm.render('', '#pay-fields');
		expect(document.getElementById('pay-fields').innerHTML).toBe('');
		pm.render('bogus', '#pay-fields');
		expect(document.getElementById('pay-fields').innerHTML).toBe('');
	});

	it('render cash shows an info alert that no extra fields are required', async () => {
		const pm = await load();
		pm.render('cash', '#pay-fields');
		const html = document.getElementById('pay-fields').innerHTML;
		expect(html).toContain('alert-success');
		expect(html).toContain('fa-money-bill-wave');
		expect(html).toContain('دفع نقدي');
		expect(html).not.toContain('<input');
	});

	it('render card builds select options + input constraints, none required', async () => {
		const pm = await load();
		pm.render('card', '#pay-fields');
		const root = document.getElementById('pay-fields');
		expect(root.textContent).toContain('آخر 4 أرقام البطاقة');
		const last4 = root.querySelector('[name="card_last4"]');
		expect(last4.getAttribute('maxlength')).toBe('4');
		expect(last4.getAttribute('pattern')).toBe('[0-9]{4}');
		expect(last4.getAttribute('placeholder')).toBe('1234');
		expect(last4.required).toBe(false);
		const typeSel = root.querySelector('select[name="card_type"]');
		const values = Array.from(typeSel.options).map((o) => o.value);
		expect(values).toEqual(['', 'visa', 'mastercard', 'amex', 'other']);
		expect(root.querySelector('[name="reference_number"]').getAttribute('placeholder')).toBe(
			'REF-123456',
		);
	});

	it('render bank_transfer with prefix emits required attrs and prefixed names', async () => {
		const pm = await load();
		pm.render('bank_transfer', '#pay-fields', 'payment');
		const ref = document.querySelector('[name="payment_reference_number"]');
		expect(ref).not.toBeNull();
		expect(ref.hasAttribute('required')).toBe(true);
		expect(document.querySelector('[name="payment_bank_name"]')).not.toBeNull();
		expect(document.querySelector('[name="payment_transfer_date"]').type).toBe('date');
	});

	it('collect gathers payment_method plus filled field values from the form', async () => {
		const pm = await load();
		pm.render('cheque', '#pay-fields');
		document.querySelector('[name="cheque_number"]').value = 'CHQ-1';
		document.querySelector('[name="bank_name"]').value = 'ENBD';
		const data = pm.collect('cheque', '#pay-fields');
		expect(data.payment_method).toBe('cheque');
		expect(data.cheque_number).toBe('CHQ-1');
		expect(data.bank_name).toBe('ENBD');
	});

	it('collect returns {} for unknown method', async () => {
		const pm = await load();
		expect(pm.collect('junk', '#pay-fields')).toEqual({});
	});

	it('populate writes values into matching fields and ignores blanks', async () => {
		const pm = await load();
		pm.render('card', '#pay-fields');
		pm.populate('card', { card_last4: '7777', card_type: 'visa', reference_number: '' });
		expect(document.querySelector('[name="card_last4"]').value).toBe('7777');
		expect(document.querySelector('[name="card_type"]').value).toBe('visa');
		expect(document.querySelector('[name="reference_number"]').value).toBe('');
	});

	it('populate no-ops for unknown method or missing data', async () => {
		const pm = await load();
		pm.render('e_wallet', '#pay-fields');
		expect(() => pm.populate('junk', { x: 1 }, '#pay-fields')).not.toThrow();
		expect(() => pm.populate('e_wallet', null, '#pay-fields')).not.toThrow();
	});

	it('initSelector renders on change events and for initial selection', async () => {
		document.body.innerHTML = `
      <select id="pm-select">
        <option value="">اختر...</option>
        <option value="e_wallet">E-Wallet</option>
        <option value="cheque">Cheque</option>
      </select>
      <div id="dyn"></div>
    `;
		const pm = await load();
		pm.initSelector('#pm-select', '#dyn');

		// No initial value → nothing rendered yet.
		expect(document.getElementById('dyn').textContent.trim()).toBe('');

		const sel = document.getElementById('pm-select');
		sel.value = 'e_wallet';
		sel.dispatchEvent(new Event('change'));
		expect(document.querySelector('#dyn [name="wallet_provider"]')).not.toBeNull();

		sel.value = 'cheque';
		sel.dispatchEvent(new Event('change'));
		expect(document.querySelector('#dyn [name="cheque_number"]')).not.toBeNull();
	});

	it('initSelector renders immediately when a method is preselected', async () => {
		document.body.innerHTML = `
      <select id="pm2"><option value="credit">Credit</option></select>
      <div id="dyn2"></div>
    `;
		const pm = await load();
		pm.initSelector('#pm2', '#dyn2');
		expect(document.querySelector('#dyn2 [name="credit_days"]')).not.toBeNull();
		// Default credit_days value attribute comes through.
		expect(document.querySelector('#dyn2 [name="credit_days"]').getAttribute('value')).toBe('30');
	});
});
