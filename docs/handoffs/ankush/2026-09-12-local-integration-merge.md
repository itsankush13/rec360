# Ankush handoff — 2026-09-12 local integration merge

## Acting developer
Ankush (backend `app/**`, migrations, Python tests, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
At the user's explicit instruction, merged all eight outstanding local `ankush/*` branches into
`consolidated`, **locally only — not pushed to `origin/consolidated`.** `consolidated` is now
27 commits ahead of `origin/consolidated`.

Merge order (chosen to isolate the one real file overlap — both X2 and X12 touch
`tests/test_evaluations.py` — to a single, cleanly auto-merged step, and to put the one
migration-bearing branch, B14, after everything else so its Alembic head check is against the
final integrated tree):

1. `ankush/x3-x4-x6-cheap-fixes` (X3, X4, X6 — no shared files with anything else)
2. `ankush/flaky-audit-ordering` (audit timestamp tie-break fix)
3. `ankush/x1-identity-extraction` (X1)
4. `ankush/x13-x15-x16-cv-source` (X13 partial, X15 API contract, X16 code path)
5. `ankush/x2-narrative-scored-count` (X2)
6. `ankush/x12-leaderboard-sql-limit` (X12) — auto-merged cleanly against `tests/test_evaluations.py`, no conflict markers left, verified by grep
7. `ankush/b14-draft-api` (B14 + X18 backend) — single Alembic head confirmed both before (`d7b3e81c4a05`) and after (`7a12e4f9c3d6`) the merge; `alembic upgrade head` runs clean
8. `ankush/b03-relevance-ranking` (B03 relevance ranking, this session's earlier work)

Every merge was a clean `git merge --no-ff` with **no conflicts** — the eight branches touched
disjoint files except the one `test_evaluations.py` case, which auto-merged with no markers left
behind (checked with `grep` for `<<<<<<<`/`=======`/`>>>>>>>` across the touched files).

## Verification
- After each merge, ran the directly affected test file(s) before continuing (all passed —
  see individual branch handoffs for the per-branch numbers).
- Full suite once on the final integrated tree: **559 passed, 5 failed, 6 skipped** — the 5
  failures are the same pre-existing `test_pptx_intake.py` `ModuleNotFoundError: No module named
  'pptx'` (the `requirements-ocr.txt` two-step gap `CLAUDE.md` already names), unrelated to any
  of the eight branches. No new failures. The flaky audit-ordering assertions did not reappear.

## Suggested `04-KNOWN-DEFECTS.md` deltas (Subhadeep to apply after review)
- **X1** — `- [ ] Fixed` / `- [ ] Test added...` / `- [ ] Re-run against all three real CVs` →
  first two checked (fixed, regression test added with the exact defect-report header as
  fixture); third stays open — no binary CV fixtures live in this repo to re-run against.
- **X2** — mark fixed: narrative's denominator now scopes to scored (weight > 0) criteria, not
  every seeded row. `- [ ] Granularity decision taken and recorded in docs/DECISIONS.md` stays
  open — this fixed the *counting* bug (option 2's mechanism already existed and just wasn't
  used by the narrative); it is not the broader "cap at 10-15 criteria" decision (option 1),
  which remains a genuine open decision.
- **X3** — `- [ ] Made lazy` → checked, fixed.
- **X4** — `- [ ] Migrated to ConfigDict` → checked, fixed.
- **X6** — `- [ ] Cleaned` → checked, fixed (emoji only, per the item's own wording — currency
  sign and box-drawing characters intentionally left alone, not in scope).
- **X12** — `- [ ] Leaderboard uses SQL limit/offset` → checked. `- [ ] Comparison page defaults
  to the top 10` stays open (that's `web/compare.html`, Subhadeep's file). `- [ ] Benchmarked
  against a campaign with more than 1,000 candidates` stays open — no such dataset available
  this session.
- **X13** — `- [ ] Tenant and site checked, not just the tail` stays open (needs a real pilot
  OneDrive registry shape). `- [ ] An ambiguous match is refused rather than resolved to the
  first hit` → checked. `- [ ] The screen shows which sync root was matched` stays open
  (Subhadeep, screen-side).
- **X15** — backend contract fixed (`LifecycleOut.held_from_status`/`held_from_label` now
  exposed); the item's own checkboxes are both browser-side (Subhadeep) and stay open.
- **X16** — code path fixed (UNC existence check at resolve time); `- [ ] Tested against a real
  network share` stays open (no real share available this session).
- **X18** — backend half now built on the merged branch: `Idempotency-Key` create-retry
  protection and `expected_version` optimistic-concurrency on `PATCH /api/campaigns/{id}`. The
  item's UI checkboxes (duplicate-create removal, close/reopen verification) stay open — that's
  `web/new-campaign.html`, Subhadeep's file. See `docs/contracts/B14-campaign-draft.md` for the
  exact contract now available to build against.

## Suggested `00-MASTER-BACKLOG.md` deltas
- **B03**: apply the delta already specified in
  `docs/handoffs/ankush/2026-09-12-b03-relevance-ranking.md` — the ranking line moves from
  "not built" to "API contract built" (now merged into `consolidated`, still not pushed).
- **B12/B14**: the B14 checklist gains `- [x] Save the campaign before importing CVs` /
  version-conflict protection isn't itself a listed line item, but `docs/contracts/
  B14-campaign-draft.md` should be linked from B14's section as the settled contract for
  whoever builds the `web/new-campaign.html` side (X18).
- **B16**: the "Avoid full-population fetch/render" line can move to done (X12 landed); the
  "design for 10,000-20,000 CV scale" and benchmarking lines stay open.

## Not done
- Nothing pushed to `origin`. Bootstrap PR into `azure-provider` still pending, per
  `08-TWO-PERSON-DELIVERY.md` section 5 — this local merge is not that gate.
- The eight source branches (`ankush/b14-draft-api` etc.) still exist locally, now fully
  contained in `consolidated`'s history; not deleted, since deletion wasn't asked for.

## Next
User instructed: start Ankush-owned backend work not yet begun. Per `00-MASTER-BACKLOG.md`'s
agreed execution order (B01/B02/B04 → B03 → B06/B05 → B07), next is **B06** (AI-generated JD —
nothing built).
