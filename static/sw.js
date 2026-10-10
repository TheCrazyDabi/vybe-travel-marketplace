/* VYBE service worker (PWA-ready): installable now, network-first at runtime.
   No app caching yet — pages and APIs always go to the network so no stale
   trips, bookings, or auth states. Safe to extend later with static precaching. */
const SW_VERSION = 'vybe-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Network-first passthrough (required fetch handler for installability).
self.addEventListener('fetch', (event) => {
  // Let the browser handle it; no interception logic needed yet.
});
