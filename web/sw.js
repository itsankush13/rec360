// Offline shell for the installed app. Screening requests use the API when online.
// Network-first, so a running instance never serves a stale screen,
// and cache-fallback, so it still opens with no connection.
var CACHE = 'qchem-talent-v26';
var SHELL = [
  'start-campaign.html','assets/campaign-home.css','index.html','campaigns.html','rubric.html','leaderboard.html','candidate.html',
  'compare.html','whatif.html','decisions.html','performance.html','audit.html','developer.html','new-campaign.html',
  'timeline.html','discover.html','pipeline.html','handoff.html','interview.html',
  'approvals.html','offer.html','comms.html',
  'assets/campaign-list.js','assets/app.css','assets/app.js','assets/journey.js','manifest.webmanifest',
  'icons/icon-192.png','icons/icon-512.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  if (new URL(e.request.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(e.request).then(function (res) {
      var copy = res.clone();
      caches.open(CACHE).then(function (c) { c.put(e.request, copy); }).catch(function () {});
      return res;
    }).catch(function () {
      // A failed script/style/asset fetch must fail visibly, not be quietly
      // replaced by unrelated HTML: substituting index.html for a JS request
      // used to make the browser try to parse a page as a script (a
      // `SyntaxError: Unexpected token '<'`), which silently broke every
      // screen that depends on that script ever having run. The offline
      // shell substitute is only ever right for a navigation (a page load),
      // and only when this exact page was never cached before.
      return caches.match(e.request).then(function (hit) {
        if (hit) return hit;
        if (e.request.mode === 'navigate') return caches.match('index.html');
        return Response.error();
      });
    })
  );
});
