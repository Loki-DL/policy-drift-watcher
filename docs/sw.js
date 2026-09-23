/* Service worker: offline shell, push alerts, and opening the right screen on tap. */
const CACHE = "pdw-shell-v1";
const SHELL = [
  "./", "index.html", "styles.css", "app.js", "config.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Data: always try the network first so alerts are fresh; fall back to the last copy offline.
// App files: network first too (so updates show up), cached copy when offline.
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("index.html"))),
  );
});

// Only allow notifications to open pages inside this app.
function safeTarget(url) {
  if (typeof url !== "string" || !url.startsWith("./")) return "./";
  return url;
}

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = {}; }
  const title = String(data.title || "Policy change detected").slice(0, 80);
  const body = String(data.body || "Open Drift Watch to see what changed.").slice(0, 200);
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag: String(data.tag || "pdw"),
      icon: "icons/icon-192.png",
      badge: "icons/icon-192.png",
      data: { url: safeTarget(data.url) },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(safeTarget(event.notification.data && event.notification.data.url), self.registration.scope).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ("focus" in w) { w.navigate(target); return w.focus(); }
      }
      return self.clients.openWindow(target);
    }),
  );
});
