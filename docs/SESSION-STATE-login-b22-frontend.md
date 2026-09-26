---
# SESSION-STATE (login gate, B22 phase 1 — frontend half)
updated: 2026-09-13T00:00:00Z

## why a separate file
Same reason as docs/SESSION-STATE-login-b22.md, which this continues: the
central docs/SESSION-STATE.md carries Ankush's uncommitted B01/B11 notes.
This file is the frontend handoff for the backend work that file describes.

## labeling note (read this first)
docs/SESSION-STATE-login-b22.md and its commit (`aa62109 B22 phase 1: real
login for ankush.saxena / subhadeep.m`) both call this work "B22". The real
`B22` in docs/plan/00-MASTER-BACKLOG.md is "Hosting, security, data
residency" (owner Chiranjib + Subhadeep, nothing started) — completely
unrelated. No box in that section is ticked for this work. This login effort
has no real plan ID; recorded as a decision in docs/DECISIONS.md instead of
inventing one or renumbering the existing mislabeled commit (CLAUDE.md says
never renumber a plan ID, and `aa62109` is already in consolidated's shared
history).

## what's built and browser-verified this session
Environment note first: this worktree's branch had been checked out at a
very old ancestor commit (`ed9f08a`, pre-dating web/, docs/plan/, and the
whole app/ package) instead of consolidated's tip. Fast-forwarded it
(`git merge --ff-only consolidated`) before starting — safe, since that old
commit had zero unique commits on top and is a strict ancestor of
consolidated. Also: the local venv reports Python 3.12.10, not 3.13.15 as
one set of instructions expected; this matches what this worktree's
committed CLAUDE.md itself says ("verified on Python 3.12"), so treated as
current truth rather than a blocker. No new venv was created.

- **web/login.html** (new). Matches the site's shared chrome: the same
  `.bar`/`.id` header (no nav/`.me`, since there's no session yet), the
  `.arch.slim` maroon banner, and the shared `.form`/`.fld`/`.err` classes
  from web/assets/app.css (the same pattern web/new-campaign.html's fields
  use) so no new visual language was invented. Email + password, POSTs to
  `/api/auth/login`. On success stores the token under
  `recruitment360.auth.token` in localStorage and redirects to
  `index.html` (the "Today" dashboard — the page `.bar`'s own logo links
  back to, and the one page `initNavigation()` already treats as a fixed
  standalone destination). On 401 shows "Wrong email or password." inline
  via a `.err` paragraph, no alert()/throw. If a still-valid token is
  already in localStorage, it silently redirects to index.html instead of
  showing the form again. Does not include assets/app.js at all (see next
  section for why), so it needed its own small inline script — self-
  contained, no shared state with the gate beyond the token key name.

- **Portal gate in web/assets/app.js** (new IIFE at the very top of the
  file, before the "Keeps disclosure state per screen" IIFE). Skips itself
  immediately when `location.pathname` ends in `login.html` (belt-and-
  braces: login.html doesn't load app.js at all, so this never actually
  fires there, but the instruction was explicit that it must not run on
  that page, so the check exists independently of that fact). Otherwise:
  reads `recruitment360.auth.token` from localStorage; with no token,
  redirects immediately via `location.replace('login.html')` before any
  network call. With a token, adds `auth-pending` to `<html>` (see the new
  CSS rule in app.css: `html.auth-pending body{visibility:hidden}`) and
  calls `GET /api/auth/me` with the bearer token. On success it stores the
  user under `window.__r360Me`, removes `auth-pending`, and dispatches a
  `r360-auth-ready` CustomEvent with the user as `detail`. On any failure
  (network error or non-2xx) it clears the token and redirects to
  login.html. This is the pragmatic ordering fix the handoff flagged:
  because the rest of app.js still runs synchronously and unmodified
  immediately afterward (initNavigation, initMe, initCascade, the campaign-
  stage-switcher IIFE, the disclosure-state IIFE), none of those needed to
  be restructured to wait on a promise — they just paint into a
  `visibility:hidden` document until the async check resolves, which reads
  as instant.

- **initMe() rewired** (same file). Replaced the free-text `prompt()` /
  `recruitment360.me` localStorage placeholder entirely. Now: renders
  immediately from `window.__r360Me` if the gate's fetch already resolved
  by the time this runs (it won't have, in practice, since fetch is always
  async — but it's a cheap correctness guard), otherwise listens for
  `r360-auth-ready` and renders then. Shows `user.display_label` in the
  `.me span` (this is "HR" for the two flip accounts per
  `auth_service.display_identity`, or the role word for anyone else) and
  the initials of `user.full_name` in the avatar. The counterpart (when
  present) is surfaced in the avatar's `title` tooltip — e.g. "Ankush
  Saxena — click to sign out · today's Hiring manager is Subhadeep
  Majumder" — rather than new header UI, per "keep it simple". **Logout**:
  clicking the `.me` chip clears the token and sends the browser to
  login.html — no confirmation dialog, to keep the interaction as simple
  as the original prompt()-based chip it replaced. This is the only way
  out of the gate, so it had to exist; there wasn't one before this
  session.

- **app.css**: one new rule for `auth-pending` (see above) plus login-page-
  local styles inline in login.html's own `<style>` block (a centered card
  under the arch banner) — nothing shared was restructured.

- **Did not touch** the campaign-stage-switcher IIFE (the second top-level
  IIFE in app.js, right after the first one that contains initMe/
  initNavigation/initCascade) or anything below it, per the explicit
  instruction that it's someone else's in-progress work.

- **Did not touch** app/core/session_auth.py, app/services/auth_service.py,
  or app/api/auth.py. No bug was found in them that blocked this work.

### Browser verification actually performed (this session, via the Browser
pane against a fresh local `tis_app.db` created with `alembic upgrade head`
in this worktree, API on port 8010 with `QUEUE_BACKEND=inline`, static
server on port 8124 — 8124 specifically because `app/main.py`'s CORS
allowlist only names `http://localhost:8124`/`5173`; using a different
static-server port throws a CORS error on every fetch, discovered by
hitting it):

1. Seeded both demo accounts (`ankush.saxena@protivitiglobal.in`,
   `subhadeep.m@protivitiglobal.in`) with a known password via a one-off,
   uncommitted script that calls `app.core.session_auth.hash_password`
   directly against a `SessionLocal()` session — not `scripts/set_password.py`
   (that script belongs to a parallel agent's worktree and doesn't exist
   here; not depended on).
2. Loaded login.html cold: chrome matches the rest of the site (screenshot
   taken).
3. Submitted a wrong password: got "Wrong email or password." inline,
   no alert, no thrown exception in the console beyond the expected 401
   network log line.
4. Submitted the right password (ankush.saxena): redirected to index.html,
   header showed avatar "AS" and label "HR" — the real identity, not the
   old default. Confirmed via `window.__r360Me` in the console: full
   `display_identity()` payload present, including `counterpart` for
   Subhadeep, and the avatar `title` tooltip carries that counterpart text.
5. Cleared localStorage, hit `index.html` directly: redirected to
   login.html (confirmed via `location.href` after the redirect settled).
6. Hit `start-campaign.html` directly while signed out: also redirected to
   login.html — the gate isn't index.html-specific.
7. Logged in as subhadeep.m instead, then visited `new-campaign.html`
   (a page with both the header identity chip and the campaign-stage-
   switcher dock): header showed avatar "SM", "Start Campaign" nav item
   highlighted correctly by the pre-existing initNavigation(), and the
   stage-switcher dock at the bottom rendered and was still interactive —
   confirms the gate and the untouched IIFE coexist without interference.
8. Clicked the identity chip (logout): token cleared (verified via
   `localStorage.getItem` returning `null`), browser landed back on
   login.html.
9. Checked `read_network_requests` across all of the above: every
   `/api/auth/me` call returned `200 OK`; the one connection-refused/401
   error in the console log is from an earlier deliberate wrong-password
   test and an earlier apiBase-mismatch test (see below), not a live
   defect — confirmed by re-running the same flow cleanly afterward with
   no new errors of that kind.
10. Ran `pytest -q tests/test_auth_api.py tests/test_frontend_integration.py`
    in this worktree's venv: **36 passed**, 0 failed (some pre-existing
    deprecation warnings from starlette/click/spacy, unrelated to this
    change).

Two things tripped verification that are worth recording so the next
person doesn't rediscover them the hard way:
- A stale service-worker cache (`sw.js`, registered by an earlier page
  load with the pre-edit app.js) served an old cached app.js/index.html to
  the browser tab even after the files on disk were updated, hiding the
  new gate entirely on a couple of early test loads. Not a defect in this
  session's code — `sw.js` is pre-existing, untouched, and does a
  network-first fetch — but a real trap for anyone iterating on app.js
  with DevTools already having installed the service worker from a prior
  visit. Cleared via `serviceWorker.getRegistrations()` +
  `caches.keys()/delete()` during this session; nothing to fix in the
  shipped code.
- `login.html`'s inline script (like the rest of the site) reads
  `localStorage.getItem('recruitment360.apiBase')` once, at page-load
  time, following the existing convention. Setting that key via the
  console *after* the page has already parsed does nothing until the next
  navigation/reload — not a bug, just how the existing pattern already
  behaves everywhere else in this app; documented here only because it
  cost time during manual testing with the API on a non-default port.

## open / left for later
- Real password-setting for anyone beyond this session's throwaway seed
  still depends on the sibling agent's `scripts/set_password.py`, which
  does not exist in this worktree. The two demo accounts currently have a
  password only because this session set one directly against the DB for
  verification; that code was not committed (per instructions) and isn't
  in this diff.
- No "forgot password" / password-reset flow exists or was asked for.
- No CSRF concern beyond the existing bearer-token design (out of scope;
  matches `session_auth.py`'s own documented stateless-token tradeoff).
- The `auth-pending` CSS hide is a `visibility:hidden` on `<body>`, not
  `display:none` — chosen so page layout/dimensions are already resolved
  once content appears (no reflow flash). Not verified against a slow/
  throttled network in this session; on a very slow `/api/auth/me` call
  the user would see a blank page for that long, which is the same
  tradeoff the handoff note anticipated ("hide body via a class until the
  auth check resolves").
- Logout has no confirmation step, by design (see initMe() note above). If
  that's judged too easy to hit by accident later, that's a one-line
  change (wrap the localStorage.removeItem/redirect in a confirm()).
- This worktree's branch was found checked out at a stale ancestor commit
  and was fast-forwarded to `consolidated` before any of the above work
  started (see the environment note above) — flagging this in case other
  worktrees spun up alongside this one hit the same issue; it looked like
  a harness/setup problem, not something in the repository itself.

## context_to_inject_on_resume
- Read: this file
- Read: docs/SESSION-STATE-login-b22.md (the backend handoff this
  continues)
- Read: web/login.html, the portal-gate IIFE and initMe() at the top of
  web/assets/app.js
- Do NOT touch: the campaign-stage-switcher IIFE in web/assets/app.js
  (starts right after initMe()/initCascade()'s enclosing IIFE closes) —
  still someone else's in-progress work
---
