# Backlog/defects reconciliation correction — 2026-09-13

## Acting developer
Ankush (verification only, no product code changed this session).

## Why this exists
User asked "what's left for Ankush," pasted a status line claiming B06/B07/B20
were all "Open, backend not started at all." Before building B06, checked the
code directly: **already merged.** Same for B07. That prompted a full check of
every Ankush-owned handoff in `docs/handoffs/ankush/` against actual git log,
files, and re-run tests, instead of trusting `00-MASTER-BACKLOG.md`/
`04-KNOWN-DEFECTS.md` text. Most of those handoffs' suggested deltas were never
applied — this is the backlog of unapplied deltas in one place, verified fresh
this session (not copied from the handoffs' own claims).

## Verified this session (re-ran tests / read code directly, 2026-09-13)
- `git log --oneline` on `consolidated`: B06 (`c88c888`/merge `b6f771a`), B10
  (`b4fc4c1`/merge `d20d586`), B12 (`67a5b44`), B15 (`3727515`), X6
  (`5177174`), X12 (`db81b83`) are all real commits on current HEAD.
- `tests/test_jd_generation.py`: 5/5 passing (B06).
- `tests/test_audit_page_maps_every_action_to_plain_english`: passing —
  `AuditAction` now includes `INTERVIEW_SCHEDULED`, `INTERVIEW_FEEDBACK_RECORDED`,
  `OFFER_SENT`, `OFFER_DRAFTED`, `OFFER_RESPONSE_RECORDED`, `MESSAGE_SENT`,
  `APPROVAL_REQUESTED/GRANTED/RETURNED`, all labeled in `web/audit.html`.
- Full suite fresh: **612 passed, 6 skipped, 0 failed** (618 collected).
- `app/db/models.py` / `app/api/approvals.py`: confirmed `cost_centre_code` is
  only a request field logged into `AuditEvent.after`, not a persisted model
  column — B13's "no cost-centre field on any model" claim is **not** stale,
  it's still accurate.
- `03-IDENTIFIER-MODEL.md` / `app/db/models.py`: confirmed B20 is genuinely
  zero code.

## Requested `00-MASTER-BACKLOG.md` deltas

**B03** — change summary from "Tier 1 built; the semantic half is not" to
"Tier 1 built; ranking backend built and merged (`0864473`); screen still
manual." Tick:
```
- [~] Find role-relevant CVs automatically — API built (`POST /discovery/resolve`
      with optional `campaign_id`, `app/core/cv_relevance.py`), merged.
      `web/discover.html` doesn't send `campaign_id` or show the score yet.
```

**B04** — change "5 of 10 event types" line: `INTERVIEW_SCHEDULED`,
`INTERVIEW_FEEDBACK_RECORDED`, `OFFER_DRAFTED/SENT/RESPONSE_RECORDED`,
`MESSAGE_SENT` all now exist and are labeled. Update the count and the
"Absent" list — only generic-only items (HR decision → `STATUS_CHANGED`) and
approval-evidence-artifact remain genuinely open.

**B06** — change owner line from "Nothing built" to "Backend built and
merged (`c88c888`). Preview-only endpoint, template floor, uncertainty
flagging." Tick the five items per
`docs/handoffs/ankush/2026-09-12-b06-jd-generation.md`'s suggested delta
(already written, never applied) — screen-wiring line stays unchecked.

**B07** — change "Not audited in this pass" to "Backend essentially
complete, audited 2026-09-12." Tick per
`docs/handoffs/ankush/2026-09-12-b07-scoring-audit.md` — sliders (UI) and
the JD-fixture-blocked test stay unchecked; bonus-points line stays as a
recorded decision ("leave as-is"), not a gap.

**B10** — tick "Use the local Outlook mailbox through pywin32" as `[~]`
(adapter built/tested against fake COM, never against a real mailbox, off by
default). Other four lines unchanged (still genuinely open, blocked on a
real mailbox).

**B11** — tick "create a calendar invite" and "block interviewer/candidate
calendars" as `[~]`, same real-mailbox caveat as B10. Other lines unchanged.

**B12** — tick per `docs/handoffs/ankush/2026-09-12-b12-offer-letter.md`'s
suggested delta (template, draft-for-review, audit trail are `[x]`; send is
`[~]`; screen display still open).

**B14** — tick "Support drafts" `[x]` and add a new line: "`[x]` Retry
protection / version-conflict checks — `Idempotency-Key` on create,
`expected_version` on PATCH, `docs/contracts/B14-campaign-draft.md`."

**B15** — tick three of four lines `[~]` per
`docs/handoffs/ankush/2026-09-12-b15-candidate-reuse.md`'s suggested delta.
Fourth line (exclusion-flag retention) stays open, blocked on B20.

## Requested `04-KNOWN-DEFECTS.md` deltas
- **X6**: tick `[x]` — fixed on `consolidated` at `5177174`.
- **X12**: tick first and third boxes `[x]` (SQL limit/offset merged at
  `db81b83`; benchmarked at 1,200 rows, 99ms, `LIMIT 10` confirmed in SQL).
  Second box (comparison-page top-10 UI) stays open, Subhadeep's file.
- Consider adding a new defect entry for the Python 3.11/3.13.5-claimed/
  3.12.10-actual three-way mismatch — flagged in at least four separate
  Ankush handoffs now (B10, B14, X13/X15/X16, B22-CI) and still untracked.

## Not corrected / still accurate as-is
B02, B13, B16 (UI half), B19, B20, B21, B22, B23 — checked directly this
session, no stale claims found in these.

## Next
Subhadeep to review and apply. No product code was touched this session —
this is a documentation-accuracy pass only.
