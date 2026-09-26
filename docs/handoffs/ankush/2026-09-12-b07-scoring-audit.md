# B07 scoring/weight audit — handoff for Subhadeep

Date: 2026-09-12. Acting developer: Ankush. No code changed this session — this was an
audit-only pass per the agreed execution order (`B06/B05` → `B07`), since B05's remaining
items are all `web/decisions.html` (Subhadeep's lane) and B06 stays on its own unmerged
branch per this session's decision.

Ran fresh this session: `tests/test_rubrics.py`, `tests/test_rubric_presets.py`,
`tests/test_evaluations.py` — **143 passed, 0 failed.**

## Suggested `00-MASTER-BACKLOG.md` B07 deltas

Most backend items were already built under Phase B and never had the box ticked. Suggest:

- [x] Validate the backend calculation — `test_overall_score_is_the_sum_of_weighted_contributions`
      (`tests/test_evaluations.py:859`) asserts `overall_score == sum(weighted_score)` and
      `0 <= overall_score <= 100`. Re-run this session, passing.
- [x] Use a bounded scale (0–10, 0–100) — `RubricWeightCreate`/`RubricWeightUpdate.weight` is
      `Field(ge=0.0, le=100.0)` (`app/schemas/rubric.py:35,47`), backend-enforced regardless of
      what the UI control looks like.
- [x] Keep the normalised total constant across roles — `is_balanced`/`weight_total` invariant
      enforced at submit/approve (`app/services/rubric_service.py` `validate_version`);
      confirmed by `test_a_weighted_draft_still_sums_to_one_hundred` and
      `test_normalize_weights_rebalances_to_exactly_100`, both re-run this session.
- [x] AI-prefill industry-standard weights — `rubric_presets.MARKET_STANDARD`, exposed at
      `GET /rubrics/weightings` and applied via `weighting=` on version creation
      (`app/api/rubrics.py:109`, `rubric_service.create_version`). Deterministic template, same
      relationship to a rubric that B06's JD templates have to a JD — not literal "AI", but
      satisfies the "prefill a standard starting point" intent.
- [x] Allow HR override and custom criteria — `add_weight`/`update_weight`/`bulk_set_weights`
      accept arbitrary labels/categories and override any prefilled value.

Left as-is / not built this session:

- [ ] Replace unrestricted text inputs with sliders — `web/rubric.html`, Subhadeep's file; not
      touched.
- [ ] Test the generated weights against the actual demo JD — **blocked**: no demo JD fixture
      exists in this repo (`sample_cvs/` has CVs, no JD file); the real client JD used in
      earlier sessions apparently lived outside git. Needs that file supplied before this can
      be built as a regression test.
- [ ] Separate category weight from good-to-have bonus points — see decision below. Not a bug;
      status quo kept.

## Decision needed in `docs/DECISIONS.md`

Asked the user directly (not inferable from code or plan): B07 asks to "separate category
weight from good-to-have bonus points." Today `PREFERRED` ("good-to-have") criteria share the
same fixed 100-point pool as `MANDATORY`/category criteria
(`rubric_service.seed_from_requirements`, `rubric_presets.apply`) — they are not bonus points
added on top of a 100-point base. Changing that would touch the "weights sum to 100" invariant
used throughout `rubric_service.py` and `evaluation_service._aggregate`, and every test built on
it.

Options put to the user: (a) leave as-is, flag for a client conversation; (b) bonus on top of
100, so `overall_score` could exceed 100; (c) bonus capped, base still 100 (mandatory+category
alone sums to 100, good-to-have adds a small bounded bonus like +5).

**User chose (a): leave as-is for now.** This needs a client conversation before any backend
redesign, not an unreviewed change to a core scoring invariant. Suggest recording this as a
decision row for `B07` with reason "changes a load-bearing invariant across scoring, tests and
UI; requires client input on what 'bonus points' should mean before implementation," owner
Ankush (raised) / Subhadeep (client coordination, per `B07`'s lead in `08-TWO-PERSON-DELIVERY.md`
— wait, B07's lead in that table is actually Ankush for the calculation half; flagging the
client-facing wording question to Subhadeep since it needs the FinOps/product conversation
lane).

## Net effect

No code changed. B07's Ankush-owned backend surface is essentially complete except the one
policy question above and the JD-fixture-blocked test. Nothing left in B07 is both (a)
Ankush's lane and (b) unblocked and authorized to build right now.
