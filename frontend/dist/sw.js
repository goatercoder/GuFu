// Minimal service worker: makes the app installable ("Add to Home Screen") and serves the last-seen copy of
// the app shell and data files when offline. Network first, cache fallback.
const CACHE = "gufu-v1";
self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok && (req.url.includes("/data/") || req.url.includes("/assets/") || req.mode === "navigate")) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || (req.mode === "navigate" ? caches.match("./") : undefined)))
  );
});
