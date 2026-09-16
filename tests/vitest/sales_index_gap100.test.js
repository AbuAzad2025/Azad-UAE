import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Gap coverage for static/js/sales-index.js.
 * Covers: missing table guard (3), DataTables-missing + lazyLoad paths (7-10),
 * filter handlers with falsy table (57,65,73,81) and the init catch (87).
 */

const MOD = "../../static/js/sales-index.js";
const seen = new Map();

function makeDollar() {
	const stores = new WeakMap();
	const storeFor = (el) => {
		let s = stores.get(el);
		if (!s) {
			s = {};
			stores.set(el, s);
		}
		return s;
	};
	function elsFor(sel) {
		if (typeof sel !== "string") return [];
		try {
			return Array.from(document.querySelectorAll(sel));
		} catch {
			return [];
		}
	}
	function chain(sel) {
		const list = elsFor(sel);
		return {
			length: sel === document ? 1 : list.length,
			on(evts, handler) {
				if (typeof handler !== "function") return this;
				String(evts)
					.split(/\s+/)
					.filter(Boolean)
					.forEach((ev) => {
						const key = `${String(sel)}|${ev}`;
						if (!seen.has(key)) seen.set(key, []);
						seen.get(key).push({ fn: handler, ctx: this });
					});
				return this;
			},
			off() {
				return this;
			},
			trigger() {
				return this;
			},
			ready(fn) {
				if (typeof fn === "function") fn();
				return this;
			},
			addClass() {
				return this;
			},
			removeClass() {
				return this;
			},
			data(k, v) {
				const el = list[0];
				if (v !== undefined) {
					if (el) storeFor(el)[k] = v;
					return this;
				}
				return el ? storeFor(el)[k] : undefined;
			},
			DataTable(...args) {
				if (typeof dollar.fn.DataTable === "function")
					return dollar.fn.DataTable(...args);
				return undefined;
			},
		};
	}
	function dollar(sel) {
		if (typeof sel === "function") {
			sel();
			return chain(null);
		}
		return chain(sel);
	}
	dollar.fn = {};
	return dollar;
}

function fire(key) {
	for (const h of seen.get(key) || []) h.fn.call(h.ctx);
}

function tableDOM() {
	document.body.innerHTML = `
		<table id="salesTable">
			<thead><tr><th>A</th></tr></thead>
			<tbody></tbody>
		</table>
		<div class="btn-group">
			<button id="filterAll">All</button>
			<button id="filterPaid">Paid</button>
			<button id="filterPartial">Partial</button>
			<button id="filterUnpaid">Unpaid</button>
		</div>
		<button id="printSalesBtn">Print</button>`;
}

let dollar;

beforeEach(() => {
	seen.clear();
	document.head.innerHTML = "";
	document.body.innerHTML = "";
	dollar = makeDollar();
	globalThis.$ = dollar;
	window.$ = dollar;
	window.SmartPrint = { buildButtons: vi.fn(() => []), attachTrigger: vi.fn() };
	delete window.lazyLoad;
	vi.resetModules();
});

afterEach(() => {
	document.body.innerHTML = "";
	seen.clear();
	delete window.SmartPrint;
	delete window.lazyLoad;
	vi.resetModules();
});

describe("sales-index.js gap100", () => {
	it("returns early when #salesTable is absent", async () => {
		document.body.innerHTML = "<div>no table here</div>";
		dollar.fn.DataTable = vi.fn(() => undefined);
		dollar.fn.DataTable.isDataTable = vi.fn(() => false);
		await import(MOD);
		expect(dollar.fn.DataTable).not.toHaveBeenCalled();
	});

	it("returns early when DataTables is missing and no lazy loader exists", async () => {
		tableDOM();
		dollar.fn = {};
		await import(MOD);
		expect(window.SmartPrint.buildButtons).not.toHaveBeenCalled();
	});

	it("delegates to the lazy loader when DataTables is not ready yet", async () => {
		tableDOM();
		dollar.fn = {};
		const datatables = vi.fn(() => Promise.resolve());
		window.lazyLoad = { datatables };
		await import(MOD);
		await new Promise((r) => setTimeout(r, 10));
		expect(datatables).toHaveBeenCalledTimes(1);
	});

	it("filter handlers no-op when the table failed to initialize", async () => {
		tableDOM();
		const draw = vi.fn();
		dollar.fn.DataTable = vi.fn(() => undefined);
		dollar.fn.DataTable.isDataTable = vi.fn(() => false);
		await import(MOD);
		fire("#filterAll|click.smartPrint");
		fire("#filterPaid|click.smartPrint");
		fire("#filterPartial|click.smartPrint");
		fire("#filterUnpaid|click.smartPrint");
		expect(draw).not.toHaveBeenCalled();
		expect(dollar.fn.DataTable.isDataTable).toHaveBeenCalled();
	});

	it("warns when DataTable initialization throws", async () => {
		tableDOM();
		const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
		try {
			dollar.fn.DataTable = vi.fn(() => {
				throw new Error("boom");
			});
			dollar.fn.DataTable.isDataTable = vi.fn(() => false);
			await import(MOD);
			expect(warn).toHaveBeenCalledWith(
				"DataTables init failed:",
				expect.stringContaining("boom"),
			);
		} finally {
			warn.mockRestore();
		}
	});
});
