# Monday demo plan

Demo: Monday 2026-09-14, client session (QChem).
Internal review: Sunday 2026-09-13, 14:00 IST.
Written: Saturday 2026-09-12. **Two working days remain.**

UX planning update, 2026-09-12 (B01/B14/B19):
- [x] Refine `07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md` with progressive disclosure and roadmap dependencies; planning artifact only.
- [ ] Rehearse and accept any implemented UX slice before using it in demo; existing D1–D4 priorities and go/no-go gates remain unchanged.

---

## 1. The one rule for this demo

**Go wide, not deep.** Show the whole recruitment lifecycle end to end for one named
candidate. Add depth only where the flow genuinely needs it.

A client who sees ten connected steps with three of them labelled "proxy" believes in the
product. A client who sees two perfect steps and seven missing ones does not.

**Never present a proxy screen as working software.** Every non-functional step carries a
visible badge. See section 5.

---

## 2. Honest current state

This is what exists in `talent-intelligence-system/` at HEAD `fe84e46`, verified live on
2026-09-12 (437 tests pass, Azure verified live, full campaign driven end to end in 37.9s).

### Already live — real code, real data, real LLM

| Capability | Evidence |
|---|---|
| Campaign create | Phase A API, driven end to end |
| JD upload + requirement extraction | 40 requirements from one JD, live LLM, 11.6s |
| Rubric seed → normalise → submit → approve | v1 approved in the live run |
| CV batch upload | 3 CVs inline, 9.5s |
| OCR on scanned PDFs | Real scanned CV, 1168 chars, `text_source=ocr`, 11.7s |
| Evaluation run (`LLM_ASSISTED`) | 15.7s, LLM refinement confirmed firing |
| Leaderboard + evaluation detail | Rendered live on :8124, no console errors |
| Candidate 360 | Commit `f31d2db` |
| Compare · What-if · KPI aggregates | Commit `8eca00d` |
| Decisions (Shortlist / Hold / Reject / Interview) | `CandidateAction`, append-only |
| Audit trail with candidate IDs, filters, CSV export | Commit `fe84e46` |
| Exports: Candidate 360 PDF, CSV, XLSX, SuccessFactors mapping | Commit `441f1fd` |
| Developer / cost tab | `web/developer.html` exists |
| Azure cost model | Measured from real tokens, not estimated |

### Not built at all — the demo gap

| Missing | Backlog ID | Blocks journey step |
|---|---|---|
| ~~Recruitment lifecycle state machine~~ — **built**, `77d3c49`, 12 states | `B02` | — |
| Timeline / journey view | `B02` | 1–10 |
| ~~Hiring-manager handoff and approval~~ — **built**, `77d3c49`, real endpoints | `B13` | — |
| ~~Email out and reply parsing (Outlook / `pywin32`)~~ — **both halves built server-side**: outbound (`app/core/outlook_adapter.py`, `app/api/reports.py`) and inbound (`app/core/reply_ingestion.py`, `app/core/reply_classifier.py`, `app/api/replies.py`) — fake-COM/API tests pass, live mailbox send/read unverified. See `00-MASTER-BACKLOG.md` B10, `docs/SESSION-STATE-b10-outbound.md`, `docs/SESSION-STATE-b10-inbound.md`. Not wired into any `web/*.html` screen yet; journey-step proxy labelling below is unchanged until that UI work lands. | `B10` | 4, 8, 9 |
| Interview scheduling and calendar invites | `B11` | 5 |
| Interview feedback capture | `B11` | 6 |
| HR discussion stage | `B13` | 7 |
| Offer draft, send, track | `B12` | 8, 9 |
| Semantic CV discovery over a repository | `B03` | 1 |
| AI-generated JD | `B06` | before 1 |
| SLA reminders and escalations | `B02` | all |

`app/core/email_sender.py` exists but no route calls it — it is dead code, superseded by
`app/core/outlook_adapter.py`. `pywin32`/`win32com` are now in the tree (`outlook_adapter.py`,
`calendar_adapter.py`; unit-tested against a fake COM double, never against a real signed-in
Outlook profile). There is still no SharePoint or Microsoft Graph code anywhere — treat that
one as not started.

---

## 3. Demo scope decision

Build these four things in the two remaining days. Everything else is proxy or existing.

| ID | Build | Why it is not optional |
|---|---|---|
| `D1` | Lifecycle state model + timeline view (`B02`) | The spine. **Backend now exists** — Ankush's `77d3c49`: 12 states, users and roles, handover, manager review, and a full API including `GET .../{candidate_id}/timeline`. Remaining: port the offer/hired states, build the timeline screen, proxy steps 5-9, auto-enter on shortlist. See `02-LIFECYCLE-MODEL.md`. |
| `D2` | Semantic CV discovery over a local folder standing in for SharePoint (`B03`) | The client asked for "no manual selection". Embeddings and BM25 already exist in the tree, so the cost is a retrieval call plus one screen. |
| `D3` | Requirement-granularity fix (`B07` / defect `X2`) | A leaderboard that says "confirmed on 6 of 40" makes good candidates look bad. The client will see this. **Option 2 built and decision recorded 2026-09-13 — see `04-KNOWN-DEFECTS.md` X2 and `docs/DECISIONS.md`.** |
| `D4` | Blank candidate name fix (defect `X1`) | The leaderboard shows "Unknown" for 1 of 3 real CVs. **Fixed 2026-09-12, commit `8fdbc32`, re-verified 2026-09-13 — see `04-KNOWN-DEFECTS.md` X1.** |

Do these if time remains, in this order:

| ID | Build | Cost |
|---|---|---|
| `D5` | Rename Developer tab to HR FinOps and plug in the measured cost numbers (`B21`) | Low. **The numbers did not already exist — `/api/developer/metrics` was missing entirely; built 2026-09-13, see `00-MASTER-BACKLOG.md` B21.** |
| `D6` | Colour semantics pass: green/amber/red/grey (`B08`) | Low. CSS only. |
| `D7` | AI-generated JD (`B06`) | Medium. One LLM call plus one screen. **Wired 2026-09-13: "Generate with AI" tab on `web/new-campaign.html` step 2 calls `POST /jd/generate` and fills the JD textarea. Extended 2026-09-15: a one-sentence AI-first entry point on `web/start-campaign.html` (`POST /api/campaigns/ai-start`) drafts the whole campaign — JD, requirements and rubric — from a recruiter's free-text hiring request; browser-verified live against the real Azure deployment. Strong demo moment: "I tell the AI what I need, it prepares the campaign" without a form.** |
| `D8` | Comparison page compaction: one table, top 10 first (`B16`) | Medium. |

Explicitly **not** before Monday: real email, real calendar, real offer letters, real
SharePoint connection, SLA escalation engine, multi-level approvals, tenant isolation.

---

## 4. The demo journey, step by step

One named demo candidate. Agree the name on Saturday and use it everywhere.

| # | Step | Status Monday | Backed by |
|---|---|---|---|
| 1 | CV discovered from the repository | **LIVE (`D2`)** | Semantic search over a local folder |
| 2 | AI screens the CV | **LIVE** | Real Azure run, real OCR, real evidence |
| 3 | Shortlist / Hold / Reject | **LIVE** | `CandidateAction`, append-only, audited |
| 4 | Hiring-manager handoff | **PROXY** | Named owner and real state/audit row. No email sent. |
| 5 | Interview scheduled | **PROXY** | Time, panel and real state/audit row. No calendar write. |
| 6 | Interview feedback received | **PROXY** | Form that writes the real lifecycle state and a real audit event |
| 7 | HR discussion | **PROXY** | Same pattern |
| 8 | Offer drafted or sent | **PROXY** | Package and revisions recorded. No letter or email sent. |
| 9 | Candidate accepts or declines | **PROXY** | Manual response capture and lifecycle state change. No reply ingestion. |
| 10 | Hired, or Completed—Unsuccessful | **LIVE** | Terminal lifecycle state, real audit trail |

**The important design point:** every proxy step still writes a real state transition and a
real audit event. The state machine, the timeline, and the audit trail are genuine. Only the
outbound integration (email, calendar, document delivery) is simulated. That is a truthful
story and it is the one to tell.

`web/pipeline.html` now opens all seven journey workspaces. `web/approvals.html`,
`web/offer.html`, `web/handoff.html`, `web/interview.html` and `web/comms.html` are
implemented as local proxy screens. The candidate's reply is entered by a person; no
inbound integration is implied.

---

## 5. Proxy labelling standard

Every simulated step must carry this on screen, not in the speaker notes:

- A grey badge reading `SIMULATED — INTEGRATION PENDING` next to the action button.
- A one-line caption naming what will replace it, for example:
  "Preview only. Outlook send arrives in the next increment."
- Grey, never green. Green is reserved for confirmed and successful (`B08`).

Rule: if a client could screenshot it and believe it works, it is mislabelled.

---

## 6. Two-day schedule

### Saturday 2026-09-12 (today, from ~11:30)

- [ ] Agree the demo candidate name, the demo role, and the demo repository folder
- [ ] `D4` blank candidate name fix — smallest item, do it first for momentum
- [ ] `D3` requirement-granularity fix, then re-run the campaign and check the confirmed count
- [x] `D1` lifecycle backend — taken from Ankush's `77d3c49`, not rebuilt
- [ ] Commit the `py313-upgrade` branch — **14 files are still uncommitted**
- [ ] Update `docs/SESSION-STATE.md`

### Sunday 2026-09-13, morning

- [ ] `D1` timeline view (frontend), wired to the real state machine
- [ ] `D2` semantic CV discovery over the local folder, plus the selection screen
- [ ] Proxy screens for steps 4–9, each writing real state and real audit events
- [ ] Full rehearsal run 1, end to end, timed

### Sunday 2026-09-13, 14:00 IST — review (`B09`)

- [ ] Walk the full journey in front of the team
- [ ] Record every gap found
- [ ] Decide what is fixable before Monday and what gets labelled instead

### Sunday 2026-09-13, evening

- [ ] Fix what the review found
- [ ] `D5`, `D6` if time remains
- [ ] Full rehearsal run 2, timed
- [ ] Freeze the code. No changes after the freeze.

### Monday 2026-09-14, before the session

- [ ] Run the go/no-go checklist in section 7
- [ ] Pre-seed the demo data so nothing depends on a live upload succeeding on the call
- [ ] Have a recorded fallback of the full journey in case the live run fails

---

## 7. Go / no-go checklist — run this Monday morning

Environment:
- [ ] `$env:QUEUE_BACKEND = "inline"` is set in the API terminal.
      Without it, uploads sit `QUEUED` forever and every screen looks empty.
- [ ] API up: `.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`
- [ ] Frontend up: `cd web ; python -m http.server 8124`
- [ ] `.\venv\Scripts\python.exe -m pytest -q` is green
- [ ] Azure key valid and a live call returns

Data:
- [ ] The demo campaign exists and its rubric is approved
- [ ] The demo candidate has a name, not "Unknown"
- [ ] The leaderboard confirmed count looks sensible, not "6 of 40"
- [ ] The scanned PDF CV goes through OCR without a hold
- [ ] The audit trail shows every step of the demo journey

Presentation:
- [ ] Every proxy step carries its grey `SIMULATED` badge
- [ ] No console errors on any screen
- [ ] Browser zoom and window size set; no horizontal scrolling on any screen
- [ ] Fallback recording ready

---

## 8. Demo script — the order to tell it in

1. **Open on the Recruitment 360 view.** Campaign in flight, stage visible at a glance.
2. **Repository discovery.** "We point it at the CV repository. It finds the relevant ones."
   Show 5 in, 2 selected, with the reason each was selected.
3. **Screening.** Real run, live. Show the scanned PDF being read by OCR — this is a strong
   moment and it is genuinely working.
4. **Leaderboard.** Ranked, with evidence behind each score.
5. **Candidate 360.** Requirement traced to CV evidence. Discrepancies listed with severity.
   AI-generated interview questions.
6. **Decision.** Shortlist, with the AI recommendation pre-selected and the rationale
   pre-filled. Override it live to show the human stays in control.
7. **The timeline.** Switch to the journey view. Walk all ten steps.
   Say plainly which are live and which are simulated.
8. **Audit trail.** Every step just taken appears, with actor, timestamp, and IDs.
   Filter it. Export it.
9. **HR FinOps.** Real measured cost. $2.65 for 200 CVs. $132 for 10,000.
   Business numbers, not Azure jargon.
10. **Close on the roadmap.** This is increment one, not the endpoint. Point at
    `05-POST-DEMO-ROADMAP.md`.

Time target: 25 minutes of demo, 20 minutes of discussion.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Live Azure call fails or is slow during the session | Pre-seed the demo data; keep the recorded fallback |
| Lifecycle model (`D1`) is not finished by Sunday review | Cut `D7` and `D8` first. `D1` is never the thing that gets cut. |
| Client asks "can we send the email now?" | Answer plainly: not in this increment, it is the next one. Do not improvise. |
| 14 uncommitted files are lost | Commit today. This is the cheapest risk to remove. |
| `QUEUE_BACKEND` not set on the demo machine | It is item one on the go/no-go checklist |
