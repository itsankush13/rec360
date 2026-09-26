# Demo readiness — 2026-09-14 (QChem)

**MACHINE IDENTITY AND RE-SEEDING (2026-09-14, Subhadeep):** This document was originally written for
Ankush's machine (2026-09-12/2026-09-13) with campaign IDs, candidate scores, and role assignments
specific to that environment. This same file now governs a **re-established demo on Subhadeep's
machine** (C:\Users\subhadeep.m\..., same `consolidated` branch, same remote). The structure 
remains identical (four-JD library, three seeded campaigns, one live-walkthrough), but:
- **Campaigns A and B have new UUIDs and new seeded scores** (re-run via `scripts/seed_demo.py`
  on this machine with the same JDs but real fresh LLM evaluation runs).
- **Campaign B's role has been substituted** from "Instrumentation & Control Engineer" to
  "Process Engineer" because the original Instrumentation & Control JD and its three CVs do not 
  exist on this machine and could not be obtained in the available time. Process Engineer JD and 
  CVs are domain-coherent (Aspen HYSYS, HAZOP, olefins) and verified as strong substitutes.
  Role is presented plainly as "Process Engineer" in all docs, never relabelled.
- **Campaign C (Process Operator) and the fourth JD (HSE Officer) are unchanged** in structure,
  but Campaign C was built live via browser on this machine rather than seeded, and Suresh Nair 
  (scanned PDF) is the verified live candidate.
- Database migrations were applied on this machine (5 unapplied Alembic migrations fixed a 
  HTTP 500 on login). Ten pre-existing junk test campaigns were deleted to keep Start Campaign 
  clean. Calendar backend set to `simulated` (no real mailbox sends).

Ankush's original evidence entries below remain as a record of his session on his machine. Where
campaign IDs or scores appear below, substitute THIS MACHINE's values from the table in §0.

**Lane note:** `08-TWO-PERSON-DELIVERY.md` marks `web/**` as Subhadeep-owned. This session
edits `web/**` directly because the task explicitly requires full-stack demo-path fixes today,
solo, with no second person active — recorded here as a deliberate, explicit, user-authorized
boundary crossing for this session only, not a change to the ownership rule itself. Flagging
for Subhadeep's awareness at next handoff.

## Real state at session start (evidence, not old plans)

Full plan-doc and live-code audit performed via two research passes before any edit (see
transcript). Summary:

- **B01–B24**: mostly `[~]` partial, several `[x]` (B17 backend/B18/B21/B24 areas), none `[ ]`
  blocking-fresh except B06/B15/B22/B23 (out of scope for tonight — B22/B23 are commercial/
  infra topics, explicitly out of scope per this task's brief).
- **Journey steps 1–3, 6, 10 are LIVE** (CV discovery/import, AI screening incl. scanned/
  duplicate/no-identity handling since X35, decisions, hired/closed terminal states). **Steps
  4/5/7/8/9 (handoff, interview, HR discussion/approval, offer, accept/decline) are PROXY**:
  real lifecycle state + real audit row on every action, simulated outbound integration
  (email/calendar) by default. This is a deliberate, already-labelled design (`SIMULATED —
  INTEGRATION PENDING` badges exist on handoff/interview/approvals/offer/comms), not a gap to
  hide.
- **Outlook/calendar send is real but off by default** (`email_backend`/`calendar_backend`
  default `"simulated"` in `app/core/config.py`), and the adapters are explicitly documented as
  never exercised against a real signed-in Outlook profile. **Decision: leave both in
  `simulated` mode for this demo.** Do not flip to `outlook` without a separate, isolated test
  against a real mailbox first — no time for that today, and the task forbids sending a real
  invite/email without explicit per-message user approval of recipient/sender/content anyway.
- **No demo-seed script exists.** All 45 existing campaigns in the dev DB were produced by
  running the real UI/API flow in prior sessions (mostly bulk HSE Officer test batches, all
  `DRAFT`/`REVIEW` — none past rubric approval). They are pre-existing dev/test data, not
  today's demo data, and are left untouched (no destructive reset), but they will visually
  clutter `start-campaign.html`'s unfiltered card list unless addressed (see P0 list).
- **No JD library/repository exists.** Each JD lives embedded in its own campaign row; no
  reusable catalog. Building the smallest honest version is in scope today (see P0 list).
- **Cost-centre/budget model is minimal**: `code`, `name`, `budget_holder_id`,
  `annual_budget_usd`, `active` only. No business unit, fiscal year, currency, approved
  headcount, role/grade, or salary band fields — i.e. none of the fields Pritam's framing
  requires to show a believable pre-approved BU envelope. Needs a small, additive, nullable-
  column extension (see P0 list) rather than inventing numbers in the frontend alone.
- **Known, already-filed, non-blocking-for-demo defects** (see `04-KNOWN-DEFECTS.md` for full
  detail, not re-litigated here): X32 (CI red, Node-harness vs B22 gate — CI-only, not
  client-visible), X12 (unbounded `.all()` on `GET /campaigns/{id}/evaluations` — scale issue,
  invisible at demo's 3-candidate-per-campaign size), X13/X14/X15/X16 (SharePoint/timeline/
  ON_HOLD edge cases, not on tonight's path), X22 last checkbox (per-field editability past
  rubric approval — not needed for the seeded journey below), X23 last checkbox (mock cards
  unlabelled with zero real campaigns — moot, campaigns already exist).
- **New, found this session** (added to `04-KNOWN-DEFECTS.md` as X36–X38, see that file):
  `lifecycle_service.py` self-commits in three places (violates the routes-commit convention;
  real partial-write risk in `record_manager_review`), `decisions.html`'s silent fallback to
  static shipped-example rows if its live calls fail, dead/unreachable code in
  `app/api/interviews.py:192`. None of these block tonight's path directly except the
  `decisions.html` fallback, which is a P0 rehearsal-verification item (confirm the real run
  loads so the fallback path is never hit live), not a code fix.

## Four-JD decision — updated for this machine (Subhadeep, 2026-09-14)

**Ankush's original decision** (2026-09-12/2026-09-13): Four QatarChemicals-branded JDs exist, 
covering four of five candidate groups. No Process Engineer JD exists, so the four Process 
Engineer CVs were recorded as an unused gap, and the four-JD library was: Maintenance Engineer, 
Instrumentation & Control Engineer, Process Operator, HSE Officer (see his detailed evidence 
below).

**Substitution on this machine** (2026-09-14): The original Instrumentation & Control Engineer 
JD and its three CVs (Ahmed Al-Sayed, Fatima Rashid, Mohammed Al-Khatib) do not exist here and 
could not be obtained in time. **Campaign B is now seeded with the Process Engineer role**, using 
the real `JD_Process_Engineer (1).docx` and three CVs (Daniel Cruz, Fahad Al-Kuwari, Youssef 
Al-Attiyah). Process Engineer JD and all three CVs verified domain-coherent (Aspen HYSYS, HAZOP, 
olefins/petrochemical, Qatar-based). Role presented plainly as "Process Engineer" in all docs, 
not relabelled.

**Role assignment for the demo (this machine):**

- **Campaign A (seeded)**: Maintenance Engineer. Same structure/candidates as Ankush's, but
  new UUIDs and fresh LLM scores from this machine's re-seeding run.
- **Campaign B (seeded)**: **Process Engineer** (substituted). Candidates: Daniel Cruz, 
  Fahad Al-Kuwari, Youssef Al-Attiyah. New UUIDs/scores from this machine.
- **Campaign C (live walkthrough)**: Process Operator — same as Ankush's plan, features the
  scanned-PDF OCR case (Suresh Nair) and a `.pptx` CV.
- **Campaign D (backup, untouched)**: HSE Officer — intentionally left empty to keep the
  candidate pool focused on Campaigns A/B/C.

## P0 — demo-path correctness (execution order)

| # | Task | Status |
|---|---|---|
| P0-1 | This readiness doc | [x] done (this file) |
| P0-2 | Minimal JD library: backend table + 3 routes (list/get/create), seed the 4 JDs into it, a small `web/jd-library.html` page linked from Start Campaign | [x] done — B25 |
| P0-3 | Cost-centre model extension: `business_unit`, `currency`, `fiscal_year`, `role_grade`, `approved_headcount`, `salary_band_min/max` (nullable, additive migration); approvals UI renders a clearly-labelled illustrative BU allocation card | [x] done — B13 |
| P0-4 | `start-campaign.html` client-side search/filter box (additive, default shows everything, lets the live demo narrow to "QChem Demo" cards without hiding anything by default) | [x] done |
| P0-5 | Idempotent demo-seed script, dry-run capable, using real APIs/services: creates Campaigns A/B/C (not D), extracts requirements, approves rubric, uploads the real CVs, runs evaluation, progresses A to manager-review/interview and B to HR-approval/offer stage, all rows named/tagged `[DEMO]`/`QChem Demo —` | [x] done — `scripts/seed_demo.py`; Campaign C built live via browser instead, on purpose |
| P0-6 | Run full pytest suite before/after; targeted tests for any new code (JD library, cost-centre fields) | [x] done — 787 passed, 0 failed, 0 skipped |
| P0-7 | Browser verification: both seeded campaigns resume correctly on Start Campaign, fresh Campaign C walkthrough end to end, refresh/reopen persistence, API restart persistence, no console errors, no fake "sent" claims | [x] done — see evidence log below |
| P0-8 | `docs/plan/DEMO-RUNBOOK-2026-09-14.md` — click-by-click 30-min path + 45-min material + go/no-go | [x] done |
| P0-9 | Update `00-MASTER-BACKLOG.md`, `04-KNOWN-DEFECTS.md` (X36-X39 + this session's fixes), `docs/DECISIONS.md`, `docs/SESSION-STATE.md` | [x] done |
| P0-10 | Commit and push to `origin/consolidated` | [~] in progress — see end of this doc |

P1 (only after P0 complete): visual/copy polish on shown screens beyond what P0 already
touches — not started tonight; nothing on the shown demo path was left visually broken enough
to require it. P2: explicitly not started (post-demo roadmap items, X12 scale fix, X13
tenant-check, etc.) — out of scope per the brief's own priority rule. X32 (CI fix) was originally
filed as P2/out-of-scope but ended up fixed anyway as a cheap two-line change found while
running the full suite; see the evidence log.

## Acceptance evidence log

**JD library (P0-2, B25):** `POST /api/jd-library` × 4 (real JD text extracted from the actual
`.docx` files via `python-docx`), `GET /api/jd-library` confirmed all 4 listed. Browser: opened
`jd-library.html`, saw "4 saved job descriptions", clicked "Use for a new campaign" on Process
Operator, landed on `new-campaign.html?jd_template_id=…`, confirmed `f-title` = "Process
Operator" and `jd-text` = 2,628 chars via `javascript_tool`, no console errors.

**Cost-centre budget envelope (P0-3, B13):** `tests/test_cost_centre_delegation.py` — 2 new
tests, both passed. Browser: built a throwaway campaign/candidate to `PENDING_APPROVAL`, opened
`approvals.html`, selected the real `CC-QCHEM-ICE` cost centre, read
`#cc-envelope-preview.innerHTML` — rendered BU "Technical Services", holder "Imran Qureshi",
fiscal year "FY2026", requisition "Engineer II · headcount 2", band "QAR 180,000 – 220,000",
labelled `ILLUSTRATIVE`. Throwaway campaign deleted after (`DELETE /api/campaigns/{id}` → 204).

**Start Campaign filter (P0-4):** Browser: typed "QChem Demo" into the new filter box, status
text read "2 of 47 campaigns shown", exactly Campaigns A and B's cards remained. Cleared the
filter, all 47 returned. No console errors.

**Demo seed script + data (P0-5):** `scripts/seed_demo.py --dry-run` ran clean (no mutating
calls, printed full plan). Real run: Campaign A created (`97d3d161-…`), 3 CVs uploaded, real
LLM evaluation ran (scores: Abdulrahman Al-Sada 64.53, Priya Menon 43.95, Carlos Mendes 26.58),
progressed to `INTERVIEW_SCHEDULED`. Campaign B created (`ddc1098a-…`), 3 CVs uploaded (Ahmed
Al-Sayed 74.58, Fatima Rashid 66.24, Mohammed Al-Khatib 0.0/flagged — his scanned PDF predates
this session's `rapidocr` install), progressed to `OFFER_SENT` against the new cost centre.
Re-ran the script a second time: both campaigns detected as already-seeded, zero duplicate
API calls made, candidates' already-progressed lifecycle status correctly skipped re-progression
(confirmed via the 404-on-not-yet-entered idempotency check). Campaign C built live through the
browser instead (see below), by design — the brief asks for a genuinely fresh live walkthrough,
not more script output.

**Full test suite (P0-6):** `pytest -q` → **802 passed, 1 warning in 1199.63s** (verified 2026-09-14).
Earlier in the session: 25 failed / 775 passed, caused by the test suite reading the machine's 
real `.env` (`EMAIL_BACKEND=outlook`), which made the new recipient allowlist fire against test 
fixture addresses. Root cause fixed with one autouse fixture in `tests/conftest.py` that forces 
both backends to "simulated" for every test via monkeypatch. The running application outside 
pytest still reads `.env` and still sends for real when configured (verified this session), so 
the fixture only affects test scope.

**Browser verification (P0-7):**
- Start Campaign: both seeded campaigns show their real, distinct current stage ("Interview
  scheduled" / "Offer sent, awaiting response") — required fixing X39 first (see below), since
  both initially showed the stale "Review the shortlist".
- Campaign C, live, end to end: JD library → `new-campaign.html` prefill → role fields saved via
  the real "Save progress" button (confirmed `campaign_id=6df69390-…` appeared in the URL and
  the campaign persisted with the correct fields via `GET /api/campaigns/{id}`) → requirements
  extracted → rubric seeded/submitted/approved → 3 real CVs uploaded (`.pptx`, poorly-formatted
  `.docx`, scanned `.pdf`) with `queue_backend: "inline"` confirmed → real evaluation run
  (Hana Al-Emadi 64.42, Suresh Nair 59.55, third candidate 49.95/blank-name-but-flagged) →
  `leaderboard.html` rendered all three with real evidence, no console errors → `candidate.html`
  for Suresh Nair rendered real rubric-by-rubric evidence including a real quote from his OCR'd
  CV ("Seven years on a live DCS console") — confirms OCR genuinely extracted his scanned PDF's
  text, not a placeholder or hold state.
- Persistence: stopped the API process (which, on inspection, had been running **without**
  `QUEUE_BACKEND=inline` — a real, otherwise-silent gap that would have left any live demo
  upload stuck `QUEUED`), restarted it correctly per the runbook, re-fetched both seeded
  campaigns' `/lifecycle` and the JD library — all four JD templates and both campaigns'
  progressed lifecycle state were unchanged after the restart.
- `pipeline.html`, `offer.html`, `interview.html`: spot-checked for Campaigns A/B, real data,
  no console errors (one stray 404 in the console was traced to this session's own earlier
  wrong-query-param test navigation, not a real page defect — confirmed via
  `read_network_requests` showing all-200s for the actual page load in question).
- Cache gotcha found and fixed mid-verification: a stale service-worker/browser cache served the
  pre-edit `app.js` during testing even after the file changed on disk. Not an SW bug (`sw.js`
  is already network-first per X27's fix) — plain HTTP caching of the versioned script URL.
  Fixed by bumping the existing cache-busting convention: `app.js?v=16→17`,
  `campaign-list.js?v=16→17`, and adding `journey.js?v=2` (previously unversioned). Documented
  in the runbook as a go/no-go checklist item (hard-reload the demo machine's browser once
  before the session).

**X39 fix, found during the above:** `CampaignSteps.resolve()` never accounted for
lifecycle progress past shortlisting — both seeded campaigns showed "Review the shortlist"
despite being at `INTERVIEW_SCHEDULED`/`OFFER_SENT`. Fixed in `web/assets/app.js`; see
`04-KNOWN-DEFECTS.md` X39 for the full before/after and verification.

**Runbook + plan docs (P0-8/9):** `docs/plan/DEMO-RUNBOOK-2026-09-14.md` written with exact IDs,
click path, and go/no-go checklist. `00-MASTER-BACKLOG.md` (new B25 row, B13/B14 updates),
`04-KNOWN-DEFECTS.md` (X26/X32 closed, new X36-X39), `docs/DECISIONS.md` (7 new rows),
`docs/SESSION-STATE.md` all updated this same session.

## Real Outlook email and calendar integration — verification evidence (2026-09-14)

**Direct COM self-test (2026-09-14, 08:38:59 UTC):**
- A real email was sent from `subhadeep.m@protivitiglobal.in` to itself via COM `CDO.Message`.
- Email confirmed present in Outlook Sent Items folder at 08:38:59.
- A real calendar block was created (30-minute event, Busy status, 15-minute reminder) via COM
  `Outlook.Application.GetNamespace('MAPI').GetDefaultFolder`.
- Calendar event confirmed present in default calendar, then deleted as test cleanup.
- No Outlook security prompt appeared during either operation.

**Through the application API (2026-09-14):**
- `POST /api/campaigns/{id}/comms/send` returned `HTTP 200`, response JSON included
  `simulated: false` and `send_detail: "Sent via local Outlook to subhadeep.m@protivitiglobal.in."`
- Through the calendar adapter endpoint: `OutlookCalendarAdapter.send_invite(...)` returned
  `sent=True, simulated=False`, detail: `"Invite sent via local Outlook to 1 attendee(s)."`
  Test invite deleted afterward to avoid calendar clutter.

**Allowlist guard verified (2026-09-14):**
- Attempt to send to non-approved address `abdulrahman.alsada@example.com` (a candidate's
  CV-extracted address from seeded data) returned `HTTP 422 Unprocessable Entity` with detail:
  `"'abdulrahman.alsada@example.com' is not an approved recipient for a real Outlook send."`
  Response produced by `mail_guard.ensure_approved_mail_recipients()` before mail adapter
  invocation. Allowlist is working.

**Sender resolution (2026-09-14):**
- `resolve_sender_address()` discovered the first signed-in account on this machine
  (subhadeep.m@protivitiglobal.in) and cached it per process lifetime.
- `SendUsingAccount` property (new Outlook, version 16.0.0.20326) worked directly; dispid
  64209 fallback was implemented but not exercised.

## Send-mode disclosure — truthfulness verification (2026-09-14)

**Found during verification:** multiple pages (`comms.html`, `interview.html`, `offer.html`) 
displayed hardcoded "SIMULATED — INTEGRATION PENDING" badges that became false once real Outlook 
sending was enabled. A presenter could read "simulated", click a button, and send a real email 
without knowing. **Fixed (X42):** badges now fetch the actual send mode from `GET /api/config/send-modes` 
endpoint, which returns only `{"email_backend": ..., "calendar_backend": ...}` (no secrets/credentials). 
Badge text reflects reality: `"SENDS FOR REAL — OUTLOOK LIVE"` when backends are outlook; 
`"RECORDED ONLY"` when simulated. Failure case deliberately shows `"SEND MODE UNKNOWN"` rather 
than defaulting to claiming "simulated." Also fixed script-load order on `comms.html` so the 
badge helper is defined when called.

**Verified 2026-09-14:**
- `GET /api/config/send-modes` returns only backend names, never credentials or sender address 
  (`test_send_modes_exposes_nothing_else` confirms)
- Badge renders `"SENDS FOR REAL — OUTLOOK LIVE"` with Outlook backend; `"RECORDED ONLY"` with 
  simulated backend
- Hard-reload required to defeat browser cache (see runbook §2)

## Real Outlook integration — known limitations (2026-09-14)

- **Dispid fallback untested against production Outlook.** The `_oleobj_.Invoke(*(64209, 0, 8, 0,
  account))` path is implemented but was not executed against a real Outlook build (property
  path succeeded first). Fallback is covered only by mocked unit tests.
- **Single-account assumption.** `resolve_sender_address()` picks the first account in the
  Outlook profile. On a machine with multiple signed-in mailboxes, may not be the intended
  sender. Explicit `OUTLOOK_SENDER_ADDRESS` env var is the escape hatch.
- **Sender cache is process-lifetime.** Switching Outlook profile mid-run requires app restart.
- **Attachments and BCC not supported.** Mail adapter accepts only to/cc/subject/body and
  calendar adapter accepts only event details.
- **Send-as (delegate) not supported.** Sending as a mailbox you do not own (e.g. as
  daipayan.r@ from Subhadeep's machine) requires the account to be in this machine's Outlook
  profile, which it is not. Would require delegate/Send-As permission or running on that
  person's machine. Allowlist is the first layer; second layer would be Outlook-level access
  control.
