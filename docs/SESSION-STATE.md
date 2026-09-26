---
# SESSION-STATE
updated: 2026-09-24T00:00:00Z
session_token_cost_estimate: 1700

## session_wrap — committed and pushed (2026-09-24, latest)
Direct instruction: "save state / commit and push all the changes that we have made till now."
Reviewed the full staged diff before committing (`git status`/`git add -A` output checked file
by file — the one untracked file, `scripts/seed_role_logins.py`, is demo-only, fixed, public
credentials, same convention as `scripts/seed_demo_login.py`, not a secret). Committed everything
accumulated across this and prior uncommitted sessions (`f5ee54c`, 34 files) — the B17
reversed-direction what-if work below, plus the still-uncommitted B26 follow-ups/B27/B28/B29/
X66/X67 work carried over from earlier sessions (see their own wraps below for the per-decision
detail). Pushed with `git push origin consolidated:develop` — a clean fast-forward
(`3f9ae87..f5ee54c`), matching the tracking relationship `git branch -vv` already showed
(`consolidated` tracks `origin/develop`, set by the 2026-09-17 push). Working tree is clean
after the push.

## session_wrap — where this session left off (2026-09-24, B17 reversed-direction UI)
Direct instruction: "at the HMs side add an option in what if analysis to send weights to
approver... at hr side when i click what if a notification should be there like HM suggested
these weights." Restored context first (`AGENT-START-HERE.md`/`docs/SESSION-STATE.md` read,
`git status`/`git log` checked — working tree matched the last-recorded state, nothing lost).

Discovered the backend for this already existed as B17 (`app/services/whatif_service.py`,
`WhatIfProposal` model, five `/api/campaigns/{id}/what-if/proposals` routes) — built 2026-09-12/13
for the *other* direction (HR proposes, hiring manager approves) and its UI was deliberately
dropped from `web/whatif.html` on 2026-09-14 per a direct instruction at the time (flagged then
for `08-TWO-PERSON-DELIVERY.md` reconciliation, still unresolved). This session's ask reverses
that direction, so it's new UI, not a revert.

**Built:**
- `app/services/whatif_service.py::propose()` — approver-role check now branches on the
  *proposer's* role: a `HIRING_MANAGER` proposer must send to `RECRUITER`/`ADMIN`; every other
  proposer (the original case) still must send to `HIRING_MANAGER`/`ADMIN`, unchanged. Chosen
  over loosening the check unconditionally, which would let one `RECRUITER` approve another's
  proposal — defeating the "correct counterpart" invariant the original test already covered.
- `app/services/auth_service.py::display_identity()` — `counterpart` now includes `id`, so the
  frontend can default a share-panel recipient to the signed-in person's actual counterpart
  without an extra lookup.
- `web/whatif.html` — a "Send weights to HR" panel (recipient dropdown, defaulted to the
  counterpart when present, optional note) shown only when `window.__r360Me.role ===
  'HIRING_MANAGER'`; and a suggestion banner ("`<name>` suggested these weights", with the note,
  and Use/Approve/Return buttons) shown to everyone else when a `PROPOSED` proposal names them as
  approver. Translates between this page's five aggregated band sliders and the API's
  per-criterion weight dict by redistributing each band's slider value across its criteria in
  their existing proportions, then normalising the whole set to total 100 (the API's own
  invariant) — and the reverse, summing a proposal's per-criterion weights back into band totals
  to preload the sliders on "Use these weights".
- Tests: `tests/test_whatif_proposals.py` — two new (`test_hiring_manager_can_propose_weights_to_hr`,
  `test_propose_requires_hr_approver_when_proposer_is_the_manager`), 18 passed total (58 with
  `test_lifecycle.py`).

**Live-verified in the browser** (dev servers already running from a prior session; the API
process needed a restart to pick up the `auth_service.py`/`whatif_service.py` changes — two stale
uvicorn processes on :8000 found and replaced with one fresh one): signed in as Subhadeep
(`HIRING_MANAGER`), changed a slider, sent to his counterpart Ankush Saxena; signed in as Ankush,
saw the banner, used "Use these weights" (sliders preloaded correctly), "Approve" (proposal
→ `APPROVED`, audit event written per `whatif_service.approve()`'s existing trail), and separately
"Return" on a second test send (→ `REJECTED`). **Found and fixed a real bug during this pass**,
not caught by the pytest suite: the new `bandCriteria()` helper matched criteria by `category`
alone, so a category holding both `MANDATORY` and optional criteria (this campaign's `SKILL`
category has 20 mandatory + 8 optional) double-counted the mandatory ones into that band's
redistribution base — sending Skills=18 actually proposed Skills≈3.7/Mandatory≈96.3 instead of
the correct ≈16.1/≈83.9. Fixed by excluding `MANDATORY`-type criteria from every non-mandatory
band, matching `buildBands()`'s own split. Caught only by checking the raw stored
`proposed_weights` against hand math, not by the UI merely rendering — logged as a caution for
future what-if-page changes. Two real `WhatIfProposal` rows now exist against the demo `HSE
Officer` campaign (one `APPROVED`, one `REJECTED`) from this verification pass; left in place, no
delete endpoint exists and they're accurate history, not broken test data.

Plan bookkeeping this turn: `00-MASTER-BACKLOG.md` (B17), `docs/DECISIONS.md` (2026-09-24 row).
No defect-severity change to `04-KNOWN-DEFECTS.md` — the band-math bug was introduced and fixed
within this same session, never shipped.

**Left / next:** not asked to restrict which HR account a hiring manager can send to beyond the
existing `RECRUITER`/`ADMIN` role check — any HR account can currently be picked from the
dropdown, not just the counterpart (the counterpart is only the default). `08-TWO-PERSON-DELIVERY.md`
still has the unresolved 2026-09-14 flag on `whatif.html`'s allocation; this session adds a second,
separate flag rather than resolving either. Not committed — working tree now also includes
`app/services/whatif_service.py`, `app/services/auth_service.py`, `web/whatif.html`,
`tests/test_whatif_proposals.py`, on top of everything the entry below already lists. Ask before
committing/pushing, per this repo's standing rule.

## session_wrap — where this session left off (2026-09-24, no plan ID — account provisioning)
Direct instruction: make `ankush.saxena@protivitiglobal.in` an administrator with every role's
access ("hm hr budget approver everyone... can perform every action"). No plan ID — same
category as the 2026-09-17 role-promotion/downgrade entries below (account provisioning, not a
feature).

Checked the current role model first rather than assuming: backend `WHO_MAY`
(`app/core/lifecycle.py`) already lists `ADMIN` for every lifecycle transition, and the two
frontend role gates (`window.__r360Locked()` for `HIRING_MANAGER`, `applyRoleGate`'s redirect
for `REVIEWER`, both in `web/assets/app.js`) only single out those two roles by name — `ADMIN`
already bypasses both. So this reduced to a plain data change, no code: `PATCH
/api/users/{id}/role {"role":"ADMIN"}` against the running API (the same endpoint the
2026-09-17 decision used), reverting this account from `RECRUITER` back to `ADMIN`.

**Live-verified:** `GET /api/users` confirmed the pre-change role was `RECRUITER`; after the
patch, signed in as this account — nav showed the full site ("HR-Administrator", "Start
Campaign" present, all six workspace stages including Handoff/Approvals reachable),
`window.__r360Me.role` read `ADMIN`, `window.__r360Locked()` read `false`.

Logged in `docs/DECISIONS.md` (2026-09-24 row) only — no backlog/defect ID applies, so
`00-MASTER-BACKLOG.md` is unchanged this turn.

**Left / next:** nothing outstanding. No code, test, or plan-checklist changes this turn (data
change only). Working tree unchanged from the `B29` entry below plus `docs/DECISIONS.md`, this
file. Ask before committing/pushing, per this repo's standing rule.

## session_wrap — where this session left off (2026-09-23, B29)
Direct instruction, continuing from the read-only session below: HR reopening a campaign
must land on the page where they left off; a hiring manager clicking a campaign must land on
the page needing his own action (not wherever the furthest-progressed candidate happens to
be — a different candidate in the same campaign can be further along). No prior ID covered
this exact request; logged as **B29** (`00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, both
2026-09-23 rows).

**Built and live-verified** (`web/campaigns.html` only, no backend change):
- Fixed a real bug that `B28` only half-caught: `renderRuns()` built its `resolveButton()`
  argument from `run.campaign` (the embedded summary, no `id` field) — `resolveButton()`'s own
  `if (!campaign.id) return` guard silently no-opped for every completed-run card, so it stayed
  on the hardcoded "Review the shortlist" → `leaderboard.html` default even once the campaign
  had actually moved on to handoff/interview/offer. This *was* HR's "I did till handoff and
  left it" complaint. Fixed by stamping `run.campaign_id` onto the campaign object before use.
- Added the hiring-manager override: one shared `fetchAwaitingMap()` (per-campaign
  `/api/campaigns/{id}/lifecycle/funnel` read, computed once in `render()`) replaces
  `markAwaitingHisDecision()`'s own separate fetch of the same data and is also passed into
  every `resolveButton()` call. When `window.__r360Locked()` is true and a campaign has someone
  `WITH_HIRING_MANAGER`/`INTERVIEW_SCHEDULED`, the card's link/label is overridden to
  `handoff.html` ("Record your shortlist verdict") / `interview.html` ("Record interview
  feedback") instead of the generic furthest-stage result. Sharing one promise avoids a race
  between the tag/reorder logic and the href override reading the same endpoint twice.
- Live-verified in the browser: as HR (`ankush.saxena@protivitiglobal.in`), previously-stuck
  "Review the shortlist" cards now correctly resolve to `handoff.html`/`interview.html`/
  `offer.html`/`pipeline.html` per the campaign's actual furthest stage; as the hiring manager
  (`subhadeep.m@protivitiglobal.in`), every "waiting on you" campaign now shows and links to his
  own pending action; signed back into HR afterward, no regression. No test suite run this
  session — frontend-only change, no backend/test files touched.

**Left / next:** not verified — a campaign where the hiring manager's own funnel counts are
zero but a draft is open concurrently (drafts are already hidden for him, `B28`); no case found
where this matters. Not committed — working tree unchanged from the entry below plus
`web/campaigns.html`, `docs/plan/00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, this file. Ask
before committing/pushing, per this repo's standing rule.

## session_wrap — where this session left off (2026-09-23, no-code session)
Read-only session, no plan ID — just oriented against the existing B28 state and answered
"where is the complete/close-campaign option" navigation questions. No code, docs, or plan
files changed by this session's own work (this entry is the only edit).

Confirmed: working tree is exactly the uncommitted B28 state described below (same file list),
nothing lost or needing restoration. Both dev servers were already running (API on `:8000`,
web on `:8124`) from a prior session — did not need to be started.

Answered where the "Close campaign" control (`B27`) lives: `web/pipeline.html`'s "Current
position" card, reached from any stage page's campaign-journey dropdown via "Campaign
pipeline" (e.g. from `comms.html`'s "Offer & hire" stop menu). Logic in
`web/assets/journey.js:98-227` (`renderCampaignClose`, POSTs `/api/campaigns/{id}/status`
`{"status":"CLOSED"}`, terminal, no role gate — flagged in the backlog as a possible follow-up).

**Left / next:** nothing outstanding from this session. Still not committed — same working
tree as the `B28` entry below; ask before committing/pushing, per the standing rule.

## session_wrap — where this session left off (2026-09-23, B28)
New session, resumed from the B26/B27 state below (uncommitted working tree carried over —
see that entry's file list, all still uncommitted). Three direct instructions this turn,
reversing part of `B26`'s "the hiring manager sees and can do everything" call: lock every
screen but his own two decisions to view-only, remove his ability to start a campaign, and
give him a "Campaign" nav destination instead. Asked two clarifying questions first (which
controls count as "his," recommended keeping it to the two existing verdict gates; where
"Campaign" should point, recommended reusing `campaigns.html` filtered) — both answered with
the recommended option.

**Built, not yet live-verified (no dev server running this session):**
- `window.__r360Locked()` (`web/assets/app.js`) — true only for `HIRING_MANAGER`. Every other
  page checks it directly rather than a blanket CSS disable, after confirming several pages'
  `<button>`s are pure view/filter controls (leaderboard tier pills, compare.html's pager and
  "+N more" toggles, new-campaign.html's tabs, developer.html's Refresh) that a blanket lock
  would have broken.
- Locked (read-only tag or disabled control, data still visible): `handoff.html` ("Send back
  to manager"/"Record as hired"/"Close the file" — "Record verdict" untouched, already
  `B26`-gated), `interview.html` ("Schedule interview" row-action — "Record feedback"
  untouched), `candidate.html` (Shortlist/Hold/Reject), `decisions.html` (Shortlist/Hold/Reject,
  "Email the shortlist"), `discover.html` (Find/Import CVs), `comms.html` (Record message), and
  via shared `journey.js`: `pipeline.html`'s Close campaign, `approvals.html`'s
  request/cost-centre/return forms, `offer.html`'s draft/send/response forms.
- Nav: his "Start Campaign" link becomes "Campaign" → `campaigns.html` (`applyHiringManagerNav`
  in `app.js`); any other campaign-creation entry point is hidden via a shared
  `data-campaign-create` marker. `start-campaign.html`/`new-campaign.html` redirect him to
  `campaigns.html` outright (portal-gate `applyRoleGate`, same mechanism as `B25`'s
  budget-approver redirect) — not reachable by typed URL either.
- `campaigns.html` for him: hides the "Not finished yet" draft band, and tags + floats to the
  top any campaign with a candidate actually at `WITH_HIRING_MANAGER`/`INTERVIEW_SCHEDULED`,
  read live per campaign from the existing `/api/campaigns/{id}/lifecycle/funnel` (no backend
  change).
- Bumped `app.js`/`journey.js` cache-busting (`v=38→39`, `v=5→6`) across every page loading
  them, and `sw.js`'s `CACHE` (`v25→v26`), per the existing convention.
- Logged as `B28` (`00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, both 2026-09-23 rows). Also
  resolves the open flag `B27` left on "Close campaign has no role gate."

**Live-verified** against the already-running dev servers (both API and web were up from
before this session): signed in as `subhadeep.m@protivitiglobal.in` (`HIRING_MANAGER`) — nav
showed "Campaign", `start-campaign.html` redirected to `campaigns.html`, the draft band and
"Start a new campaign" were hidden, `campaigns.html` correctly tagged/floated campaigns with
real pending counts ("14 campaigns are waiting for your decision"), and every locked control
(`handoff.html` ready-to-close, `interview.html` scheduling, `candidate.html`'s decision
buttons, `decisions.html`'s send button, `pipeline.html`'s close-campaign) showed its
read-only state with no request sent. Signed back in as HR and confirmed no regression.
Found and fixed two real bugs while verifying: `renderRuns()`/`markAwaitingHisDecision()`
were reading a run's embedded `campaign.id` (doesn't exist on that payload — real id is
`run.campaign_id`), which silently skipped nearly every campaign from the funnel check; and
`discover.html`/`candidate.html`'s initial lock ran before the portal gate's async auth check
necessarily resolved `window.__r360Me` — fixed via the existing `r360-auth-ready` event (plus
a click-time re-check on `candidate.html`).

**Left / next:** nothing outstanding on `B28` itself. Not committed — working tree now also
includes `web/assets/app.js`,
`web/assets/journey.js`, `web/handoff.html`, `web/interview.html`, `web/candidate.html`,
`web/decisions.html`, `web/discover.html`, `web/comms.html`, `web/campaigns.html`,
`web/index.html`, every other `web/*.html` (cache-bust bump only), `web/sw.js`,
`docs/plan/00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, this file, on top of everything the
2026-09-23 entry below already lists. Ask before committing/pushing, per this repo's standing
rule.

## session_wrap — where this session left off (2026-09-23, B26 follow-ups + B27)
Continuation of B26 (role-based interface). Three separate direct instructions this session:
seed two named logins, restrict two more HR/HM-shared screens by role, and add a way to
close a whole campaign.

**1. Named logins (no plan ID — account provisioning, not a feature):**
- `ankush.saxena@protivitiglobal.in` set to `RECRUITER` (HR) — was `ADMIN`. Made the change
  per the direct, unambiguous instruction ("make ankush.saxena... as a HR"), but flagged to
  the user afterward that this was a real downgrade (loses the admin bypass in `WHO_MAY`),
  in case it should be reverted — no response yet, so `ADMIN` was not restored.
- `subhadeep.m@protivitiglobal.in` confirmed already `HIRING_MANAGER` (unchanged) — this is
  the same account `app/services/auth_service.py`'s `FLIP_COUNTERPART` two-person demo map
  already hardcodes as Ankush's counterpart, so the "HR-Recruiter" / "Hiring manager"
  display-label flip (`display_identity`) works correctly with no further change.
- Both via a one-off scratch script calling `scripts/set_password.py`'s `set_password()`
  directly (not the CLI, which needs an interactive `getpass` prompt this session can't
  drive) — password `Demo12345!`, matching `scripts/seed_role_logins.py`'s existing
  convention. Scratch script discarded, not committed.

**2. B26 follow-ups — two more screens gated by role (`00-MASTER-BACKLOG.md`, `DECISIONS.md`,
2026-09-23 rows):**
- `web/handoff.html`'s "With the hiring manager" group: HR no longer sees "Record verdict"
  (a control that let HR enter the hiring manager's own decision on their behalf) — only a
  read-only "Pending" tag. The button (still posts to `/lifecycle/{id}/review`) is shown only
  when `window.__r360Me.role` is `HIRING_MANAGER` or `ADMIN`. Direct instruction: "hr should
  not have action over hm."
- `web/interview.html`'s "Scheduled" group: same gate on "Record interview feedback" — HR sees
  a read-only "Awaiting hiring manager's feedback" tag instead of an openable form
  (`canRecordFeedback()`, same role check).
- Both live-verified by actually signing in as each account in the browser (not just reading
  code): HR saw the read-only tag with no control in both places; the hiring manager
  (`subhadeep.m@...`) still saw and could use both controls unchanged.
- The "returned, with a question" and "ready to close" handoff groups, and everything else on
  both pages, are untouched — replying to a manager's question and closing a file after a
  decision are HR's own actions, not the hiring manager's verdict.

**3. B27 (new plan ID — close a campaign, no prior ID covered this):**
- Added a "Close campaign" control to `web/pipeline.html` (the campaign-level "complete
  journey" overview), at the end of the "Current position" card. Inline confirm (open →
  Confirm/Cancel), matching the existing inline-confirm convention elsewhere
  (`handoff.html`'s "Close the file"). Calls `POST /api/campaigns/{id}/status
  {"status":"CLOSED"}` — an endpoint that already existed and needed **no backend change**
  (`app/api/campaigns.py::transition_status`, `Campaign.can_transition_to()` in
  `app/db/models.py`, already-working audit trail). Researched first via a subagent to
  confirm nothing like this already existed before building.
- Once closed, the button is replaced by a "Campaign closed" tag (`renderCampaignClose()`,
  `web/assets/journey.js`) — `CLOSED` is terminal, no transition back out.
- No role gate on this control (unlike the two B26 follow-ups above) — not asked to restrict
  it, and closing a campaign isn't clearly an HR-vs-HM distinction the way recording a verdict
  is. Flagged in the backlog in case that should change later.
- Bumped `journey.js`'s cache-busting query (`v=4→5`, on `pipeline.html`/`approvals.html`/
  `offer.html`, every page that loads it) and `web/sw.js`'s `CACHE` (`v24→v25`), per the
  existing convention (`X50`/`X59`/`X60`/`X67`) for any changed shared asset.
- Live-verified end to end against the real API: created a disposable test campaign, drove
  the real UI through open→cancel (no request sent) and open→confirm (button hid, tag
  appeared), confirmed via `GET /api/campaigns/{id}` that `status`/`version` changed
  server-side, then deleted the disposable campaign. Separately confirmed the button renders
  and opens correctly — never confirmed — against the real, populated `HSE Officer — Coastal
  Terminal` campaign, since `CLOSED` is irreversible and that campaign's data isn't disposable.

**Left / next:** nothing outstanding on any of the three items above. Not committed —
working tree has uncommitted changes across `app/api/lifecycle.py`, `app/core/lifecycle.py`,
`app/core/mail_guard.py` (all three pre-existing from before this session, untouched by it),
`web/handoff.html`, `web/interview.html`, `web/pipeline.html`, `web/sw.js`,
`web/assets/journey.js`, every other `web/*.html` (cache-bust bump only, from the B26 turn
before this one), `docs/plan/00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, this file. Ask
before committing/pushing, per this repo's standing rule.

## session_wrap — where this session left off (2026-09-22, B26)
Resumed an RBAC design discussion carried in this assistant's memory (not previously written
to this repo — HR/hiring-manager/budget-approver interface split, agreed but not coded). User
asked to build it: demo logins for all three roles, and the interface changed per role, then
described the exact seven-login walkthrough they'll use to demo it (HR → HM → HR → HM → HR →
budget approver → HR).

No prior plan ID covered this (B25 was already the JD library), so it landed as a new one,
**B26** (`00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, both dated 2026-09-22).

**Built and live-verified:**
- `REVIEWER` `UserRole` repurposed as "Budget approver" (label only, `app/api/lifecycle.py`)
  — it was unused and `journey.js` already anticipated it as an approver role.
- `app/core/lifecycle.py` `WHO_MAY`: `RECRUITER` added to `PENDING_COST_CENTRE`, `REVIEWER`
  added to `APPROVED`. Nothing removed — every existing role capability is untouched.
- `scripts/seed_role_logins.py` (new, same convention as `scripts/seed_demo_login.py`) — run
  live against the local dev DB. Three accounts now exist: `hr@demo.local` (RECRUITER),
  `hm@demo.local` (HIRING_MANAGER), `budget@demo.local` (REVIEWER), all password
  `Demo12345!`.
- Frontend role gate: `web/assets/app.js`'s portal gate redirects a signed-in `REVIEWER` to
  `approvals.html` from anywhere else, before the page paints; hides the sitewide nav and the
  campaign-stage dock for that role. `web/assets/journey.js`'s approvals workspace narrows the
  candidate list and action form to the budget-approval step only for `REVIEWER`, shows a
  read-only "waiting on the budget approver" message to everyone else at that step, and
  defaults/locks the "Acting person" field to the signed-in user. HR and the hiring manager
  are deliberately **not** narrowed — the user's fresh walkthrough said the hiring manager
  should see everything, which supersedes the more restrictive HM design from the earlier
  (uncommitted) RBAC discussion.
- `app.js`/`journey.js` cache-busting bumped (`v=37→38`, `v=3→4`) across every `web/*.html`
  page that references them, per this repo's existing convention (`X50`/`X59`/`X60`/`X67`).

**Verification:** live in the browser (not just API calls) — HR routed a real candidate from
`PENDING_APPROVAL` to `PENDING_COST_CENTRE`; logged in as the budget approver, got redirected
straight to `approvals.html` with nav/dock hidden, saw only that one candidate, granted it to
`APPROVED` through the real button ("Saved to the candidate record."); HR and hiring-manager
logins both landed on `index.html` with the full site intact. Targeted suite
(`test_lifecycle.py`, `test_approvals_api.py`, `test_cost_centre_delegation.py`,
`test_auth_api.py`): 69 passed. Full suite re-run once at the end: **835 passed**, no
regressions.

**Left / next:** no screen besides `approvals.html` itself changes by role — every other page
(candidate.html, decisions.html, etc.) is reachable and fully functional for HR and the
hiring manager alike, which is intended, not a gap. `B13`'s `on_behalf_of_id` delegation path
was not specifically re-tested against the new `WHO_MAY` entries (existing delegation tests
still pass unchanged). Not committed — working tree has uncommitted changes across
`app/core/lifecycle.py`, `app/api/lifecycle.py`, `web/assets/app.js`, `web/assets/journey.js`,
every `web/*.html` (cache-bust bump only), `scripts/seed_role_logins.py` (new),
`docs/plan/00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, this file. Ask before committing/
pushing, per this repo's standing rule.

## session_wrap — where this session left off (2026-09-18, X67)
User reported: screening from the Shortlist stage (and reportedly other stages) shows the
journey rail correctly highlighting the current stage, but the page body underneath is
`index.html`'s ("Today") content. Investigated via a research agent rather than guessing.

Ruled out the journey rail (`web/assets/app.js`) — it's plain `<a href>` navigation per stage,
not a client-side router, so it can't be swapping content. Root cause is `web/sw.js`'s
network-first-with-offline-fallback: on a failed fetch for an uncached navigation request it
falls back to `caches.match('index.html')` (`sw.js:47-51`). This exact mechanism was already
found and scoped once before in `X27` (2026-09-13, restricted the substitution to
`e.request.mode === 'navigate'`). The code on disk already has that fix and lists
`leaderboard.html` in `SHELL`, so the likely trigger is a browser tab still running an **older,
previously-installed service worker** (predating `X27` or predating stage pages being added to
`SHELL`) that never re-checked/activated — a long-lived tab can keep running stale fetch logic
against a stale `qchem-talent-v<old>` cache indefinitely without a hard reload.

**Fix:** bumped `CACHE` in `web/sw.js` (`v23` → `v24`), matching the existing cache-busting
convention already used for `app.js`/`app.css` (`X50`/`X59`/`X60`), to force any stale worker
instance to install the current script and purge its old cache.

Logged as `X67` in `docs/plan/04-KNOWN-DEFECTS.md` (open — two boxes unchecked) and
`docs/DECISIONS.md` (2026-09-18 row). No plan ID pre-existed for this; it's a newly found defect,
not a backlog item, so `00-MASTER-BACKLOG.md`/`01-DEMO-MONDAY.md` are unchanged this turn.

**Left / next:** not yet reproduced live against a genuinely stale pre-`X27` worker instance.
Ask the user to hard-refresh, or DevTools → Application → Service Workers → Unregister then
reload, to confirm the stale-SW theory and close `X67` out. If it recurs even after that, the
`activate` handler may need to proactively notify/reload already-open clients (`self.clients.claim()`
already runs, but nothing pings existing tabs) rather than relying on a manual hard refresh.

## session_wrap — where this session left off (2026-09-17, latest)
Committed and pushed, on direct instruction. `git commit` on `consolidated` (`1989f8e`,
"B08/X66: recolour+icon the campaign journey rail; manager-question email reply") covers both
wraps below, then `git push origin consolidated:develop` — a clean fast-forward (`7afb7d7..
1989f8e`), since `origin/develop` was already a strict ancestor of `consolidated`. Targeted
tests (`test_lifecycle.py`, `test_reports_api.py`, 55 passed) run before committing; full suite
not re-run this turn.

**Flagged, not yet resolved:** `develop` is not named anywhere in `CLAUDE.md` or
`08-TWO-PERSON-DELIVERY.md` — those only describe `azure-provider` (shared product branch) and
`origin/consolidated` (authorized publish target). The push was safe (fast-forward, no rewrite),
but if `develop` is meant to be a real integration branch going forward, `08-TWO-PERSON-DELIVERY.md`
needs a line recording that, or the next session will hit the same undocumented-branch surprise.

**Left / next:** decide/record `develop`'s role in `08-TWO-PERSON-DELIVERY.md`; otherwise nothing
outstanding on the committed slice.

## session_wrap — earlier the same day (2026-09-17, B08 nav rail)
B08, direct instruction with a reference screenshot: restyled the sitewide `.cjourney-bar`
(campaign journey rail, `web/assets/app.js`) to match — per-stop icons (inline SVG) inside the
circle, done = solid `--maroon-deep`/white icon (was green), current = `--maroon-soft` fill with
a `--maroon` ring/icon (was a solid red dot), pending unchanged; the `>>>>>>>>` chevron
connectors became a plain dotted `--maroon-mid` line. `web/assets/app.js` (`STOPS`/`ICONS`,
`repaint()`) and `web/assets/app.css` (`.cjourney-circle`, `.cjourney-arrow`). Bumped the
sitewide `app.js`/`app.css` cache-busting query (`v=36→37`, `v=26→27`) across every `web/*.html`
page — needed because the browser kept serving the pre-edit files from disk cache under the
unchanged `?v=` URL even after a full reload. Browser-verified live on `candidate.html` and
`leaderboard.html` against the real `HSE Officer · Coastal Terminal` campaign: icons/colours/
dotted connectors render as designed; the per-stop caret dropdown (e.g. Shortlist → Candidate
360/Compare/Decisions) still opens and links correctly. No backend change, no test change.
Plan bookkeeping: `00-MASTER-BACKLOG.md` (B08), `docs/DECISIONS.md` (2026-09-17 row).

**Left / next:** nothing outstanding on this slice — purely a `web/assets/app.js`+`app.css`
restyle, no backend or data contract touched. The rest of B08 (amber semantics, a sitewide
colour rollout beyond what's listed above) remains open, per the master backlog.

## session_wrap — earlier the same day (2026-09-17)
X66 second follow-up, direct instruction: on `web/handoff.html`'s "Returned, with a question" row,
the recruiter needed real named managers in the dropdown ("like subhadeep ankush"), a place to
write the answer to the manager's question, and a real email sent to that manager on confirm — the
same real-send capability the prior turn proved for the other direction (`decisions.html` →
`with_manager`), but this row's own "Send back to manager" action never emailed anyone.

- `app/api/lifecycle.py`'s `send_to_manager` (`POST .../lifecycle/{id}/send-to-manager`) now looks
  up the candidate's most recent `QUESTION` reason (`_last_question`, mirroring `handoff.py`'s
  private helper of the same name) and, only when one is on file, emails the chosen manager for
  real (`mail_guard.ensure_approved_mail_recipients` + `outlook_adapter.get_mail_adapter().send`),
  quoting the question and the recruiter's note as the answer. The same endpoint also does the very
  first, question-free handoff — that path is unchanged, no mail sent. `LifecycleOut` gained
  `mail_sent`/`mail_detail` (`None` when no question existed to answer).
- `web/handoff.html`: `loadManagers` now fetches and merges `role=HIRING_MANAGER` and `role=ADMIN`
  (deduped by id), so an admin-promoted stand-in (the user's own account, from the prior X66 turn)
  shows up here too. The `send` action's note field is relabelled "Your answer to the manager's
  question (sent to them by email)" and required whenever `entry.question` is present; on confirm,
  a green line reports `mail_detail` for ~1.4s before the fold reloads.
- Created a third real account, `Subhadeep` (`subhadeep.m@protivitiglobal.in`, `HIRING_MANAGER`),
  via the running server's own `POST /api/users` — that address was already on
  `mail_guard.APPROVED_MAIL_RECIPIENTS` but had no `User` row, so it could not previously own a
  lifecycle row or receive a real send.
- Restarted the dev server (`QUEUE_BACKEND=inline`, port 8000) so it picked up the new code.
- **Verified live** on the real campaign (`5212142d-6150-4ecc-b2c7-9e97d8e31312`,
  `AHMED KARIM AL-SAYED`, `RETURNED_TO_RECRUITER` with a question on file): manager dropdown
  showed Subhadeep and Ankush Saxena alongside the demo accounts; answered the question, chose
  Ankush, confirmed — "Mailed the manager: Sent via local Outlook to
  ankush.saxena@protivitiglobal.in." (real, non-simulated); `GET .../handoff/queue` confirmed the
  candidate now sits under `with_manager`, owned by Ankush Saxena, `returned` empty.
- New test: `tests/test_lifecycle.py::test_answering_a_managers_question_emails_them_the_answer`;
  extended `test_a_candidate_is_handed_to_a_named_manager` to assert no mail on a question-free
  first handoff. Full suite: **835 passed**.
- Plan bookkeeping this turn: `00-MASTER-BACKLOG.md` (B01 item 4), `04-KNOWN-DEFECTS.md` (X66
  second follow-up), `docs/DECISIONS.md` (2026-09-17 row).

**Left / next:** nothing outstanding on this slice. The two `@qchem-demo.example` demo
`HIRING_MANAGER` accounts remain outside `mail_guard`'s approved list for a real send — not a
blocker; the three real accounts (Ankush, Subhadeep, Demo Admin/Imran as ADMIN) cover self-testing.
Fuller history lives in `docs/DECISIONS.md` and `docs/plan/04-KNOWN-DEFECTS.md` (X66 and its two
follow-ups) — not repeated here.

**Committed and pushed** — see the latest wrap above.

## how_to_run
Terminal 1 (API):
    $env:QUEUE_BACKEND = "inline"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
Terminal 2 (web):
    cd web ; python -m http.server 8124
Tests: `.\venv\Scripts\python.exe -m pytest -q` (full suite ~2.5-4 min); target a single file
while iterating.
