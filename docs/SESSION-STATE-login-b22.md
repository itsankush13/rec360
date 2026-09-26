---
# SESSION-STATE (login gate, B22 phase 1)
updated: 2026-09-13T00:00:00Z
session_token_cost_estimate: 55000

## why a separate file
docs/SESSION-STATE.md has Ankush's uncommitted B01/B11 notes in the working
tree right now. Overwriting it would destroy unpushed work, so this task's
state lives here until it's safe to merge the two.

## completed_this_session
- Real email+password login for ankush.saxena@protivitiglobal.in and
  subhadeep.m@protivitiglobal.in. New: app/core/session_auth.py (bcrypt hash
  + stateless HMAC session token), app/services/auth_service.py (the
  HR <-> Hiring manager flip: whoever logs in is "HR", the other is
  "Hiring manager" for display only, NOT a UserRole change), app/api/auth.py
  (`POST /api/auth/login`, `GET /api/auth/me`), migration
  4e9b2765d18c (users.password_hash, nullable).
- app/api/interviews.py: `_approved_attendees` is now flip-aware — the
  logged-in actor's counterpart (the other of the two named accounts) is
  accepted as co-manager, on top of the fixed DEMO_CO_MANAGERS list. Added
  daipayan.r@protivitiglobal.in to DEMO_RECIPIENTS (chiranjib.sarma and
  preetam.c were already there).
- tests/test_auth_api.py: 6 passing tests (hash round-trip, tampered-token
  rejection, login failure with no password set, the co-manager flip).

## open_tasks (not started)
- web/login.html does not exist yet. web/assets/app.js has no portal gate —
  every page is still reachable without logging in.
- No scripts/set_password.py yet — nobody can actually set a password for
  the two accounts, so /api/auth/login cannot succeed against real data yet.
- .env has CALENDAR_BACKEND=outlook locally (not in .env.example). This
  makes tests/test_interviews_api.py fail 10/13 right now — pydantic-settings
  reads the real .env even under pytest, so calendar_backend is "outlook"
  instead of the "simulated" the tests assume. CONFIRMED PRE-EXISTING: not
  caused by this session's edits (verified by stashing this session's
  tracked-file changes and re-running — same failures). Needs either an
  autouse fixture that pins calendar_backend to "simulated" in tests/conftest.py,
  or .env should not carry that flag for a local run of the full suite.
- Real Outlook sending (_require_demo_sender, calendar_backend=="outlook")
  still only works for subhadeep.m as sender — deliberately NOT flipped: one
  real mailbox is configured, ankush.saxena has no Outlook OAuth credential
  registered. Flagged to the user as a known limitation, not silently solved.
- docs/DECISIONS.md / 00-MASTER-BACKLOG.md (B22 line) not yet updated.

## current_module_confidence
- app/core/session_auth.py: HIGH (tested)
- app/services/auth_service.py: HIGH (tested)
- app/api/auth.py: MEDIUM (no test hits the endpoints through a set password yet)
- app/api/interviews.py flip logic: HIGH (tested end to end)
- web/ (login page, gate): NOT STARTED

## next_session_start_with
"Write scripts/set_password.py (getpass, upserts by email), then
web/login.html + a portal gate at the top of web/assets/app.js, then update
initMe() in app.js to read the real session instead of the old free-text
localStorage prompt from before this task."

## context_to_inject_on_resume
- Read: docs/SESSION-STATE-login-b22.md (this file)
- Read: app/services/auth_service.py
- Read: app/api/auth.py
- Read: web/assets/app.js (the initMe() function near the top, and the
  campaign-stage-switcher IIFE below it — that second one is Ankush's,
  leave it alone)
- Do NOT read: sibling prototypes (app/, app-v2/, Recruitment-360-Delivery/),
  full plan backlog, CV/JD sample files, venv
---
