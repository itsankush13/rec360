// Recruitment 360 — front-end prototype.

// Portal gate (B22 phase 1, login.html + this gate). Every page but
// login.html itself needs a real, verified session before it shows anything.
// Runs first, synchronously, so the "hide body" class lands before the rest
// of this file (which still renders inline, further down) has a chance to
// paint real data for an unauthenticated visitor. The auth check itself is
// necessarily async (GET /api/auth/me), so the class is removed in that
// call's .then() rather than by reordering every other init*() below —
// those keep running inline exactly as before; they just do it behind a
// hidden <html> element until the check resolves.
(function () {
  var TOKEN_KEY = 'recruitment360.auth.token';
  var page = location.pathname.split('/').pop() || 'index.html';
  if (page === 'login.html') return; // the login page is never gated

  document.documentElement.classList.add('auth-pending');

  function toLogin() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
    location.replace('login.html');
  }

  var token = null;
  try { token = localStorage.getItem(TOKEN_KEY); } catch (e) {}
  if (!token) { toLogin(); return; }

  // B25: role-gated interface. The budget approver (REVIEWER) exists to do
  // one thing — grant or return a candidate waiting on a cost centre's
  // budget — so every other screen redirects there instead of rendering.
  // Every other role (HR/RECRUITER, hiring manager, admin) sees the whole
  // site, per the user's own walkthrough of the demo journey.
  var BUDGET_APPROVER_HOME = 'approvals.html';
  // B28: the hiring manager no longer starts campaigns — that stays HR's
  // job — so the two pages that only exist to create one redirect him to
  // the campaign list instead of rendering the setup wizard.
  var CAMPAIGN_CREATE_PAGES = ['start-campaign.html', 'new-campaign.html'];
  var HM_CAMPAIGN_HOME = 'campaigns.html';
  function applyRoleGate(user) {
    if (user && user.role === 'REVIEWER' && page !== BUDGET_APPROVER_HOME) {
      location.replace(BUDGET_APPROVER_HOME);
      return true;
    }
    if (user && user.role === 'HIRING_MANAGER' && CAMPAIGN_CREATE_PAGES.indexOf(page) !== -1) {
      location.replace(HM_CAMPAIGN_HOME);
      return true;
    }
    return false;
  }

  var API_BASE = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
  fetch(API_BASE + '/api/auth/me', { headers: { Authorization: 'Bearer ' + token } })
    .then(function (response) {
      if (!response.ok) throw new Error('unauthorized');
      return response.json();
    })
    .then(function (data) {
      window.__r360Me = data.user;
      if (applyRoleGate(data.user)) return;
      document.documentElement.classList.remove('auth-pending');
      window.dispatchEvent(new CustomEvent('r360-auth-ready', { detail: data.user }));
    })
    .catch(toLogin);
})();

// Send-mode disclosure (truthfulness fix, demo 2026-09-14). Every page that
// used to hardcode a "SIMULATED" badge now asks the API which backend is
// really active, so the badge cannot lie once Outlook goes live. A failed
// call must NOT default to "simulated" — that is the dangerous direction —
// so callers get null and must show an "unknown, may transmit" state.
(function () {
  var API_BASE = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
  var modesPromise = null;

  function sendMode(kind) {
    if (!modesPromise) {
      modesPromise = fetch(API_BASE + '/api/config/send-modes')
        .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .catch(function () { return null; });
    }
    return modesPromise.then(function (modes) {
      if (!modes) return null; // unknown — caller must fail safe, not claim "simulated"
      return kind === 'calendar' ? modes.calendar_backend : modes.email_backend;
    });
  }

  // badgeEl/noteEl: elements to fill. kind: 'email' | 'calendar'. wording:
  // {realBadge, realNote, simBadge, simNote}. Never called with the button
  // itself sending — this only labels it honestly.
  window.__r360ApplySendBadge = function (badgeEl, noteEl, kind, wording) {
    sendMode(kind).then(function (mode) {
      if (mode === 'outlook') {
        if (badgeEl) { badgeEl.textContent = wording.realBadge; badgeEl.classList.add('real'); }
        if (noteEl) noteEl.textContent = wording.realNote;
      } else if (mode === 'simulated') {
        if (badgeEl) { badgeEl.textContent = wording.realBadge; badgeEl.classList.add('real'); }
        if (noteEl) noteEl.textContent = wording.realNote;
      } else {
        if (badgeEl) { badgeEl.textContent = 'SEND MODE UNKNOWN'; badgeEl.classList.add('real'); }
        if (noteEl) noteEl.textContent = 'Could not confirm how this environment sends. Treat this action as if it may transmit for real.';
      }
    });
  };
  window.__r360SendMode = sendMode;
})();

// Keeps disclosure state per screen so a reopened row stays open.
(function () {
  var KEY = 'qchem.open.' + location.pathname;

  function restore() {
    var open;
    try { open = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) { open = []; }
    document.querySelectorAll('details[data-id]').forEach(function (d) {
      if (open.indexOf(d.dataset.id) !== -1) d.open = true;
    });
  }

  function remember() {
    var open = [];
    document.querySelectorAll('details[data-id]').forEach(function (d) {
      if (d.open) open.push(d.dataset.id);
    });
    try { sessionStorage.setItem(KEY, JSON.stringify(open)); } catch (e) {}
  }

  document.querySelectorAll('details').forEach(function (d, i) {
    if (!d.dataset.id) d.dataset.id = 'd' + i;
    d.addEventListener('toggle', remember);
  });
  restore();

  // Five stable destinations; campaign tools belong to Start Campaign.
  function initNavigation() {
    var nav = document.querySelector('.bar nav');
    if (!nav) return;
    var current = location.pathname.split('/').pop() || 'index.html';
    var standalone = ['index.html', 'whatif.html', 'audit.html', 'developer.html'];
    var active = standalone.indexOf(current) >= 0 ? current : 'start-campaign.html';
    nav.querySelectorAll('a').forEach(function (link) {
      var selected = link.getAttribute('href') === active;
      link.classList.toggle('on', selected);
      if (selected) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }

  initNavigation();

  // Signed-in name + role, top right, from the real session (B22 phase 1:
  // see the portal gate above, which fetched /api/auth/me before this ran).
  // A click signs out — a gate with no way out would trap the person behind it.
  function initMe() {
    var el = document.querySelector('.me');
    if (!el) return;
    var TOKEN_KEY = 'recruitment360.auth.token';
    var span = el.querySelector('span');
    var av = el.querySelector('.av');

    function initials(name) {
      var parts = (name || '').trim().split(/\s+/);
      return ((parts[0] && parts[0][0] || '') + (parts[1] ? parts[1][0] : '')).toUpperCase() || 'HR';
    }

    function render(user) {
      if (!user) return;
      span.textContent = user.display_label || user.role || 'HR';
      av.textContent = initials(user.full_name);
      av.title = user.full_name + ' — click to sign out' +
        (user.counterpart ? ' · today’s ' + user.counterpart.display_label + ' is ' + user.counterpart.full_name : '');
      // B25: the budget approver only ever lands on approvals.html (see the
      // portal gate's role redirect above) and has nothing to navigate to
      // from there, so the site nav and the campaign-stage dock (built
      // earlier in this file, before the role was known) are both hidden
      // rather than left dangling.
      if (user.role === 'REVIEWER') {
        var nav = document.querySelector('.bar nav');
        if (nav) nav.style.display = 'none';
        var dock = document.getElementById('cjourney-bar');
        if (dock) dock.style.display = 'none';
      }
    }

    el.style.cursor = 'pointer';
    el.title = 'Click to sign out';
    el.addEventListener('click', function () {
      try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
      location.href = 'login.html';
    });

    if (window.__r360Me) render(window.__r360Me);
    window.addEventListener('r360-auth-ready', function (event) { render(event.detail); });
  }

  initMe();

  // The name recorded against any action taken in this session — replaces
  // every hardcoded "Fatima Al-Rashid" placeholder actor with whoever is
  // actually signed in (window.__r360Me, set by the portal gate above).
  window.__r360ActorName = function () {
    return (window.__r360Me && (window.__r360Me.full_name || window.__r360Me.display_label)) || 'Unknown user';
  };

  // B28: the hiring manager sees the whole site (unlike the budget
  // approver, who is redirected away entirely per B25) but only acts on
  // the two decisions that are actually his — recording a shortlist
  // verdict (handoff.html) and interview feedback (interview.html), both
  // already gated to him alone. Every page's own script is responsible for
  // locking its own mutating controls when window.__r360Locked() is true;
  // this just swaps campaign creation out of the nav, since starting a
  // campaign isn't a "lock the button" case — it isn't his to reach at all.
  window.__r360Locked = function () {
    return !!(window.__r360Me && window.__r360Me.role === 'HIRING_MANAGER');
  };

  function applyHiringManagerNav(user) {
    if (!user || user.role !== 'HIRING_MANAGER') return;
    var nav = document.querySelector('.bar nav');
    if (nav) {
      var startLink = nav.querySelector('a[href="start-campaign.html"]');
      if (startLink) {
        startLink.setAttribute('href', 'campaigns.html');
        startLink.textContent = 'Campaign';
      }
    }
    // Any other entry point into the campaign-creation flow (e.g. the
    // Today page's empty-state "New campaign" link, campaigns.html's own
    // "Start a new campaign" button) is marked with this attribute in its
    // markup so it can be hidden sitewide from one place.
    document.querySelectorAll('[data-campaign-create]').forEach(function (node) {
      node.hidden = true;
    });
  }

  if (window.__r360Me) applyHiringManagerNav(window.__r360Me);
  window.addEventListener('r360-auth-ready', function (event) { applyHiringManagerNav(event.detail); });

  // Shared Cascade layout for screen-level bands. Every summary keeps a
  // stable full-width position; opening one story pushes later stories down.
  function initCascade() {
    var page = document.querySelector('.page');
    if (!page) return;
    if (page.hasAttribute('data-cascade-disabled')) return;
    var bands = Array.prototype.filter.call(page.children, function (child) {
      return child.classList && child.classList.contains('band');
    });
    if (!bands.length) return;

    page.classList.add('cascade-page');
    var blocks = [];

    bands.forEach(function (band) {
      var label = Array.prototype.find.call(band.children, function (child) {
        return child.classList && child.classList.contains('label');
      });
      if (!label) {
        band.classList.add('story-always');
        return;
      }

      band.classList.add('story-block');
      label.classList.add('story-trigger');
      label.setAttribute('role', 'button');
      label.setAttribute('tabindex', '0');
      label.setAttribute('aria-expanded', 'false');

      var detail = document.createElement('div');
      detail.className = 'story-detail';
      detail.setAttribute('aria-hidden', 'true');
      var inner = document.createElement('div');
      inner.className = 'story-detail-inner';
      Array.prototype.slice.call(band.children).forEach(function (child) {
        if (child !== label) inner.appendChild(child);
      });

      // A closed story is a deliberate headline plus one useful sentence, not
      // a cropped copy of its expanded content. Existing asides are already
      // written as summaries; other bands receive a compact first fact.
      var summary = label.querySelector('.aside, .story-summary');
      if (!summary) {
        var text = label.getAttribute('data-summary') || '';
        if (!text) {
          var candidates = inner.querySelectorAll('.sub, .where, p, .b, .note');
          Array.prototype.some.call(candidates, function (candidate) {
            var candidateText = (candidate.textContent || '').replace(/\s+/g, ' ').trim();
            if (candidateText.length > 18) {
              text = candidateText;
              return true;
            }
            return false;
          });
        }
        if (!text) text = 'Open to review the detail and the next step.';
        if (text) {
          summary = document.createElement('span');
          summary.textContent = text.length > 132 ? text.slice(0, 129).replace(/\s+$/, '') + '…' : text;
          label.appendChild(summary);
        }
      }
      if (summary) summary.classList.add('story-summary');

      detail.appendChild(inner);
      band.appendChild(detail);
      blocks.push(band);
    });

    function toggle(block) {
      var open = !block.classList.contains('is-open');
      block.classList.toggle('is-open', open);
      var trg = block.querySelector('.story-trigger');
      var det = block.querySelector('.story-detail');
      if (trg) trg.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (det) det.setAttribute('aria-hidden', open ? 'false' : 'true');
      if (window.__r360SaveOpen) window.__r360SaveOpen();
    }

    blocks.forEach(function (block) {
      var trigger = block.querySelector('.story-trigger');
      if (!trigger) return;
      trigger.addEventListener('click', function (event) {
        if (event.target.closest('a,button,input,select,textarea')) return;
        toggle(block);
      });
      trigger.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggle(block);
        }
      });
    });
  }

  initCascade();

  // register the service worker so the app can be installed to a home screen
  if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
    navigator.serviceWorker.register('sw.js').catch(function () {});
  }
})();

// Campaign journey bar: a left-to-right strip of six stops on every campaign
// workspace (07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md). It never appears on the
// standalone pages (Today, Start Campaign, What-if, Audit, FinOps) — only
// once a campaign workspace is actually open.
(function () {
  var page = location.pathname.split('/').pop() || 'index.html';
  if (['index.html', 'start-campaign.html', 'audit.html', 'developer.html', 'whatif.html'].indexOf(page) !== -1) return;
  var stages = [
    ['role', 'Role and job description', 'new-campaign.html', 'role'],
    ['rules', 'Scoring rules', 'rubric.html', ''],
    ['cvs', 'Upload CVs', 'new-campaign.html', 'cvs'],
    ['shortlist', 'Candidate shortlist', 'leaderboard.html', ''],
    ['candidate', 'Candidate 360', 'candidate.html', ''],
    ['compare', 'Compare candidates', 'compare.html', ''],
    ['decisions', 'Decisions and export', 'decisions.html', ''],
    ['handoff', 'Manager review', 'handoff.html', ''],
    ['interview', 'Interviews and feedback', 'interview.html', ''],
    ['approvals', 'HR and budget approvals', 'approvals.html', ''],
    ['offer', 'Offers and responses', 'offer.html', ''],
    ['comms', 'Communication record', 'comms.html', ''],
    ['pipeline', 'Campaign pipeline', 'pipeline.html', ''],
    ['timeline', 'Candidate timeline', 'timeline.html', '']
  ];
  var key = 'recruitment360.campaign';
  var params = new URLSearchParams(location.search);
  var campaignId = params.get('campaign_id') || params.get('campaign') ||
    (page === 'new-campaign.html' ? '' : localStorage.getItem(key)) || '';
  if (campaignId) localStorage.setItem(key, campaignId);
  var current = page === 'new-campaign.html' ? (location.hash === '#cvs' ? 'cvs' : 'role') : page.replace('.html', '');
  if (current === 'rubric') current = 'rules';
  if (current === 'leaderboard') current = 'shortlist';
  var index = stages.findIndex(function (stage) { return stage[0] === current; });
  if (index < 0) return;

  // Six journey stops. Each bundles a handful of the fine-grained stages
  // above under one label; a stop is "done" once its own primary stage is —
  // the same signal deriveDoneStages() below already computes, so nothing
  // new to trust.
  var ICONS = {
    setup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    shortlist: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    handoff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="21" y1="3" x2="10" y2="14"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
    interview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    approvals: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    offer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>'
  };
  var STOPS = [
    { label: 'Set up', primary: 'cvs', members: ['role', 'rules', 'cvs'], icon: ICONS.setup },
    { label: 'Shortlist', primary: 'shortlist', members: ['shortlist', 'candidate', 'compare', 'decisions'], icon: ICONS.shortlist },
    { label: 'Handoff', primary: 'handoff', members: ['handoff'], icon: ICONS.handoff },
    { label: 'Interview', primary: 'interview', members: ['interview'], icon: ICONS.interview },
    { label: 'Approvals', primary: 'approvals', members: ['approvals'], icon: ICONS.approvals },
    { label: 'Offer & hire', primary: 'offer', members: ['offer', 'comms', 'pipeline', 'timeline'], icon: ICONS.offer }
  ];
  function stopOf(stageId) {
    for (var s = 0; s < STOPS.length; s++) if (STOPS[s].members.indexOf(stageId) !== -1) return s;
    return -1;
  }
  function stopStage(stopIndex) {
    var primary = STOPS[stopIndex].primary;
    return stages.find(function (stage) { return stage[0] === primary; });
  }
  var currentStop = stopOf(current);

  // A stop's green state means it is genuinely finished. The truth for that
  // lives in the API, not in this browser: a rubric is approved, a run
  // completed, an offer was sent. deriveDoneStages() below reads those
  // signals, so walking the campaign marks itself. The stored map stays as a
  // manual override for the few stages the backend cannot know about.
  // Opening a stop is not the same as finishing it, so arriving ticks nothing.
  function doneStorageKey(id) { return 'recruitment360.doneStages.' + (id || ('page:' + page)); }
  function readDoneStages() {
    try { return JSON.parse(localStorage.getItem(doneStorageKey(campaignId)) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function writeDoneStages(map) {
    try { localStorage.setItem(doneStorageKey(campaignId), JSON.stringify(map)); } catch (e) {}
  }
  var doneStages = readDoneStages();
  function href(stage) {
    var url = stage[2];
    if (campaignId) url += (url.indexOf('?') < 0 ? '?' : '&') +
      (stage[2] === 'new-campaign.html' ? 'campaign_id=' : 'campaign=') + encodeURIComponent(campaignId);
    return url + (stage[3] ? '#' + stage[3] : '');
  }
  function remember() {
    if (!campaignId) return;
    [key, 'recruitment360.interviewsCampaign', 'recruitment360.handoff.campaignId',
      'recruitment360.comms.campaignId'].forEach(function (name) { localStorage.setItem(name, campaignId); });
  }
  function navigate(event, stage) {
    if (page !== 'new-campaign.html' || !window.__r360SaveCampaignForNavigation) { remember(); return; }
    if (campaignId) { remember(); return; }
    event.preventDefault();
    var oldError = document.getElementById('cjourney-error');
    if (oldError) oldError.remove();
    bar.setAttribute('aria-busy', 'true');
    window.__r360SaveCampaignForNavigation().then(function (campaign) {
      campaignId = campaign.id;
      remember();
      location.href = href(stage);
    }).catch(function (error) {
      bar.removeAttribute('aria-busy');
      var message = document.createElement('p');
      message.id = 'cjourney-error';
      message.className = 'cjourney-error';
      message.textContent = 'Campaign could not be saved. ' + ((error && error.message) || 'Try again.');
      bar.appendChild(message);
    });
  }

  // `.cjourney-*`, not `.journey-*`: assets/journey.js already owns
  // `.journey-bar`/`.journey-track` for the unrelated funnel-chart rows it
  // builds inside `#journey-chart`. Reusing those names silently lost this
  // bar's height to the chart's `.journey-track{height:12px}` rule.
  var bar = document.createElement('nav');
  bar.className = 'cjourney-bar';
  bar.id = 'cjourney-bar';
  bar.setAttribute('aria-label', 'Campaign journey');

  var prevBtn = document.createElement('a');
  prevBtn.className = 'cjourney-end';
  prevBtn.textContent = '‹';
  prevBtn.setAttribute('aria-label', 'Previous stage');
  var nextBtn = document.createElement('a');
  nextBtn.className = 'cjourney-end';
  nextBtn.textContent = '›';
  nextBtn.setAttribute('aria-label', 'Next stage');
  function isStopDone(stopIndex) { return !!doneStages[STOPS[stopIndex].primary]; }

  // The dropdown dock this bar replaced always named the open campaign —
  // losing that made a screen with several campaigns in flight ambiguous.
  var campaignName = document.createElement('div');
  campaignName.className = 'cjourney-name';
  function refreshCampaignName() {
    campaignName.textContent = campaignId ? 'Loading campaign…' : 'New campaign';
    campaignName.title = '';
    if (!campaignId) return;
    var checkedId = campaignId;
    var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
    fetch(base + '/api/campaigns/' + encodeURIComponent(checkedId))
      .then(function (response) { if (!response.ok) throw new Error(); return response.json(); })
      .then(function (campaign) {
        if (checkedId !== campaignId) return;
        var name = campaign.job_title || campaign.name || 'Campaign';
        campaignName.textContent = name;
        campaignName.title = name;
      }).catch(function () {
        if (checkedId === campaignId) campaignName.textContent = 'Campaign unavailable';
      });
  }
  refreshCampaignName();

  var track = document.createElement('div');
  track.className = 'cjourney-track';
  var stopEls = [], arrowEls = [], menuEls = [], menuDotEls = {}, menuLinkEls = {};
  function closeMenus(exceptMenu) {
    menuEls.forEach(function (m) { if (m && m !== exceptMenu) m.hidden = true; });
  }
  STOPS.forEach(function (stop, stopIndex) {
    if (stopIndex > 0) {
      var arrowSpan = document.createElement('span');
      arrowSpan.className = 'cjourney-arrow';
      arrowSpan.setAttribute('aria-hidden', 'true');
      track.appendChild(arrowSpan);
      arrowEls.push(arrowSpan);
    }
    var wrap = document.createElement('div');
    wrap.className = 'cjourney-stopwrap';

    var link = document.createElement('a');
    link.className = 'cjourney-stop';
    var circle = document.createElement('span');
    circle.className = 'cjourney-circle';
    circle.setAttribute('aria-hidden', 'true');
    circle.innerHTML = stop.icon || '';
    var label = document.createElement('span');
    label.className = 'cjourney-label';
    label.textContent = stop.label;
    link.appendChild(circle);
    link.appendChild(label);
    link.addEventListener('click', function (event) { navigate(event, stopStage(stopIndex)); });
    wrap.appendChild(link);
    stopEls.push(link);

    // A stop with more than one real page behind it (Shortlist bundles the
    // shortlist, Candidate 360, Compare and Decisions screens; Set up bundles
    // role/rules/CVs; Offer & hire bundles offer/comms/pipeline/timeline)
    // gets a caret that opens the full list — the same pages the
    // pre-redesign dropdown dock always listed, just reachable from here now.
    var menu = null;
    if (stop.members.length > 1) {
      var caret = document.createElement('button');
      caret.type = 'button';
      caret.className = 'cjourney-caret';
      caret.textContent = '▾';
      caret.setAttribute('aria-label', 'More ' + stop.label + ' pages');
      caret.setAttribute('aria-expanded', 'false');
      menu = document.createElement('div');
      menu.className = 'cjourney-menu';
      menu.hidden = true;
      stop.members.forEach(function (memberId) {
        var memberStage = stages.find(function (s) { return s[0] === memberId; });
        if (!memberStage) return;
        var mLink = document.createElement('a');
        mLink.href = href(memberStage);
        if (memberId === current) mLink.className = 'current';
        var dot = document.createElement('span');
        dot.className = 'cjourney-menu-dot' + (doneStages[memberId] ? ' done' : '');
        var text = document.createElement('span');
        text.textContent = memberStage[1];
        mLink.appendChild(dot);
        mLink.appendChild(text);
        menuDotEls[memberId] = dot;
        menuLinkEls[memberId] = mLink;
        mLink.addEventListener('click', function (event) {
          menu.hidden = true;
          navigate(event, memberStage);
        });
        menu.appendChild(mLink);
      });
      // The bar itself scrolls horizontally (`overflow-x:auto`), and a
      // scroll container clips anything that overflows its own box — a
      // plain `position:absolute` dropdown nested inside it would be cut
      // off rather than floating over the page. Appending the menu to
      // <body> and positioning it with `fixed` coordinates, computed fresh
      // from the wrap's own place on screen each time it opens, escapes
      // that clip.
      document.body.appendChild(menu);
      caret.addEventListener('click', function (event) {
        event.stopPropagation();
        var opening = menu.hidden;
        closeMenus(opening ? menu : null);
        if (opening) {
          var rect = wrap.getBoundingClientRect();
          menu.style.top = (rect.bottom + 6) + 'px';
          menu.style.left = (rect.left + rect.width / 2) + 'px';
        }
        menu.hidden = !opening;
        caret.setAttribute('aria-expanded', String(opening));
      });
      wrap.appendChild(caret);
    }
    menuEls.push(menu);

    track.appendChild(wrap);
  });
  document.addEventListener('click', function () { closeMenus(null); });
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closeMenus(null); });
  bar.addEventListener('scroll', function () { closeMenus(null); });
  window.addEventListener('resize', function () { closeMenus(null); });

  function repaint() {
    STOPS.forEach(function (stop, stopIndex) {
      var done = isStopDone(stopIndex);
      var cls = 'cjourney-stop';
      // The page someone is standing on right now always gets the red-dot
      // "current" mark, even if that stage is also finished — being done and
      // being here are different facts, and only one of them is "you are
      // here". Every other stop shows green-done ahead of grey-pending.
      if (stopIndex === currentStop) cls += ' current';
      else if (done) cls += ' done';
      else cls += ' pending';
      var link = stopEls[stopIndex];
      link.className = cls;
      link.href = href(stopStage(stopIndex));
      link.setAttribute('aria-current', stopIndex === currentStop ? 'step' : 'false');
      if (stopIndex > 0) arrowEls[stopIndex - 1].className = 'cjourney-arrow';
    });
    Object.keys(menuDotEls).forEach(function (memberId) {
      menuDotEls[memberId].className = 'cjourney-menu-dot' + (doneStages[memberId] ? ' done' : '');
    });
    var prevTarget = currentStop > 0 ? stopStage(currentStop - 1) : null;
    var nextTarget = currentStop >= 0 && currentStop < STOPS.length - 1 ? stopStage(currentStop + 1) : null;
    if (prevTarget) { prevBtn.href = href(prevTarget); prevBtn.removeAttribute('aria-disabled'); }
    else { prevBtn.removeAttribute('href'); prevBtn.setAttribute('aria-disabled', 'true'); }
    if (nextTarget) { nextBtn.href = href(nextTarget); nextBtn.removeAttribute('aria-disabled'); }
    else { nextBtn.removeAttribute('href'); nextBtn.setAttribute('aria-disabled', 'true'); }
    prevBtn.onclick = function (event) { if (prevTarget) navigate(event, prevTarget); };
    nextBtn.onclick = function (event) { if (nextTarget) navigate(event, nextTarget); };
  }
  repaint();

  bar.appendChild(campaignName); bar.appendChild(prevBtn); bar.appendChild(track); bar.appendChild(nextBtn);
  var topBar = document.querySelector('.bar');
  if (topBar && topBar.parentNode) topBar.parentNode.insertBefore(bar, topBar.nextSibling);
  else document.body.insertBefore(bar, document.body.firstChild);

  // Bottom-right "done" button: the person's own signal that they have
  // finished this stage, separate from merely having visited it. Only this
  // click earns the stage — and its journey stop — their green state.
  var doneBtn = document.createElement('button');
  doneBtn.type = 'button';
  doneBtn.className = 'page-done-btn';
  function refreshDoneBtn() {
    var isDone = !!doneStages[current];
    doneBtn.classList.toggle('is-done', isDone);
    doneBtn.textContent = isDone ? '✓ Marked done' : 'Mark this page done';
  }
  refreshDoneBtn();
  doneBtn.addEventListener('click', function () {
    doneStages[current] = true;
    writeDoneStages(doneStages);
    refreshDoneBtn();
    repaint();
  });
  document.body.appendChild(doneBtn);

  // Ordered so "has this candidate reached at least X" is one index compare.
  // Mirrors LifecycleStatus in app/db/models.py; the terminal//parked states
  // (ON_HOLD, NOT_PROCEEDING, WITHDRAWN, WAITLISTED) are deliberately absent
  // because they are not progress along this path.
  var LIFECYCLE_ORDER = ['SHORTLISTED', 'WITH_HIRING_MANAGER',
    'RETURNED_TO_RECRUITER', 'INTERVIEW_SCHEDULED', 'FEEDBACK_COMPLETE',
    'PENDING_APPROVAL', 'PENDING_COST_CENTRE', 'APPROVED', 'OFFER_DRAFTED',
    'OFFER_SENT', 'OFFER_ACCEPTED', 'OFFER_DECLINED', 'HIRED', 'CLOSED'];
  function anyReached(rows, status) {
    var want = LIFECYCLE_ORDER.indexOf(status);
    if (want < 0) return false;
    return (rows || []).some(function (row) {
      return LIFECYCLE_ORDER.indexOf(row.status) >= want;
    });
  }
  function deriveDoneStages() {
    if (!campaignId) return;
    var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
    var checkedId = campaignId;
    function get(path) {
      return fetch(base + '/api/campaigns/' + encodeURIComponent(checkedId) + path)
        .then(function (response) { return response.ok ? response.json() : null; })
        .catch(function () { return null; });
    }
    Promise.all([get(''), get('/rubric/active'), get('/candidates'),
      get('/evaluations/runs'), get('/lifecycle'), get('/interviews'),
      get('/messages')]).then(function (parts) {
      if (checkedId !== campaignId) return;
      var campaign = parts[0] || {}, rubric = parts[1] || null;
      var candidates = parts[2] || [], runs = parts[3] || [];
      var life = parts[4] || [], interviews = parts[5] || [], messages = parts[6] || [];
      var scored = runs.some(function (run) { return run.status === 'COMPLETED'; });
      var derived = {
        role: !!String(campaign.job_description || '').trim(),
        rules: !!rubric && ['APPROVED', 'LOCKED'].indexOf(rubric.status) !== -1,
        cvs: candidates.length > 0,
        shortlist: scored,
        candidate: scored,
        compare: scored && candidates.length > 1,
        decisions: life.length > 0,
        handoff: anyReached(life, 'WITH_HIRING_MANAGER'),
        interview: interviews.length > 0,
        approvals: anyReached(life, 'APPROVED'),
        offer: anyReached(life, 'OFFER_SENT'),
        comms: messages.length > 0,
        pipeline: life.length > 0,
        timeline: life.length > 0
      };
      // Derived ticks are not written back to storage: they must follow the
      // campaign, so that undoing something in the API untocks the stage too.
      Object.keys(derived).forEach(function (id) {
        if (derived[id]) doneStages[id] = true;
      });
      repaint();
      refreshDoneBtn();
    }).catch(function (error) {
      // Never let a tick calculation break the page it decorates.
      if (window.console) console.warn('stage ticks unavailable:', error);
    });
  }
  deriveDoneStages();
  function refreshEmptyStage() {
    if (index < 5 || page === 'interview.html') return;
    var surface = document.querySelector('.page');
    if (!surface) return;
    var previousNote = surface.querySelector('.campaign-empty-note');
    if (previousNote) previousNote.remove();
    surface.classList.remove('campaign-empty-stage');
    if (!campaignId) return;
    var checkedId = campaignId;
    var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
    fetch(base + '/api/campaigns/' + encodeURIComponent(checkedId) + '/candidates')
      .then(function (response) { if (!response.ok) throw new Error('Campaign unavailable'); return response.json(); })
      .then(function (candidates) {
        if (candidates.length || checkedId !== campaignId) return;
        var note = document.createElement('section');
        note.className = 'campaign-empty-note';
        var title = document.createElement('h1');
        title.textContent = 'No candidates in ' + stages[index][1].toLowerCase() + ' yet';
        var text = document.createElement('p');
        text.textContent = 'This stage is ready. Candidates will appear after CVs are uploaded and assessed.';
        var link = document.createElement('a');
        link.href = href(stages[2]); link.textContent = 'Go to Upload CVs';
        note.appendChild(title); note.appendChild(text); note.appendChild(link);
        surface.insertBefore(note, surface.firstChild);
        surface.classList.add('campaign-empty-stage');
      }).catch(function () { /* A failed read must never be called an empty stage. */ });
  }
  refreshEmptyStage();
  document.addEventListener('change', function (event) {
    if ((event.target.id === 'campaign-select' || event.target.id === 'c-campaign-select') && event.target.value) {
      window.dispatchEvent(new CustomEvent('campaign-changed', { detail: { id: event.target.value } }));
    }
  });
  window.addEventListener('campaign-changed', function (event) {
    campaignId = event.detail && event.detail.id || '';
    if (!campaignId) return;
    remember();
    doneStages = readDoneStages();
    repaint();
    Object.keys(menuLinkEls).forEach(function (memberId) {
      var memberStage = stages.find(function (s) { return s[0] === memberId; });
      if (memberStage) menuLinkEls[memberId].href = href(memberStage);
    });
    refreshEmptyStage();
    refreshDoneBtn();
    refreshCampaignName();
    // readDoneStages() above returns only the manual overrides, so this
    // handler would otherwise wipe every tick derived from the API. The
    // campaign selector fires a change on load, which made the derived
    // ticks appear and then vanish. Read the new campaign's real state.
    deriveDoneStages();
  });
  window.addEventListener('hashchange', function () {
    if (page !== 'new-campaign.html') return;
    current = location.hash === '#cvs' ? 'cvs' : 'role';
    index = stages.findIndex(function (stage) { return stage[0] === current; });
    currentStop = stopOf(current);
    repaint();
  });
})();


/* -- Section open/closed state, remembered per page -- */
(function () {
  var KEY = 'r360:open:' + (location.pathname.split('/').pop() || 'index.html');

  function read() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function write(s) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {}
  }
  function storyKey(block, i) {
    var h = block.querySelector('.story-trigger h2');
    return 'story:' + ((h && h.textContent.trim()) || i);
  }
  function detailKey(el, i) {
    var s = el.querySelector('summary');
    return 'details:' + (el.getAttribute('data-id') ||
      (s && s.textContent.trim().slice(0, 60)) || i);
  }
  function applyOpen(block, open) {
    block.classList.toggle('is-open', open);
    var trg = block.querySelector('.story-trigger');
    var det = block.querySelector('.story-detail');
    if (trg) trg.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (det) det.setAttribute('aria-hidden', open ? 'false' : 'true');
  }
  function each(sel, fn) {
    Array.prototype.forEach.call(document.querySelectorAll(sel), fn);
  }
  function save() {
    var s = read();
    each('.story-block', function (b, i) { s[storyKey(b, i)] = b.classList.contains('is-open'); });
    each('details', function (d, i) { s[detailKey(d, i)] = d.open; });
    write(s);
  }
  function restore() {
    var s = read();
    each('.story-block', function (b, i) {
      var k = storyKey(b, i);
      if (k in s) applyOpen(b, !!s[k]);
    });
    each('details', function (d, i) {
      var k = detailKey(d, i);
      if (k in s) d.open = !!s[k];
      if (!d.__r360bound) { d.__r360bound = true; d.addEventListener('toggle', save); }
    });
  }
  window.__r360SaveOpen = save;
  window.__r360RestoreOpen = restore;

  // Open the cascade band that contains a node, and remember it as open.
  // A deep link that lands on a step has to open that step's band; writing the
  // state as well as the class matters, because restore() runs again at 150ms
  // and 700ms and would otherwise close what the link just opened.
  // Returns true only when this call changed a closed band, so a caller can
  // tell whether there is an opening transition to wait for.
  window.__r360OpenBand = function (node) {
    var block = node && node.closest ? node.closest('.story-block') : null;
    if (!block || block.classList.contains('is-open')) return false;
    applyOpen(block, true);
    save();
    return true;
  };

  function boot() { restore(); setTimeout(restore, 150); setTimeout(restore, 700); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

// --- The next-step rule, and where each step lives ------------------------
// 07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md section 1. One campaign, one question:
// which step is it on? Derived from saved records every time it is asked —
// the stored status and the campaign's own fields. No `current_step` field:
// a stored step is a second workflow state and it disagrees with
// Campaign.status the first time anything is edited out of order
// (02-LIFECYCLE-MODEL.md).
//
// It lives here, not in campaigns.html, because slice 2 needs the same rule
// on new-campaign.html to know which step to open. Two copies of a rule are
// two rules.
//
// This is the coarse rule. The finer setup steps in the proposal —
// requirements extracted, rubric version locked, batch uploaded — need a read
// per campaign, and the number of campaigns is unbounded. The stored status
// already separates them.
(function () {
  var LABEL = {
    role: 'Describe the role',
    jd: 'Add the job description',
    requirements: 'Review the scoring rules',
    rubric: 'Approve the scoring rules',
    cvs: 'Upload CVs',
    assess: 'Wait for the CVs to be read',
    shortlist: 'Review the shortlist'
  };

  // Which element on new-campaign.html each step opens at. `rubric` shares
  // band 3 with `requirements`: the rules are there, and no approval screen
  // exists yet. A URL for a page that does not exist is a broken promise.
  var ANCHOR = {
    role: 'role',
    jd: 'jd',
    requirements: 'step3',
    rubric: 'step3',
    cvs: 'cvs'
  };

  function next(campaign, run) {
    if (!campaign) return null;
    var status = campaign.status;
    if (status === 'DRAFT') {
      if (!campaign.job_title) return 'role';
      if (!campaign.job_description) return 'jd';
      return 'requirements';
    }
    if (status === 'AWAITING_RUBRIC_APPROVAL') return 'rubric';
    if (status === 'APPROVED') return run ? 'assess' : 'cvs';
    if (status === 'PROCESSING') return 'assess';
    if (status === 'REVIEW') return 'shortlist';
    return null; // CLOSED, or a status this rule has not been taught
  }

  // The URL that opens a step, or null when this rule has no better
  // destination than wherever the caller already points. Never a guess.
  function href(campaign, run, step) {
    var id = step || next(campaign, run);
    if (!id || !campaign) return null;
    if (ANCHOR[id]) {
      if (!campaign.id) return null;
      return 'new-campaign.html?campaign_id=' + encodeURIComponent(campaign.id) + '#' + id;
    }
    if (id === 'shortlist' && run && run.run_id) {
      return 'leaderboard.html?run_id=' + encodeURIComponent(run.run_id);
    }
    return null; // assess: there is nothing to act on yet
  }

  // Once a campaign reaches REVIEW and has a completed run, "Review the
  // shortlist" stops being the true next step the moment any candidate is
  // actually sent into the Review & Hire phase (handoff/interview/approvals/
  // offer/hired) — those stages live on `CandidateLifecycle`, not on
  // `Campaign.status`, so the coarse rule above never sees them. Demo-
  // readiness pass, 2026-09-14 (docs/plan/DEMO-READINESS-2026-09-14.md P0-4):
  // a saved-campaign card used to freeze at "Review the shortlist" forever,
  // even for a campaign whose candidate already had an offer sent.
  //
  // Rank order mirrors `LifecycleStatus`'s own declaration order in
  // app/db/models.py (X11's "declared stage sequence" convention) — the
  // furthest-progressed candidate in the campaign decides the card's label.
  var LIFECYCLE_RANK = {
    SHORTLISTED: 0, WAITLISTED: 0,
    WITH_HIRING_MANAGER: 1, RETURNED_TO_RECRUITER: 1, ON_HOLD: 1,
    INTERVIEW_SCHEDULED: 2,
    FEEDBACK_COMPLETE: 3,
    PENDING_APPROVAL: 4,
    PENDING_COST_CENTRE: 5,
    APPROVED: 6,
    OFFER_DRAFTED: 7,
    OFFER_SENT: 8,
    OFFER_ACCEPTED: 9, OFFER_DECLINED: 9,
    HIRED: 10, CLOSED: 10, NOT_PROCEEDING: 10, WITHDRAWN: 10
  };
  var LIFECYCLE_LABEL = {
    WITH_HIRING_MANAGER: 'With the hiring manager', RETURNED_TO_RECRUITER: 'Manager sent back a question',
    ON_HOLD: 'On hold', INTERVIEW_SCHEDULED: 'Interview scheduled',
    FEEDBACK_COMPLETE: 'Ready for HR approval', PENDING_APPROVAL: 'Awaiting HR sign-off',
    PENDING_COST_CENTRE: 'Awaiting budget sign-off', APPROVED: 'Approved — ready to offer',
    OFFER_DRAFTED: 'Offer drafted', OFFER_SENT: 'Offer sent, awaiting response',
    OFFER_ACCEPTED: 'Offer accepted', OFFER_DECLINED: 'Offer declined',
    HIRED: 'Hired', CLOSED: 'Closed', NOT_PROCEEDING: 'Not proceeding', WITHDRAWN: 'Withdrawn'
  };
  var LIFECYCLE_PAGE = {
    WITH_HIRING_MANAGER: 'handoff.html', RETURNED_TO_RECRUITER: 'handoff.html', ON_HOLD: 'pipeline.html',
    INTERVIEW_SCHEDULED: 'interview.html', FEEDBACK_COMPLETE: 'approvals.html',
    PENDING_APPROVAL: 'approvals.html', PENDING_COST_CENTRE: 'approvals.html',
    APPROVED: 'offer.html', OFFER_DRAFTED: 'offer.html', OFFER_SENT: 'offer.html',
    OFFER_ACCEPTED: 'pipeline.html', OFFER_DECLINED: 'offer.html',
    HIRED: 'pipeline.html', CLOSED: 'pipeline.html', NOT_PROCEEDING: 'pipeline.html', WITHDRAWN: 'pipeline.html'
  };
  function furthestLifecycleStep(rows) {
    var best = null;
    (rows || []).forEach(function (row) {
      var rank = LIFECYCLE_RANK[row.status];
      if (rank == null || rank === 0) return; // still just shortlisted — no override
      if (!best || rank > LIFECYCLE_RANK[best.status]) best = row;
    });
    return best;
  }

  window.CampaignSteps = {
    LABEL: LABEL,
    // Hash id -> element id on new-campaign.html. Exposed so that page maps a
    // hash without a second copy of the table.
    anchorFor: function (step) { return ANCHOR[step] || null; },
    next: next,
    label: function (campaign, run) {
      var id = next(campaign, run);
      return id ? LABEL[id] : '';
    },
    href: href,
    // Read only the records needed for this campaign. Callers must show a
    // retry on failure; a failed read is never evidence of an empty stage.
    resolve: async function (campaign, read) {
      var step = next(campaign, null), run = null;
      var path = '/api/campaigns/' + encodeURIComponent(campaign.id);
      if (campaign.status === 'DRAFT' || campaign.status === 'AWAITING_RUBRIC_APPROVAL') {
        if (!String(campaign.job_title || '').trim() || campaign.job_title === 'New role') step = 'role';
        else if (!String(campaign.job_description || '').trim()) step = 'jd';
        else {
          var requirements = await read(path + '/requirements');
          step = requirements.length ? (campaign.status === 'DRAFT' ? 'requirements' : 'rubric') : 'jd';
        }
      } else if (['APPROVED', 'PROCESSING', 'REVIEW', 'CLOSED'].indexOf(campaign.status) >= 0) {
        var runs = await read(path + '/evaluations/runs');
        runs.sort(function (a, b) { return String(b.created_at).localeCompare(String(a.created_at)); });
        run = runs[0] || null;
        if (run) {
          run = Object.assign({}, run, { run_id: run.id });
          step = /^(COMPLETED|COMPLETED_WITH_ERRORS)$/.test(run.status) ? 'shortlist' : 'assess';
        }
      }
      if (step === 'shortlist') {
        try {
          var lifecycle = await read(path + '/lifecycle');
          var furthest = furthestLifecycleStep(lifecycle);
          if (furthest) {
            return {
              step: 'shortlist',
              label: LIFECYCLE_LABEL[furthest.status] || (LABEL.shortlist),
              href: (LIFECYCLE_PAGE[furthest.status] || 'pipeline.html') + '?campaign=' + encodeURIComponent(campaign.id)
            };
          }
        } catch (error) { /* fall through to the shortlist-review default below */ }
      }
      return {
        step: step,
        label: step === 'jd' && String(campaign.job_description || '').trim()
          ? 'Read the job description' : (LABEL[step] || 'View closed campaign'),
        href: href(campaign, run, step) || ('pipeline.html?campaign=' + encodeURIComponent(campaign.id))
      };
    }
  };
})();

// --- How a campaign is named in a chooser --------------------------------
// Every campaign select used to read `job_title + ' — ' + name`. The two
// fields are near-duplicates of each other in practice — "Process Engineer ·
// E2E Verification - Process Engineer" — and `name` is an internal label
// ("rail demo", "X22 verify") that means nothing to a recruiter. The result
// was a long option that said the role twice and helped with neither choosing
// nor telling two campaigns apart.
//
// The role and the site are what a recruiter picks by, so they are what the
// option says. The internal name is added back only to campaigns that would
// otherwise read identically, because two identical options are worse than a
// long one.
(function () {
  function role(campaign) {
    return campaign.job_title || campaign.name || 'Untitled role';
  }

  function plainLabel(campaign) {
    var text = role(campaign);
    return campaign.location ? text + ' — ' + campaign.location : text;
  }

  // [{ id, label }] for a list of campaigns, in the order given.
  function campaignOptions(campaigns) {
    var list = campaigns || [];
    var seen = {};
    list.forEach(function (campaign) {
      var label = plainLabel(campaign);
      seen[label] = (seen[label] || 0) + 1;
    });
    return list.map(function (campaign) {
      var label = plainLabel(campaign);
      // Same role at the same site twice: say which one, using whatever the
      // person who set it up called it.
      if (seen[label] > 1 && campaign.name && campaign.name !== role(campaign)) {
        label += ' · ' + campaign.name;
      }
      return { id: campaign.id, label: label };
    });
  }

  window.campaignLabel = plainLabel;
  window.campaignOptions = campaignOptions;
})();
