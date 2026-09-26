// Carries CVs chosen on start-campaign.html's AI form across the navigation
// to new-campaign.html's manual review step, so "Or review it manually" does
// not throw away files the recruiter already picked. Files can't survive a
// full page navigation on their own (they're not serializable to a URL or
// sessionStorage), so they're stashed in IndexedDB per campaign id and taken
// back exactly once on the other side.
(function () {
  var DB_NAME = 'r360-pending-resumes';
  var STORE = 'resumes';

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        req.result.createObjectStore(STORE);
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function save(campaignId, files) {
    if (!campaignId || !files || !files.length) return Promise.resolve();
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).put({ files: Array.prototype.slice.call(files), savedAt: Date.now() }, campaignId);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    }).catch(function () { /* best-effort — a failed stash just means the other side asks again */ });
  }

  // Reads and deletes in the same transaction, so a reload of the manual
  // review step never replays a selection the recruiter has since changed.
  function take(campaignId) {
    if (!campaignId) return Promise.resolve(null);
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        var store = tx.objectStore(STORE);
        var getReq = store.get(campaignId);
        getReq.onsuccess = function () {
          var record = getReq.result;
          store.delete(campaignId);
          resolve(record ? record.files : null);
        };
        getReq.onerror = function () { reject(getReq.error); };
      });
    }).catch(function () { return null; });
  }

  window.PendingResumes = { save: save, take: take };
})();
