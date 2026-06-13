// NOVA service worker — minimal PWA shell.
// Network-first for everything; cached shell only as offline fallback.
// API calls (POST, /voice, /chat, etc.) are never intercepted.

const CACHE = 'nova-shell-v1';
const SHELL = ['/', '/static/css/styles.css'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Only GET requests for the UI shell — never touch API traffic
  if (e.request.method !== 'GET') return;
  if (!(url.pathname === '/' || url.pathname.startsWith('/static'))) return;

  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
