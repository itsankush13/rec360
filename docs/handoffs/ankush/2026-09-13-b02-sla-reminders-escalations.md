# Ankush handoff — 2026-09-13 B02 SLA reminders and escalations

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).
B02's allocation there names Ankush's deliverable as exactly this: "Stored states, valid
transitions, SLA/reminder mechanics and tests." `timeline.html` display is explicitly
Subhadeep's; not touched here except as noted below.

## What this session did
Started from the backlog/defect reconciliation already recorded in
`2026-09-13-backlog-reconciliation-correction.md` and the user's own restated list of what's
left. Picked the one item on it that is genuinely unbuilt, backend-owned and unblocked: **B02 —
"Add SLA reminders and escalations."** Before writing anything, checked the user's file-ownership
intent against `08-TWO-PERSON-DELIVERY.md` twice, since the request was to build "frontend and
backend together":

1. Confirmed with the user that `web/timeline.html` (the amber-badge/display half) stays with
   Subhadeep; this session built backend only and writes this contract note instead of the screen.
2. Adding `AuditAction.SLA_REMINDER_SENT`/`SLA_ESCALATED` requires two label lines in
   `web/audit.html` to keep `test_audit_page_maps_every_action_to_plain_english` green (that test
   iterates every `AuditAction` and asserts a quoted label exists in the file). A prior B15 session
   deliberately avoided this exact situation by reusing `STATUS_CHANGED` instead of adding a new
   action. Surfaced the precedent to the user explicitly; the user chose to keep two new, correctly
   labelled actions rather than overload an existing one for events that are not status changes.
   **Two lines added to `web/audit.html`'s existing `ACTION_WORDS` map, nothing else in that file
   touched.**

## Design, from `02-LIFECYCLE-MODEL.md`'s SLA section
"A target duration per stage, a due date, reminders before and escalation after, clocks stopping
on hold, every reminder itself an audit event." No client-specified durations exist anywhere
(checked `docs/DECISIONS.md`, `04-KNOWN-DEFECTS.md` — nothing). Built with placeholder defaults,
sized to the stage, clearly marked as such in code and here for whoever settles the real policy.

- **`app/core/lifecycle.SLA_HOURS`**: `dict[LifecycleStatus, tuple[target_hours, reminder_lead_hours]]`,
  one entry per stage where a clock should run (every stage in `ALLOWED` except the off-ramps/holds
  already in `CLOCK_STOPPED`). `sla_target_hours()`/`sla_reminder_lead_hours()` read it.
- **`lifecycle_service._write()`** now sets `CandidateLifecycle.due_at` (the column already
  existed, unused, since the original lifecycle build) from `entered_at + target_hours` on every
  new row, `None` when the target status has no SLA entry — which is every `CLOCK_STOPPED` member
  by construction, so a hold or a terminal state clears the clock automatically with no special
  case in `_write()` itself.
- **`app/services/sla_service.py`** (new):
  - `sla_status(record, now=...)` → `'ON_TRACK'` / `'DUE_SOON'` / `'OVERDUE'`, derived from the
    stored `due_at` at read time — never a stored column of its own, so a screen computing it the
    same way can't disagree with the audit trail about whether a stage is late.
  - `evaluate(db, campaign_id=None, now=...)` → walks every `is_current` row with a `due_at`,
    writes `AuditAction.SLA_REMINDER_SENT` once the reminder lead window opens and
    `AuditAction.SLA_ESCALATED` once overdue, each **at most once per lifecycle row** (checked
    against the audit trail itself — `entity_type="candidate_lifecycle"`, `entity_id=record.id` —
    rather than a new mutable column, so repeated calls are free). Commits; returns
    `{"reminders_sent": n, "escalations_sent": n}`.
  - No scheduler exists in this codebase to call `evaluate()` on a clock (RQ cannot fork on
    Windows; the deferred queue backend is for CV processing, not a timer). Exposed instead as
    `POST /api/lifecycle/sla/evaluate?campaign_id=` (`app/api/lifecycle.py`, new `sla_router`,
    registered in `app/main.py`) — callable by hand, by a script, or by a future scheduler once one
    exists. Deliberately idempotent so "callable any number of times" is actually true.
- **`LifecycleOut`** (`app/api/lifecycle.py`) gained `sla_status`, alongside the existing `due_at`
  it already returned but never populated with anything. `GET .../lifecycle/{id}`,
  `GET .../lifecycle` and the timeline candidate picker all pick this up with no other change.
- **`AuditAction.SLA_REMINDER_SENT` / `SLA_ESCALATED`** (`app/db/models.py`) — written with
  `actor="system"`, never a person.
- 7 new tests, `tests/test_sla.py`: due date set on entry, cleared on hold, `sla_status`'s three
  bands against a real stored `due_at`, `evaluate()` sends exactly one reminder and one escalation
  and never repeats either, a held candidate is skipped, the endpoint is campaign-scoped.

## Contract for Subhadeep — `web/timeline.html`
- `GET /api/campaigns/{id}/lifecycle/{candidate_id}` and `GET /api/campaigns/{id}/lifecycle` now
  return `sla_status: 'ON_TRACK' | 'DUE_SOON' | 'OVERDUE'` alongside the `due_at` the screen
  already reads. `02-LIFECYCLE-MODEL.md`'s demo note — "show an amber badge on any stage past its
  due time" — maps directly: amber (or your choice) for `DUE_SOON`, a stronger treatment for
  `OVERDUE`, nothing for `ON_TRACK`/`null`.
- `POST /api/lifecycle/sla/evaluate?campaign_id=<id>` (or omit `campaign_id` for every campaign)
  writes any newly-due reminder/escalation audit events and returns
  `{"reminders_sent": n, "escalations_sent": n}`. Nothing currently calls this automatically —
  `sla_status` above is always freshly derived regardless of whether `evaluate()` has run recently,
  so the badge is correct either way; `evaluate()` only controls when the *audit trail* records the
  reminder/escalation, not what the badge shows.
- Two new `web/audit.html` labels already added (`SLA_REMINDER_SENT`, `SLA_ESCALATED`) so the audit
  screen doesn't need anything further for these to render correctly.

## Verification
- `tests/test_sla.py`: 7 passed (new).
- `tests/test_sla.py tests/test_lifecycle.py tests/test_audit_trail.py tests/test_frontend_integration.py tests/test_whatif_proposals.py`:
  110 passed (regression check on the state machine, the enforced audit-label test, and the
  cross-file `people` fixture import).
- Full suite once: **656 passed, 6 skipped, 0 failed** (91s). No new migration — `due_at` already
  existed in `alembic/versions/d7b3e81c4a05_users_and_lifecycle.py`; nothing else changed shape.

## Requested central-doc delta (I don't edit these directly — Subhadeep-owned)
For `docs/plan/00-MASTER-BACKLOG.md`, `B02`:
- `[~]` Add SLA reminders and escalations — stored `due_at` per stage
  (`app/core/lifecycle.SLA_HOURS`, placeholder durations), `sla_status` derivation and
  `sla_service.evaluate()` writing idempotent `SLA_REMINDER_SENT`/`SLA_ESCALATED` audit events.
  Backend and tests done; no scheduler triggers `evaluate()` automatically yet, and the
  `timeline.html` amber badge (contract above) is not wired up.

## Not done yet (explicitly deferred)
- No automatic trigger for `evaluate()` — nothing in this environment can run a recurring job
  (RQ needs fork, unavailable on Windows). A cron-style caller is a small follow-up once one exists.
- `timeline.html` badge itself — Subhadeep's file, contract above.
- SLA duration policy is a placeholder, not a client-approved number; flag if that matters before
  a demo that shows real overdue timestamps.

## Next-session start pointer
Read `AGENT-START-HERE.md` → `docs/plan/08-TWO-PERSON-DELIVERY.md` → `docs/SESSION-STATE.md` →
this file. Backend queue: pick from the still-open items in the user's own restated list
(B13, B21, or the small unblocked X1/X2), or wire a scheduler to call
`POST /api/lifecycle/sla/evaluate` automatically once that infrastructure exists.
