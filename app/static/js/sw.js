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

// Tapping a notification has to land on the thing it was about, as it is
// now. Bringing a window to the front is not enough: the chat it already
// shows was loaded before the message that caused the notification, so the
// message you came to read is the one thing missing from it. Every window
// is therefore navigated, which for a window already on that page is a
// reload. The app sends no-store on every page, so what comes back is
// current.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    // The window already on that page first, then any other window of
    // ours, so a second window is not opened on top of the app.
    const here = open.find((client) => client.url === url);
    const client = here || open[0];
    if (client) {
      if ("navigate" in client) {
        try {
          const moved = await client.navigate(url);
          return (moved || client).focus();
        } catch (err) {
          // Some browsers refuse navigate for a window they do not
          // control. Focusing it is still better than a new window.
        }
      }
      if ("focus" in client) return client.focus();
    }
    return self.clients.openWindow(url);
  })());
});
