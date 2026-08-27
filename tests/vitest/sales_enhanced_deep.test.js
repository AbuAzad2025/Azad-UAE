import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * Minimal jQuery seam backed by real jsdom elements. Covers the exact
 * operations sales-enhanced.js performs: traversal (find/closest/prev),
 * content (html/text/val), attributes/classes/data, delegated events,
 * style, plus tolerant no-op chains for vendor widgets (select2/modal/focus).
 */
function makeDOMJQuery() {
	const dataStore = new WeakMap();
	const calls = [];

	function wrap(els) {
		const list = Array.isArray(els) ? els.filter(Boolean) : [els].filter(Boolean);
		const api = {
			length: list.length,
			__els: list,
			each(fn) {
				list.forEach((el, i) => fn.call(el, i, el));
				return api;
			},
			find(sel) {
				const out = [];
				list.forEach((el) => out.push(...Array.from(el.querySelectorAll(sel))));
				return wrap(out);
			},
			closest(sel) {
				return wrap(list.map((el) => el.closest(sel)).filter(Boolean));
			},
			prev() {
				return wrap(list.map((el) => el.previousElementSibling).filter(Boolean));
			},
			append(arg) {
				list.forEach((el) => {
					if (typeof arg === 'string') {
						el.insertAdjacentHTML('beforeend', arg);
					} else if (arg && arg.__els) {
						arg.__els.forEach((child) => el.appendChild(child));
					} else if (arg instanceof Node) {
						el.appendChild(arg);
					}
				});
				return api;
			},
			html(arg) {
				if (arg === undefined) return list[0] ? list[0].innerHTML : '';
				list.forEach((el) => {
					el.innerHTML = arg;
				});
				return api;
			},
			text(arg) {
				if (arg === undefined) return list[0] ? list[0].textContent : '';
				list.forEach((el) => {
					el.textContent = String(arg);
				});
				return api;
			},
			val(arg) {
				if (arg === undefined) return list[0] ? list[0].value : '';
				list.forEach((el) => {
					el.value = String(arg);
				});
				return api;
			},
			attr(name, valArg) {
				if (valArg === undefined)
					return list[0] ? list[0].getAttribute(name) : undefined;
				list.forEach((el) => el.setAttribute(name, String(valArg)));
				return api;
			},
			prop(name, valArg) {
				if (valArg === undefined) return list[0] ? list[0][name] : undefined;
				list.forEach((el) => {
					el[name] = valArg;
				});
				return api;
			},
			data(key, valArg) {
				if (valArg === undefined) {
					if (!list[0]) return undefined;
					const store = dataStore.get(list[0]);
					if (store && Object.prototype.hasOwnProperty.call(store, key)) return store[key];
					const camel = String(key).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
					return list[0].dataset ? list[0].dataset[camel] : undefined;
				}
				list.forEach((el) => {
					const store = dataStore.get(el) || {};
					store[key] = valArg;
					dataStore.set(el, store);
				});
				return api;
			},
			addClass(names) {
				list.forEach((el) => String(names).split(/\s+/).forEach((c) => c && el.classList.add(c)));
				return api;
			},
			removeClass(names) {
				list.forEach((el) =>
					String(names).split(/\s+/).forEach((c) => c && el.classList.remove(c)),
				);
				return api;
			},
			hasClass(name) {
				return Boolean(list[0] && list[0].classList.contains(name));
			},
			css(propName, valArg) {
				if (valArg !== undefined) {
					list.forEach((el) => {
						el.style[propName] = valArg;
					});
					return api;
				}
				return list[0] ? list[0].style[propName] : undefined;
			},
			show() {
				list.forEach((el) => {
					el.style.display = 'block';
				});
				return api;
			},
			hide() {
				list.forEach((el) => {
					el.style.display = 'none';
				});
				return api;
			},
			remove() {
				list.forEach((el) => el.parentNode && el.parentNode.removeChild(el));
				return api;
			},
			empty() {
				list.forEach((el) => {
					el.innerHTML = '';
				});
				return api;
			},
			on(...args) {
				let evtNames;
				let selector = null;
				let handler;
				if (typeof args[0] === 'string' && typeof args[1] === 'function') {
					evtNames = args[0];
					handler = args[1];
				} else if (typeof args[1] === 'string' && typeof args[2] === 'function') {
					evtNames = args[0];
					selector = args[1];
					handler = args[2];
				} else {
					return api;
				}
				const names = evtNames.split(/\s+/).filter(Boolean);
				names.forEach((evtName) => {
					list.forEach((el) =>
						el.addEventListener(evtName, function (...evArgs) {
							if (selector) {
								const hit =
									evArgs[0].target instanceof Element &&
									evArgs[0].target.closest(selector);
								if (!hit) return;
							}
							handler.apply(this, evArgs);
						}),
					);
				});
				return api;
			},
			trigger(evt, params) {
				const e = new Event(evt);
				e.params = params;
				list.forEach((el) => el.dispatchEvent(e));
				return api;
			},
			focus() {
				if (list[0] && list[0].focus) list[0].focus();
				return api;
			},
		};
		const proxy = new Proxy(api, {
			get(target, prop) {
				if (prop in target) return target[prop];
				if (typeof prop === 'symbol') return undefined;
				if (/^\d+$/.test(prop)) return target.__els[Number(prop)];
				if (prop === 'then') return undefined;
				return (...args) => {
					calls.push({ sel: target.__sel || null, method: String(prop), args });
					return proxy;
				};
			},
		});
		return proxy;
	}

	function $(sel) {
		if (typeof sel === 'string') {
			if (sel.trimStart().startsWith('<')) {
				const tpl = document.createElement('template');
				tpl.innerHTML = sel.trim();
				return wrap(tpl.content.firstElementChild);
			}
			return wrap(Array.from(document.querySelectorAll(sel)));
		}
		if (sel && sel.__els) return wrap(sel.__els.flat());
		if (sel instanceof Node || sel === document || sel === window) {
			const api = wrap([sel]);
			api.ready = (fn) => {
				fn();
				return api;
			};
			return api;
		}
		return wrap([]);
	}
	$.fn = {};
	$.calls = calls;
	$.ajaxHandlers = [];
	$.ajax = (opts) => {
		calls.push({ method: 'ajax', args: [opts] });
		$.ajaxHandlers.push(opts);
	};
	return $;
}

function flush() {
	return new Promise((resolve) => setTimeout(resolve, 0));
}

const MODAL_HTML = `
  <div id="serialNumberModal">
    <span id="serial_product_name"></span>
    <span id="serial_quantity_needed"></span>
    <ul id="serial_list"></ul>
    <span id="serial_count"></span>
    <input id="serial_input" type="text" />
    <button id="add_serial_btn">+</button>
    <button id="generate_serial_btn">gen</button>
    <button id="print_serials_btn">print</button>
    <button id="save_serials_btn">save</button>
  </div>
`;

function pageHTML(withModal = true, customerValue = '') {
	return `
    <form id="saleForm">
      <input type="hidden" name="csrf_token" value="t">
      <select id="customer_id"><option value="">-</option></select>
      <div id="linesContainer"></div>
      <input type="hidden" id="line_count" value="0" name="line_count">
      <input name="discount_amount" value="0">
      <input name="shipping_cost" value="0">
      <input name="tax_rate" value="0">
      <span id="subtotal"></span><span id="total"></span><span id="line_count_display"></span>
      <span id="discount_currency"></span><span id="shipping_currency"></span><span id="total_currency_label"></span>
      <span id="payment_currency_display"></span>
      <input id="exchange_rate" value="">
      <select id="currency">
        <option value="AED">AED</option><option value="EGP">EGP</option>
        <option value="SAR">SAR</option><option value="JOD">JOD</option>
        <option value="KWD">KWD</option>
      </select>
      <div id="payment_fields_container"></div>
      <div id="payment_amount_group"></div>
      <select id="payment_method">
        <option value="">اختر</option><option value="card">card</option>
        <option value="cheque">cheque</option>
      </select>
      ${withModal ? MODAL_HTML : ''}
      <button type="submit">submit</button>
    </form>`;
}

let azadStubs;

beforeEach(() => {
	document.body.innerHTML = pageHTML(true);
	let meta = document.querySelector('meta[name="csrf-token"]');
	if (!meta) {
		meta = document.createElement('meta');
		meta.setAttribute('name', 'csrf-token');
		document.head.appendChild(meta);
	}
	meta.setAttribute('content', 'tok');

	delete window.SmartSelectors;
	window._CURRENCY_SYMBOL = 'د.إ';
	window._FX_FALLBACK_BASE = 'AED';
	delete window._CURRENCY_NAME_AR;

	azadStubs = {
		formatNumber: vi.fn((n) => String(n)),
		showError: vi.fn(),
		showWarning: vi.fn(),
		showInfo: vi.fn(),
		showSuccess: vi.fn(),
		showLoading: vi.fn(),
		hideLoading: vi.fn(),
	};
	window.azad = azadStubs;

	global.$ = makeDOMJQuery();
	global.jQuery = global.$;
	global.fetch = vi.fn(() =>
		Promise.resolve({
			ok: true,
			json: () =>
				Promise.resolve({
					success: true,
					data: { subtotal: 100, total: 100, tax_amount: 0, line_count: 1 },
				}),
		}),
	);

	vi.resetModules();
});

afterEach(() => {
	document.body.innerHTML = '';
	delete window.azad;
	delete window.SmartSelectors;
	delete global.fetch;
	delete global.$;
	delete global.jQuery;
	vi.useRealTimers();
	vi.resetModules();
});

describe('sales-enhanced.js deep behaviors', () => {
	async function load() {
		await import('../../static/js/sales-enhanced.js');
	}
	async function loadWithLine0(stock = '') {
		await load();
		expect(document.getElementById('line_0')).not.toBeNull();
	}

	it('document ready bootstraps first line and counter', async () => {
		await load();
		const line = document.getElementById('line_0');
		expect(line).not.toBeNull();
		expect(document.getElementById('line_count').value).toBe('1');
		const select = document.querySelector('#line_0 select.product-select');
		expect(select.getAttribute('required')).toBe('');
		expect(select.name).toBe('lines[0][product_id]');
		expect(select.dataset.index).toBe('0');
		expect(
			document.querySelector('#line_0 input[name="lines[0][quantity]"]').value,
		).toBe('1');
	});

	it('delegated [data-action=add-line] click appends another line', async () => {
		await load();
		document
			.body
			.insertAdjacentHTML('beforeend', '<button data-action="add-line">+</button>');
		document.querySelector('[data-action="add-line"]').click();
		expect(document.getElementById('line_1')).not.toBeNull();
		expect(document.getElementById('line_count').value).toBe('2');
	});

	it('uses SmartSelectors when available instead of select2 fallback', async () => {
		const initProducts = vi.fn();
		window.SmartSelectors = { initProducts };
		await load();
		expect(initProducts).toHaveBeenCalledTimes(1);
		expect(initProducts.mock.calls[0][0].classList.contains('product-select')).toBe(true);
	});

	it('falls back to select2 with RTL Arabic search config and result mapping', async () => {
		delete window.SmartSelectors;
		await load();
		const call = global.$.calls
			.filter((c) => c.method === 'select2')
			.map((c) => c.args[0])
			.find((cfg) => cfg && cfg.ajax && cfg.ajax.data({ term: 'x' }).type === 'products');
		expect(call).toBeDefined();
		const cfg = call;
		expect(cfg.dir).toBe('rtl');
		expect(cfg.language).toBe('ar');
		expect(cfg.placeholder).toBe('ابحث عن منتج...');
		expect(cfg.minimumInputLength).toBe(0);
		expect(cfg.ajax.url).toBe('/api/search');
		expect(cfg.ajax.data({ term: 'galaxy', page: 2 })).toEqual({
			q: 'galaxy',
			type: 'products',
			page: 2,
		});
		const mapped = cfg.ajax.processResults({
			results: [
				{
					id: 3,
					name: 'Keyboard',
					default_price: 45,
					current_stock: 12,
					cost_price: 30,
					unit: 'قطعة',
					sku: 'KB-01',
				},
			],
			has_more: true,
		});
		expect(mapped.results[0]).toEqual({
			id: 3,
			text: 'Keyboard',
			price: 45,
			stock: 12,
			cost: 30,
			unit: 'قطعة',
			sku: 'KB-01',
		});
		expect(mapped.pagination.more).toBe(true);
	});

	it('select2:select without customer uses search-result price and stock inline', async () => {
		document.getElementById('exchange_rate').value = '2';
		document.getElementById('currency').value = 'EGP';
		await loadWithLine0();

		const select = document.querySelector('#line_0 select.product-select');
		const ev = new Event('select2:select');
		ev.params = {
			data: { id: 7, price: 40, stock: 3, unit: 'كرتون', cost: '8.5' },
		};
		select.dispatchEvent(ev);
		await flush();

		const priceInput = document.getElementById('price_0');
		expect(priceInput.value).toBe('20.00');
		const stockEl = document.getElementById('stock_0');
		expect(stockEl.textContent).toContain('3');
		expect(stockEl.textContent).toContain('كرتون');
		expect(document.getElementById('cost_0').textContent).toContain('8.50');
		expect(document.getElementById(`line_info_0`).style.display).toBe('block');
	});

	it('low stock path flags danger styling and warns via azad', async () => {
		const ajaxOpts = (global.$.ajaxHandlers = []);
		document.getElementById('customer_id').innerHTML =
			'<option value="" selected>-</option><option value="4" selected>Ali</option>';
		await loadWithLine0();

		const select = document.querySelector('#line_0 select.product-select');
		const ev = new Event('select2:select');
		ev.params = { data: { id: 7 } };
		select.dispatchEvent(ev);
		await flush();

		expect(ajaxOpts.length).toBeGreaterThan(0);
		const handler = ajaxOpts[ajaxOpts.length - 1];
		handler.success({
			data: { price: 12, current_stock: 0, unit: 'قطعة', cost_price: 6 },
		});

		const stockEl = document.getElementById('stock_0');
		expect(stockEl.classList.contains('text-danger')).toBe(true);
		expect(azadStubs.showWarning).toHaveBeenCalledWith(expect.stringContaining('المخزون منخفض'));
		expect(document.getElementById('cost_0').textContent).toContain('6.00');
	});

	it('_applyBasePrice ignores non-finite prices', async () => {
		document.getElementById('currency').value = 'EGP';
		document.getElementById('exchange_rate').value = '2';
		await loadWithLine0();
		const select = document.querySelector('#line_0 select.product-select');
		const ev = new Event('select2:select');
		ev.params = { data: { id: 7, price: Number.NaN } };
		select.dispatchEvent(ev);
		await flush();
		expect(document.getElementById('price_0').value).toBe('');
	});

	it('serial modal: open validates needed flag and renders required quantity', async () => {
		await loadWithLine0();
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '2';

		global.$('#serial_btn_0').data('needed', true);
		global.$('#serial_btn_0').data('product-name', 'Galaxy S24');

		window.triggerSerialModal(0);
		expect(document.getElementById('serial_product_name').textContent).toBe('Galaxy S24');
		expect(document.getElementById('serial_quantity_needed').textContent).toBe('2');
		const modalShow = global.$.calls.find((c) => c.method === 'modal');
		expect(modalShow).toBeDefined();
	});

	it('serial modal refuses to open when not flagged needed', async () => {
		await loadWithLine0();
		global.$('#serial_btn_0').data('needed', false);
		window.triggerSerialModal(0);
		expect(document.getElementById('serial_product_name').textContent).toBe('');
	});

	it('add / duplicate-reject / generate / save-back serials round trip', async () => {
		await loadWithLine0();
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '3';
		global.$('#serial_btn_0').data('needed', true);
		global.$('#serial_btn_0').data('product-name', 'P');
		window.triggerSerialModal(0);

		const input = document.getElementById('serial_input');
		input.value = 'SN-A';
		document.getElementById('add_serial_btn').click();
		input.value = 'SN-A';
		document.getElementById('add_serial_btn').click();

		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('مُدخل مسبقاً'));
		input.value = 'SN-B';
		document.getElementById('add_serial_btn').click();
		expect(document.querySelectorAll('#serial_list li').length).toBe(2);
		expect(document.getElementById('serial_count').textContent).toBe('2');
		expect(document.getElementById('save_serials_btn').disabled).toBe(true);

		document.getElementById('generate_serial_btn').click();
		expect(document.querySelectorAll('#serial_list li').length).toBe(3);
		expect(document.getElementById('save_serials_btn').disabled).toBe(false);

		document.getElementById('save_serials_btn').click();
		const hidden = Array.from(
			document.querySelectorAll('#line_0 input[name="lines[0][serials][]"]'),
		);
		expect(hidden.length).toBe(3);
		expect(hidden.map((h) => h.value)).toEqual(
			expect.arrayContaining(['SN-A', 'SN-B']),
		);
	});

	it('reopening the modal restores saved serials from hidden inputs', async () => {
		await loadWithLine0();
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '1';
		global.$('#serial_btn_0').data('needed', true);
		window.triggerSerialModal(0);
		document.getElementById('serial_input').value = 'SN-Z';
		document.getElementById('add_serial_btn').click();
		document.getElementById('save_serials_btn').click();

		global.$('#serial_btn_0').data('needed', true);
		window.triggerSerialModal(0);
		expect(document.getElementById('serial_count').textContent).toBe('1');
	});

	it('print serials escapes HTML before opening the print window', async () => {
		const writes = [];
		const fakeWin = {
			document: {
				open: vi.fn(),
				write: vi.fn((s) => writes.push(s)),
				close: vi.fn(),
			},
			print: vi.fn(),
		};
		const origOpen = window.open;
		window.open = vi.fn(() => fakeWin);

		try {
			await loadWithLine0();
			document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '1';
			global.$('#serial_btn_0').data('needed', true);
			window.triggerSerialModal(0);
			document.getElementById('serial_input').value = '<b>X&Y</b>';
			document.getElementById('add_serial_btn').click();

			writes.length = 0;
			document.getElementById('print_serials_btn').click();
			const joined = writes.join('');
			expect(joined).toContain('&lt;b&gt;X&amp;Y&lt;/b&gt;');
			expect(fakeWin.print).toHaveBeenCalled();
		} finally {
			window.open = origOpen;
		}
	});

	it('removeLine deletes the line node and re-renders totals', async () => {
		await loadWithLine0();
		expect(window.removeLine).toBeTypeOf('function');
		window.removeLine(0);
		expect(document.getElementById('line_0')).toBeNull();
	});

	it('calculateTotals posts line payload and paints server numbers', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			`
      <div class="product-line">
        <input class="quantity-input" name="lines[4][quantity]" value="2">
        <input name="lines[4][unit_price]" value="15">
        <input name="lines[4][discount_percent]" value="10">
      </div>`,
		);
		document.querySelector('[name="discount_amount"]').value = '5';
		document.querySelector('[name="shipping_cost"]').value = '7';
		document.querySelector('[name="tax_rate"]').value = '5';

		await load();
		// Neutralize the auto-created bootstrap line so only our seeded line counts.
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '';

		document
			.querySelector('[name="discount_amount"]')
			.dispatchEvent(new Event('change', { bubbles: true }));
		await flush();

		const payload = JSON.parse(global.fetch.mock.calls.at(-1)[1].body);
		expect(payload.lines).toEqual([
			{ quantity: 2, unit_price: 15, discount_percent: 10 },
		]);
		expect(payload.discount_amount).toBe(5);
		expect(payload.shipping_cost).toBe(7);
		expect(payload.tax_rate).toBe(5);
		// Server numbers painted with azad.formatNumber + raw counters.
		expect(document.getElementById('subtotal').textContent).toBe('100');
		expect(document.getElementById('line_count_display').textContent).toBe('1');
	});

	it('server failure falls back to client math with a single warning per outage', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			`
      <div class="product-line">
        <input class="quantity-input" name="lines[0][quantity]" value="2">
        <input name="lines[0][unit_price]" value="100">
        <input name="lines[0][discount_percent]" value="0">
      </div>`,
		);
		document.querySelector('[name="tax_rate"]').value = '10';
		global.fetch = vi.fn(() => Promise.reject(new TypeError('down')));

		await load();
		document
			.querySelector('[name="shipping_cost"]')
			.dispatchEvent(new Event('change', { bubbles: true }));
		await flush();
		expect(azadStubs.showWarning).toHaveBeenCalledTimes(1);
		// subtotal 200 + shipping 0 - discount 0 => tax 20 total 220
		expect(document.getElementById('total').textContent).toBe('220');

		// Repeated keystrokes during the same outage must not spam the toast.
		document
			.querySelector('[name="shipping_cost"]')
			.dispatchEvent(new Event('keyup', { bubbles: true }));
		await flush();
		expect(azadStubs.showWarning).toHaveBeenCalledTimes(1);
	});

	it('manual exchange-rate entry without server rate triggers audit flag + full repaint', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			`
      <div class="product-line" id="line_0">
        <select class="product-select" data-index="0"></select>
        <input id="price_0" value="">
      </div>`,
		);
		document.getElementById('currency').value = 'EGP';
		await load();

		global.$('#price_0').data('base-price', 80);
		const rate = document.getElementById('exchange_rate');
		rate.value = '4';
		rate.dispatchEvent(new Event('change', { bubbles: true }));
		await flush();

		expect(rate.style.backgroundColor).toBe('rgb(255, 243, 205)');
		expect(document.querySelector('#saleForm input[name="exchange_rate_manual"]')).not.toBeNull();
		expect(document.getElementById('price_0').value).toBe('20.00');
		expect(document.getElementById('discount_currency').textContent).toBe('EGP');
		expect(document.getElementById('total_currency_label').textContent).toBe('EGP');
	});

	it('saleForm submit blocks on zero lines, negative totals, and missing customer', async () => {
		global.fetch = vi.fn(() =>
			Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ success: true, data: { subtotal: 0, total: 0, tax_amount: 0, line_count: 0 } }),
			}),
		);
		await load();

		const form = document.getElementById('saleForm');
		form.submit = vi.fn();
		form.dispatchEvent(new Event('submit', { cancelable: true }));
		await flush();
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('منتج واحد'));
		expect(form.submit).not.toHaveBeenCalled();
	});

	it('saleForm submit blocks missing customer when totals valid', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			'<div class="product-line"><input name="lines[0][quantity]" value="1"><input name="lines[0][unit_price]" value="50"></div>',
		);
		await load();
		const form = document.getElementById('saleForm');
		form.submit = vi.fn();
		form.dispatchEvent(new Event('submit', { cancelable: true }));
		await flush();
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('اختيار زبون'));
		expect(form.submit).not.toHaveBeenCalled();
	});

	it('successful submit finalizes with loading state and native submit', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			'<div class="product-line"><input name="lines[0][quantity]" value="1"><input name="lines[0][unit_price]" value="50"></div>',
		);
		document.getElementById('customer_id').innerHTML =
			'<option value="3" selected>Omar</option>';
		await load();
		const form = document.getElementById('saleForm');
		form.submit = vi.fn();
		form.dispatchEvent(new Event('submit', { cancelable: true }));
		await flush();
		expect(azadStubs.showLoading).toHaveBeenCalled();
		expect(form.submit).toHaveBeenCalledTimes(1);
	});

	it('currency=AED pins exchange rate to 1 and informs the user', async () => {
		await load();
		document.getElementById('currency').value = 'AED';
		document.getElementById('currency').dispatchEvent(new Event('change', { bubbles: true }));

		expect(document.getElementById('exchange_rate').value).toBe('1.000000');
		expect(azadStubs.showInfo).toHaveBeenCalled();
		expect(document.getElementById('payment_currency_display').textContent).toBe('AED');
	});

	it('foreign currency fetches live rate and repaints line prices', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			'<div class="product-line" id="line_5"><select class="product-select" data-index="5"></select><input id="price_5" value=""></div>',
		);
		await load();

		global.$('#price_5').data('base-price', 100);
		document.getElementById('currency').value = 'SAR';
		document.getElementById('currency').dispatchEvent(new Event('change'));

		const ajax = global.$.ajaxHandlers.at(-1);
		expect(ajax.url).toBe('/api/currency-rate/SAR/AED');
		ajax.success({ rate: 2.5 });

		expect(document.getElementById('exchange_rate').value).toBe('2.500000');
		expect(document.getElementById('price_5').value).toBe('40.00');
		expect(azadStubs.showSuccess).toHaveBeenCalled();
	});

	it('manual-input-required responses prompt user entry and focus', async () => {
		await load();
		document.getElementById('currency').value = 'JOD';
		document.getElementById('currency').dispatchEvent(new Event('change'));

		const ajax = global.$.ajaxHandlers.at(-1);
		ajax.success({ manual_input_required: true });
		expect(document.getElementById('exchange_rate').value).toBe('');
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('يدوياً'));
	});

	it('rate-fetch network errors surface actionable guidance', async () => {
		await load();
		document.getElementById('currency').value = 'KWD';
		document.getElementById('currency').dispatchEvent(new Event('change'));
		global.$.ajaxHandlers.at(-1).error();
		expect(azadStubs.showError).toHaveBeenCalledWith(
			expect.stringContaining('فشل تحميل سعر الصرف'),
		);
	});

	it('manual rate edits append audit trail when below server rate', async () => {
		await load();
		const rate = document.getElementById('exchange_rate');
		rate.value = '1.0';

		global.$(rate).data('server-rate', 2.0);
		rate.dispatchEvent(new Event('change', { bubbles: true }));

		expect(rate.style.backgroundColor).toBe('rgb(248, 215, 218)');
		expect(document.querySelector('#saleForm input[name="exchange_rate_manual"]')).not.toBeNull();
		expect(document.querySelector('#saleForm input[name="exchange_rate_server"]').value).toBe('2');
		expect(document.querySelector('#saleForm input[name="exchange_rate_difference"]').value).toBe(
			'-50.00',
		);
		expect(azadStubs.showWarning).toHaveBeenCalled();
	});

	it('manual rate above server informs without audit fields', async () => {
		await load();
		const rate = document.getElementById('exchange_rate');
		rate.value = '4.0';
		global.$(rate).data('server-rate', 2.0);
		rate.dispatchEvent(new Event('change', { bubbles: true }));
		expect(azadStubs.showInfo).toHaveBeenCalled();
		expect(document.querySelector('#saleForm input[name="exchange_rate_manual"]')).toBeNull();
	});

	it('invalid manual rates restore the last server rate', async () => {
		await load();
		const rate = document.getElementById('exchange_rate');
		rate.value = '-3';
		global.$(rate).data('server-rate', 1.5);
		rate.dispatchEvent(new Event('change', { bubbles: true }));
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('أكبر من صفر'));
		expect(rate.value).toBe('1.500000');
	});

	it('payment_method change hides amount group when cleared', async () => {
		await load();
		const group = document.getElementById('payment_amount_group');
		group.style.display = 'block';
		const pm = document.getElementById('payment_method');
		pm.value = '';
		pm.dispatchEvent(new Event('change'));
		expect(group.style.display).toBe('none');
	});

	it('payment_method change renders API-provided dynamic fields', async () => {
		await load();
		const pm = document.getElementById('payment_method');
		pm.value = 'card';
		pm.dispatchEvent(new Event('change'));

		const ajax = global.$.ajaxHandlers.at(-1);
		expect(ajax.url).toBe('/api/payment-fields/card');
		ajax.success({
			ar_title: 'بطاقة',
			fields: [
				{ name: 'card_last4', label_ar: 'آخر أرقام', type: 'text', required: true },
				{
					name: 'card_type',
					type: 'select',
					options: [
						{ value: 'visa', label_ar: 'فيزا' },
						{ value: 'mc', label_en: 'Mastercard' },
					],
				},
			],
		});

		const container = document.getElementById('payment_fields_container');
		const last4 = container.querySelector('input[name="card_last4"]');
		expect(last4.hasAttribute('required')).toBe(true);
		expect(last4.placeholder).toContain('آخر أرقام');
		const opts = Array.from(container.querySelectorAll('select[name="card_type"] option')).map(
			(o) => o.textContent,
		);
		expect(opts).toEqual(['اختر...', 'فيزا', 'Mastercard']);
		expect(groupVisible()).toBe(true);

		function groupVisible() {
			return document.getElementById('payment_amount_group').style.display === 'block';
		}
	});

	it('dynamic payment-field load failures notify the cashier', async () => {
		await load();
		const pm = document.getElementById('payment_method');
		pm.value = 'cheque';
		pm.dispatchEvent(new Event('change'));
		global.$.ajaxHandlers.at(-1).error();
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('حقول الدفع'));
	});

	it('window.loadProductPrice pulls price/stock/serial needs for chosen customer', async () => {
		await loadWithLine0();
		document.getElementById('customer_id').innerHTML =
			'<option value="9" selected>Sara</option>';
		const prodSelect = document.querySelector('#line_0 select.product-select');
		prodSelect.innerHTML += '<option value="55">iPhone</option>';
		prodSelect.value = '55';

		window.loadProductPrice(0);
		expect(azadStubs.showLoading).toHaveBeenCalled();
		const ajax = global.$.ajaxHandlers.at(-1);
		expect(ajax.url).toBe('/sales/api/get-price');
		expect(ajax.data).toEqual({ product_id: '55', customer_id: '9' });

		ajax.success({
			data: {
				price: 250,
				current_stock: 4,
				unit: 'حبة',
				cost_price: 180,
				has_serial_number: true,
				name: 'iPhone',
			},
		});
		await flush();

		expect(document.getElementById('price_0').value).toBe('250.00');
		expect(document.getElementById('stock_0').textContent).toContain('4');
		expect(document.getElementById('cost_0').textContent).toContain('180.00');
		expect(
			document.getElementById('serial_btn_container_0').style.display,
		).toBe('block');
		expect(global.$('#serial_btn_0').data('needed')).toBe(true);

		global.$.ajaxHandlers.at(-1).error();
		expect(azadStubs.hideLoading).toHaveBeenCalled();
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('فشل تحميل السعر'));
	});

	it('window.loadProductPrice silently skips incomplete selections', async () => {
		await loadWithLine0();
		const before = global.$.ajaxHandlers.length;
		window.loadProductPrice(0);
		expect(global.$.ajaxHandlers.length).toBe(before);
	});

	it('serial modal remove buttons drop individual serials', async () => {
		await loadWithLine0();
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '2';
		global.$('#serial_btn_0').data('needed', true);
		window.triggerSerialModal(0);

		const input = document.getElementById('serial_input');
		input.value = 'SN-1';
		document.getElementById('add_serial_btn').click();
		input.value = 'SN-2';
		document.getElementById('add_serial_btn').click();

		document.querySelector('#serial_list li button').click();
		expect(document.querySelectorAll('#serial_list li').length).toBe(1);
		expect(document.getElementById('save_serials_btn').disabled).toBe(true);
	});

	it('server refusing totals (success:false) falls back to local math', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			'<div class="product-line"><input name="lines[3][quantity]" value="3"><input name="lines[3][unit_price]" value="10"></div>',
		);
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
		);
		await load();
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = '';
		document
			.querySelector('[name="discount_amount"]')
			.dispatchEvent(new Event('change', { bubbles: true }));
		await flush();

		expect(azadStubs.showWarning).toHaveBeenCalledTimes(1);
		expect(document.getElementById('total').textContent).toBe('30');
	});

	it('saleForm submit refuses negative totals', async () => {
		document.querySelector('#linesContainer').insertAdjacentHTML(
			'beforeend',
			'<div class="product-line"><input name="lines[2][quantity]" value="1"><input name="lines[2][unit_price]" value="50"></div>',
		);
		document.querySelector('[name="discount_amount"]').value = '1000';
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, json: () => Promise.resolve({ success: false }) }),
		);
		await load();
		const form = document.getElementById('saleForm');
		form.submit = vi.fn();
		form.dispatchEvent(new Event('submit', { cancelable: true }));
		await flush();
		expect(azadStubs.showError).toHaveBeenCalledWith(expect.stringContaining('سالب'));
		expect(form.submit).not.toHaveBeenCalled();
	});

	it('customer select2 renders option markup through provided templates', async () => {
		delete window.SmartSelectors;
		await load();
		const cfg = global.$.calls
			.filter((c) => c.method === 'select2')
			.map((c) => c.args[0])
			.find((c) => c && c.placeholder === 'ابحث عن زبون...');
		expect(cfg.dir).toBe('rtl');
		expect(cfg.ajax.data({ term: 'omar' })).toEqual({
			q: 'omar',
			type: 'customers',
			page: 1,
		});
		expect(cfg.templateResult({ loading: true, text: 'جارٍ...' })).toBe('جارٍ...');
		const rendered = cfg.templateResult({ text: 'Omar' });
		expect(rendered.length).toBeGreaterThan(0);
		expect(cfg.templateSelection({ text: 'Omar' })).toBe('Omar');
	});
});
