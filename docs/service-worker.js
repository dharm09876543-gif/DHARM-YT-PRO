/* DHARM YT PRO service worker
 * Only the app shell (HTML/CSS/JS/icons) is cached.
 * API responses are NEVER cached: cross-origin and /api/ requests go straight to the network.
 */
'use strict';

const CACHE = 'dharm-yt-shell-v5';
const SHELL = [
  './',
  './index.html',
  './privacy.html',
  './terms.html',
  './manifest.json',
  './css/dashboard.css',
  './js/app.js',
  './js/api.js',
  './js/auth.js',
  './js/demo-data.js',
  './js/components/ui.js',
  './js/components/overview.js',
  './js/components/channels.js',
  './js/components/queue.js',
  './js/components/drive.js',
  './js/components/metadata.js',
  './js/components/scheduler.js',
  './js/components/analytics.js',
  './js/components/quota.js',
  './js/components/health.js',
  './js/components/leaderboard.js',
  './js/components/vpn.js',
  './js/components/settings.js',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

const SHELL_URLS = new Set(SHELL.map((p) => new URL(p, self.registration.scope).href));

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                       // POST/PATCH/DELETE: never touched
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;         // backend API (different origin): network only
  if (url.pathname.includes('/api/')) return;              // same-origin API too: network only
  if (req.headers.has('Authorization')) return;            // request with a token: network only

  const key = url.origin + url.pathname;                    // query string ignore
  if (!SHELL_URLS.has(key) && req.mode !== 'navigate') return;

  // Network-first (to get the new version), shell from cache when offline.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && SHELL_URLS.has(key)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(key, copy));
        }
        return res;
      })
      .catch(() => caches.match(key).then((hit) => hit || caches.match(new URL('./index.html', self.registration.scope).href)))
  );
});
