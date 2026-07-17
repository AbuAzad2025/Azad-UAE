const POS_CACHE = 'pos-cache-v1';
const POS_QUEUE_DB = 'pos-offline-queue';
const POS_QUEUE_STORE = 'checkout-queue';

const ASSETS_TO_CACHE = [
  '/static/css/pos.css',
  '/static/js/pos/index.js',
  '/static/js/barcode-scanner.js',
  '/static/js/pos/offline.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(POS_CACHE).then((cache) => {
      const base = self.location.origin;
      return Promise.allSettled(
        ASSETS_TO_CACHE.map((url) => cache.add(base + url).catch(() => {}))
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => { if (k !== POS_CACHE) return caches.delete(k); }))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method === 'POST' && url.pathname.includes('/pos/api/checkout')) {
    event.respondWith(networkFirstWithQueue(request));
    return;
  }

  if (isStaticAsset(request)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  if (url.pathname.startsWith('/pos/') || url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }
});

function isStaticAsset(request) {
  const url = new URL(request.url);
  const ext = url.pathname.split('.').pop();
  return ['css', 'js', 'png', 'jpg', 'gif', 'svg', 'woff', 'woff2', 'ttf', 'eot'].includes(ext) ||
    ASSETS_TO_CACHE.includes(url.pathname);
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  return cached || fetchAndCache(request);
}

async function networkFirst(request) {
  try {
    return await fetchAndCache(request);
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: 'offline', message: 'أنت غير متصل بالإنترنت' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
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
        message: 'تم حفظ الفاتورة في قائمة الانتظار. سيتم إرسالها تلقائياً عند الاتصال.',
      }),
      { status: 202, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function fetchAndCache(request) {
  const response = await fetch(request);
  if (response.ok && request.method === 'GET') {
    const cache = await caches.open(POS_CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

function openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(POS_QUEUE_DB, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(POS_QUEUE_STORE, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function queueCheckout(request) {
  const body = await request.clone().text();
  const db = await openQueueDB();
  const tx = db.transaction(POS_QUEUE_STORE, 'readwrite');
  tx.objectStore(POS_QUEUE_STORE).add({
    url: request.url,
    headers: Object.fromEntries(request.headers.entries()),
    body,
    timestamp: Date.now(),
  });
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function retryQueue() {
  const db = await openQueueDB();
  const tx = db.transaction(POS_QUEUE_STORE, 'readonly');
  const items = await new Promise((resolve) => {
    const result = [];
    const cursor = tx.objectStore(POS_QUEUE_STORE).openCursor();
    cursor.onsuccess = () => {
      const c = cursor.result;
      if (c) { result.push(c.value); c.continue(); }
      else resolve(result);
    };
  });

  for (const item of items) {
    try {
      const res = await fetch(item.url, {
        method: 'POST',
        headers: item.headers,
        body: item.body,
      });
      if (res.ok) {
        const delTx = db.transaction(POS_QUEUE_STORE, 'readwrite');
        delTx.objectStore(POS_QUEUE_STORE).delete(item.id);
        await new Promise((r) => { delTx.oncomplete = r; });
      }
    } catch {
      break;
    }
  }
}

self.addEventListener('message', (event) => {
  if (event.data === 'retry-queue') retryQueue();
});
