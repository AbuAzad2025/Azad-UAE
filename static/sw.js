const CACHE_NAME = "azad-shop-v1";
const urlsToCache = ["/", "/static/css/shop-palestine.css", "/static/css/shop-utilities.css"];

self.addEventListener("install", (event) => {
	event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache)));
});

self.addEventListener("fetch", (event) => {
	event.respondWith(
		caches
			.match(event.request)
			.then((response) => response || fetch(event.request).catch(() => caches.match("/s/offline"))),
	);
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((cacheNames) =>
				Promise.all(
					cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)),
				),
			),
	);
});
