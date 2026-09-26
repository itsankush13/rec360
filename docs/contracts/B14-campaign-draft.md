# B14 — Campaign draft/PATCH/version/retry contract

Author: Ankush · 2026-09-12 · Status: implemented on branch `ankush/b14-draft-api`,
not yet merged. Verified against `app/api/campaigns.py`, `app/services/campaign_service.py`
and `tests/test_campaigns.py` on this branch, not from plan prose.

Answers the first-parallel-wave item in
[08-TWO-PERSON-DELIVERY.md](../plan/08-TWO-PERSON-DELIVERY.md) section 8 and fills the
backend half of `X18` (duplicate campaign creation, cosmetic draft save) from
[04-KNOWN-DEFECTS.md](../plan/04-KNOWN-DEFECTS.md).

## What was verified before this branch

| Capability | Found | Evidence |
|---|---|---|
| Draft save | Present. `Campaign.status` defaults to `DRAFT`; no separate "save as draft" endpoint is needed — `POST /api/campaigns` always creates a draft. | `app/db/models.py` `Campaign.status` default; `tests/test_campaigns.py::test_create_campaign_defaults_to_draft` |
| Partial update (PATCH) | Present. `PATCH /api/campaigns/{id}` updates only the fields sent, audits only real changes. | `app/services/campaign_service.py::update_campaign`; `tests/test_campaigns.py::test_update_campaign_fields` |
| Version / conflict checks | **Missing.** No column or check existed; two concurrent PATCHes silently last-write-wins. | absent before this branch |
| Retry protection | **Missing.** `create_campaign` had no dedup path; a retried `POST` (timeout, double-click, network retry) created a second campaign row. | absent before this branch; matches `X18` |

This branch implements the two missing guarantees. Nothing about draft save or PATCH
itself changed.

## Migration

`alembic/versions/7a12e4f9c3d6_campaign_version_and_idempotency_key.py`, revises
`d7b3e81c4a05` (current single head before this branch). Adds to `campaigns`:

- `version INTEGER NOT NULL DEFAULT 1`
- `idempotency_key VARCHAR(255) NULL`, unique index `ix_campaigns_idempotency_key`

## API

### `POST /api/campaigns` — retry protection

Optional request header: `Idempotency-Key: <opaque client-generated string>`.

- No header: unchanged behavior, always creates a new campaign (`201`).
- Header present, not seen before: creates the campaign, stores the key, `201`.
- Header present, already stored on a campaign: returns **that** campaign unchanged,
  `200` (not `201` — no new resource was made). No new audit event is written.

The client should generate one key per user-initiated "create campaign" action (e.g. once
per submit-button press) and resend the same key on any automatic retry of that same
action, not a new key per HTTP attempt.

Sample:

```
POST /api/campaigns
Idempotency-Key: 6f2b6e1e-2f3a-4a9b-9b0a-3c9b6b9f2a10
{ "name": "...", "job_title": "...", ... }

-> 201 { "id": "c1", "version": 1, ... }

# client's connection drops before it sees the 201; it retries the exact request
POST /api/campaigns
Idempotency-Key: 6f2b6e1e-2f3a-4a9b-9b0a-3c9b6b9f2a10
{ "name": "...", "job_title": "...", ... }

-> 200 { "id": "c1", "version": 1, ... }   # same id, no second campaign
```

### `PATCH /api/campaigns/{id}` — version/conflict checks

`CampaignOut` now includes `"version": <int>`, starting at `1` and incrementing by 1 on
every accepted `PATCH` and every `POST /{id}/status` transition (not on a no-op PATCH that
changes nothing).

Request body gains an optional field: `"expected_version": <int>`.

- Omitted: no conflict check, behavior unchanged (last write wins) — existing callers
  need no changes.
- Present and equal to the campaign's current `version`: PATCH applies normally.
- Present and **not** equal to the current `version`: the PATCH is rejected, no fields
  are changed, `409 Conflict` with a message naming the current and expected version.

A dependent UI that wants conflict protection reads `version` from the last `GET`/`PATCH`
response and echoes it back as `expected_version` on the next save; a screen that never
reads `version` gets the old unprotected behavior for free.

Sample:

```
PATCH /api/campaigns/c1  { "vacancies": 5, "expected_version": 1 }
-> 200 { "vacancies": 5, "version": 2, ... }

# a second tab/tab still holding version 1 tries to save
PATCH /api/campaigns/c1  { "vacancies": 9, "expected_version": 1 }
-> 409 { "detail": "Campaign was changed by someone else (have version 2, expected 1)" }
```

## Errors

| Status | Cause |
|---|---|
| `404` | Campaign id does not exist (unchanged) |
| `409` | `CampaignTransitionError` — invalid status transition (unchanged) |
| `409` | `CampaignConflictError` — `expected_version` stale (new) |

## What this does not fix

The UI half of `X18` — the campaign-setup screen calling create twice across JD-extraction
and final-assessment steps, and "Save as draft" only changing button text without saving —
is unchanged by this branch. The contract above gives that screen what it needs (a stable
`Idempotency-Key` held for the whole setup flow, and `version`/`expected_version` for a real
save), but wiring it in is Subhadeep's file (`web/new-campaign.html`) per
[08-TWO-PERSON-DELIVERY.md](../plan/08-TWO-PERSON-DELIVERY.md).

## Tests

`tests/test_campaigns.py`: `test_create_campaign_defaults_to_version_one`,
`test_retried_create_with_same_idempotency_key_returns_same_campaign`,
`test_create_without_idempotency_key_makes_separate_campaigns`,
`test_update_campaign_increments_version`,
`test_patch_with_correct_expected_version_succeeds`,
`test_patch_with_stale_expected_version_is_rejected`,
`test_status_transition_also_advances_version`.
