# Ankush handoff — 2026-09-12 B15 candidate reuse (first increment)

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
Restored the TWO-PERSON-OWNERSHIP checkpoint: read `AGENT-START-HERE.md`, `08-TWO-PERSON-DELIVERY.md`,
`docs/SESSION-STATE.md`. Confirmed `consolidated` clean at `1cf5cc0`, 44 commits ahead of
`origin/consolidated` (unpushed, local-only mode still in force), `git fetch origin` showed no
new commits on `origin/azure-provider`.

Every item this session's `next_session_start_with` named as open was already built and merged
(X1-X4, X6, X12, X13-partial, X15, X16, flaky-ordering; B03/B06/B07/B10/B11/B12 proxy halves;
B14 draft API) — verified in code, not just from the prior handoffs' say-so. Asked the user which
fresh B-item to start; picked **B15 — historical candidate reuse**, which had zero prior work
(verified: no `waitlist`/`backup`/`rank` column or concept anywhere in `app/` or `alembic/`).

## Scope taken — and scope explicitly deferred
B15's four backlog lines: preserve the ranking, keep backup/waitlisted candidates, surface the
next ranked candidate on decline/no-show, retain exclusion flags during future searches.

Explored the actual data model before designing anything (`Candidate.campaign_id` is a hard FK —
one row per person per campaign; `CandidateLifecycle.enter()` only admits `SHORTLIST`/`INTERVIEW`
dispositions; ranking was 100% query-time, never stored). The fourth line — **retain exclusion
flags during future searches** — needs a cross-campaign candidate identity that does not exist
today (a person can't currently be recognised across two campaigns at all). Building that is an
unresolved architecture question overlapping `B20`'s "Candidate ID: persistent candidate profile,
across campaigns" line, not a small slice, and not something this session invented an answer to.
**Left open, flagged here rather than silently dropped or silently designed.** The other three
lines are built this session, scoped to one campaign at a time.

## What was built
- **`Disposition.WAITLIST`** (`app/db/models.py`) — a screening-time decision, same tier as
  SHORTLIST/REJECT/HOLD, recorded through the existing `POST /candidates/{id}/disposition` and
  `disposition_service.set_disposition()` with no code changes needed there (both already handle
  any `Disposition` value generically). Word mapping added to
  `disposition_service.DISPOSITION_WORDS`: "kept as a backup candidate".
- **`LifecycleStatus.WAITLISTED`** (`app/db/models.py`, `app/core/lifecycle.py`) — entered
  directly (mirrors how `SHORTLISTED` is only ever entered, never arrived at from another state),
  promotes to `SHORTLISTED` or closes to `NOT_PROCEEDING`/`WITHDRAWN`. Added to `STAGE_ORDER`/
  `OFF_RAMP` (funnel), `CLOCK_STOPPED` (no SLA while parked). **Did not** add a new `AuditAction`
  for it — a new one would need a matching label in `web/audit.html` per the enforced
  `test_audit_page_maps_every_action_to_plain_english`, and that file is Subhadeep's; the generic
  `STATUS_CHANGED` action `_write()` already falls back to covers it correctly.
- **`CandidateLifecycle.campaign_rank`** (nullable `Integer`, migration
  `alembic/versions/2a13836a93f4_candidate_lifecycle_campaign_rank.py`) — the leaderboard rank a
  candidate held at the moment they entered the lifecycle, stored once and carried forward through
  every later transition (`lifecycle_service._write()`), never recomputed. This is what "preserve
  the campaign ranking" actually means once you notice a re-evaluation can move scores around
  after the decision was made — CLAUDE.md's stored-not-derived rule, applied to ranking as well as
  status. Applies to `SHORTLISTED` entries too, not just waitlist ones (`enter()` now also snapshots
  rank).
- **`app/services/evaluation_service.ranked_evaluations()`/`rank_of()`** — extracted the
  leaderboard's ordering query (`app/api/evaluations.py`) into one shared function so the rank
  snapshot and the leaderboard display can never drift apart. `leaderboard()` now calls it instead
  of duplicating the query; same SQL, same X12 `.limit()` behaviour, verified by the existing
  leaderboard tests passing unchanged.
- **`lifecycle_service.enter_waitlist()`, `waitlisted_candidates()`, `next_backup_candidate()`** —
  the waitlist-entry gate (mirrors `enter()`'s SHORTLIST/INTERVIEW gate, but for `WAITLIST`), the
  ordered backup list, and "who's next" lookup (best rank first, `None` rank sorts last).
- **`GET /api/campaigns/{id}/lifecycle/backups`** and **`POST /api/campaigns/{id}/lifecycle/{candidate_id}/waitlist`**
  (`app/api/lifecycle.py`) — list current backups; enter one. `LifecycleOut` gained
  `campaign_rank` and `next_backup_candidate_id`/`_name`/`_rank` (populated whenever the candidate's
  status is `OFFER_DECLINED` or `WITHDRAWN` — the two states that literally are "declined" and
  "does not join" in the existing state machine).
- **`OfferResponseOut`** (`app/api/offers.py`) gained the same three `next_backup_*` fields,
  populated on a decline, so the recruiter sees who to fall back to in the same response as the
  decline itself, not a second lookup.
- 9 new tests, `tests/test_candidate_reuse.py`: waitlist-entry gate, rank persisted at both
  shortlist and waitlist entry, backups list ordering, decline surfaces the backup, accept does
  not, "does not join" (`OFFER_ACCEPTED` → `WITHDRAWN`) also surfaces it, no backup when nobody's
  waitlisted, promotion carries the stored rank forward and clears the backups list.
- Updated one pre-existing test, `tests/test_metrics_api.py::test_funnel_wraps_lifecycle_service_funnel`,
  which hard-codes the full `STAGE_ORDER` list — added `WAITLISTED` in its position (after
  `ON_HOLD`, before `OFFER_DECLINED`). This is the only existing test the new state required
  touching; found by running the full suite, not guessed at.

## Verification
- `tests/test_candidate_reuse.py`: 9 passed (new).
- `tests/test_lifecycle.py tests/test_offers_api.py tests/test_evaluations.py tests/test_handoff_api.py`:
  157 passed (regression check on everything touching the state machine, offers and leaderboard).
- `tests/test_audit_trail.py tests/test_decisions.py tests/test_disposition_service.py`: 67 passed
  (regression check on the new `Disposition`/`DISPOSITION_WORDS` value and the
  every-`AuditAction`-has-a-label enforcement — confirmed unaffected since no new `AuditAction` was
  added).
- Full suite once: **596 passed, 6 skipped, 5 failed** — the 5 are the pre-existing
  `test_pptx_intake.py` `ModuleNotFoundError: No module named 'pptx'` (documented baseline, did not
  `pip install` per `CLAUDE.md`). No other regression.
- `alembic upgrade head` run against the local dev database: applied `2a13836a93f4` cleanly on top
  of `7a12e4f9c3d6`, single head confirmed both before and after
  (`alembic heads` → one line).

## Requested central-doc deltas (I don't edit these directly — Subhadeep-owned)
For `docs/plan/00-MASTER-BACKLOG.md`, `B15`:
- `[~]` Preserve the campaign ranking — stored at entry (`CandidateLifecycle.campaign_rank`),
  carried through every later transition. Done for single-campaign ranking; not evaluated for any
  cross-campaign meaning since candidates don't have one.
- `[~]` Keep backup and waitlisted candidates — `Disposition.WAITLIST` +
  `LifecycleStatus.WAITLISTED`, `GET .../lifecycle/backups`. Backend only; no screen yet.
- `[~]` Surface the next ranked candidate on decline/no-show — `OfferResponseOut` and
  `LifecycleOut` both carry `next_backup_candidate_*` on the relevant transitions. Backend only.
- `[ ]` Retain exclusion flags during future searches — **not started, and not a small slice.**
  Needs a cross-campaign candidate identity decision (ties into `B20`). Flagged, not designed.

## Not done yet (explicitly deferred)
- Cross-campaign candidate identity / exclusion-flag retention (B15's fourth line) — architecture
  question, needs a decision before building, not attempted.
- No UI: `web/new-campaign.html`/`leaderboard`/`compare` style surfacing of "waitlist this
  candidate" or a backups panel — Subhadeep's file, contract is the four new/changed response
  shapes above (`campaign_rank`, `next_backup_candidate_id/_name/_rank` on `LifecycleOut` and
  `OfferResponseOut`; `BackupCandidateOut` list from the new `/backups` endpoint).
- No decision yet on merging/pushing this or any other local work, or opening PRs.

## Next-session start pointer
Read `AGENT-START-HERE.md` → `docs/plan/08-TWO-PERSON-DELIVERY.md` → `docs/SESSION-STATE.md` →
this file. Backend `next_session_start_with` queue is empty again; ask the user whether to (a)
scope the B15 cross-campaign identity question (ties into B20), (b) pick a different B-item, or
(c) merge/push/PR the accumulated local work.
