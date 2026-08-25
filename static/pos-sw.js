const POS_CACHE = "pos-cache-v5";
const POS_QUEUE_DB = "pos-offline-queue";
const POS_QUEUE_STORE = "checkout-queue";

const ASSETS_TO_CACHE = [
	"/static/css/pos.css",
	"/static/js/barcode-scanner.js",
	"/static/js/pos/pos-config.js",
	"/static/js/pos/cfd-broadcast.js",
	"/static/js/pos/scale-serial.js",
	"/static/js/pos/offline-catalog.js",
	"/static/js/pos/offline-sync.js",
	"/static/js/pos/terminal.js",
	"/static/js/pos/escpos-printer.js",
	"/static/js/pos/print-tickets.js",
	"/static/js/pos/core.js",
	"/static/js/pos/cart.js",
	"/static/js/pos/ui.js",
	"/static/js/pos/payments.js",
	"/static/js/pos/printer.js",
	"/static/js/pos/cashier-logic.js",
	"/static/js/pos/index.js",
	"/static/js/pos/offline.js",
];

self.addEventListener("install", (event) => {
	event.waitUntil(
		caches
			.open(POS_CACHE)
			.then((cache) => {
				const base = self.location.origin;
				return Promise.allSettled(
					ASSETS_TO_CACHE.map((url) => cache.add(base + url).catch(() => {})),
				);
			})
			.then(() => self.skipWaiting()),
	);
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== POS_CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim()),
	);
});

self.addEventListener("fetch", (event) => {
	const { request } = event;
	const url = new URL(request.url);

	// Only handle same-origin requests
	if (url.origin !== self.location.origin) return;

	if (request.method === "POST" && isQueueablePost(url.pathname)) {
		event.respondWith(networkFirstWithQueue(request));
		return;
	}

	if (isStaticAsset(request)) {
		event.respondWith(cacheFirst(request));
		return;
	}

	// POS APIs and currency APIs need network-first but with graceful offline fallback
	if (url.pathname.startsWith("/pos/") || url.pathname.startsWith("/api/")) {
		event.respondWith(networkFirst(request));
	}
});

// Financial mutations that must survive connectivity loss: checkout sales,
// returns/refunds, line voids, and cash pay-in/out movements.
function isQueueablePost(pathname) {
	return (
		pathname === "/pos/api/checkout" ||
		pathname === "/pos/api/returns" ||
		pathname === "/pos/api/cash-movements" ||
		(pathname.startsWith("/pos/api/carts/") && pathname.endsWith("/void-line"))
	);
}

function isStaticAsset(request) {
	const url = new URL(request.url);
	// Query strings like ?v=xxx are cache-busted static assets — still static
	const pathname = url.pathname;
	const ext = pathname.split(".").pop().toLowerCase();
	return (
		[
			"css",
			"js",
			"png",
			"jpg",
			"jpeg",
			"gif",
			"svg",
			"woff",
			"woff2",
			"ttf",
			"eot",
			"map",
		].includes(ext) || ASSETS_TO_CACHE.some((a) => pathname === a || pathname.startsWith(`${a}?`))
	);
}

async function cacheFirst(request) {
	const cached = await caches.match(request);
	if (cached) return cached;
	try {
		return await fetchAndCache(request);
	} catch (_) {
		// Offline and not cached — return the cached fallback if any, otherwise fail gracefully
		const fallback = await caches.match(request);
		if (fallback) return fallback;
		throw _;
	}
}

async function networkFirst(request) {
	try {
		// For the session probe we never want a stale cached 503
		if (request.url.includes("/pos/api/session/current")) {
			const fresh = await fetch(request);
			// Cache successful session probes for offline display
			if (fresh.ok) {
				const cache = await caches.open(POS_CACHE);
				cache.put(request, fresh.clone()).catch(() => {});
			}
			return fresh;
		}
		return await fetchAndCache(request);
	} catch {
		const cached = await caches.match(request);
		if (cached) return cached;
		return new Response(JSON.stringify({ error: "offline", message: "أنت غير متصل بالإنترنت" }), {
			status: 503,
			headers: { "Content-Type": "application/json" },
		});
	}
}

async function networkFirstWithQueue(request) {
	try {
		return await fetchAndCache(request);
	} catch {
		const clone = request.clone();
		await queueCheckout(clone);
		return new Response(
			JSON.stringify({
				queued: true,
				message: "تم حفظ الفاتورة في قائمة الانتظار. سيتم إرسالها تلقائياً عند الاتصال.",
			}),
			{ status: 202, headers: { "Content-Type": "application/json" } },
		);
	}
}

async function fetchAndCache(request) {
	const response = await fetch(request);
	if (response.ok && request.method === "GET") {
		const cache = await caches.open(POS_CACHE);
		// Don't cache API JSON that is user-specific and may be stale (products, session)
		// Only cache static assets and the offline catalog snapshot
		const url = new URL(request.url);
		const shouldCache =
			isStaticAsset(request) ||
			url.pathname === "/pos/api/catalog/snapshot" ||
			url.pathname === "/pos/api/categories";
		if (shouldCache) {
			await cache.put(request, response.clone()).catch(() => {});
		}
	}
	return response;
}

function openQueueDB() {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(POS_QUEUE_DB, 1);
		req.onupgradeneeded = () => {
			const store = req.result.createObjectStore(POS_QUEUE_STORE, {
				keyPath: "id",
				autoIncrement: true,
			});
			// Index for retry scheduling
			try {
				store.createIndex("timestamp", "timestamp", { unique: false });
			} catch (_) {}
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function queueCheckout(request) {
	const body = await request.clone().text();
	const db = await openQueueDB();
	const tx = db.transaction(POS_QUEUE_STORE, "readwrite");
	tx.objectStore(POS_QUEUE_STORE).add({
		url: request.url,
		headers: Object.fromEntries(request.headers.entries()),
		body,
		timestamp: Date.now(),
		attempts: 0,
		nextAttemptAt: 0,
	});
	return new Promise((resolve, reject) => {
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

async function retryQueue() {
	let db;
	try {
		db = await openQueueDB();
	} catch (_) {
		return;
	}
	const tx = db.transaction(POS_QUEUE_STORE, "readonly");
	const items = await new Promise((resolve) => {
		const result = [];
		let req;
		try {
			req = tx.objectStore(POS_QUEUE_STORE).openCursor();
		} catch (_) {
			resolve([]);
			return;
		}
		req.onsuccess = () => {
			const c = req.result;
			if (c) {
				result.push(c.value);
				c.continue();
			} else resolve(result);
		};
		req.onerror = () => resolve(result);
	});

	const now = Date.now();
	for (const item of items) {
		if (item.nextAttemptAt && item.nextAttemptAt > now) continue;
		try {
			const res = await fetch(item.url, {
				method: "POST",
				headers: item.headers,
				body: item.body,
			});
			if (
				res.ok ||
				(res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429)
			) {
				// Delivered, or permanently rejected (4xx): drop from the queue.
				// A 4xx will never succeed on retry and would poison the queue.
				await deleteQueued(db, item.id);
				// Notify clients that queue drained one item
				void notifyClients({ type: "queue-flushed", id: item.id, status: res.status });
			} else {
				// 5xx / 408 / 429: transient — back off exponentially.
				await scheduleRetry(db, item, now);
			}
		} catch {
			// Still offline: stop here and wait for the next online/sync event.
			break;
		}
	}
}

async function notifyClients(msg) {
	const clients = await self.clients.matchAll({ includeUncontrolled: true });
	for (const c of clients) c.postMessage(msg);
}

const RETRY_BASE_MS = 15000;
const RETRY_MAX_MS = 15 * 60 * 1000;
const RETRY_MAX_ATTEMPTS = 8;

async function scheduleRetry(db, item, now) {
	const attempts = (item.attempts || 0) + 1;
	if (attempts > RETRY_MAX_ATTEMPTS) {
		await deleteQueued(db, item.id);
		void notifyClients({ type: "queue-dropped", id: item.id, attempts });
		return;
	}
	const delay = Math.min(RETRY_BASE_MS * 2 ** (attempts - 1), RETRY_MAX_MS);
	const updTx = db.transaction(POS_QUEUE_STORE, "readwrite");
	updTx.objectStore(POS_QUEUE_STORE).put({
		...item,
		attempts,
		nextAttemptAt: now + delay,
	});
	await new Promise((r) => {
		updTx.oncomplete = r;
		updTx.onerror = r;
	});
}

async function deleteQueued(db, id) {
	const delTx = db.transaction(POS_QUEUE_STORE, "readwrite");
	delTx.objectStore(POS_QUEUE_STORE).delete(id);
	await new Promise((r) => {
		delTx.oncomplete = r;
		delTx.onerror = r;
	});
}

self.addEventListener("message", (event) => {
	if (event.data === "retry-queue" || event.data?.type === "retry-queue") void retryQueue();
	// Allow clients to request queue length
	if (event.data === "queue-length" || event.data?.type === "queue-length") {
		void (async () => {
			try {
				const db = await openQueueDB();
				const tx = db.transaction(POS_QUEUE_STORE, "readonly");
				const countReq = tx.objectStore(POS_QUEUE_STORE).count();
				countReq.onsuccess = () => {
					event.ports?.[0]?.postMessage({ count: countReq.result });
				};
			} catch (_) {}
		})();
	}
});

self.addEventListener("sync", (event) => {
	if (event.tag === "pos-queue-retry") event.waitUntil(retryQueue());
});
