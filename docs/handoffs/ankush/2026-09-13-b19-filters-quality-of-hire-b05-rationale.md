# B19 dashboard remainder + B05 suggested rationale — handoff for Subhadeep

Date: 2026-09-13. Acting developer: Ankush. Branch `consolidated`, uncommitted.

Scope: the exact remainder named against `B19` and `B05` this session — campaign/role and
3-/6-month filters, historical reporting windows and a quality-of-hire metric for `B19`;
auto-fill rationale contract for `B05`. `B07` was re-checked against
`2026-09-12-b07-scoring-audit.md` and needed nothing further — still essentially complete,
remaining items are UI (`web/rubric.html`) or blocked (JD fixture, bonus-points policy
already decided "leave as-is"). No code touched for B07 this session.

## B19 — period and role filters (`app/api/analytics.py`)

`GET /api/analytics/kpis` (global) gains three query params:

- `role: str | None` — case-insensitive substring match against `Campaign.job_title`.
  A role that matches nothing returns **zero campaigns**, not every campaign — checked
  explicitly by `test_global_kpis_filters_by_role`. No role given behaves exactly as before.
- `months: int | None` (1-24) — convenience for "last N months to date". Ignored once an
  explicit `since` is given; an exact boundary always wins over a rounded one.
- `since` / `until: datetime | None` — explicit ISO8601 timestamps, for a historical window
  that isn't "the last N months from today" (e.g. a specific quarter). This is the
  "historical reporting windows" line item: any past window is queryable, not just a
  running to-date total.

`GET /api/campaigns/{id}/kpis` gains `months`/`since`/`until` (no `role` — one campaign
already has one job title).

Both routes now return a `"period"` block:

```json
{"since": "2026-06-15T00:00:00+00:00", "until": null, "months": 3, "label": "Last 3 months"}
```

`label` is always one of `"All campaigns to date"`, `"Last N month(s)"`, or `"Custom
reporting window"` — plug this straight into `#p-period` in `web/performance.html` and
delete the hardcoded placeholder there ("1–30 September · reporting period" /
"Loading current records…"). The global route also returns `"role_filter"`, echoing what
was applied (or `null`).

Filtering now scopes every KPI group (workload, throughput, efficiency, quality,
exceptions, outcomes) consistently — jobs by `ProcessingJob.queued_at`, evaluations/
overrides/findings by their own `created_at`. `campaign_id` was generalised internally to
a `campaign_ids: list[str] | None` (`_kpi_payload`), so `role` and the existing single-
campaign path share one filtering path rather than diverging.

**Not done, and out of scope for this slice:** the actual `performance.html` filter UI
(campaign/role picker, 3/6-month toggle) — that is your file. The API is ready to be
called with `?role=...&months=3` today.

## B19 — quality of hire (`app/api/metrics.py` + `app/services/lifecycle_service.py`)

Added to `GET /api/campaigns/{id}/metrics/outcomes` (and therefore `/overview`):

```json
"quality_of_hire": {
  "hired_count": 2,
  "with_recorded_rank": 2,
  "average_shortlist_rank": 1.5,
  "hired_from_top_3_of_shortlist": {"count": 2, "of": 2, "value": 100.0, "statement": "2 of 2"},
  "basis": "Proxy measure, not a post-hire outcome. ..."
}
```

or `null` with no hires yet. **This is explicitly a proxy, not the real thing** —
`web/performance.html` already says correctly that quality of hire "needs a full hiring
cycle plus a probation period" this system does not track. What it measures instead: for
every candidate whose current lifecycle status is `HIRED`, where they stood by AI score
against the rest of the field at the moment they entered the pipeline — using
`CandidateLifecycle.campaign_rank`, the rank B15 already stores at shortlist/waitlist
entry and carries forward rather than recomputing. New `lifecycle_service.hired_candidates()`
mirrors the existing `waitlisted_candidates()` shape.

If you show this on a screen, keep the `basis` string (or your own equivalent wording)
visible next to it — do not present it as measured post-hire performance.

## B05 — suggested rationale (`app/services/disposition_service.py`)

`GET /api/campaigns/{id}/candidates/{candidate_id}/recommendation` (already existed) gains
one field:

```json
"suggested_rationale": "AI assessment: a strong fit (82/100). Confirmed: AWS, Python, Distributed systems. Flagged: Team leadership."
```

Empty string when there is no current evaluation to draft from. Built from the same
per-criterion evidence the score already carries (top 3 `CONFIRMED_MATCH` criteria by
weight as strengths, top 3 `CONTRADICTORY_EVIDENCE`/`NOT_DEMONSTRATED` as concerns) — it
never asserts anything the evaluation doesn't already show.

**This is a draft for the comment box, not an auto-filed decision.** Per
`AGENT-START-HERE.md` §5 ("AI recommendation remains separate from human decision") and the
master backlog's own B05 wording ("auto-fill the rationale/comment", not "auto-submit"):
prefill `web/decisions.html`'s comment field with this text when a recommendation loads,
but leave it editable and still require the recruiter's own Save action before anything is
persisted — exactly like today's `set_disposition`/`override_recommendation` flow, just
with a starting draft instead of a blank box. The other two B05 items in your lane
("auto-select the recommended action" and "fix incomplete control wiring / incorrect
selection styling") are unchanged by this session — still open, still `web/decisions.html`.

## Tests

- `tests/test_analytics.py`: 5 new (`test_global_kpis_names_the_all_time_period_by_default`,
  `test_global_kpis_filters_by_role`, `test_kpis_months_convenience_names_its_own_label`,
  `test_kpis_since_excludes_activity_before_the_window`,
  `test_explicit_since_overrides_the_months_convenience`). 37/37 passed.
- `tests/test_metrics_api.py`: 3 new quality-of-hire tests, plus `_move()` extended with an
  optional `campaign_rank` param. 12/12 passed.
- `tests/test_decisions.py`: 2 new (`test_effective_recommendation_suggests_a_rationale_draft`,
  `test_suggested_rationale_is_empty_with_no_evaluation`). 43/43 passed.
- Full suite re-run at the end of this session — see `docs/SESSION-STATE.md` for the fresh
  count.

## Suggested `00-MASTER-BACKLOG.md` deltas (applied directly this session, per existing
practice of editing this file for my own session's evidence)

- `B19`: filters line and metrics line updated — see the file itself.
- `B05`: "Auto-fill the rationale/comment" row annotated with the new contract; still open
  because the box itself is unfilled until `web/decisions.html` calls it.
