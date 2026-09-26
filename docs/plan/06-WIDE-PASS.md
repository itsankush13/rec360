# The wide pass — cover all of Recruitment 360, then build down

Ownership update: [08-TWO-PERSON-DELIVERY.md](08-TWO-PERSON-DELIVERY.md) supersedes
this document's historical screen-plus-router/agent allocation for current two-person
development. Preserve its coverage goals; do not restart old parallel assignments.

Written 2026-09-12 (Saturday). Overlay on `00-MASTER-BACKLOG.md` and `01-DEMO-MONDAY.md`.
Changes the **order** of the agreed plan. Changes none of its content.

## 1. The question and the answer

> Go wide across the whole recruitment 360 now, so the end-to-end feeling comes,
> then build depth into each feature afterwards. Is that possible?

Yes. It is already the agreed plan. One thing moves: the proxy screens for journey
steps 4–9, currently scheduled for **Sunday morning**, move to **Saturday afternoon**
and run in parallel. Sunday then becomes rehearsal, review and fix — not build.

That is the whole change. It buys one thing: Sunday's 14:00 review looks at a complete
journey instead of a half-built one, so the gaps it finds are real gaps and not just
unfinished work.

## 2. Why wide works here and does not produce mocks

The usual danger of a wide pass is twelve fake screens. This repo does not have that
problem, because the lifecycle state machine is already real:

- 17 states, a validated transition map, `app/core/lifecycle.py`
- a real hiring-manager handoff and a real manager verdict
- an append-only audit trail behind every disposition

So a "proxy" screen here is **not a mock**. It is a thin real screen that writes real
state and a real audit event, and only simulates the outward action — the email that is
not sent, the calendar invite that is not issued. That is the standard in
`01-DEMO-MONDAY.md` section 5, and every wide ticket must hold to it.

**The rule for every wide ticket: real state, real audit event, simulated outward action,
grey `SIMULATED` badge on the screen.** A screen that invents numbers is worse than no screen.

## 3. Coverage map — the ten journey steps of B01

| Step | What it is | Backend | Screen | Wide ticket |
|---:|---|---|---|---|
| 1 | CV imported | real | exists | — |
| 2 | AI screens the CV | real | exists | — |
| 3 | Shortlist / Hold / Reject | real | exists | — |
| 4 | Hiring-manager handoff | real endpoint | none | W-A |
| 5 | Interview scheduled | state only | none | W-B |
| 6 | Interview feedback | state only | none | W-B |
| 7 | HR discussion / approval | declared, nothing drives it | none | W-C |
| 8 | Offer drafted or sent | states only | none | W-D |
| 9 | Candidate accepts or declines | states only | none | W-D |
| 10 | Hired / Completed—Unsuccessful | real, terminal | none | W-A |

Cross-cutting, same wave:

| Ticket | Covers | Backlog |
|---|---|---|
| W-T | **Timeline screen — running now** | `B02`, unblocks `B01` and half of `B19` |
| W-E | Communication log — templates, simulated send, real audit row | `B10` |
| W-F | Semantic CV discovery over the local folder, plus a selection screen | `B03` / `D2` |
| W-G | Recruitment 360 dashboard rewired to lifecycle metrics | `B19` |

Every absent dashboard metric is a lifecycle metric. They became computable when the state
machine landed. `W-G` is the ticket that makes them visible.

## 4. Parallel rule — this is what makes the afternoon fit

One agent owns **one screen plus one router module**. No two agents touch the same file.

| Ticket | Owns screen | Owns router |
|---|---|---|
| W-T | `web/timeline.html` | none (read-only) |
| W-A | `web/handoff.html` | `app/api/handoff.py` |
| W-B | `web/interview.html` | `app/api/interviews.py` |
| W-C | `web/approvals.html` | `app/api/approvals.py` |
| W-D | `web/offer.html` | `app/api/offers.py` |
| W-E | `web/comms.html` | `app/api/messages.py` |
| W-F | `web/discover.html` | `app/api/discovery.py` |
| W-G | `web/performance.html` | `app/api/metrics.py` |

Shared files that agents must NOT edit, to avoid collision:
`app/main.py` router registration, `web/sw.js`, and the nav block in existing pages.
**The supervisor makes those three edits once, after each batch lands.**

Order: W-T alone first (it is running, and every other screen links into it).
Then batch one — W-A, W-B, W-D, W-F. Then batch two — W-C, W-E, W-G.

## 5. Schedule

| When | Work |
|---|---|
| Sat afternoon | W-T lands. Then batch one, four agents in parallel. |
| Sat, between batches | Supervisor wires routers, nav and `sw.js`. Runs the suite. |
| Sat evening | Batch two, three agents. Then `D4` and `D3` defect fixes. |
| Sat, end | Rehearsal run 1, timed. Update `SESSION-STATE.md`. |
| Sun morning | Fix what rehearsal 1 broke. Pre-seed demo data. |
| Sun 14:00 | The `B09` review, against a complete journey. |
| Sun evening | Fix what the review found. Rehearsal run 2. **Freeze.** |
| Mon | Go / no-go checklist. Demo. |

The two defect fixes `D4` (blank candidate name) and `D3` (32 of 40 requirements coming
back `INSUFFICIENT_EVIDENCE`) are **not** wide work and must not be delegated into a wide
ticket. They are on the go/no-go checklist. They are scheduled above on their own.

## 6. The deep pass — after the demo, not before

The wide pass creates this backlog deliberately. Ordered by how much it costs us if a
client looks closely:

1. **Real scoring correction — `B07`.** The approved rubric and the weights must actually
   change the ranking. This is the biggest credibility hole in the product.
2. **Evidence coverage.** Every scored criterion traced to a CV page or section.
3. **Turn each proxy into the real thing** — real email (`B10`), real scheduling (`B11`),
   real offer documents (`B12`), real approval routing (`B13`). Each proxy already writes
   real state, so each of these is a swap of the outward action, not a rewrite.
4. **SLA reminders and escalations** — the one B02 line the wide pass leaves unticked.
   `due_at` exists; no reminder code exists.
5. **`X11`** `funnel()` sorts by count, not stage order, and drops empty stages.
6. **`X12`** the leaderboard loads every evaluation then slices in Python.
7. **`X9`** `runtime.txt` pins 3.11 while everything runs on 3.13.5.
8. Hosting, security and data residency — `B22`.
9. FinOps and the commercial model — `B21`, `B23`.

## 7. Risks

- **Proxy drift.** An agent builds a screen that shows invented data instead of writing
  real state. Caught by: every wide ticket's acceptance line requires an audit row.
- **Router collision.** Two agents edit `app/main.py`. Prevented by the supervisor owning
  that file.
- **The suite goes red and nobody notices.** Every ticket runs `pytest -q` before and
  after, and reports both numbers.
- **Wide work eats the defect fixes.** `D3` and `D4` are on the go/no-go checklist. If the
  wide pass is not finished by Saturday evening, the defects still come first.

## 8. The demo CV repository (settled 2026-09-12)

Path: `..\CV-Repository` — one level up from this repo, outside git on purpose.
Extracted from `files (3) (1).zip`, which had never been unpacked.

12 CVs, 4 JDs, 3 CVs per JD. The set is deliberately difficult:

| JD | CVs | The hard part |
|---|---|---|
| Process Engineer | Youssef Al Attiyah, Daniel Cruz, Fahad Al Kuwari | polished / unstructured / multi-page tables |
| Process Operator | Suresh Nair, Hana Al Emadi, James O'Brien | scanned PDF / PPTX / poor format with header info |
| Maintenance Engineer | Abdulrahman Al Sada, Carlos Mendes, Priya Menon | tiny font / tables / date variations |
| HSE Officer | Tariq Al Naimi, Grace Owusu, Michael Fitzgerald | paragraph experience / skills spread / chaotic format |

Three files decide go/no-go:

- `Resume_ProcessOperator_SureshNair_ScannedPDF.pdf` — the OCR checklist line. It must not be held.
- the two `HeaderInfo` CVs — the likely source of `D4` / `X1`, the blank candidate name.
- `Resume_ProcessOperator_HanaAlEmadi.pptx` — PPTX is not a supported CV format. Expect a held
  file. Decide whether to drop her from the demo or show the hold as a feature.

`W-F` (semantic CV discovery, `B03` / `D2`) searches this folder. It is the demo repository
folder that `01-DEMO-MONDAY.md` section 6 leaves open.

The JDs stay where they are: the project root, duplicated in
`Recruitment-360-Delivery/sample-inputs/job-descriptions/`.
