# Ankush handoff — 2026-09-12 flaky audit-ordering root cause and fix

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
Restored the TWO-PERSON-OWNERSHIP checkpoint: confirmed acting developer explicitly (asked;
answer was Ankush), read `AGENT-START-HERE.md`, `08-TWO-PERSON-DELIVERY.md`, `docs/SESSION-STATE.md`
and the prior `2026-09-12-x3-x4-x6-and-flaky-tests.md` handoff. `git fetch origin` showed no new
commits on `origin/azure-provider` or `origin/consolidated`; `consolidated` was clean, 6 commits
ahead of `origin/consolidated` (unpushed). All five prior local `ankush/*` branches confirmed still
present and untouched.

Picked up the next task named in `docs/SESSION-STATE.md`'s `next_session_start_with`: root-cause
the flaky `test_approvals_api` / `test_messages_api` / `test_interviews_api` "oldest/newest first"
ordering failures. New local branch `ankush/flaky-audit-ordering` (`a4b2a50`) off `consolidated`,
**not pushed, no PR** — same local-only mode as the other five branches.

## Root cause
Every audit-ordered read (`disposition_service.audit_trail()`, `interviews.py`'s `_events()`) sorts
by `AuditEvent.created_at.desc()` alone. `created_at`'s default is `datetime.now(timezone.utc)`,
and two rows written back to back in the same request or test can land on the identical instant —
the wall clock's resolution isn't always finer than two sequential Python statements. When that
tie happens, SQL gives no guarantee which row comes first, and `AuditEvent.id` can't break the tie
either: it's a random UUID (`uuid.uuid4()`, `app/db/models.py:22`), not an insertion-ordered key, so
adding it as a secondary sort key would make the order deterministic but not necessarily *correct*.

Confirmed by writing `tests/test_disposition_service.py`: freezing the clock (subclassing
`datetime` so `.now()` always returns the same instant) across two `record_audit()` calls
reproduced the exact tie (`first.created_at == second.created_at`) before the fix, red first as
the project convention asks.

## Fix
`app/services/disposition_service.py`: `record_audit()` (the sole place `AuditEvent` rows are
constructed — verified with `grep AuditEvent(` across `app/`) now passes `created_at=_now()`
explicitly instead of leaving it to the column default. `_now()` (previously dead code — defined,
never called) now keeps a module-level `_last_audit_timestamp` and bumps by one microsecond
whenever the wall clock hasn't advanced past it, so every audit row this process ever writes is
strictly after the last one. This fixes the read side (messages, interviews, approvals,
dispositions) in one place, without touching the four call sites separately and without a schema
change — `AuditEvent.id` stays a UUID; no migration needed.

Portability note: this was deliberately done at the application level rather than by ordering on
SQLite's implicit `rowid`, because `DATABASE_URL` (`app/db/session.py:18`) is already
environment-configurable and the intended target is Azure — an ordering fix that only works on
SQLite would be a second, quieter version of this same bug later.

## Verification
- New regression test `tests/test_disposition_service.py::test_audit_events_written_in_the_same_clock_tick_still_order_correctly`: red before the fix (reproduced the exact tie), green after.
- `tests/test_interviews_api.py tests/test_messages_api.py tests/test_approvals_api.py` run **8 times consecutively**: 30 passed each run, no flakes (previously 1-2 of these failed per session, a different assertion each time).
- Full suite run once: **542 passed, 6 skipped, 5 failed** — the 5 failures are the pre-existing
  `test_pptx_intake.py` `ModuleNotFoundError: No module named 'pptx'` (unrelated, documented last
  session). Last session's run on `ankush/x3-x4-x6-cheap-fixes` was 539 passed/7 failed on the same
  suite; the delta is exactly these two tests no longer flaking (539 + 3 = 542, matching 3 more
  passing test functions across the two files' full runs).

## Requested central-doc deltas (I don't edit these directly — Subhadeep-owned)
For `docs/plan/04-KNOWN-DEFECTS.md`: this was never given a stable X-number (see the prior
handoff's "new X-item suggestion"). Suggest recording it as a new item, e.g.:

> **X19 — Flaky audit-ordering assertions on same-tick writes · FIXED**
> `record_audit()` now forces each audit row strictly after the last one this process wrote
> (`app/services/disposition_service.py`), instead of relying on the raw wall clock with no
> tiebreaker. Fixes `test_approvals_api`, `test_messages_api`, `test_interviews_api`'s
> intermittent "oldest/newest first" failures. Verified: 8/8 clean runs of the three files; full
> suite 542 passed / 5 failed (pptx only), up from 539/7. On branch `ankush/flaky-audit-ordering`
> (`a4b2a50`), unmerged.
> - [x] Root-caused
> - [x] Fixed
> - [x] Regression test added
> - [x] Re-run repeatedly to confirm no more flakes

For `docs/SESSION-STATE.md` (Subhadeep-owned; noting here per standing rule, not edited directly —
the user did not say "save the state" this turn): six local branches now await the same merge/PR
decision: the five from last session plus `ankush/flaky-audit-ordering`.

## Not done yet (explicitly deferred)
- No decision yet on merging/pushing any of the six local branches, or opening PRs.
- X13/X15/X16 (SharePoint tail-match, ON_HOLD resume, UNC verification) and X11's remaining
  off-ramp outcome chart — continuing to these next in this same session, per
  `docs/SESSION-STATE.md`'s `next_session_start_with` order.

## Next-session start pointer
Read `AGENT-START-HERE.md` → `docs/plan/08-TWO-PERSON-DELIVERY.md` → `docs/SESSION-STATE.md` →
this file. If this session did not reach X13/X15/X16/X11, continue there in priority order; ask
the user whether to merge/PR the six local `ankush/*` branches before starting further new work.
