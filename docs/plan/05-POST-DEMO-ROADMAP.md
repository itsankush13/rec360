# Post-demo roadmap

Starts Tuesday 2026-09-15. The demo is increment one, not the endpoint (`B24`).

Each increment is sized to be demonstrable on its own. Do not start an increment until the
previous one can be shown working.

## Proposed UX dependency adjustment — pending sequencing review

See `07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md` (B01/B14/B19). Pull durable campaign
setup/resume from B14 ahead of live integrations; establish B20 application correlation
before real send/reply processing and necessary B13 approval gates before real offers.
Use Act → Understand → Inspect disclosure across each increment. These are proposed
dependencies, not changed deadlines or claims of delivered work; tables below retain
the existing increment plan until sequencing is agreed.

---

## Increment 2 — turn the proxies into real integrations

Target: every step of the journey writes real state through a real integration.

| Order | Item | Backlog | Why this order |
|---|---|---|---|
| 1 | Local Outlook send through `pywin32` | `B10` | Everything downstream depends on an email leaving the machine |
| 2 | Application ID in the email subject | `B20` | Reply parsing cannot work without it |
| 3 | Reply parsing and stage update from the reply | `B10` | Closes the hiring-manager loop |
| 4 | Calendar invite through `pywin32`; track sent / accepted / declined | `B11` | Depends on 1–3 |
| 5 | Interview feedback capture from the reply or the workflow | `B11` | |
| 6 | Offer template, draft, send, track | `B12` | Last, because it needs the approval chain |

Exit test: one candidate completes all ten journey steps with no `is_simulated=True` row.

---

## Increment 3 — governance and data integrity

| Item | Backlog |
|---|---|
| Multi-level approvals by seniority | `B13` |
| Cost-centre controls and delegation of authority | `B13` |
| Mandatory approval evidence captured through email or system | `B13` |
| Interviewers and approvers recorded | `B13` |
| Critical behavioural / integrity flag | `B13` |
| "Do not consider for future recruitment" | `B13` |
| Separate campaign setup from CV ingestion; drafts; campaign and JD reuse | `B14` |
| Historical candidate reuse, waitlist, next-ranked surfacing | `B15` |
| SLA reminders and escalations | `B02` |

Exit test: an approval cannot be bypassed, and every approval has evidence attached.

---

## Increment 4 — scale and the review surfaces

| Item | Backlog | Note |
|---|---|---|
| Comparison page: one compact table, filters, pagination, top 10 first | `B16` | Design for 10,000–20,000 CVs. No full-population fetch. |
| What-if: preview-only, proposer separate from approver, no hardcoded approver | `B17` | Audit both proposed and approved versions |
| Candidate 360: every requirement traced, every discrepancy listed with severity | `B18` | Today it shows one discrepancy; it must show all |
| Recruitment 360 dashboard with filters and drill-down | `B19` | Full metric list in the backlog |

Exit test: a 200-CV campaign renders without a slow screen.

---

## Increment 5 — commercial and platform

| Item | Backlog | Owner |
|---|---|---|
| HR FinOps tab, full cost model, 10,000-CV scenario, market comparison | `B21` | Subhadeep + Chiranjib |
| Client volumetrics confirmed (chase Alrana) | `B21` | Subhadeep |
| Qatar data residency, approved hyperscaler, region availability, test migration | `B22` | Chiranjib + Subhadeep |
| Tenant isolation, authentication, secure profiles, service mailbox, onboarding | `B22` | |
| QChem commercial positioning, SmartRecruiters and UiPath comparison, indicative cost | `B23` | Chiranjib + Kallol |

---

## The one decision that cannot be deferred much longer

`B23` long-term model: **bespoke asset, or multi-customer subscription product.**

These lead to different architectures. A subscription product needs customer onboarding,
login and profile management, tenant security, hosted infrastructure, and ongoing operations.
None of that exists today, and none of it should be implied in front of a client.

Take this decision after the Monday demo and before Increment 3 starts, because governance and
tenant isolation are built differently under each model.

Record the decision in `docs/DECISIONS.md`. If it is hard to reverse and the result of a real
trade-off, write an ADR under `docs/adr/`.
