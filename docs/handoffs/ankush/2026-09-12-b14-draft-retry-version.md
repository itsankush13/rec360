# Ankush handoff — B14 backend verification (draft/PATCH/version/retry)

## Acting developer
Ankush (backend `app/**`, migrations, integrations, Python tests, per
[08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)). Branch:
`ankush/b14-draft-api`, created off `consolidated` (bootstrap into `azure-provider` still
pending, so this targets `consolidated` for now per section 5/6 of 08).

## What this session did
1. Fetched `origin`; no new commits on `origin/consolidated` or `origin/azure-provider`.
   Created task branch `ankush/b14-draft-api` off local `consolidated` (2 commits ahead of
   `origin/consolidated`, clean tree).
2. Verified actual B14 backend behavior against code and tests, not plan prose:
   - Draft save: present (`Campaign.status` defaults `DRAFT`).
   - PATCH partial update: present (`update_campaign`, tested).
   - Version/conflict checks: **were missing** — no optimistic concurrency at all.
   - Retry protection: **were missing** — `create_campaign` had no dedup path; a retried
     `POST` made a second campaign. This is the backend half of `X18`.
3. Implemented the two missing guarantees, regression tests first:
   - Migration `alembic/versions/7a12e4f9c3d6_campaign_version_and_idempotency_key.py`
     (revises `d7b3e81c4a05`, single head confirmed before and after) adds
     `campaigns.version` and `campaigns.idempotency_key` (unique).
   - `POST /api/campaigns` accepts an `Idempotency-Key` header; a repeat with the same key
     returns the existing campaign (`200`) instead of creating a duplicate (`201` on first
     use). See `app/services/campaign_service.py::create_campaign`,
     `app/api/campaigns.py`.
   - `PATCH /api/campaigns/{id}` accepts optional `expected_version`; a stale value is
     rejected with `409` (new `CampaignConflictError`) and no fields change. `version`
     increments on every accepted PATCH and on every status transition.
   - `CampaignOut` now returns `version`.
4. Full contract published at
   [docs/contracts/B14-campaign-draft.md](../../contracts/B14-campaign-draft.md).
5. Tests: `tests/test_campaigns.py` — 7 new tests, all 14 in that file pass. Full suite:
   `548 passed, 6 skipped, 5 failed`. **The 5 failures are pre-existing and unrelated**:
   all in `tests/test_pptx_intake.py`,
   `ModuleNotFoundError: No module named 'pptx'` — `python-pptx` is not installed in this
   venv (`./venv/Scripts/python.exe -c "import pptx"` fails directly, before any change on
   this branch). Also observed: this venv's Python is **3.12.10**, not the 3.13.5 CLAUDE.md
   names as verified — worth Subhadeep/whoever owns the environment checking; not touched
   here per "do not `pip install`" and no destructive action taken.

## Requested central-document deltas (Ankush does not edit these directly — see 08 §7)

**`docs/plan/00-MASTER-BACKLOG.md`, B14 section:**
- `[~] Support drafts` → `[x] Support drafts` — `CampaignStatus.DRAFT` default verified;
  flow audited this session (was previously "not audited").
- Add a line: `[x] Retry protection / version-conflict checks on campaign save —
  Idempotency-Key on create, expected_version on PATCH, see docs/contracts/B14-campaign-draft.md`
  (new B14 line item; this was implicit in "durable setup" but not previously tracked).

**`docs/plan/04-KNOWN-DEFECTS.md`, `X18`:**
- Add: "Backend contract gap closed 2026-09-12 on `ankush/b14-draft-api`: campaign create
  now supports an `Idempotency-Key` retry guard and PATCH supports `expected_version`
  conflict checks (`docs/contracts/B14-campaign-draft.md`). **Still open**: the UI
  (`web/new-campaign.html`) does not yet call these — duplicate creation across
  JD-extraction/final-assessment steps and the cosmetic draft-save button are unchanged
  until Subhadeep wires the contract in."

**`docs/DECISIONS.md`:**
- Append: "B14/X18, 2026-09-12 (Ankush): campaign retry/version protection implemented as
  an opt-in contract (`Idempotency-Key` header, `expected_version` field) rather than
  mandatory, so existing callers need no changes and the UI adopts it on its own schedule.
  Alternative considered: reject any PATCH missing `expected_version` — rejected because it
  would break every existing caller in one migration instead of letting Subhadeep adopt it
  with the new-campaign UI work."

## Not done yet (explicitly deferred)
- No PR opened yet for `ankush/b14-draft-api` (bootstrap into `azure-provider` still
  pending; this branch is intended to merge into `consolidated` for now).
- UI adoption of the new header/field is Subhadeep's file per ownership.
- X1/X2/X12 (also assigned to Ankush this wave) not started this session — next.
- `python-pptx` / Python-version environment discrepancy noted above, not investigated
  further or fixed.

## Next-session start pointer
Read `AGENT-START-HERE.md` → `docs/plan/08-TWO-PERSON-DELIVERY.md` → this file. Either
open the PR for `ankush/b14-draft-api` into `consolidated`, or continue with X1/X2/X12
(identity extraction, scoring granularity, SQL limit/offset scale) per the first-parallel-wave
list, each as a separate focused branch/PR off `consolidated`.
