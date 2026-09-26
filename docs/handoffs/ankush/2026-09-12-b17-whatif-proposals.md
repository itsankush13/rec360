# B17 — what-if proposal workflow (Ankush, 2026-09-12)

Session context: restored the TWO-PERSON-OWNERSHIP checkpoint (acting developer
Ankush), confirmed `consolidated` clean at `f21af38` with no new
`origin/azure-provider` commits and no unmerged local branches. Two decisions
from the prior session's handoff (B15/B20 cross-campaign identity; push/bootstrap
authorization) were surfaced again and deliberately deferred — the user chose to
start **B17** instead, which needed neither.

## What landed

B17's three previously unchecked backlog lines, first increment:

- **A proposal now reaches a backend** (`web/whatif.html:173`'s "Propose these
  weights for approval" button previously had nothing behind it). New
  `WhatIfProposal` table + `app/services/whatif_service.py` + three routes under
  `/api/campaigns/{campaign_id}/what-if/proposals` (propose / list / get /
  approve / reject) in `app/api/analytics.py`.
- **Proposer separate from approver.** Both are named, real, active users
  (reuses `lifecycle_service.require_user`); propose rejects proposer==approver,
  and rejects an approver who isn't `HIRING_MANAGER`/`ADMIN` — "the correct
  hiring manager", not whoever clicks first. Only the named approver can decide
  their own proposal (enforced on both `/approve` and `/reject`).
- **Both the proposed and the approved versions are audited**, as two separate
  `AuditEvent` rows (reused `AuditAction.APPROVAL_REQUESTED` /
  `APPROVAL_GRANTED` / `APPROVAL_RETURNED` — same actions B13's approvals
  router already uses and `web/audit.html` already labels, so no new
  `AuditAction`/label pair was needed, same call B15 made for `WAITLIST`).
  Approving can amend the weights on the way through, so the "approved"
  snapshot audited can genuinely differ from the "proposed" one that was
  audited at request time — not just the same dict twice.

**Deliberately scoped out:** approving a proposal does **not** create, submit
or approve a new `RubricVersion`, and nothing is re-scored. It only authorizes
proceeding — the existing `rubric_service` draft → submit → approve workflow
still owns actually changing what a CV is scored against, exactly as
`whatif.html`'s own copy already promises ("A new balance needs its own
approval and a re-score of every CV before it can be used"). Wiring the
approved proposal into an actual draft rubric version is a reasonable next
increment but is a separate, larger slice (it would touch `rubric_service`'s
one-draft-at-a-time invariant) — flagged, not built.

## Files changed

- `app/db/models.py` — `WhatIfProposalStatus` enum, `WhatIfProposal` model.
- `alembic/versions/9d3f6b1a4c72_whatif_proposals.py` — new table + 3 indexes.
  Applied cleanly on top of `2a13836a93f4`; single head confirmed before and
  after (`alembic heads`).
- `app/services/whatif_service.py` — new. `propose` / `approve` / `reject` /
  `get_proposal` / `list_proposals`. Pure `app.core.analytics.what_if()`
  preview is untouched and never called from here — proposals validate weight
  *shape* only (`analytics.validate_weights`, reused unchanged), not a
  re-derived preview.
- `app/api/analytics.py` — five new routes + `WhatIfProposeIn` /
  `WhatIfDecisionIn` / `WhatIfProposalOut` schemas + `_proposal_out`
  serializer. Existing comparison/what-if-preview/KPI routes unchanged;
  updated the module docstring to name the proposal routes as the file's one
  deliberate write path.
- `tests/test_whatif_proposals.py` — new, 11 tests. Reuses the
  `analysed_campaign` fixture from `test_analytics.py` and the `people`
  fixture from `test_lifecycle.py` (imported, not duplicated).

## Verified

- `tests/test_whatif_proposals.py`: 11 passed.
- Regression: `test_analytics.py` / `test_lifecycle.py` / `test_approvals_api.py`
  / `test_audit_trail.py`: 104 passed (audit-label enforcement test included —
  no new `AuditAction` means nothing to add to `web/audit.html`).
- Full suite once: **607 passed, 6 skipped, 5 failed** — the 5 are the
  pre-existing `test_pptx_intake.py` `ModuleNotFoundError: No module named
  'pptx'`, same as every prior baseline (did not `pip install`, per
  `CLAUDE.md`). 607 = the 596 from the last recorded baseline + these 11 new
  tests. No regression.
- `alembic upgrade head` applied `9d3f6b1a4c72` cleanly on the local dev DB;
  single head confirmed before and after.

## Requested `00-MASTER-BACKLOG.md` deltas (B17 section)

```
- [x] Send proposed weight changes to the correct hiring manager/team — POST
      `/api/campaigns/{id}/what-if/proposals` (`app/api/analytics.py`,
      `app/services/whatif_service.py`); approver must be a real, active,
      named HIRING_MANAGER/ADMIN, never hardcoded.
- [x] Separate the proposer from the approver — rejected at propose time
      (same person) and enforced again at decision time (only the named
      approver can approve/reject their own proposal).
- [x] Audit both the proposed and the approved versions — two separate
      AuditEvent rows per decided proposal
      (`tests/test_whatif_proposals.py::test_propose_and_approve_each_write_their_own_audit_event`).
```

All three of B17's remaining lines are now checked at this increment's scope
(a proposal decision, not yet wired into an actual rubric revision — see
"deliberately scoped out" above, worth a one-line note if B17 is otherwise
marked fully done).

## Suggested `docs/DECISIONS.md` entry

> **B17 (2026-09-12, Ankush):** A what-if proposal is a new `WhatIfProposal`
> row + audit trail, not an automatic new `RubricVersion`. Approving a
> proposal authorizes proceeding to a real rubric revision; it does not
> perform one — re-scoring stays gated behind the existing rubric
> draft/submit/approve workflow. Reused `AuditAction.APPROVAL_REQUESTED` /
> `APPROVAL_GRANTED` / `APPROVAL_RETURNED` (already used by B13's approvals
> router and already labeled in `web/audit.html`) rather than adding new
> `AuditAction` values, matching the precedent set for B15's `WAITLIST`
> disposition.

## Still open (unchanged from prior handoff, not attempted this session)

- B15/B20 cross-campaign candidate identity — needs a user decision, resurfaced
  and deferred again.
- Push `consolidated` / bootstrap PR into `azure-provider` — resurfaced and
  deferred again; still Subhadeep-coordinated, still needs explicit
  authorization.
- Wiring an *approved* what-if proposal into an actual `RubricVersion` draft
  (see "deliberately scoped out" above) — natural next B17 increment.
- B13 cost-centre field/delegation rules, B19 campaign/period filters — both
  still real, unblocked, unstarted.
