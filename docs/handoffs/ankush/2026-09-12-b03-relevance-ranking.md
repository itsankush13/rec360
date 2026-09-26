# Ankush handoff — 2026-09-12 B03 relevance ranking

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
Branched `ankush/b03-relevance-ranking` off `consolidated` (which now includes this session's
save-state commit `4953f9c`; does not include the still-unmerged `flaky-audit-ordering` or
`x13-x15-x16-cv-source` branches from earlier sessions). **Not pushed, no PR** — same
local-only mode as the other seven branches, per this session's explicit decision to defer
that question and pick new backend scope instead.

Scope chosen: `00-MASTER-BACKLOG.md`'s B03 unchecked item — "Find role-relevant CVs
automatically; no manual selection — not built." Today `/discovery/resolve` lists every file in
a folder and the recruiter ticks each one manually; there is no ranking signal at all.

### What was built
New module `app/core/cv_relevance.py`: deterministic, pre-import relevance scoring.

- `terms_for_weights(weights)` mines match terms from each active `RubricWeight.label`, reusing
  `skill_taxonomy.extract_terms` — the same "rubric → searchable terms" bridge
  `evaluation_service._campaign_terms` already uses for real evaluation. Duplicated as a small
  standalone function rather than importing evaluation_service's private helper, to avoid
  coupling discovery to evaluation's internals for a 4-line union.
- `score_file(path, filename, terms)` extracts text via the existing
  `document_intake.extract_document` (deterministic, LLM-free, same intake path used before
  import) and scores coverage with `skill_taxonomy.find_term` — the identical matcher
  `criterion_scorer` uses for real per-criterion scoring, so a CV that would score well against
  the rubric also ranks well here. Returns `None` (not zero) when the file can't be read
  (unsupported extension, corrupt, below `MIN_TEXT_CHARS`) — an unranked file must not look
  irrelevant.
- `RECOMMENDED_THRESHOLD = 0.4`: a CV covering at least 40% of the campaign's mined terms is
  flagged `recommended`. Deliberately looser than `criterion_scorer.BINARY_THRESHOLD` (0.7) —
  that threshold is coverage of *one* criterion's own aliases; this is coverage across *every*
  criterion's terms at once, so a genuinely strong CV rarely clears a high bar there.

This is explicitly **not** evaluation: no per-criterion weighting, outcome classification, or
persistence. It is a fast, throwaway pre-import signal so a recruiter pointed at 200 CVs isn't
ticking through an unordered list. Real scoring still runs unchanged on import.

`app/api/discovery.py`'s `/discovery/resolve`:
- Request gains optional `campaign_id`. Omitted → identical response shape and ordering as
  before (verified by a new regression test) — **additive, backward compatible**, per
  `08-TWO-PERSON-DELIVERY.md`'s merge-order rule.
- When given, looks up the campaign's active (`APPROVED`/`LOCKED`) rubric version via
  `rubric_service.get_active_version`; if none exists yet, ranking is silently unavailable
  (`ranking_available: false`) rather than erroring — a campaign mid-setup can still browse a
  repository.
- Each file in the response gains `relevance_score` (0–1 coverage, `null` if unranked) and
  `recommended` (bool). Files are sorted by score descending when ranking is available;
  unranked files sort last rather than being mixed in as if they scored zero.

### What was not built
- **The screen** (`web/discover.html`) — Subhadeep's file. This session supplies the contract
  above; the screen still needs to send `campaign_id`, show the score/recommended flag, and
  decide the "show selected CVs before screening starts" UX (a separate unchecked B03 line).
- Mixed-role repository handling, retention/consent metadata tags, and the 200-CV/15-20-relevant
  target-story acceptance line — all still open; only the "small demo, 5 in / ranked" shape was
  verified here (see tests).
- No change to `/discovery/import` — it is untouched, still reuses the normal batch intake path.

## Verification
`tests/test_discovery.py` — 3 new tests, all passing:
- `test_resolve_without_campaign_id_does_not_rank` — old behavior unchanged when `campaign_id`
  is omitted.
- `test_resolve_ranks_by_rubric_term_coverage` — using the existing `screening_campaign` fixture
  (rubric seeded from `required_skills: Python, AWS, PostgreSQL`, preferred `Kubernetes`), a CV
  mentioning those terms outranks one that doesn't, is flagged `recommended`, and sorts first.
- `test_resolve_ranking_unavailable_without_approved_rubric` — a campaign with no rubric yet
  returns `ranking_available: false`, not an error.

`tests/test_discovery.py` full file: 7 passed. `tests/test_cv_source.py` +
`tests/test_evaluations.py` + `tests/test_rubrics.py` run together with it: 143 passed (no
regression). Full suite once: 544 passed, 5 failed, 6 skipped — the 5 failures are the
pre-existing `test_pptx_intake.py` `ModuleNotFoundError: No module named 'pptx'` failures
(`requirements-ocr.txt` two-step gap `CLAUDE.md` already names), unrelated to this change; no
new failures.

## Suggested `00-MASTER-BACKLOG.md` delta (Subhadeep to apply after review/merge)
Under B03, change:
```
- [ ] Find role-relevant CVs automatically; no manual selection — **not built.** The screen
      lists every CV in the folder and the user ticks the ones they want.
```
to:
```
- [~] Find role-relevant CVs automatically — **API contract built, unmerged.**
      `POST /discovery/resolve` now accepts an optional `campaign_id`, scores each discovered
      file's coverage of the campaign's active rubric terms (`app/core/cv_relevance.py`,
      reusing the same deterministic matcher as real evaluation), and returns
      `relevance_score`/`recommended` per file, sorted best-first. On branch
      `ankush/b03-relevance-ranking`, not merged. `web/discover.html` does not yet send
      `campaign_id` or surface the score — the screen still shows manual ticking only.
```
And update the B03 summary line from "Tier 1 built; the semantic half is not" to "Tier 1 built;
ranking backend built and unmerged; screen still manual" once the branch merges.

## Next
Either: (a) continue this branch toward the screen-facing acceptance items (mixed-role
repository, retention/consent tags), or (b) get this contract in front of Subhadeep for
`discover.html` consumption, or (c) move to the next agreed backend item (B06/B05/B07) and
leave this as a settled, reviewable contract. No instruction was given this session on which;
flagging rather than assuming.
