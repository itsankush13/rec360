# Plan index

Start with [the agent execution guide](../../AGENT-START-HERE.md): one entry point
for reading every plan, checking done versus left, progressing and updating evidence.

Created 2026-09-12. This folder is the cemented record of the full product vision,
the Monday demo plan, and the checklist that tracks both.

## Canonical tree warning

Only `talent-intelligence-system/` is live code. These sibling folders are dead prototypes:
`app/`, `app-v2/`, `talent-intelligence-system-final/`, `Recruitment-360-Delivery/`.
Their `SESSION-STATE.md` files name the wrong tree as canonical. Do not read or edit them.

## The documents

| File | What it holds | Read it when |
|---|---|---|
| `00-MASTER-BACKLOG.md` | All 24 backlog items, P0/P1/P2, with stable IDs and checkboxes | Planning any work |
| `01-DEMO-MONDAY.md` | The 2-day demo plan, honest LIVE/PROXY/FUTURE status, hour schedule, go/no-go gate, demo script | Now, and every hour until Monday |
| `02-LIFECYCLE-MODEL.md` | The 14 recruitment states, transitions, owners, SLA hooks | Building B01 and B02 |
| `03-IDENTIFIER-MODEL.md` | Campaign / Candidate / Application / Run ID contract | Building anything that emits an ID |
| `04-KNOWN-DEFECTS.md` | Defects a client could hit, with severity and fix cost | Before any demo rehearsal |
| `05-POST-DEMO-ROADMAP.md` | P1 and P2 sequenced after Monday | Tuesday onward |
| `06-WIDE-PASS.md` | End-to-end coverage and historical wide-pass delivery overlay | Reconciling journey coverage and proxy scope |
| `07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md` | B01/B14/B19 campaign journey, Act → Understand → Inspect disclosure, full-roadmap mapping and proposed delivery gates | Reviewing or implementing campaign UX |
| `08-TWO-PERSON-DELIVERY.md` | B01–B24/defect allocation, exclusive file owners, shared-baseline and GitHub PR workflow | Before any Subhadeep/Ankush parallel development |

## How to use the checklist

Every item has a stable ID (`B01`, `D3`, `X2`). Never renumber. Update the box in place:

- `[ ]` not started
- `[~]` in progress
- `[x]` done and verified
- `[-]` deliberately dropped, with a reason on the line

Update `docs/SESSION-STATE.md` at the end of every session. This folder holds the *plan*;
SESSION-STATE holds *where we actually are*.
