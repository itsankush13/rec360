# Ankush handoff — 2026-09-12 X6 correction + B11 calendar-invite adapter

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).
Confirmed explicitly from the task assignment, not inferred from git config/username.

## Checkpoint restored
Read `AGENT-START-HERE.md`, `08-TWO-PERSON-DELIVERY.md`, `docs/SESSION-STATE.md`. `consolidated`
clean at `32c5405`, `git fetch origin` showed no new commits on `origin/azure-provider` (still
41 commits ahead of `origin/consolidated`, unpushed — local-only mode unchanged). Picked the two
items `SESSION-STATE.md`'s `next_session_start_with` offered without a decision yet: X6, then B11.

## X6 — correction to the prior handoff, then actually fixed

The prior handoff (`2026-09-12-x3-x4-x6-and-flaky-tests.md`) removed the emoji from
`manage_tenants.py`/`auth.py` and deliberately left the `₹` sign and box-drawing `─` divider in
`manage_tenants.py`, reasoning they "aren't reported as crashing." **That's wrong — I reproduced
the crash this session:** `manage_tenants.py` is a standalone CLI, never imported through
`app/main.py`, so `configure_utf8_output()` never runs for it. Importing it under a forced
cp1252 stdout (`PYTHONIOENCODING=cp1252`) raised `UnicodeEncodeError` on the `₹`/`─` prints
before my fix, exactly as X6 describes. `app/auth.py`'s own prints, separately, turned out to
already be plain ASCII — no non-ASCII character above `\x7f` anywhere in that file — so that half
of X6 really was already resolved, just not for the reason the prior note gave.

Fix: added the same `configure_utf8_output(sys.stdout)` / `(sys.stderr)` call
`app/main.py` already uses, at the top of `app/core/manage_tenants.py`. This fixes the crash
regardless of which characters the script prints, rather than chasing individual glyphs.

- `app/core/manage_tenants.py` — added the import and the two-line reconfigure loop.
- `tests/test_console_encoding.py` — one new test,
  `test_manage_tenants_configures_console_encoding_at_import`, asserting the call is present
  (mirrors the existing `test_main_configures_console_encoding_at_import`).
- Verified: forced-cp1252 import no longer raises; `tests/test_console_encoding.py` 9 passed.

## B11 — interview calendar invite, same shape as B10/B12

`web/interview.html` (Subhadeep's) already records schedule/reschedule/feedback with real
lifecycle and audit rows; no calendar invite was ever sent — "The calendar invite is recorded,
not sent" was hardcoded into the schedule summary. Built the first, backend-only checklist line:

- `app/core/calendar_adapter.py` — new. Same interface shape as B10's `outlook_adapter.py`:
  `CalendarAdapter` interface, `SimulatedCalendarAdapter` (default, records intent, sends
  nothing), `OutlookCalendarAdapter` (COM automation via `win32com.client`, dispatch function
  injected so tests never touch real COM — creates an `olAppointmentItem`, sets
  `MeetingStatus = olMeeting`, adds required attendees — panel + candidate, the ones a real
  invite blocks the calendar of — and optional attendees, then `.Send()`).
- `app/core/config.py` — new `calendar_backend: str = "simulated"` setting. Deliberately a
  **separate** flag from B10's `email_backend`, not reused: a calendar invite is a different COM
  item and a site may want one live before the other. Same opt-in shape as `email_backend` and
  `QUEUE_BACKEND` — only an explicit `"outlook"` value attempts a real invite.
- `app/api/interviews.py` — `schedule_interview` and `reschedule_interview` now call
  `get_calendar_adapter().send_invite(...)` with the panel (resolved to emails via a new
  `_resolve_panel_emails`) and the candidate's email as required attendees. Never raises — a
  candidate with no email on file just means one fewer required attendee, not a failed schedule.
  The audit `after` detail and the `InterviewOut` response/read-back schema both gained additive
  `invite_simulated` / `invite_detail` fields (same pattern as B12's `offer.simulated`/
  `send_detail`), so a future UI can show the honest transmission state instead of the old
  hardcoded sentence.
- `requirements.txt` — unchanged; `pywin32` was already added for B10.
- Tests: `tests/test_calendar_adapter.py` (6 new — simulated adapter, Outlook adapter against a
  fake COM double for required/optional attendees and for the COM-failure path, adapter-selection
  logic including the fallback-when-unconstructable path — mirrors `test_outlook_adapter.py`
  exactly) and one new test in `tests/test_interviews_api.py`
  (`test_scheduling_records_a_simulated_calendar_invite_by_default`, checked both on the schedule
  response and the read-back list). `tests/test_interviews_api.py` went 9 → 10 passed, no
  existing assertion changed.
- Verified: `test_interviews_api.py` + `test_calendar_adapter.py` + `test_outlook_adapter.py` +
  `test_console_encoding.py` together, 31 passed. Full suite once: **587 passed, 6 skipped, 5
  failed** — the same pre-existing `test_pptx_intake.py` `ModuleNotFoundError: No module named
  'pptx'` failures as every prior session's baseline (`requirements-ocr.txt`/two-step install
  gap — did not `pip install`, per `CLAUDE.md`). No regression.

## Explicitly NOT built / not verified

- **Never run against a real Outlook mailbox/calendar.** Every test uses a fake COM double.
  `calendar_backend` defaults to `"simulated"`, so nothing changes for anyone until someone
  deliberately sets it to `"outlook"` on a machine with a signed-in Outlook profile and confirms
  an invite actually blocks a real calendar. Treat the real-COM path as unverified, exactly like
  B10's mail adapter still is.
- "Track invite status: sent, accepted, declined" — only the *sent/simulated* half is built.
  Accepted/declined needs reading a real mailbox for RSVP replies — same reply-ingestion blocker
  already open on B10, needs the same real-mailbox access this session doesn't have.
- "Do not require a Teams link initially" — untouched; `location_or_link` already free-text, no
  video-link generation was in scope here.
- "Link the invite to the recruitment/application ID" — the invite subject uses the candidate's
  name and round number, not a recruitment/application ID, because B20 (identifier model) has
  nothing built yet — same blocker B10's subject-line line already names.
- "Capture interview feedback from the reply" — `record_feedback` already exists as a manual
  workflow entry (pre-existing, not this session); capturing it *from a reply* has the same
  real-mailbox blocker as above.
- `web/interview.html` — Subhadeep's file — doesn't surface `invite_simulated`/`invite_detail`
  yet; the API contract is ready for it, same shape as B12's `offer.html` gap already on record.

## Requested central-doc deltas (I don't edit these directly — Subhadeep-owned)

For `docs/plan/04-KNOWN-DEFECTS.md`:
- X6: check `- [ ] Cleaned` → done this session, on `consolidated` at `5177174`. Correct the
  prior handoff's assumption that the `₹`/`─` characters "aren't reported as crashing" — they
  were, reproducibly, and now the fix covers the whole class rather than the specific glyphs.

For `docs/plan/00-MASTER-BACKLOG.md` B11 delta:
- [~] On hiring-manager approval, create a calendar invite through `pywin32` — adapter built and
      unit-tested against a fake COM double; **not exercised against a real mailbox.** Off by
      default (`calendar_backend=simulated`); opt-in via `calendar_backend=outlook`.
- [~] Block the interviewer and candidate calendars — panel + candidate are required attendees on
      the invite; unverified against a real calendar (see above).
- [ ] Do not require a Teams link initially — unchanged, already true, not touched this session.
- [~] Track invite status: sent, accepted, declined — sent/simulated half built and audited;
      accepted/declined blocked on real-mailbox reply ingestion (same as B10).
- [ ] Link the invite to the recruitment/application ID — blocked on `B20`, nothing built.
- [ ] Capture interview feedback from the reply or the workflow — the workflow half pre-exists;
      the reply half has the same real-mailbox blocker as B10.

## Next

No instruction on what's next after this. Candidates: (a) B10's reply-parsing/stage-update
(needs a real mailbox — same blocker named here and in the B10 handoff), (b) B12's remaining
`web/offer.html` display gap (Subhadeep's), (c) push `consolidated` / open the bootstrap PR into
`azure-provider` (Subhadeep-coordinated, needs explicit authorization), (d) something else.
