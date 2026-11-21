// The service worker. It does one thing: show a notification when one
// arrives, and open the right page when it is tapped. It caches nothing, so
// the app never shows an old page.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const title = data.title || "Campus Market";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: "/static/img/icon-192.png",
    badge: "/static/img/icon-192.png",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of open) {
      if (client.url === url && "focus" in client) return client.focus();
    }
    return self.clients.openWindow(url);
  })());
});
