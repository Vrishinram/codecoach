const CACHE_NAME = 'codecoach-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/manifest.json',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/chat.js',
  '/static/js/quiz.js',
  '/static/js/dashboard.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Network first for API/WS, cache fallback for static assets
  if (event.request.url.includes('/api/') || event.request.url.includes('/ws/')) {
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

// Push notification received event
self.addEventListener('push', (event) => {
  let data = {
    title: 'CodeCoach Reminder',
    body: 'Your daily C# training session is ready!',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    data: { url: '/' }
  };

  if (event.data) {
    try {
      const payload = event.data.json();
      data = { ...data, ...payload };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/icons/icon-192.png',
    badge: data.badge || '/static/icons/icon-192.png',
    data: data.data || { url: '/' },
    vibrate: [100, 50, 100],
    actions: [
      { action: 'open', title: 'Open Training' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Deep link navigation when user clicks notification
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (let client of windowClients) {
        if (client.url === targetUrl && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

