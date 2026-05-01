/* SublyAI — minimal offline-friendly service worker.
 *
 * Strategy:
 *   - Cache static assets (HTML shell, CSS, JS, manifest, icons) on install.
 *   - For navigation requests, try the network first; fall back to the cached
 *     shell when offline.
 *   - Static asset requests use cache-first with a network fallback.
 *   - API requests (/api/, /download/) always go straight to the network so
 *     the worker never serves stale job state.
 */

const VERSION = "v3";
const STATIC_CACHE = `sublyai-static-${VERSION}`;
const PRECACHE = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      Promise.all(
        PRECACHE.map((url) =>
          cache.add(url).catch(() => {
            /* missing optional asset is fine */
          })
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Always bypass cache for API and download endpoints.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/download/")) {
    return;
  }

  // HTML navigation: network-first, fall back to cached shell.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((m) => m || caches.match("/")))
    );
    return;
  }

  // Static assets: cache-first.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((cached) =>
        cached ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
      )
    );
  }
});
