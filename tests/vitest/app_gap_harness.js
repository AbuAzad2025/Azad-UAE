import { vi } from "vitest";

/**
 * Shared jQuery-compatible mock + import helpers for app.js gap-coverage tests.
 * The mock works against the real jsdom DOM (scoped find/closest/parent,
 * real attributes/classes/styles) so every init branch in static/js/app.js
 * executes faithfully. All .on() bindings are recorded for manual invocation.
 */
export function createGapJQuery(options = {}) {
	const elData = new WeakMap();
	const handlers = [];
	const calls = {
		modal: [],
		tab: [],
		alert: [],
		tooltip: [],
		select2: [],
		datepicker: [],
		datatable: [],
	};

	const getStore = (el) => {
		if (!elData.has(el)) elData.set(el, {});
		return elData.get(el);
	};
	const toCamel = (key) => String(key).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
	const isDatasetKey = (key) => /^[A-Za-z][A-Za-z0-9]*$/.test(key);
	const toStyleProp = (name) => String(name).replace(/-([a-z])/g, (_, c) => c.toUpperCase());

	const api = (elements) => {
		const els = (Array.isArray(elements) ? elements : [elements]).filter(
			(el) => el !== null && el !== undefined && el !== false,
		);
		const o = {
			length: els.length,
			get: (i) => (i === undefined ? els.slice() : els[i]),
			on: (evt, selOrFn, fn) => {
				const rec =
					typeof selOrFn === "function"
						? { elements: els.slice(), evt, selector: null, handler: selOrFn }
						: { elements: els.slice(), evt, selector: selOrFn, handler: fn };
				handlers.push(rec);
				els.forEach((el) => {
					if (el !== document && (el.nodeType === undefined || el.nodeType === null)) return;
					const store = getStore(el);
					const key = `on:${evt}`;
					store[key] = store[key] || [];
					store[key].push(rec);
				});
				return o;
			},
			off: () => o,
			trigger: (evt) => {
				els.forEach((el) => {
					const store = getStore(el);
					(store[`on:${evt}`] || []).forEach((rec) => {
						if (!rec.selector && typeof rec.handler === "function") {
							rec.handler.call(el, {
								type: evt,
								preventDefault: () => {},
								stopImmediatePropagation: () => {},
							});
						}
					});
				});
				return o;
			},
			each: (fn) => {
				els.forEach((el, i) => fn.call(el, i, el));
				return o;
			},
			find: (sel) => {
				const found = [];
				els.forEach((el) => {
					const scope = el === document ? document : el;
					if (!scope || typeof scope.querySelectorAll !== "function") return;
					scope.querySelectorAll(sel).forEach((node) => {
						if (!found.includes(node)) found.push(node);
					});
				});
				return api(found);
			},
			closest: (sel) => {
				const el = els[0];
				if (!el || typeof el.closest !== "function") return api([]);
				const found = el.closest(sel);
				return found ? api([found]) : api([]);
			},
			parent: () => {
				const el = els[0];
				return el && el.parentElement ? api([el.parentElement]) : api([]);
			},
			appendTo: (target) => {
				const dest = target && target.nodeType ? target : target && target[0];
				els.forEach((el) => {
					if (dest && typeof dest.appendChild === "function") dest.appendChild(el);
				});
				return o;
			},
			append: (child) => {
				const el = els[0];
				if (!el || typeof el.appendChild !== "function") return o;
				if (typeof child === "string") {
					const tmp = document.createElement("div");
					tmp.innerHTML = child;
					while (tmp.firstChild) el.appendChild(tmp.firstChild);
				} else if (child && typeof child.get === "function") {
					child.get().forEach((node) => {
						if (node && node.nodeType) el.appendChild(node);
					});
				} else if (child && child.nodeType) {
					el.appendChild(child);
				}
				return o;
			},
			remove: () => {
				els.forEach((el) => {
					if (typeof el.remove === "function") el.remove();
				});
				return o;
			},
			clone: () => api(els.map((el) => el.cloneNode(true))),
			data: (key, val) => {
				const el = els[0];
				if (!el) return val !== undefined ? o : undefined;
				const store = getStore(el);
				if (val !== undefined) {
					store[`data:${key}`] = val;
					try {
						const camel = toCamel(key);
						if (isDatasetKey(camel) && el.dataset) el.dataset[camel] = String(val);
					} catch {
						// dataset sync is best-effort
					}
					return o;
				}
				if (`data:${key}` in store) return store[`data:${key}`];
				try {
					const camel = toCamel(key);
					if (isDatasetKey(camel) && el.dataset && camel in el.dataset) return el.dataset[camel];
				} catch {
					// fall through
				}
				return undefined;
			},
			attr: (name, val) => {
				const el = els[0];
				if (!el || typeof el.getAttribute !== "function")
					return val !== undefined ? o : undefined;
				if (val !== undefined) {
					el.setAttribute(name, val);
					return o;
				}
				return el.getAttribute(name);
			},
			removeAttr: (name) => {
				els.forEach((el) => {
					if (el && typeof el.removeAttribute === "function") el.removeAttribute(name);
				});
				return o;
			},
			val: (v) => {
				if (!els.length) return v !== undefined ? o : "";
				if (v !== undefined) {
					els.forEach((el) => {
						el.value = v;
					});
					return o;
				}
				return els[0].value ?? "";
			},
			html: (v) => {
				if (!els.length) return v !== undefined ? o : "";
				if (v !== undefined) {
					els.forEach((el) => {
						el.innerHTML = v;
					});
					return o;
				}
				return els[0].innerHTML ?? "";
			},
			text: (v) => {
				if (!els.length) return v !== undefined ? o : "";
				if (v !== undefined) {
					els.forEach((el) => {
						el.textContent = v;
					});
					return o;
				}
				return els[0].textContent ?? "";
			},
			prop: (name, val) => {
				const el = els[0];
				if (!el) return val !== undefined ? o : undefined;
				if (val !== undefined) {
					el[name] = val;
					return o;
				}
				return el[name];
			},
			addClass: (cls) => {
				els.forEach((el) => {
					if (!el.classList) return;
					String(cls || "")
						.split(" ")
						.filter(Boolean)
						.forEach((c) => el.classList.add(c));
				});
				return o;
			},
			removeClass: (cls) => {
				els.forEach((el) => {
					if (!el.classList) return;
					if (cls === undefined) {
						el.removeAttribute("class");
						return;
					}
					String(cls)
						.split(" ")
						.filter(Boolean)
						.forEach((c) => el.classList.remove(c));
				});
				return o;
			},
			hasClass: (cls) => els.some((el) => el.classList && el.classList.contains(cls)),
			css: (name, val) => {
				const el = els[0];
				if (!el || !el.style) return typeof name === "string" && val === undefined ? "" : o;
				if (typeof name === "string" && val !== undefined) {
					el.style[toStyleProp(name)] = val;
					return o;
				}
				if (typeof name === "string") return el.style[toStyleProp(name)] || "";
				if (name && typeof name === "object") {
					Object.entries(name).forEach(([k, v]) => {
						el.style[toStyleProp(k)] = v;
					});
				}
				return o;
			},
			is: () => false,
			show: () => o,
			hide: () => o,
			not: (sel) => {
				if (typeof sel === "function")
					return api(els.filter((el, i) => !sel.call(el, i, el)));
				return api(
					els.filter((el) => {
						try {
							return !el.matches(sel);
						} catch {
							return true;
						}
					}),
				);
			},
			filter: (sel) => {
				if (typeof sel === "function")
					return api(els.filter((el, i) => sel.call(el, i, el)));
				return api(
					els.filter((el) => {
						try {
							return el.matches(sel);
						} catch {
							return false;
						}
					}),
				);
			},
			map: (fn) => {
				const arr = els.map((el, i) => fn.call(el, i, el));
				arr.get = (i) => (i === undefined ? arr.slice() : arr[i]);
				return arr;
			},
			serialize: () => {
				const isField = (node) =>
					node && node.tagName && /^(INPUT|SELECT|TEXTAREA)$/.test(node.tagName);
				const fields =
					els.length && isField(els[0])
						? els
						: els.flatMap((el) =>
								el && typeof el.querySelectorAll === "function"
									? Array.from(el.querySelectorAll("input, select, textarea"))
									: [],
							);
				return fields
					.filter((node) => node.name)
					.map(
						(node) =>
							`${encodeURIComponent(node.name)}=${encodeURIComponent(node.value ?? "")}`,
					)
					.join("&");
			},
			select2: (opts) => {
				els.forEach((el) => {
					getStore(el)["select2:opts"] = opts;
					calls.select2.push({ el, opts });
					if (el.classList) el.classList.add("select2-hidden-accessible");
				});
				return o;
			},
			datepicker: (opts) => {
				els.forEach((el) => {
					getStore(el)["datepicker:opts"] = opts;
					calls.datepicker.push({ el, opts });
				});
				return o;
			},
			DataTable: (opts) => {
				els.forEach((el) => {
					getStore(el)["datatable:opts"] = opts;
					calls.datatable.push({ el, opts });
				});
				return o;
			},
			tooltip: (...args) => {
				els.forEach((el) => calls.tooltip.push({ el, args }));
				return o;
			},
			modal: (...args) => {
				els.forEach((el) => calls.modal.push({ el, args }));
				return o;
			},
			tab: (...args) => {
				els.forEach((el) => calls.tab.push({ el, args }));
				return o;
			},
			alert: (...args) => {
				els.forEach((el) => calls.alert.push({ el, args }));
				return o;
			},
			ready: (fn) => {
				if (typeof fn === "function") fn();
				return o;
			},
		};
		els.forEach((el, i) => {
			o[i] = el;
		});
		return o;
	};

	const $ = (sel) => {
		if (typeof sel === "function") return api([]).ready(sel);
		if (sel && sel.nodeType) return api([sel]);
		if (sel && typeof sel.length === "number" && typeof sel.get === "function") return sel;
		if (Array.isArray(sel)) return api(sel);
		if (typeof sel === "string") {
			const trimmed = sel.trim();
			if (trimmed.startsWith("<")) {
				const tmp = document.createElement("div");
				tmp.innerHTML = trimmed;
				return api(Array.from(tmp.children));
			}
			return api(Array.from(document.querySelectorAll(sel)));
		}
		return api([]);
	};

	const plugins = options.plugins || "full";
	if (plugins === "full") {
		const dt = () => ({});
		dt.isDataTable = options.isDataTable || (() => false);
		$.fn = { DataTable: dt };
		$.fn.dataTable = options.buttons === false ? undefined : { Buttons: true };
		$.fn.datepicker = () => ({});
		$.fn.select2 = () => ({});
		$.fn.tooltip = () => ({});
		$.fn.modal = () => ({});
		$.fn.tab = () => ({});
		$.fn.alert = () => ({});
	} else {
		$.fn = {};
	}
	$.get = (...args) => (options.getImpl || (() => ({ done: () => ({ fail: () => ({}) }) })))(...args);
	$._handlers = handlers;
	$._calls = calls;
	$._storeOf = (el) => getStore(el);
	return $;
}

export function findHandlers($, evt, selector) {
	return $._handlers.filter((h) => h.evt === evt && h.selector === selector);
}

export function installGapGlobals($, lang = "ar") {
	global.$ = $;
	global.jQuery = $;
	window.$ = $;
	window.getCurrentLanguage = () => lang;
	globalThis.getCurrentLanguage = () => lang;
	window.I18N_LANG = lang;
	const mo = { cb: null, observeArgs: null };
	global.MutationObserver = class {
		constructor(cb) {
			mo.cb = cb;
		}
		observe(...args) {
			mo.observeArgs = args;
		}
		disconnect() {}
	};
	window.__azadModalStackingBound = false;
	window.__bootstrapCompatDelegatesBound = false;
	window._mutationPending = false;
	delete window.bootstrap;
	delete window.apiFetch;
	delete window.AzadPrint;
	delete window.applyDataTablePrintStyles;
	delete window.showNotification;
	delete window.showSystemAlert;
	delete window.saveFormData;
	delete window.performSearch;
	delete window.notify;
	delete globalThis.io;
	delete globalThis.Swal;
	return mo;
}

export function resetGapState() {
	document.body.innerHTML = "";
	delete window.bootstrap;
	delete window.apiFetch;
	delete window.AzadPrint;
	delete window.applyDataTablePrintStyles;
	delete window.showNotification;
	delete window.showSystemAlert;
	delete window.saveFormData;
	delete window.performSearch;
	delete window.notify;
	delete globalThis.io;
	delete globalThis.Swal;
	delete window.__azadModalStackingBound;
	delete window.__bootstrapCompatDelegatesBound;
	delete window._mutationPending;
}

export async function loadApp() {
	vi.resetModules();
	await import("../../static/js/app.js");
}

export function ensureCsrfMeta() {
	let meta = document.querySelector('meta[name="csrf-token"]');
	if (!meta) {
		meta = document.createElement("meta");
		meta.setAttribute("name", "csrf-token");
		meta.setAttribute("content", "test-csrf");
		document.head.appendChild(meta);
	}
	return meta;
}
