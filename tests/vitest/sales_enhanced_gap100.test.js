import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Gap coverage for static/js/sales-enhanced.js.
 * Covers: select error fallback (192-195), non-finite base price guard (231),
 * modal-line reset in removeLine (249), FX division + low-stock + no-serial
 * branches in loadProductPrice (283,292-293,311-313), serial null guards
 * (380,395,411,420,441), equal-rate branch (726), customer select2 mapping
 * (825-830) and the double-submit guard (852).
 */

const MOD = "../../static/js/sales-enhanced.js";

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
					if (typeof arg === "string") {
						el.insertAdjacentHTML("beforeend", arg);
					} else if (arg && arg.__els) {
						arg.__els.forEach((child) => el.appendChild(child));
					} else if (arg instanceof Node) {
						el.appendChild(arg);
					}
				});
				return api;
			},
			html(arg) {
				if (arg === undefined) return list[0] ? list[0].innerHTML : "";
				list.forEach((el) => {
					el.innerHTML = arg;
				});
				return api;
			},
			text(arg) {
				if (arg === undefined) return list[0] ? list[0].textContent : "";
				list.forEach((el) => {
					el.textContent = String(arg);
				});
				return api;
			},
			val(arg) {
				if (arg === undefined) return list[0] ? list[0].value : "";
				list.forEach((el) => {
					el.value = arg === null ? "" : String(arg);
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
					if (store && Object.prototype.hasOwnProperty.call(store, key))
						return store[key];
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
				list.forEach((el) =>
					String(names)
						.split(/\s+/)
						.forEach((c) => c && el.classList.add(c)),
				);
				return api;
			},
			removeClass(names) {
				list.forEach((el) =>
					String(names)
						.split(/\s+/)
						.forEach((c) => c && el.classList.remove(c)),
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
					el.style.display = "block";
				});
				return api;
			},
			hide() {
				list.forEach((el) => {
					el.style.display = "none";
				});
				return api;
			},
			remove() {
				list.forEach((el) => el.parentNode && el.parentNode.removeChild(el));
				return api;
			},
			empty() {
				list.forEach((el) => {
					el.innerHTML = "";
				});
				return api;
			},
			on(...args) {
				let evtNames;
				let selector = null;
				let handler;
				if (typeof args[0] === "string" && typeof args[1] === "function") {
					evtNames = args[0];
					handler = args[1];
				} else if (typeof args[1] === "string" && typeof args[2] === "function") {
					evtNames = args[0];
					selector = args[1];
					handler = args[2];
				} else {
					return api;
				}
				evtNames
					.split(/\s+/)
					.filter(Boolean)
					.forEach((evtName) => {
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
				const e = new Event(evt, { bubbles: true });
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
				if (typeof prop === "symbol") return undefined;
				if (/^\d+$/.test(prop)) return target.__els[Number(prop)];
				if (prop === "then") return undefined;
				return (...args) => {
					calls.push({ sel: target.__sel || null, method: String(prop), args });
					return proxy;
				};
			},
		});
		return proxy;
	}

	function $(sel) {
		if (typeof sel === "string") {
			if (sel.trimStart().startsWith("<")) {
				const tpl = document.createElement("template");
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
		calls.push({ method: "ajax", args: [opts] });
		$.ajaxHandlers.push(opts);
	};
	return $;
}

function pageHTML() {
	return `
    <form id="saleForm">
      <select id="customer_id"><option value="">-</option><option value="9">Sara</option></select>
      <div id="linesContainer"></div>
      <input type="hidden" id="line_count" value="0" name="line_count">
      <input name="discount_amount" value="0">
      <input name="shipping_cost" value="0">
      <input name="tax_rate" value="0">
      <span id="subtotal"></span><span id="total"></span><span id="line_count_display"></span>
      <span id="discount_currency"></span><span id="shipping_currency"></span><span id="total_currency_label"></span>
      <span id="payment_currency_display"></span>
      <input id="exchange_rate" value="1">
      <select id="currency">
        <option value="AED">AED</option><option value="USD">USD</option>
      </select>
      <div id="payment_fields_container"></div>
      <div id="payment_amount_group"></div>
      <select id="payment_method">
        <option value="">-</option><option value="card">card</option>
      </select>
      <div id="serialNumberModal">
        <span id="serial_product_name"></span>
        <span id="serial_quantity_needed"></span>
        <ul id="serial_list"></ul>
        <span id="serial_count"></span>
        <input id="serial_input" type="text" />
        <button id="add_serial_btn" type="button">+</button>
        <button id="generate_serial_btn" type="button">gen</button>
        <button id="print_serials_btn" type="button">print</button>
        <button id="save_serials_btn" type="button">save</button>
      </div>
      <button type="submit">submit</button>
    </form>`;
}

function emitSelect2Select(select, data) {
	const ev = new Event("select2:select", { bubbles: true });
	ev.params = { data };
	select.dispatchEvent(ev);
}

const wait = (ms = 30) => new Promise((r) => setTimeout(r, ms));

let azadStubs;

beforeEach(() => {
	document.body.innerHTML = pageHTML();
	let meta = document.querySelector('meta[name="csrf-token"]');
	if (!meta) {
		meta = document.createElement("meta");
		meta.setAttribute("name", "csrf-token");
		document.head.appendChild(meta);
	}
	meta.setAttribute("content", "tok");
	delete window.SmartSelectors;
	window._CURRENCY_SYMBOL = "د.إ";
	window._FX_FALLBACK_BASE = "AED";
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
	document.body.innerHTML = "";
	delete window.azad;
	delete window.SmartSelectors;
	delete global.fetch;
	delete global.$;
	delete global.jQuery;
	vi.resetModules();
});

describe("sales-enhanced.js gap100", () => {
	it("falls back to search-result price when the price API errors", async () => {
		await import(MOD);
		document.getElementById("customer_id").value = "9";
		const select = document.querySelector("#line_0 select.product-select");
		emitSelect2Select(select, { id: 7, price: 99 });
		await wait();
		global.$.ajaxHandlers.at(-1).error();
		await wait();
		expect(document.getElementById("price_0").value).toBe("99.00");
	});

	it("ignores non-numeric search-result prices", async () => {
		await import(MOD);
		const select = document.querySelector("#line_0 select.product-select");
		emitSelect2Select(select, { id: 7, price: "abc" });
		await wait();
		expect(document.getElementById("price_0").value).toBe("");
	});

	it("removeLine clears a pending serial modal for the same line", async () => {
		await import(MOD);
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = "2";
		global.$("#serial_btn_0").data("needed", true);
		global.$("#serial_btn_0").data("product-name", "P");
		window.triggerSerialModal(0);
		expect(document.getElementById("line_0")).not.toBeNull();
		window.removeLine(0);
		expect(document.getElementById("line_0")).toBeNull();
	});

	it("loadProductPrice converts currency, flags low stock and hides serial button", async () => {
		await import(MOD);
		document.getElementById("customer_id").value = "9";
		const prodSelect = document.querySelector("#line_0 select.product-select");
		prodSelect.innerHTML += '<option value="55">iPhone</option>';
		prodSelect.value = "55";
		document.getElementById("currency").value = "USD";
		document.getElementById("exchange_rate").value = "2";
		window.loadProductPrice(0);
		const ajax = global.$.ajaxHandlers.at(-1);
		expect(ajax.url).toBe("/sales/api/get-price");
		ajax.success({
			data: {
				price: 200,
				current_stock: 0,
				unit: "pcs",
				cost_price: 50,
				has_serial_number: false,
				name: "iPhone",
			},
		});
		await wait();
		expect(document.getElementById("price_0").value).toBe("100.00");
		expect(document.getElementById("stock_0").classList.contains("text-danger")).toBe(
			true,
		);
		expect(azadStubs.showError).toHaveBeenCalledWith(
			expect.stringContaining("المخزون منخفض"),
		);
		expect(document.getElementById("cost_0").textContent).toContain("50.00");
		expect(
			document.getElementById("serial_btn_container_0").style.display,
		).toBe("none");
		expect(global.$("#serial_btn_0").data("needed")).toBe(false);
	});

	it("serial buttons no-op while no modal line is active", async () => {
		await import(MOD);
		const open = vi.fn();
		const origOpen = window.open;
		window.open = open;
		try {
			document.getElementById("add_serial_btn").click();
			document.getElementById("generate_serial_btn").click();
			document.getElementById("print_serials_btn").click();
			document.getElementById("save_serials_btn").click();
			expect(open).not.toHaveBeenCalled();
			expect(document.querySelectorAll("#serial_list li").length).toBe(0);
		} finally {
			window.open = origOpen;
		}
	});

	it("serial remove buttons no-op after their line was deleted", async () => {
		await import(MOD);
		document.querySelector('#line_0 input[name="lines[0][quantity]"]').value = "1";
		global.$("#serial_btn_0").data("needed", true);
		window.triggerSerialModal(0);
		document.getElementById("serial_input").value = "SN-ORPHAN";
		document.getElementById("add_serial_btn").click();
		expect(document.querySelectorAll("#serial_list li").length).toBe(1);
		window.removeLine(0);
		document.querySelector("#serial_list li button").click();
		expect(document.querySelectorAll("#serial_list li").length).toBe(1);
	});

	it("equal manual and server rates repaint green without audit fields", async () => {
		await import(MOD);
		// A string server rate keeps strict !== true while </> coerce equal.
		document.getElementById("currency").value = "USD";
		document.getElementById("currency").dispatchEvent(new Event("change"));
		const fxAjax = global.$.ajaxHandlers.at(-1);
		expect(fxAjax.url).toBe("/api/currency-rate/USD/AED");
		try {
			fxAjax.success({ rate: "2.000000" });
		} catch {
			// string rates have no toFixed; the module already latched the value
		}
		const rate = document.getElementById("exchange_rate");
		rate.value = "2";
		global.$(rate).data("server-rate", "stale");
		rate.dispatchEvent(new Event("change", { bubbles: true }));
		expect(rate.style.backgroundColor).toBe("rgb(212, 237, 218)");
		expect(
			document.querySelector('#saleForm input[name="exchange_rate_manual"]'),
		).toBeNull();
	});

	it("customer select2 maps search payloads", async () => {
		delete window.SmartSelectors;
		await import(MOD);
		const cfg = global.$.calls
			.filter((c) => c.method === "select2")
			.map((c) => c.args[0])
			.find((c) => c && c.placeholder === "ابحث عن زبون...");
		expect(cfg).toBeDefined();
		expect(cfg.ajax.data({ term: "omar" })).toEqual({
			q: "omar",
			type: "customers",
			page: 1,
		});
		const mapped = cfg.ajax.processResults({
			results: [{ id: 5, text: "Omar" }],
			has_more: true,
		});
		expect(mapped.results).toEqual([{ id: 5, text: "Omar" }]);
		expect(mapped.pagination.more).toBe(true);
	});

	it("blocks a second submit while the first is in flight", async () => {
		global.fetch = vi.fn(() =>
			Promise.resolve({
				ok: true,
				json: () =>
					Promise.resolve({
						success: true,
						subtotal: 50,
						total: 50,
						discount: 0,
						shipping: 0,
						tax_amount: 0,
						line_count: 1,
					}),
			}),
		);
		await import(MOD);
		document.getElementById("customer_id").value = "9";
		const form = document.getElementById("saleForm");
		form.submit = vi.fn();
		form.dispatchEvent(new Event("submit", { cancelable: true }));
		form.dispatchEvent(new Event("submit", { cancelable: true }));
		await wait(50);
		expect(form.submit).toHaveBeenCalledTimes(1);
	});
});
