import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Gap coverage for static/js/sales.js (100% lines).
 * Covers: jQuery loader without window.jQuery (31-34), Sortable init (121-125),
 * currentMaxIndex regex fallback (139-141), renumber id rewrite (150),
 * clearRow select reset (159-160), isSelect2 incl. catch (194-198),
 * reinitSelect2 incl. catch (201-205), initAjaxSelect incl. transport/data/
 * processResults (209-229), row select2 wiring incl. select2:select payload,
 * price fallback and warehouse change (252-306,312) and header ajax-select
 * init (365-375).
 */

const MOD = "../../static/js/sales.js";

function makeSalesJQuery() {
	const dataStore = new WeakMap();
	const select2Calls = [];
	const storeOf = (el) => {
		let s = dataStore.get(el);
		if (!s) {
			s = {};
			dataStore.set(el, s);
		}
		return s;
	};
	function wrap(list) {
		return {
			length: list.length,
			each(fn) {
				list.forEach((el, i) => fn.call(el, i, el));
				return this;
			},
			find(sel) {
				const out = [];
				list.forEach((el) => {
					if (el.querySelectorAll) out.push(...el.querySelectorAll(sel));
				});
				return wrap(out);
			},
			closest(sel) {
				const out = [];
				list.forEach((el) => {
					const c = el.closest ? el.closest(sel) : null;
					if (c) out.push(c);
				});
				return wrap(out);
			},
			empty() {
				list.forEach((el) => {
					el.innerHTML = "";
				});
				return this;
			},
			val(v) {
				if (v !== undefined) {
					list.forEach((el) => {
						if ("value" in el) el.value = v === null ? "" : String(v);
					});
					return this;
				}
				return list[0] ? list[0].value : "";
			},
			data(k, v) {
				if (v !== undefined) {
					list.forEach((el) => {
						storeOf(el)[k] = v;
					});
					return this;
				}
				const el = list[0];
				if (!el) return undefined;
				if (k === "select2" && el.hasAttribute("data-throw-select2"))
					throw new Error("no select2 data");
				const s = dataStore.get(el);
				if (s && Object.prototype.hasOwnProperty.call(s, k)) return s[k];
				const a = el.getAttribute ? el.getAttribute(`data-${k}`) : null;
				return a === null ? undefined : a;
			},
			hasClass(c) {
				return list[0] ? list[0].classList.contains(c) : false;
			},
			off(...args) {
				const el = list[0];
				if (args.length === 0 && el && el.hasAttribute("data-throw-off"))
					throw new Error("off boom");
				return this;
			},
			on(ev, handler) {
				if (typeof handler === "function") {
					list.forEach((el) =>
						String(ev)
							.split(/\s+/)
							.filter(Boolean)
							.forEach((e) => el.addEventListener(e, handler)),
					);
				}
				return this;
			},
			trigger(ev) {
				list.forEach((el) =>
					el.dispatchEvent(new Event(ev, { bubbles: true })),
				);
				return this;
			},
			select2(arg) {
				if (typeof arg === "string") return this;
				list.forEach((el) => {
					storeOf(el).select2 = true;
					select2Calls.push({ el, opts: arg });
				});
				return this;
			},
		};
	}
	function dollar(sel) {
		if (typeof sel === "function") {
			sel();
			return wrap([]);
		}
		if (typeof sel === "string") {
			const s = sel.trim();
			if (s.startsWith("<")) {
				const t = document.createElement("template");
				t.innerHTML = s;
				return wrap(
					t.content.firstElementChild ? [t.content.firstElementChild] : [],
				);
			}
			return wrap(Array.from(document.querySelectorAll(sel)));
		}
		if (sel instanceof Element) return wrap([sel]);
		if (sel === document || sel === window) return wrap([sel]);
		return wrap([]);
	}
	dollar.fn = {
		select2() {},
	};
	dollar.ajaxCalls = [];
	dollar.ajaxImpl = null;
	dollar.ajax = (params) => {
		dollar.ajaxCalls.push(params);
		if (dollar.ajaxImpl) return dollar.ajaxImpl(params);
		return Promise.resolve({ results: [] });
	};
	dollar.select2Calls = select2Calls;
	return dollar;
}

const flush = (ms = 20) => new Promise((r) => setTimeout(r, ms));

const SORTABLE_SRC =
	"https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js";
const JQUERY_SRC =
	"https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js";

let mock$;

function installJQuery(withSelect2 = true) {
	mock$ = makeSalesJQuery();
	if (!withSelect2) mock$.fn = {};
	globalThis.$ = mock$;
	globalThis.jQuery = mock$;
	window.$ = mock$;
	window.jQuery = mock$;
	return mock$;
}

function baseDOM(rowsHTML) {
	document.head.innerHTML = "";
	document.body.innerHTML = `
		<form id="saleForm">
			<input name="sale_date" type="datetime-local" value="">
			<select name="currency"><option value="">--</option><option value="USD">USD</option></select>
			<div id="saleLines">${rowsHTML}</div>
			<button type="button" id="addLine">+</button>
			<input id="taxRate" value="0">
			<input id="shippingCost" value="0">
		</form>`;
}

const rowWithIds = (i) => `
	<div class="sale-line" data-index="${i}">
		<input type="number" id="lines-${i}-quantity" name="lines-${i}-quantity" class="quantity-input" value="1">
		<input type="number" id="lines-${i}-unit_price" name="lines-${i}-unit_price" class="price-input" value="10">
		<input type="number" id="lines-${i}-discount_rate" name="lines-${i}-discount_rate" class="discount-input" value="0">
		<button type="button" class="remove-line">x</button>
		<span class="stock-badge"></span>
	</div>`;

function select2DOM() {
	return `
	<div class="sale-line" data-index="0">
		<select class="warehouse-select" data-endpoint="/api/warehouses" data-placeholder="WH">
			<option value="">-</option><option value="1" selected>W1</option>
		</select>
		<select class="product-select" data-endpoint="/api/products" data-placeholder="PR">
			<option value="">-</option><option value="2">P2</option>
		</select>
		<select class="ajax-select" data-endpoint="/api/inner" data-placeholder="IN">
			<option value="">-</option>
		</select>
		<input type="number" name="lines-0-quantity" class="quantity-input" value="1">
		<input type="number" name="lines-0-unit_price" class="price-input" value="10">
		<input type="number" name="lines-0-discount_rate" class="discount-input" value="0">
		<input type="number" name="lines-0-tax" class="tax-input" value="0">
		<button type="button" class="remove-line">x</button>
		<span class="stock-badge"></span>
	</div>
	<div class="sale-line" data-index="1">
		<select class="product-select" data-endpoint="/api/products">
			<option value="">-</option>
		</select>
		<input type="number" name="lines-1-quantity" class="quantity-input" value="1">
		<input type="number" name="lines-1-unit_price" class="price-input" value="10">
		<input type="number" name="lines-1-discount_rate" class="discount-input" value="0">
		<input type="number" name="lines-1-tax" class="tax-input" value="0">
		<button type="button" class="remove-line">x</button>
		<span class="stock-badge"></span>
	</div>
	<div class="sale-line" data-index="2">
		<select class="warehouse-select" data-endpoint="/api/warehouses">
			<option value="">-</option>
		</select>
		<input type="number" name="lines-2-quantity" class="quantity-input" value="1">
		<input type="number" name="lines-2-unit_price" class="price-input" value="10">
		<input type="number" name="lines-2-discount_rate" class="discount-input" value="0">
		<input type="number" name="lines-2-tax" class="tax-input" value="0">
		<button type="button" class="remove-line">x</button>
		<span class="stock-badge"></span>
	</div>
	<select class="ajax-select" data-endpoint="/api/customers" data-placeholder="CUST" data-throw-select2>
		<option value="">-</option>
	</select>
	<select class="ajax-select"><option value="">-</option></select>`;
}

function preseedSortable() {
	const s = document.createElement("script");
	s.src = SORTABLE_SRC;
	document.head.appendChild(s);
	window.Sortable = vi.fn();
}

function mockFetch(info = { stock: 5, price: 33 }) {
	globalThis.fetch = vi.fn(async () => ({
		json: async () => ({ ...info }),
	}));
}

beforeEach(() => {
	document.head.innerHTML = "";
	document.body.innerHTML = "";
	delete window.Sortable;
	global.alert = vi.fn();
	mockFetch();
	vi.resetModules();
});

afterEach(() => {
	document.head.innerHTML = "";
	document.body.innerHTML = "";
	delete window.Sortable;
	delete global.fetch;
	vi.resetModules();
});

describe("sales.js gap100", () => {
	it("loads jQuery from CDN when missing and continues the select2 chain", async () => {
		installJQuery();
		delete window.jQuery;
		delete globalThis.jQuery;
		baseDOM("");
		document
			.getElementById("saleForm")
			.insertAdjacentHTML("afterbegin", '<div class="select2"></div>');
		await import(MOD);
		const tag = document.head.querySelector(`script[src="${JQUERY_SRC}"]`);
		expect(tag).not.toBeNull();
		tag.onload();
		await flush();
		const cssLinks = document.head.querySelectorAll('link[rel="stylesheet"]');
		expect(cssLinks.length).toBeGreaterThanOrEqual(1);
	});

	it("initializes Sortable when the vendor script is ready", async () => {
		installJQuery();
		baseDOM(rowWithIds(0));
		preseedSortable();
		await import(MOD);
		await flush();
		expect(window.Sortable).toHaveBeenCalledWith(
			document.getElementById("saleLines"),
			expect.objectContaining({ handle: ".drag-handle", animation: 150 }),
		);
	});

	it("falls back to name-pattern matching for rows without dataset index", async () => {
		installJQuery();
		baseDOM(`
			<div class="sale-line">
				<input type="number" name="lines-3-quantity" class="quantity-input" value="1">
				<input type="number" name="lines-3-unit_price" class="price-input" value="10">
				<button type="button" class="remove-line">x</button>
				<span class="stock-badge"></span>
			</div>
			<div class="sale-line" data-index="abc">
				<input type="number" name="lines-9-quantity" class="quantity-input" value="1">
				<input type="number" name="lines-9-unit_price" class="price-input" value="10">
				<button type="button" class="remove-line">x</button>
				<span class="stock-badge"></span>
			</div>`);
		await import(MOD);
		expect(window._salesCurrentMaxIndex()).toBe(9);
	});

	it("renumbers element ids along with names", async () => {
		installJQuery();
		baseDOM(rowWithIds(0));
		await import(MOD);
		const row = document.querySelector(".sale-line");
		window._salesRenumberRow(row, 7);
		expect(row.querySelector('[name$="-quantity"]').id).toBe(
			"lines-7-quantity",
		);
		expect(row.querySelector('[name$="-quantity"]').name).toBe(
			"lines-7-quantity",
		);
	});

	it("clearRow resets selects and notifies listeners", async () => {
		installJQuery();
		baseDOM(`
			<div class="sale-line" data-index="0" data-price-manual="1">
				<input type="number" name="lines-0-quantity" class="quantity-input" value="4">
				<input type="text" name="lines-0-note" value="keep?">
				<select name="lines-0-warehouse"><option value="">-</option><option value="1">W</option></select>
				<button type="button" class="remove-line">x</button>
				<span class="stock-badge">old</span>
			</div>`);
		await import(MOD);
		const row = document.querySelector(".sale-line");
		const sel = row.querySelector("select");
		sel.selectedIndex = 1;
		let changed = 0;
		sel.addEventListener("change", () => {
			changed++;
		});
		window._salesClearRow(row);
		expect(sel.selectedIndex).toBe(0);
		expect(changed).toBe(1);
		expect(row.querySelector('[name$="-quantity"]').value).toBe("");
		expect(row.querySelector(".stock-badge").textContent).toBe("");
		expect(row.dataset.priceManual).toBe("");
	});

	it("skips select2 wiring gracefully when the plugin is missing", async () => {
		installJQuery(false);
		baseDOM(select2DOM());
		preseedSortable();
		await expect(import(MOD)).resolves.toBeDefined();
		await flush();
	});

	it("wires warehouse/product ajax selects, header selects and availability", async () => {
		installJQuery();
		baseDOM(select2DOM());
		preseedSortable();
		await import(MOD);
		await flush();

		// header ajax-select with throwing data() still gets select2 (isSelect2 catch)
		const throwEl = document.querySelector("[data-throw-select2]");
		expect(
			mock$.select2Calls.some((c) => c.el === throwEl),
		).toBe(true);

		const row0 = document.querySelectorAll(".sale-line")[0];
		const wh = row0.querySelector("select.warehouse-select");
		const pd = row0.querySelector("select.product-select");
		const priceInp = row0.querySelector('input[name$="-unit_price"]');
		const badge = row0.querySelector(".stock-badge");

		const whCall = mock$.select2Calls.find((c) => c.el === wh);
		expect(whCall).toBeDefined();
		// ajax.data maps the search term
		expect(whCall.opts.ajax.data({ term: "bolt" })).toEqual({
			q: "bolt",
			limit: 50,
		});
		// ajax.processResults accepts {results} and bare arrays
		expect(whCall.opts.ajax.processResults({ results: [{ id: 1 }] })).toEqual({
			results: [{ id: 1 }],
		});
		expect(whCall.opts.ajax.processResults([{ id: 2 }])).toEqual({
			results: [{ id: 2 }],
		});
		// transport with endpoint function resolves through jQuery.ajax
		const pdCall = mock$.select2Calls.find((c) => c.el === pd);
		expect(pdCall).toBeDefined();
		const ok = vi.fn();
		const ng = vi.fn();
		const params = { url: "OLD" };
		pdCall.opts.ajax.transport(params, ok, ng);
		expect(params.url).toBe("/api/warehouses/1/products");
		await flush();
		expect(ok).toHaveBeenCalled();
		expect(ng).not.toHaveBeenCalled();
		// transport failure path
		mock$.ajaxImpl = () => Promise.reject(new Error("down"));
		const ok2 = vi.fn();
		const ng2 = vi.fn();
		whCall.opts.ajax.transport({ url: "OLD" }, ok2, ng2);
		await flush();
		expect(ng2).toHaveBeenCalled();
		expect(ok2).not.toHaveBeenCalled();
		mock$.ajaxImpl = null;
		// header select uses the string endpoint branch
		const headerCall = mock$.select2Calls.find((c) => c.el === throwEl);
		const hp = { url: "OLD" };
		headerCall.opts.ajax.transport(hp, vi.fn(), vi.fn());
		expect(hp.url).toBe("/api/customers");
		await flush();

		// select2:select with inline price
		const emit = (data) => {
			pd.value = "2";
			const ev = new Event("select2:select", { bubbles: true });
			ev.params = { data };
			pd.dispatchEvent(ev);
		};
		emit({ id: 2, price: 50 });
		await flush(30);
		expect(priceInp.value).toBe("50.00");
		expect(badge.textContent).toBe("متاح: 5");

		// select2:select without price falls back to fetchProductInfo
		emit({ id: 2 });
		await flush(30);
		expect(priceInp.value).toBe("33.00");

		// manual price flag skips remote updates
		row0.dataset.priceManual = "1";
		emit({ id: 2, price: 77 });
		await flush(30);
		expect(priceInp.value).toBe("33.00");
		row0.dataset.priceManual = "";

		// warehouse change re-inits products (reinit catch) and clears badge on empty ids
		pd.setAttribute("data-throw-off", "");
		wh.dispatchEvent(new Event("change", { bubbles: true }));
		await flush(30);
		expect(mock$.select2Calls.filter((c) => c.el === pd).length).toBeGreaterThan(
			1,
		);
		expect(badge.textContent).toBe("");
		// second change without the throwing flag takes the normal reinit path
		pd.removeAttribute("data-throw-off");
		wh.value = "1";
		wh.dispatchEvent(new Event("change", { bubbles: true }));
		await flush(30);

		// updateAvailability: missing badge, null stock and normal stock
		const bare = document.createElement("div");
		await window._salesUpdateAvailability(1, 1, bare);
		mockFetch({});
		const row = document.querySelector(".sale-line");
		await window._salesUpdateAvailability(0, 0, row);
		expect(row.querySelector(".stock-badge").textContent).toBe("");
		mockFetch({ stock: 8 });
		await window._salesUpdateAvailability(1, 1, row);
		expect(row.querySelector(".stock-badge").textContent).toBe("متاح: 8");
	});
});
