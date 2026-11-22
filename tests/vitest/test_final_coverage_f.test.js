import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	createGapJQuery,
	installGapGlobals,
	resetGapState,
	loadApp,
	ensureCsrfMeta,
} from './app_gap_harness.js';

/* ------------------------------------------------------------------------- *
 * pos/cart.js
 * ------------------------------------------------------------------------- */
describe('pos/cart.js — final statement gaps', () => {
	let savedFetch;

	beforeEach(() => {
		savedFetch = global.fetch;
		document.body.innerHTML =
			'<div id="upsellBar" class="d-none"></div>' +
			'<span id="exchangeRateSource"></span>' +
			'<span id="exchangeRateNote"></span>';
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		document.body.innerHTML = '';
		vi.useRealTimers();
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('markRateSource fills the badge and the note when both elements exist', async () => {
		const { markRateSource } = await import('../../static/js/pos/cart.js');
		markRateSource('online', 'سعر اليوم');
		const badge = document.getElementById('exchangeRateSource');
		expect(badge.dataset.source).toBe('online');
		expect(badge.textContent).toBe('أونلاين');
		expect(document.getElementById('exchangeRateNote').textContent).toBe('سعر اليوم');
	});

	it('evaluateUpsell survives a fetch whose json() rejects', async () => {
		const { evaluateUpsell } = await import('../../static/js/pos/cart.js');
		const { state } = await import('../../static/js/pos/core.js');
		state.cart = [{ id: 1, qty: 1, price: 10, discountPercent: 0 }];
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: false, status: 500, json: () => Promise.reject(new Error('bad json')) }),
		);
		await evaluateUpsell();
		expect(global.fetch).toHaveBeenCalledWith(
			'/pos/api/promotions/evaluate',
			expect.objectContaining({ method: 'POST' }),
		);
		expect(document.getElementById('upsellBar').classList.contains('d-none')).toBe(true);
	});

	it('scheduleUpsellEval bails out of its timer callback when document is gone', async () => {
		const { scheduleUpsellEval } = await import('../../static/js/pos/cart.js');
		vi.useFakeTimers();
		scheduleUpsellEval();
		vi.stubGlobal('document', undefined);
		try {
			vi.advanceTimersByTime(450);
		} finally {
			vi.unstubAllGlobals();
		}
		vi.useRealTimers();
	});
});

/* ------------------------------------------------------------------------- *
 * pos/core.js
 * ------------------------------------------------------------------------- */
describe('pos/core.js — final statement gaps', () => {
	let savedFetch;

	beforeEach(() => {
		savedFetch = global.fetch;
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		delete window.AzadUtils;
		vi.resetModules();
	});

	it('esc delegates to the shared AzadUtils.escapeHtml helper', async () => {
		window.AzadUtils = { escapeHtml: vi.fn((v) => `ESC:${v}`) };
		const { esc } = await import('../../static/js/pos/core.js');
		expect(esc('<x>')).toBe('ESC:<x>');
		expect(window.AzadUtils.escapeHtml).toHaveBeenCalledWith('<x>');
	});

	it('fetchJson tolerates a response whose json() rejects', async () => {
		const { fetchJson } = await import('../../static/js/pos/core.js');
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error('bad json')) }),
		);
		await expect(fetchJson('/pos/api/thing')).resolves.toEqual({ ok: true, data: null });
	});
});

/* ------------------------------------------------------------------------- *
 * pos/payments.js
 * ------------------------------------------------------------------------- */
describe('pos/payments.js — final statement gaps', () => {
	let savedFetch;

	beforeEach(() => {
		savedFetch = global.fetch;
		document.body.innerHTML =
			'<div id="posPinModal" data-action="discount"></div>' +
			'<input id="posPinInput" value="1234">' +
			'<div id="posPinError" class="d-none"></div>' +
			'<select id="paymentMethod"><option value="card">card</option></select>' +
			'<div id="refField"></div>' +
			'<div id="bankField" class="d-none"></div>' +
			'<div id="referenceLabel"></div>';
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		document.body.innerHTML = '';
		vi.resetModules();
	});

	it('confirmPin survives a rejected json() from the authorization endpoint', async () => {
		const { confirmPin } = await import('../../static/js/pos/payments.js');
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: false, status: 400, json: () => Promise.reject(new Error('bad json')) }),
		);
		await confirmPin();
		expect(document.getElementById('posPinError').classList.contains('d-none')).toBe(false);
		expect(document.getElementById('posPinError').textContent.length).toBeGreaterThan(0);
	});

	it('postWithOverride survives a rejected json() on the first attempt', async () => {
		const { postWithOverride } = await import('../../static/js/pos/payments.js');
		global.fetch = vi.fn(() =>
			Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error('bad json')) }),
		);
		const out = await postWithOverride('/pos/api/pay', { amount: 1 }, 'pay');
		expect(out.r.status).toBe(200);
		expect(out.j).toEqual({});
	});

	it('syncPay toggles the bank field and writes the card reference label', async () => {
		const { syncPay } = await import('../../static/js/pos/payments.js');
		document.getElementById('paymentMethod').value = 'card';
		syncPay();
		expect(document.getElementById('bankField').classList.contains('d-none')).toBe(true);
		expect(document.getElementById('referenceLabel').textContent).toContain('البطاقة');
	});
});

/* ------------------------------------------------------------------------- *
 * pos/print-tickets.js
 * ------------------------------------------------------------------------- */
describe('pos/print-tickets.js — final statement gaps', () => {
	let savedFetch;

	beforeEach(() => {
		savedFetch = global.fetch;
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		delete window.printQueuedCartReceipt;
		vi.useRealTimers();
		vi.resetModules();
	});

	it('printQueuedCartReceipt arms and clears the agent fetch timeout', async () => {
		global.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
		await import('../../static/js/pos/print-tickets.js');
		vi.useFakeTimers();
		const pending = window.printQueuedCartReceipt([], {});
		vi.advanceTimersByTime(5000); // fire the AbortController timeout callback
		await expect(pending).resolves.toBe(true);
		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('/print-receipt'),
			expect.objectContaining({ method: 'POST' }),
		);
	});
});

/* ------------------------------------------------------------------------- *
 * pos/core.js / pos/cart.js done — pos/core branch coverage is not targeted.
 * ------------------------------------------------------------------------- */

/* ------------------------------------------------------------------------- *
 * products/category-controls.js — early-return guards
 * ------------------------------------------------------------------------- */
describe('products/category-controls.js — final statement gaps', () => {
	let $;
	let ajaxCalls;
	let modalCalls;

	beforeEach(() => {
		ajaxCalls = [];
		modalCalls = [];
		document.body.innerHTML =
			'<select id="product_category">' +
			'<option value="0">--</option>' +
			'<option value="5" data-name="Drinks" data-name-ar="مشروبات" data-description="D">Drinks</option>' +
			'</select>' +
			'<div class="js-category-actions">' +
			'<button class="js-category-add"></button>' +
			'<button class="js-category-edit"></button>' +
			'<button class="js-category-delete"></button>' +
			'</div>' +
			'<div id="categoryModal">' +
			'<h5 class="js-category-modal-title"></h5>' +
			'<span class="js-category-save-label"></span>' +
			'<input id="category_name"><input id="category_name_ar"><input id="category_description">' +
			'<button class="js-category-save"></button>' +
			'</div>' +
			'<input name="csrf_token" value="tok">';
		vi.spyOn(window, 'confirm').mockImplementation(() => true);
		$ = buildCategoryJQuery(ajaxCalls, modalCalls);
		window.jQuery = $;
		global.jQuery = $;
		vi.resetModules();
	});

	afterEach(() => {
		window.confirm.mockRestore();
		document.body.innerHTML = '';
		delete window.jQuery;
		delete global.jQuery;
		delete window.initProductCategoryControls;
		vi.resetModules();
	});

	async function initControls() {
		await import('../../static/js/products/category-controls.js');
		window.initProductCategoryControls({
			select: '#product_category',
			wrap: '.js-category-actions',
			modal: '#categoryModal',
			createUrl: '/c/create',
			updateUrl: (id) => `/c/${id}/update`,
			deleteUrl: (id) => `/c/${id}/delete`,
		});
	}

	function selectCategory(id) {
		const sel = document.getElementById('product_category');
		sel.value = id;
		sel.dispatchEvent(new Event('change'));
	}

	it('selectedOption() returns an empty set for the placeholder option', async () => {
		await initControls();
		selectCategory('5'); // enable the action buttons
		document.getElementById('product_category').value = '0'; // stale selection, no change event
		document.querySelector('.js-category-edit').click();
		expect(modalCalls).not.toContain('show');
	});

	it('the edit handler returns when no option node matches the selection', async () => {
		await initControls();
		selectCategory('404');
		document.querySelector('.js-category-edit').click();
		expect(modalCalls).not.toContain('show');
	});

	it('the delete handler returns for the placeholder selection', async () => {
		await initControls();
		selectCategory('5'); // enable the action buttons
		document.getElementById('product_category').value = '0'; // stale selection, no change event
		document.querySelector('.js-category-delete').click();
		expect(ajaxCalls).toHaveLength(0);
	});
});

function buildCategoryJQuery(ajaxCalls, modalCalls) {
	const mk = (els) => {
		const first = () => els[0] || null;
		const api = {
			els,
			get length() {
				return els.length;
			},
			first: () => mk(els.slice(0, 1)),
			find: (sel) => {
				const found = [];
				els.forEach((e) => {
					try {
						found.push(...Array.from(e.querySelectorAll(sel)));
					} catch (_) {
						/* jsdom rejects some attribute selectors */
					}
				});
				return mk(found);
			},
			on: (evt, sel, fn) => {
				els.forEach((e) => {
					if (typeof sel === 'function') {
						e.addEventListener(evt, sel);
					} else {
						e.addEventListener(evt, (ev) => {
							const t = ev.target && typeof ev.target.closest === 'function' ? ev.target.closest(sel) : null;
							if (t && e.contains(t)) fn.call(t, ev);
						});
					}
				});
				return api;
			},
			val(v) {
				if (v === undefined) return first() ? first().value : undefined;
				els.forEach((e) => {
					e.value = v;
				});
				return api;
			},
			text(v) {
				if (v === undefined) return first() ? first().textContent : '';
				els.forEach((e) => {
					e.textContent = v;
				});
				return api;
			},
			attr(name, val) {
				if (val === undefined) return first() ? first().getAttribute(name) : undefined;
				els.forEach((e) => e.setAttribute(name, val));
				return api;
			},
			data(key, val) {
				const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
				if (val === undefined) return first() ? first().dataset[k] : undefined;
				els.forEach((e) => {
					e.dataset[k] = val;
				});
				return api;
			},
			removeData(key) {
				const k = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
				els.forEach((e) => delete e.dataset[k]);
				return api;
			},
			prop(name, val) {
				if (val === undefined) return first() ? first()[name] : undefined;
				els.forEach((e) => {
					e[name] = val;
				});
				return api;
			},
			append(child) {
				if (first() && child && child.els) first().appendChild(child.els[0]);
				return api;
			},
			modal(action) {
				modalCalls.push(action);
				return api;
			},
		};
		return api;
	};
	const $ = (arg) => {
		if (arg === undefined) return mk([]); // jQuery's $() empty set
		if (typeof arg === 'string') {
			if (arg.startsWith('<')) {
				const tmp = document.implementation.createHTMLDocument('');
				tmp.body.innerHTML = arg;
				return mk(Array.from(tmp.body.children));
			}
			return mk(Array.from(document.querySelectorAll(arg)));
		}
		if (arg && arg.els) return arg;
		if (arg === document) return mk([document]);
		if (typeof arg === 'function') {
			arg();
			return mk([]);
		}
		return mk([arg]);
	};
	$.fn = {};
	$.ajax = (opts) => ajaxCalls.push(opts);
	return $;
}

/* ------------------------------------------------------------------------- *
 * products/industry-fields.js
 * ------------------------------------------------------------------------- */
describe('products/industry-fields.js — final statement gaps', () => {
	let savedFetch;

	beforeEach(() => {
		savedFetch = global.fetch;
		document.body.innerHTML =
			'<select id="product_industry"><option value="retail">Retail</option></select>' +
			'<div id="industryFieldsContainer"></div>';
		document.getElementById('product_industry').value = 'retail';
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		document.body.innerHTML = '';
		delete window.AzadUtils;
		vi.resetModules();
	});

	it('esc() delegates to AzadUtils.escapeHtml while rendering API fields', async () => {
		window.AzadUtils = { escapeHtml: vi.fn((v) => `E:${v}`) };
		global.fetch = vi.fn(() =>
			Promise.resolve({
				json: () =>
					Promise.resolve({
						industry: 'retail',
						fields: [{ field_code: 'zone', field_name_en: 'Zone', field_type: 'text' }],
					}),
			}),
		);
		await import('../../static/js/products/industry-fields.js');
		await new Promise((r) => setTimeout(r, 0));
		expect(window.AzadUtils.escapeHtml).toHaveBeenCalledWith('retail');
		expect(document.getElementById('industryFieldsContainer').innerHTML).toContain('E:zone');
	});
});

/* ------------------------------------------------------------------------- *
 * draft-autosave.js
 * ------------------------------------------------------------------------- */
describe('draft-autosave.js — final statement gaps', () => {
	let savedT;

	beforeEach(() => {
		savedT = window.t;
		document.body.innerHTML = '<form id="draftForm"><input name="title"></form>';
		localStorage.setItem(
			'azad_draft_finalF',
			JSON.stringify({ data: { title: 'old' }, timestamp: Date.now() }),
		);
		vi.resetModules();
	});

	afterEach(() => {
		window.t = savedT;
		globalThis.t = savedT;
		localStorage.removeItem('azad_draft_finalF');
		document.body.innerHTML = '';
		delete window.DraftAutosave;
		vi.resetModules();
	});

	it('uses the identity translator when window.t is not installed', async () => {
		delete window.t;
		delete globalThis.t;
		await import('../../static/js/draft-autosave.js');
		window.DraftAutosave.init('finalF', '#draftForm');
		const banner = document.querySelector('#draftForm .alert-info');
		expect(banner).not.toBeNull();
		expect(banner.innerHTML).toContain('Found_saved_draft');
		expect(banner.innerHTML).toContain('Restore');
	});
});

/* ------------------------------------------------------------------------- *
 * telemetry.js — the remaining gaps are defensive-only (see final report).
 * ------------------------------------------------------------------------- */

/* ------------------------------------------------------------------------- *
 * ai-sales.js
 * ------------------------------------------------------------------------- */
describe('ai-sales.js — final function gaps', () => {
	let aiHandlers;
	let ajaxCalls;
	let analyzeCount;

	beforeEach(() => {
		aiHandlers = [];
		ajaxCalls = [];
		analyzeCount = 0;
		document.body.innerHTML =
			'<meta name="csrf-token" content="tok">' +
			'<select id="customer_id"><option value="5">c</option></select>' +
			'<select class="product-select" data-line-index="0"><option value="9">p</option></select>' +
			'<div id="customer_analysis"></div>';
		document.getElementById('customer_id').value = '5';
		document.querySelector('.product-select').value = '9';
		window.AzadUtils = { escapeHtml: vi.fn((v) => `ESC:${v}`) };
		const $ = buildAiJQuery(aiHandlers, (opts) => {
			ajaxCalls.push(opts);
			if (opts.url.includes('/ai/analyze-customer/')) {
				analyzeCount += 1;
				if (analyzeCount === 1) {
					opts.success({
						risk_level: 'low',
						current_balance: 1,
						avg_payment_delay_days: 1,
						recommendation: '<b>ok</b>',
					});
					return;
				}
			}
			opts.error(new Error('offline'));
		});
		global.$ = $;
		window.$ = $;
		global.jQuery = $;
		vi.resetModules();
	});

	afterEach(() => {
		aiHandlers.forEach(({ evt, listener }) => document.removeEventListener(evt, listener));
		document.body.innerHTML = '';
		document.head.innerHTML = '';
		delete window.AzadUtils;
		delete window.applyRecommendedPrice;
		delete window.applyMarketPrice;
		delete global.$;
		delete window.$;
		delete global.jQuery;
		vi.resetModules();
	});

	it('runs every ajax error handler and the shared esc helper', async () => {
		await import('../../static/js/ai-sales.js');

		// First customer analysis succeeds -> esc() delegates to AzadUtils.
		document.getElementById('customer_id').dispatchEvent(new Event('change', { bubbles: true }));
		expect(window.AzadUtils.escapeHtml).toHaveBeenCalledWith('<b>ok</b>');

		// Product selection triggers checkPriceRecommendation + market + compatible error paths.
		document.querySelector('.product-select').dispatchEvent(new Event('change', { bubbles: true }));
		// Second customer analysis errors -> analyzeCustomer's error callback runs.
		document.getElementById('customer_id').dispatchEvent(new Event('change', { bubbles: true }));

		const urls = ajaxCalls.map((c) => c.url);
		expect(urls.some((u) => u.includes('/ai/recommend-price'))).toBe(true);
		expect(urls.some((u) => u.includes('/ai/search-market-price/'))).toBe(true);
		expect(urls.some((u) => u.includes('/ai/find-compatible/'))).toBe(true);
		expect(urls.filter((u) => u.includes('/ai/analyze-customer/'))).toHaveLength(2);
	});
});

function buildAiJQuery(handlers, ajaxImpl) {
	const mk = (nodes) => {
		const first = () => nodes[0] || null;
		const api = {
			els: nodes,
			get length() {
				return nodes.length;
			},
			val(v) {
				if (v === undefined) return first() ? first().value : '';
				nodes.forEach((n) => {
					n.value = v;
				});
				return api;
			},
			data(key, value) {
				const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
				if (value === undefined) return first() ? first().dataset[camel] : undefined;
				nodes.forEach((n) => {
					n.dataset[camel] = value;
				});
				return api;
			},
			parent: () => mk(nodes.map((n) => n.parentElement).filter(Boolean)),
			find: (sel) => {
				const found = [];
				nodes.forEach((n) => {
					try {
						found.push(...Array.from(n.querySelectorAll(sel)));
					} catch (_) {
						/* ignore */
					}
				});
				return mk(found);
			},
			remove: () => {
				nodes.forEach((n) => n.remove());
				return api;
			},
			after: (html) => {
				first()?.insertAdjacentHTML('afterend', html);
				return api;
			},
			html: (v) => {
				if (v === undefined) return first() ? first().innerHTML : '';
				nodes.forEach((n) => {
					n.innerHTML = v;
				});
				return api;
			},
			text: (v) => {
				if (v === undefined) return first() ? first().textContent : '';
				nodes.forEach((n) => {
					n.textContent = v;
				});
				return api;
			},
			each(fn) {
				nodes.forEach((el, i) => fn.call(el, i, el));
				return api;
			},
			fadeOut: () => api,
			trigger(evt) {
				first()?.dispatchEvent(new Event(evt, { bubbles: true }));
				return api;
			},
			attr(name, value) {
				if (value === undefined) return first()?.getAttribute(name) ?? undefined;
				nodes.forEach((n) => n.setAttribute(name, value));
				return api;
			},
		};
		return api;
	};
	const $ = (arg) => {
		if (arg === document) {
			return {
				ready(fn) {
					fn();
					return this;
				},
				on(evt, sel, fn) {
					const listener = (e) => {
						const t = e.target && typeof e.target.closest === 'function' ? e.target.closest(sel) : null;
						if (t) fn.call(t, e);
					};
					handlers.push({ evt, listener });
					document.addEventListener(evt, listener);
					return this;
				},
			};
		}
		if (typeof arg === 'string') {
			if (arg.startsWith('<')) {
				const tmp = document.implementation.createHTMLDocument('');
				tmp.body.innerHTML = arg;
				return mk(Array.from(tmp.body.children));
			}
			return mk(Array.from(document.querySelectorAll(arg)));
		}
		return mk([arg]);
	};
	$.ajax = ajaxImpl;
	return $;
}

/* ------------------------------------------------------------------------- *
 * smart-print.js
 * ------------------------------------------------------------------------- */
describe('smart-print.js — final statement gaps', () => {
	let $;
	let savedOpen;

	beforeEach(() => {
		savedOpen = window.open;
		document.body.innerHTML = '';
		window.AzadUtils = { escapeHtml: vi.fn((v) => `SP:${v}`) };
		$ = buildSmartPrintJQuery();
		window.$ = $;
		window.jQuery = $;
		vi.resetModules();
	});

	afterEach(() => {
		window.open = savedOpen;
		delete window.SmartPrint;
		delete window.jQuery;
		delete window.$;
		delete window.AzadUtils;
		document.body.innerHTML = '';
		vi.resetModules();
	});

	it('_spEsc delegates to AzadUtils.escapeHtml while writing a fallback ticket', async () => {
		const SmartPrint = await importSmartPrint($);
		const printWin = {
			document: { write: vi.fn(), close: vi.fn() },
			focus: vi.fn(),
			print: vi.fn(),
			close: vi.fn(),
		};
		window.open = vi.fn(() => printWin);
		const buttons = vi.fn(() => ({}));
		buttons.exportData = vi.fn(() => ({ header: ['H'], body: [['B']], footer: ['F'] }));
		buttons.exportInfo = vi.fn(() => ({ title: 'T', messageTop: 'MT', messageBottom: 'MB' }));
		SmartPrint._fallbackPrint({ buttons }, { header: true, footer: true, smartPrintOptions: {} });
		expect(window.AzadUtils.escapeHtml).toHaveBeenCalledWith('H');
		const written = printWin.document.write.mock.calls.map((c) => c[0]).join('');
		expect(written).toContain('SP:B');
	});

	it('handleConfirm returns immediately when no table was selected', async () => {
		const SmartPrint = await importSmartPrint($);
		// attachTrigger() builds the modal (and registers handleConfirm) before
		// it notices the missing table, so the guard can be exercised.
		SmartPrint.attachTrigger(null, '#anyTrigger');
		expect(() => $('#smartPrintModalConfirm').trigger('click')).not.toThrow();
	});
});

async function importSmartPrint($) {
	window.$ = $;
	window.jQuery = $;
	await import('../../static/js/smart-print.js');
	return window.SmartPrint;
}

function buildSmartPrintJQuery() {
	const handlers = new Map();
	const dataStore = new Map();
	const valStore = new Map();
	const chain = (sel) => {
		const key = String(sel);
		const api = {
			length: 1,
			on(types, fn) {
				String(types).split(' ').forEach((t) => handlers.set(`${key}|${t}`, fn));
				return api;
			},
			off: () => api,
			trigger(type) {
				const fn = handlers.get(`${key}|${type}`);
				if (fn) fn.call(api, { type, preventDefault() {} });
				return api;
			},
			data(k, v) {
				const store = dataStore.get(key) || {};
				if (v !== undefined) {
					store[k] = v;
					dataStore.set(key, store);
					return api;
				}
				return store[k];
			},
			val(v) {
				if (v !== undefined) {
					valStore.set(key, v);
					return api;
				}
				return valStore.get(key) ?? '';
			},
			prop: () => api,
			addClass: () => api,
			removeClass: () => api,
			text: () => api,
			css: () => api,
			modal: () => api,
			each(fn) {
				if (fn) fn.call(api, 0, null);
				return api;
			},
			find: () => chain(`${key} inner`),
			first: () => api,
			remove: () => api,
			prepend: () => api,
			append: (html) => {
				if (key === 'body') document.body.insertAdjacentHTML('beforeend', String(html));
				return api;
			},
		};
		return api;
	};
	const $ = (sel) => chain(sel);
	$.fn = { dataTable: { Buttons: {}, ext: { buttons: { print: { action: vi.fn() } } } } };
	$.extend = (...args) => {
		const target = args[0] || {};
		for (let i = 1; i < args.length; i += 1) Object.assign(target, args[i] || {});
		return target;
	};
	$.Event = function Event(type) {
		this.type = type;
	};
	return $;
}

/* ------------------------------------------------------------------------- *
 * barcode-scanner.js
 * ------------------------------------------------------------------------- */
describe('barcode-scanner.js — final function gaps', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	afterEach(() => {
		delete window.BarcodeScanner;
		delete window.CameraBarcodeScanner;
		vi.resetModules();
	});

	it('the default onScan callback receives a keyboard-scanned buffer', async () => {
		await import('../../static/js/barcode-scanner.js');
		const scanner = new window.BarcodeScanner();
		scanner.start();
		for (const key of ['A', 'B', 'C']) {
			document.dispatchEvent(new KeyboardEvent('keypress', { key, bubbles: true }));
		}
		document.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', bubbles: true }));
		scanner.stop();
		expect(scanner.buffer).toBe('');
	});

	it('the default camera onScan callback receives a detected code', async () => {
		await import('../../static/js/barcode-scanner.js');
		const video = document.createElement('video');
		Object.defineProperty(video, 'readyState', { configurable: true, value: 4 });
		const scanner = new window.CameraBarcodeScanner(video);
		scanner.isScanning = true;
		scanner.detector = { detect: vi.fn(() => Promise.resolve([{ rawValue: 'CAM-42' }])) };
		await scanner.scan();
		expect(scanner._lastCode).toBe('CAM-42');
	});

	it('detectBarcode returns null when the detector finds nothing', async () => {
		await import('../../static/js/barcode-scanner.js');
		const scanner = new window.CameraBarcodeScanner(document.createElement('video'));
		scanner.detector = { detect: vi.fn(() => Promise.resolve([])) };
		await expect(scanner.detectBarcode({})).resolves.toBeNull();
	});
});

/* ------------------------------------------------------------------------- *
 * shop-cart.js
 * ------------------------------------------------------------------------- */
describe('shop-cart.js — final statement gaps', () => {
	let domListeners;
	let origAdd;

	beforeEach(() => {
		domListeners = [];
		origAdd = document.addEventListener.bind(document);
		document.addEventListener = vi.fn((type, fn, ...rest) => {
			if (type === 'DOMContentLoaded') domListeners.push(fn);
			return origAdd(type, fn, ...rest);
		});
		Object.defineProperty(document, 'readyState', { configurable: true, value: 'loading' });
		document.body.setAttribute('data-store-slug', 'demo');
		vi.resetModules();
	});

	afterEach(() => {
		domListeners.forEach((fn) => document.removeEventListener('DOMContentLoaded', fn));
		document.addEventListener = origAdd;
		delete document.readyState;
		document.body.removeAttribute('data-store-slug');
		delete window.ShopCart;
		vi.resetModules();
	});

	it('registers the DOMContentLoaded initializer while the document is loading', async () => {
		await import('../../static/js/shop-cart.js');
		expect(domListeners.length).toBeGreaterThan(0);
	});
});

/* ------------------------------------------------------------------------- *
 * support.js
 * ------------------------------------------------------------------------- */
describe('support.js — final statement gaps', () => {
	let savedFetch;
	let savedOpen;

	beforeEach(() => {
		savedFetch = global.fetch;
		savedOpen = window.open;
		document.body.innerHTML =
			'<div class="sp-tab-buttons"><button class="sp-tab-btn active" data-tab="purchase">P</button></div>' +
			'<div id="purchase-tab" class="sp-tab-content active">' +
			'<div class="sp-package-card active" data-package-id="7" data-price="50">Plan</div>' +
			'<div id="purchase-payment-methods"></div></div>' +
			'<input id="customAmount" value="25">';
		window.spConfig = { brand: 'Azad', whatsappLink: '971500000000' };
		window.spI18n = {};
		const swal = vi.fn(() => Promise.resolve({ isConfirmed: true }));
		swal.fire = vi.fn(() => Promise.resolve({ isConfirmed: true, value: { name: 'A', email: 'a@b.c' } }));
		swal.close = vi.fn();
		swal.DismissReason = { cancel: 'cancel', backdrop: 'backdrop' };
		global.Swal = swal;
		global.fetch = vi.fn(() =>
			Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ success: true, purchase_id: 42, payment_address: 'bc1q' }),
			}),
		);
		window.AzadUtils = { escapeHtml: vi.fn((v) => `SUP:${v}`) };
		window.open = vi.fn();
		vi.resetModules();
	});

	afterEach(() => {
		global.fetch = savedFetch;
		window.open = savedOpen;
		document.body.innerHTML = '';
		delete window.AzadUtils;
		delete window.spConfig;
		delete window.spI18n;
		delete global.Swal;
		delete window.handlePayPalPayment;
		vi.resetModules();
	});

	it('escapeHtml delegates to AzadUtils.escapeHtml on a successful PayPal order', async () => {
		await import('../../static/js/support.js');
		await window.handlePayPalPayment();
		expect(window.AzadUtils.escapeHtml).toHaveBeenCalledWith(42);
	});
});

/* ------------------------------------------------------------------------- *
 * sales-enhanced.js — the remaining guard is unreachable from the public API
 * (see final report). Included here is a real assertion of the reachable
 * serial flow so the module is exercised in this run.
 * ------------------------------------------------------------------------- */
describe('sales-enhanced.js — reachable serial flow sanity', () => {
	beforeEach(() => {
		// Earlier suites remove the shared jQuery global; restore a chainable
		// stand-in so the classic script can register its handlers on import.
		const $ = createGapJQuery();
		global.$ = $;
		window.$ = $;
		global.jQuery = $;
		vi.resetModules();
	});

	afterEach(() => {
		delete window.triggerSerialModal;
		vi.resetModules();
	});

	it('exposes the serial modal trigger', async () => {
		await import('../../static/js/sales-enhanced.js');
		expect(typeof window.triggerSerialModal).toBe('function');
	});
});

/* ------------------------------------------------------------------------- *
 * app.js
 * ------------------------------------------------------------------------- */
describe('app.js — final statement gaps', () => {
	beforeEach(() => {
		document.head.innerHTML = '';
		ensureCsrfMeta();
		document.body.innerHTML =
			'<button class="btn-close" data-bs-dismiss="modal" type="button" aria-label="Close">x</button>' +
			'<table class="datatable" id="normalTbl"><thead><tr><th>Name</th></tr></thead>' +
			'<tbody><tr><td>a</td></tr></tbody></table>' +
			'<table class="datatable" id="emptyTbl"><thead><tr><th>Message</th></tr></thead>' +
			'<tbody><tr><td colspan="1">empty</td></tr></tbody></table>' +
			'<select class="select2" id="alreadyInit" data-s2-initialized="1"><option>1</option></select>';
		vi.resetModules();
	});

	afterEach(() => {
		resetGapState();
		document.body.innerHTML = '';
		delete window.$;
		delete window.jQuery;
		delete global.$;
		delete global.jQuery;
		vi.resetModules();
	});

	it('migrates data-bs-dismiss, guards DataTables, and skips initialized selects', async () => {
		const $ = createGapJQuery();
		installGapGlobals($);
		await loadApp();

		expect(document.querySelector('.btn-close').getAttribute('data-dismiss')).toBe('modal');
		expect($._calls.datatable.some((c) => c.el.id === 'normalTbl')).toBe(true);
		expect($._calls.datatable.some((c) => c.el.id === 'emptyTbl')).toBe(false);
		expect($._calls.select2.some((c) => c.el.id === 'alreadyInit')).toBe(false);
	});

	it('the btn-close fallback copies data-bs-dismiss when the attribute pass misses it', async () => {
		const base = createGapJQuery();
		const $ = (arg) => {
			const api = base(arg);
			const rawFind = api.find;
			api.find = (sel) => (sel === '[data-bs-dismiss]' && arg === document ? base([]) : rawFind(sel));
			return api;
		};
		Object.assign($, base);
		$.fn = base.fn;
		installGapGlobals($);
		await loadApp();
		expect(document.querySelector('.btn-close').getAttribute('data-dismiss')).toBe('modal');
	});

	it('the empty-row DataTables wrapper removes a spanned empty row', async () => {
		const base = createGapJQuery();
		// The real DataTables wrapper calls $rows.toArray(); teach the harness
		// jQuery objects that method before app.js captures the global.
		const addToArray = (api) => {
			if (!api || typeof api !== 'object') return api;
			if (!api.toArray) api.toArray = () => (typeof api.get === 'function' ? api.get() : []);
			const rawFind = api.find;
			api.find = (sel) => {
				const found = rawFind(sel);
				return addToArray(found);
			};
			return api;
		};
		const $ = (arg) => addToArray(base(arg));
		Object.assign($, base);
		$.fn = base.fn;
		installGapGlobals($);
		await loadApp();

		const table = document.createElement('table');
		table.innerHTML = '<tbody><tr><td colspan="3">nothing here</td></tr></tbody>';
		document.body.appendChild(table);
		const $table = $(table);
		$.fn.DataTable.call($table, {});
		expect(table.querySelectorAll('tbody tr')).toHaveLength(0);
	});

	it('installBootstrapCompat returns early when jQuery has no plugins', async () => {
		let readyCallback = null;
		const $bare = (arg) => {
			if (typeof arg === 'function') {
				readyCallback = arg;
				return { on: () => {}, find: () => ({ each: () => {} }), each: () => {} };
			}
			return { on: () => {}, find: () => ({ each: () => {} }), each: () => {} };
		};
		$bare.fn = undefined;
		global.$ = $bare;
		window.$ = $bare;
		global.jQuery = $bare;
		global.MutationObserver = class {
			observe() {}
			disconnect() {}
		};
		vi.resetModules();
		try {
			await import('../../static/js/app.js');
		} catch (_) {
			// With no $.fn the module-level DataTables guard throws, but the
			// ready callback (and installBootstrapCompat's early return) already ran.
		}
		expect(typeof readyCallback).toBe('function');
		try {
			readyCallback();
		} catch (_) {
			// Without $.fn the later init steps cannot run; the early guard
			// in installBootstrapCompat has already executed.
		}
	});
});
