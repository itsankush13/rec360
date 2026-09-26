# Recruitment lifecycle model

Backlog: `B02`. Demo build item: `D1`. This is the spine of the product.

**Status 2026-09-12: the backend exists, and the offer/hired tail is ported.** Ankush built and pushed it as `77d3c49`
("Recruitment lifecycle phases 0-1: users, state machine, handover, manager review") on
`azure-provider`. This document now describes *his* model and the gap between it and the
client's requested state list. It is a port list, not a design.

A second, parallel implementation was built the same afternoon and thrown away. See
`X10` in `04-KNOWN-DEFECTS.md`.

---

## What exists

| Piece | Where |
|---|---|
| `LifecycleStatus` enum, 17 members (12 his + 5 ported) | `app/db/models.py` |
| `CandidateLifecycle` — the operative row per candidate per campaign, superseded not edited | `app/db/models.py` |
| `LifecycleTransition` — every move, with actor and reason | `app/db/models.py` |
| `UserRole` and users | `app/db/models.py` |
| Transition rules | `app/core/lifecycle.py` |
| Service layer | `app/services/lifecycle_service.py` |
| HTTP API | `app/api/lifecycle.py` |
| Migration | `d7b3e81c4a05` |

Two design decisions worth keeping and not relitigating:

1. **Current status is stored, never derived on read.** A status nobody can point at a
   transition for is a status nobody can audit. It also removes the tie-break problem that
   deriving "the latest row" creates.
2. **Only shortlisted or interview candidates enter the lifecycle.** It is a record of a
   hiring process, not of everyone who applied. So there are deliberately no
   `APPLICATION_RECEIVED` or `SCREENING_*` states.

---

## The 17 states

His 12: `SHORTLISTED` · `WITH_HIRING_MANAGER` · `RETURNED_TO_RECRUITER` ·
`INTERVIEW_SCHEDULED` · `FEEDBACK_COMPLETE` · `PENDING_APPROVAL` · `PENDING_COST_CENTRE` ·
`APPROVED` · `CLOSED` · `ON_HOLD` · `NOT_PROCEEDING` · `WITHDRAWN`

Ported 2026-09-12: `OFFER_DRAFTED` · `OFFER_SENT` · `OFFER_ACCEPTED` · `OFFER_DECLINED` ·
`HIRED`

The offer path: `APPROVED -> OFFER_DRAFTED -> OFFER_SENT -> OFFER_ACCEPTED -> HIRED`.
`OFFER_SENT -> OFFER_DRAFTED` re-issues a revised offer. `OFFER_ACCEPTED -> WITHDRAWN`
stays open, because a candidate who accepts can still not join. `OFFER_DECLINED -> CLOSED`,
with a reason required. `HIRED` is terminal and admin-only.

Verified independently of the test suite: every state is reachable from `SHORTLISTED`,
there are no non-terminal dead ends, and no enum name leaks into a reader-facing string.

## The API

| Method | Path | Purpose |
|---|---|---|
| GET | `/campaigns/{id}/lifecycle` | Every candidate's status |
| GET | `/campaigns/{id}/lifecycle/funnel` | Stage counts |
| GET | `.../{candidate_id}` | One candidate's status |
| GET | `.../{candidate_id}/timeline` | **The timeline view's data source** |
| POST | `.../{candidate_id}/enter` | Enter the lifecycle |
| POST | `.../{candidate_id}/send-to-manager` | Journey step 4, for real |
| POST | `.../{candidate_id}/review` | Manager verdict — proceed / decline / question |
| GET | `.../{candidate_id}/reviews` | Review history |
| POST | `.../{candidate_id}/transition` | Move a candidate |

---

## Gap against the client's requested states

The client listed 14 rows. Mapping them onto the 17 states:

| # | Client asked for | Covered by | Gap |
|---|---|---|---|
| 1 | Application received | — | **By design.** Only shortlisted candidates enter. |
| 2 | Screening pending / completed | — | **By design.** Same reason. |
| 3 | Shortlisted / held / rejected | `SHORTLISTED`, `ON_HOLD`, `NOT_PROCEEDING` | Covered |
| 4 | Sent to hiring manager | `WITH_HIRING_MANAGER` | Covered |
| 5 | HM approved / rejected | `INTERVIEW_SCHEDULED`, `NOT_PROCEEDING`, `RETURNED_TO_RECRUITER` | Covered, and richer |
| 6 | Interview scheduled | `INTERVIEW_SCHEDULED` | Covered |
| 7 | Interview accepted / declined | — | **Gap** |
| 8 | Feedback pending / received | `FEEDBACK_COMPLETE` | Partial — no explicit pending |
| 9 | Passed / rejected after interview | `PENDING_APPROVAL`, `NOT_PROCEEDING` | Partial |
| 10 | HR discussion | `PENDING_APPROVAL` | Approximate |
| 11 | Offer pending / drafted / sent | `APPROVED`, `OFFER_DRAFTED`, `OFFER_SENT` | Covered |
| 12 | Offer accepted / rejected | `OFFER_ACCEPTED`, `OFFER_DECLINED` | Covered |
| 13 | Hired | `HIRED` | Covered — terminal, distinct from `APPROVED` |
| 14 | Recruitment completed unsuccessfully | `NOT_PROCEEDING`, `CLOSED`, `WITHDRAWN` | Covered |

### The port list — what to add

- [x] Offer stages: `OFFER_DRAFTED`, `OFFER_SENT`. No separate "offer pending" —
      `APPROVED` already means approved to hire with no offer drafted yet.
- [x] Offer outcome: `OFFER_ACCEPTED`, `OFFER_DECLINED`. Declined, not rejected —
      `NOT_PROCEEDING` is the company declining the candidate; this is the reverse.
      A reason is required. The reader sees "Offer declined by the candidate".
- [x] A real `HIRED` terminal state, distinct from `APPROVED`. `OFFER_ACCEPTED -> WITHDRAWN`
      stays reachable, so `HIRED` means joined rather than agreed. Admin only.
- [ ] Interview invite response: accepted / declined
- [ ] Explicit feedback-pending, so the timeline can show who is being waited on

Rows 1 and 2 stay out. His reasoning is sound and the screening record already lives in
`EvaluationRun` and the audit trail. **But the demo journey shows step 1 and step 2**, so the
timeline screen must render those two from the evaluation record rather than the lifecycle,
and say so.

- [x] Timeline screen renders discovery and screening from the evaluation record, not the
      lifecycle — `web/timeline.html`, steps 1 and 2 of the spine, reading
      `GET /api/processing/candidates/{id}` and
      `GET /api/campaigns/{id}/candidates/{id}/evaluations`
- [ ] Automatic entry: a shortlist disposition should call `enter` + `SHORTLISTED` rather
      than needing a separate manual step

---

## What every transition records

Already implemented in `LifecycleTransition`. For the demo, the field that matters is a
marker separating a real integration from a simulated one. Steps 5-9 of the demo journey are
proxies: they must write a real transition and a real audit event, and be visibly labelled.

- [ ] Confirm whether `LifecycleTransition` carries a simulated/proxy marker; add one if not

---

## SLA reminders and escalations

Designed as phase 5 in Ankush's brief: a target duration per stage, a due date, reminders
before and escalation after, clocks stopping on hold, every reminder itself an audit event.

Not before Monday. For the demo, show an amber badge on any stage past its due time.

---

## Remaining `D1` work

1. Port the two remaining states above: interview accepted/declined, explicit feedback-pending
2. ~~Timeline screen against `GET .../{candidate_id}/timeline`~~ — done, `web/timeline.html`
3. Proxy actions for journey steps 5-9, each writing a real transition
4. Automatic lifecycle entry on a shortlist disposition
