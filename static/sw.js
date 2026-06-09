const CACHE_NAME = 'azad-uae-ui-v8';
const urlsToCache = [
  '/static/css/erp-theme.css',
  '/static/css/accessibility.css',
  '/static/css/print.css',
  '/static/js/ui-theme.js',
  '/static/js/app.js',
  '/static/js/azad-app.js',
  '/static/adminlte/js/adminlte.min.js',
  '/static/assets/brand/azad/logos/logo.png',
  '/static/assets/brand/azad/logos/logo-dark.png',
  '/offline.html'
];

const STATIC_PREFIXES = ['/static/', '/adminlte/'];

function isStaticAsset(url) {
  return STATIC_PREFIXES.some(p => url.pathname.startsWith(p));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(urlsToCache))
  );
  self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  if (!event.request || event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);
  const isSameOrigin = url.origin === self.location.origin;

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => isSameOrigin ? caches.match('/offline.html') : new Response(null, { status: 503 }))
    );
    return;
  }

  if (isSameOrigin && isStaticAsset(url)) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request)
          .then((response) => {
            if (response && response.status === 200) {
              const responseToCache = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
            }
            return response;
          });
      })
    );
    return;
  }

  event.respondWith(fetch(event.request).catch(() => new Response(null, { status: 503 })));
});

self.addEventListener('activate', (event) => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

