/**
 * ANVEXA AI — Progressive Web App Service Worker
 * Enables offline caching, fast asset loading, and standalone app installation on Android, iOS, and PC.
 */

const CACHE_NAME = 'anvexa-pwa-v1.0.0';

const PRECACHE_ASSETS = [
  '/',
  '/dashboard',
  '/manifest.json',
  '/favicon.ico',
  '/static/favicon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-192-maskable.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-512-maskable.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/icon.svg'
];

// Install: Cache essential shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[PWA SW] Precache warning:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean up outdated caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Smart caching strategy
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 1. Never cache non-GET requests (e.g. POST /upload, POST /verify)
  if (req.method !== 'GET') {
    return;
  }

  // 2. API calls (/api/v1/...) -> Network First with offline JSON fallback
  if (url.pathname.startsWith('/api/v1/')) {
    event.respondWith(
      fetch(req)
        .then((response) => {
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(req);
          if (cached) return cached;
          return new Response(
            JSON.stringify({
              offline: true,
              message: 'You are currently offline. Live verification and external source checks require an internet connection.'
            }),
            {
              status: 503,
              headers: { 'Content-Type': 'application/json' }
            }
          );
        })
    );
    return;
  }

  // 3. Navigation requests (HTML pages) -> Network First with cached shell fallback
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((response) => {
          // Update cache with fresh page
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match('/') || await caches.match('/dashboard');
          if (cachedPage) return cachedPage;
          return new Response(
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Offline - ANVEXA AI</title>' +
            '<style>body{background:#0f172a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;' +
            'justify-content:center;height:100vh;margin:0;text-align:center;padding:1rem;}</style></head>' +
            '<body><div><h1>⚡ ANVEXA AI (Offline)</h1><p>You are currently offline. Please reconnect to access live paper verification.</p>' +
            '<button onclick="location.reload()" style="background:#4f46e5;color:#fff;border:none;padding:10px 20px;' +
            'border-radius:8px;cursor:pointer;font-weight:600;margin-top:1rem;">Retry Connection</button></div></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        })
    );
    return;
  }

  // 4. Static assets (images, fonts, stylesheets, scripts) -> Stale-While-Revalidate
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      const fetchPromise = fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return networkResponse;
        })
        .catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
