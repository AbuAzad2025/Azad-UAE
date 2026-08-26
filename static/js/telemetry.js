// cspell:ignore unhandledrejection sendBeacon keepalive popstate azad qids
/*
 * Azad frontend telemetry: error traps, breadcrumbs, offline-resilient batch shipper.
 * Privacy: never captures bodies, headers, cookies, storage or form values.
 * Silence: telemetry must never break the host page — every step is guarded.
 */
(() => {
	const ENDPOINT = "/api/v1/telemetry/logs";
	const MAX_BREADCRUMBS = 20;
	const FLUSH_BATCH_SIZE = 10;
	const MAX_BATCH_SEND = 50;
	const FLUSH_INTERVAL_MS = 30000;
	const MAX_STORED_EVENTS = 100;
	const DB_NAME = "azad-telemetry";
	const STORE_NAME = "outbox";
	const ALLOWED_CATEGORIES = ["SOFTWARE_EXCEPTION", "HARDWARE_WARN"];
	const SENSITIVE_QUERY_KEYS = ["token", "key", "password", "secret"];

	const queue = [];
	const breadcrumbs = [];
	let nextQueueId = 1;
	let dbPromise = null;
	let flushing = false;
	let booted = false;

	const safe = (fn) => {
		try {
			return fn();
		} catch {
			return undefined;
		}
	};

	const nowIso = () => {
		try {
			return new Date().toISOString();
		} catch {
			return "";
		}
	};

	const truncate = (value, max) => {
		const text = typeof value === "string" ? value : String(value || "");
		return text.length > max ? text.slice(0, max) : text;
	};

	const redactUrl = (rawUrl, maxLen = 500) => {
		try {
			const parsed = new URL(rawUrl || window.location.href, window.location.href);
			for (const key of SENSITIVE_QUERY_KEYS) {
				if (parsed.searchParams.has(key)) parsed.searchParams.set(key, "[redacted]");
			}
			return truncate(parsed.href, maxLen);
		} catch {
			return truncate(rawUrl, maxLen);
		}
	};

	const pageUrl = () => redactUrl(window.location.href);

	const isTelemetryUrl = (rawUrl) => {
		try {
			const parsed = new URL(rawUrl || "", window.location.href);
			if (parsed.pathname === ENDPOINT) return true;
			const legacy = typeof window._LOG_ENDPOINT === "string" ? window._LOG_ENDPOINT : "";
			return legacy !== "" && parsed.href === new URL(legacy, window.location.href).href;
		} catch {
			return false;
		}
	};

	const addBreadcrumb = (crumb) => {
		safe(() => {
			breadcrumbs.push(crumb);
			if (breadcrumbs.length > MAX_BREADCRUMBS) {
				breadcrumbs.splice(0, breadcrumbs.length - MAX_BREADCRUMBS);
			}
		});
	};

	// ── IndexedDB outbox (tiny promise wrapper, no library) ─────────────
	const openDb = () => {
		if (dbPromise) return dbPromise;
		dbPromise = new Promise((resolve) => {
			try {
				const request = indexedDB.open(DB_NAME, 1);
				request.onupgradeneeded = () => {
					try {
						request.result.createObjectStore(STORE_NAME, { keyPath: "qid" });
					} catch {
						/* store may already exist */
					}
				};
				request.onsuccess = () => resolve(request.result);
				request.onerror = () => resolve(null);
				request.onblocked = () => resolve(null);
			} catch {
				resolve(null);
			}
		});
		return dbPromise;
	};

	const idbPut = (record) => {
		openDb().then((db) => {
			if (!db) return;
			try {
				db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).put(record);
			} catch {
				/* outbox unavailable — in-memory queue still works */
			}
		});
	};

	const idbRemove = (qids) => {
		openDb().then((db) => {
			if (!db || !qids.length) return;
			try {
				const store = db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME);
				for (const qid of qids) store.delete(qid);
			} catch {
				/* best effort */
			}
		});
	};

	const idbTrim = () => {
		openDb().then((db) => {
			if (!db) return;
			try {
				const store = db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME);
				const keysRequest = store.getAllKeys();
				keysRequest.onsuccess = () => {
					const keys = keysRequest.result || [];
					const overflow = keys.length - MAX_STORED_EVENTS;
					for (let i = 0; i < overflow; i += 1) store.delete(keys[i]);
				};
			} catch {
				/* best effort */
			}
		});
	};

	const idbDrain = () =>
		openDb().then(
			(db) =>
				new Promise((resolve) => {
					if (!db) {
						resolve([]);
						return;
					}
					try {
						const tx = db.transaction(STORE_NAME, "readwrite");
						const store = tx.objectStore(STORE_NAME);
						const allRequest = store.getAll();
						allRequest.onsuccess = () => {
							const records = allRequest.result || [];
							store.clear();
							resolve(records);
						};
						allRequest.onerror = () => resolve([]);
					} catch {
						resolve([]);
					}
				}),
		);

	// ── Shipper ──────────────────────────────────────────────────────────
	const sendBatch = (body) => {
		const beaconOk = safe(() => {
			if (typeof navigator.sendBeacon !== "function") return false;
			const blob = new Blob([body], { type: "application/json" });
			return navigator.sendBeacon(ENDPOINT, blob);
		});
		if (beaconOk) return Promise.resolve(true);
		try {
			return fetch(ENDPOINT, {
				method: "POST",
				body,
				headers: { "Content-Type": "application/json" },
				credentials: "same-origin",
				keepalive: true,
			})
				.then((response) => response.ok)
				.catch(() => false);
		} catch {
			return Promise.resolve(false);
		}
	};

	const requeue = (batch) => {
		safe(() => {
			for (let i = batch.length - 1; i >= 0; i -= 1) {
				queue.unshift(batch[i]);
				idbPut(batch[i]);
			}
			if (queue.length > MAX_STORED_EVENTS) {
				queue.splice(0, queue.length - MAX_STORED_EVENTS);
			}
		});
	};

	const flush = () => {
		if (flushing || queue.length === 0) return;
		const batch = queue.splice(0, MAX_BATCH_SEND);
		flushing = true;
		sendBatch(JSON.stringify({ events: batch }))
			.then((ok) => {
				flushing = false;
				if (ok) {
					idbRemove(batch.map((event) => event.qid));
				} else {
					requeue(batch);
				}
			})
			.catch(() => {
				flushing = false;
				requeue(batch);
			});
	};

	const enqueue = (event) => {
		safe(() => {
			const record = { qid: nextQueueId, ...event };
			nextQueueId += 1;
			queue.push(record);
			if (queue.length > MAX_STORED_EVENTS) {
				queue.splice(0, queue.length - MAX_STORED_EVENTS);
			}
			idbPut(record);
			idbTrim();
			if (queue.length >= FLUSH_BATCH_SIZE) flush();
		});
	};

	const buildEvent = ({ category, message, level, stack, extra }) => ({
		category: ALLOWED_CATEGORIES.includes(category) ? category : "SOFTWARE_EXCEPTION",
		message: truncate(message, 2000),
		level,
		url: pageUrl(),
		stack: stack ? truncate(stack, 4000) : undefined,
		client_ts: nowIso(),
		username:
			(typeof window.CURRENT_USERNAME === "string" ? window.CURRENT_USERNAME : null) ||
			window.CURRENT_USER?.username ||
			undefined,
		breadcrumbs: breadcrumbs.slice(),
		extra: extra || {},
	});

	const capture = (category, message, extra) => {
		safe(() => {
			if (!message) return;
			const cleanCategory = ALLOWED_CATEGORIES.includes(category) ? category : "SOFTWARE_EXCEPTION";
			enqueue(
				buildEvent({
					category: cleanCategory,
					message,
					level: cleanCategory === "HARDWARE_WARN" ? "WARNING" : "ERROR",
					extra: extra && typeof extra === "object" ? extra : {},
				}),
			);
		});
	};

	// ── Global traps ─────────────────────────────────────────────────────
	const armErrorTrap = () => {
		window.addEventListener("error", (ev) => {
			safe(() => {
				if (!ev?.message) return; // resource-load errors carry no message
				enqueue(
					buildEvent({
						category: "SOFTWARE_EXCEPTION",
						message: truncate(ev.message, 2000),
						level: "ERROR",
						stack: ev.error?.stack ? ev.error.stack : "",
						extra: {
							kind: "error",
							filename: truncate(ev.filename || "", 500),
							lineno: ev.lineno || 0,
							colno: ev.colno || 0,
						},
					}),
				);
			});
		});
		window.addEventListener("unhandledrejection", (ev) => {
			safe(() => {
				const reason = ev ? ev.reason : null;
				const message = reason?.message
					? reason.message
					: truncate(String(reason || "unhandled rejection"), 2000);
				enqueue(
					buildEvent({
						category: "SOFTWARE_EXCEPTION",
						message,
						level: "ERROR",
						stack: reason?.stack ? reason.stack : "",
						extra: { kind: "unhandledrejection" },
					}),
				);
			});
		});
	};

	// ── Breadcrumb sources ───────────────────────────────────────────────
	const armClickBreadcrumbs = () => {
		document.addEventListener(
			"click",
			(ev) => {
				safe(() => {
					const target = ev.target?.closest ? ev.target.closest("*") : ev.target;
					if (!target?.tagName) return;
					addBreadcrumb({
						type: "click",
						tag: truncate(target.tagName.toLowerCase(), 30),
						id: truncate(target.id || "", 60),
						text: truncate((target.textContent || "").trim(), 60),
						ts: nowIso(),
					});
				});
			},
			true,
		);
	};

	const armRouteBreadcrumbs = () => {
		const wrap = (method) => {
			const original = history[method];
			if (typeof original !== "function") return;
			history[method] = (...args) => {
				const result = original.apply(history, args);
				addBreadcrumb({ type: "route", url: pageUrl(), ts: nowIso() });
				return result;
			};
		};
		safe(() => wrap("pushState"));
		safe(() => wrap("replaceState"));
		window.addEventListener("popstate", () => {
			addBreadcrumb({ type: "route", url: pageUrl(), ts: nowIso() });
		});
	};

	const armFetchBreadcrumbs = () => {
		if (typeof window.fetch !== "function") return;
		const originalFetch = window.fetch;
		window.fetch = (...args) => {
			const started = safe(() => performance.now()) || 0;
			let method = "GET";
			let url = "";
			safe(() => {
				const input = args[0];
				if (typeof input === "string") {
					url = input;
				} else if (input?.url) {
					url = input.url;
					if (input.method) method = String(input.method).toUpperCase();
				}
				const init = args[1];
				if (init?.method) method = String(init.method).toUpperCase();
			});
			const note = (status) => {
				safe(() => {
					if (!url || isTelemetryUrl(url)) return;
					addBreadcrumb({
						type: "fetch",
						method: truncate(method, 10),
						url: redactUrl(url, 300),
						status,
						duration_ms: Math.round((safe(() => performance.now()) || 0) - started),
						ts: nowIso(),
					});
				});
			};
			return originalFetch
				.apply(window, args)
				.then((response) => {
					note(response ? response.status : 0);
					return response;
				})
				.catch((err) => {
					note(0);
					throw err;
				});
		};
	};

	// ── Flush triggers ───────────────────────────────────────────────────
	const armFlushTriggers = () => {
		document.addEventListener("visibilitychange", () => {
			if (document.visibilityState === "hidden") flush();
		});
		window.addEventListener("online", () => {
			idbDrain().then((records) => {
				safe(() => {
					const kept = records.slice(-MAX_STORED_EVENTS);
					for (const record of kept) {
						if (record && typeof record === "object") queue.push(record);
					}
				});
				flush();
			});
		});
		setInterval(() => safe(flush), FLUSH_INTERVAL_MS);
	};

	const boot = () => {
		if (booted) return;
		booted = true;
		safe(armErrorTrap);
		safe(armClickBreadcrumbs);
		safe(armRouteBreadcrumbs);
		safe(armFetchBreadcrumbs);
		safe(armFlushTriggers);
		idbDrain().then((records) => {
			safe(() => {
				const kept = records.slice(-MAX_STORED_EVENTS);
				for (const record of kept) {
					if (record && typeof record === "object") queue.push(record);
				}
			});
			safe(flush);
		});
	};

	window.azadTelemetry = { capture };
	boot();
})();
