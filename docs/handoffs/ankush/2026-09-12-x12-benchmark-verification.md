# X12 — leaderboard scale fix: already merged, now benchmarked

Session: 2026-09-12, acting developer Ankush. No branch — verification only,
no product code changed. Central-doc deltas below are for Subhadeep to apply
to `docs/plan/04-KNOWN-DEFECTS.md`; not edited directly per
`08-TWO-PERSON-DELIVERY.md` file ownership.

## What was found

X12's code fix was **already on `consolidated`** — commit `db81b83`
("X12: leaderboard limit pushed into SQL instead of a Python slice"),
an ancestor of current HEAD (`bdd6a61`). `app/api/evaluations.py`'s
`leaderboard()` already does `.order_by(...).limit(limit)` in the SQL
statement, not `evaluations[:limit]` in Python. A regression test already
exists: `tests/test_evaluations.py::test_leaderboard_limit_selects_the_top_scorers_not_the_first_rows`.

`04-KNOWN-DEFECTS.md`'s X12 checkboxes were stale — all three still showed
`[ ]` even though the first was done. This looked like open work when I
picked X12 as this session's next slice; it was really just an unchecked box
plus one genuinely missing checkbox (the benchmark).

## What I did this session

Ran `tests/test_evaluations.py` in full: **98 passed**, confirming the
existing X12 regression test still holds.

Then closed the one checkbox that was genuinely open — "Benchmarked against
a campaign with more than 1,000 candidates" — with a one-off script (not
committed; scratch-only), seeding 1,200 candidates/evaluations directly via
bulk ORM insert (bypassing the document pipeline, which isn't what's under
test) into an in-memory SQLite DB, then hitting the real
`GET /api/campaigns/{id}/leaderboard?limit=10` through the FastAPI app:

- 200 OK, exactly 10 rows returned (not 1,200 sliced down).
- 99 ms for the full request/response round trip.
- Compiled the equivalent SQLAlchemy statement and confirmed `LIMIT 10`
  appears in it — i.e., confirmed this is the database doing the limiting,
  not Python.
- Returned rows were the correct top-10 by `overall_score` (100.0, 99.9,
  99.9, ...), consistent with the existing correctness test's assertion
  that `limit` selects top scorers, not first rows.

## Requested delta to `04-KNOWN-DEFECTS.md` (X12 section)

```
- [x] Leaderboard uses SQL limit/offset — merged `db81b83`, regression test
      `test_leaderboard_limit_selects_the_top_scorers_not_the_first_rows`
      passing (98/98 in test_evaluations.py, 2026-09-12).
- [ ] Comparison page defaults to the top 10 — Subhadeep/B16, UI-side, still
      open.
- [x] Benchmarked against a campaign with more than 1,000 candidates —
      1,200-row in-memory benchmark, 2026-09-12: 200 OK, 10 rows back
      (not 1,200), 99 ms, confirmed `LIMIT` in the compiled SQL, correct
      top-10 ordering. Script was scratch-only, not committed (one-off
      verification, not a maintained perf-regression test).
```

X12 is otherwise unchanged: still linked to B16 for the comparison-page UI
half, which remains Subhadeep's.

## Next

No further backend work identified for X12. Open items in Ankush's lane
remain as listed in `docs/SESSION-STATE.md`'s `open_tasks` (B11, X6, X13/
X15/X16 infra-blocked, bootstrap PR pending). No decision taken this session
on which of those to pick up next.
