# Demo runbook — QChem, 2026-09-14

Companion to [DEMO-READINESS-2026-09-14.md](DEMO-READINESS-2026-09-14.md), which has the full
audit and evidence log. This file is the thing to have open during the session.

## 0. What's seeded, right now

Seeded via `scripts/seed_demo.py` on this machine (2026-09-14, Subhadeep). Idempotent — safe to
re-run; it will report "already seeded" and change nothing if run again.

**MACHINE-SPECIFIC VALUES (this machine only; different from the original Ankush session):**

| Role | JD library entry | Campaign | Status today | Candidates & scores |
|---|---|---|---|---|
| Maintenance Engineer | ✓ (`JD_Maintenance_Engineer.docx`) | **Campaign A** `5618904f-c91c-4e87-8975-35a76fc04ab0` (`RC20260914-82963`) | **Interview scheduled**, awaiting feedback. Candidate: **Abdulrahman Al-Sada** (score 69.47). | 3 uploaded: Abdulrahman Al-Sada 69.47, Priya Menon 48.72, Carlos Mendes 31.71 |
| **Process Engineer** (substituted) | ✓ (`JD_Process_Engineer (1).docx`) | **Campaign B** `4a16f573-b7f8-40ac-bded-5c759e8f00da` (`RC20260914-82058`) | **Offer sent**, awaiting response. Candidate: **Fahad Al-Kuwari** (score 74.65). Cost centre demo envelope (BU, currency, budget holder, fiscal year, salary band). | 3 uploaded: Fahad Al-Kuwari 74.65, Youssef Al-Attiyah 74.64, Daniel Cruz 51.92 |
| Process Operator | ✓ (`JD_Process_Operator.docx`) | **Campaign C** (built live via browser, not seeded script). | **Screened, not yet decided** — the live-walkthrough segment. | 3 uploaded (Hana Al-Emadi, Suresh Nair with scanned PDF, one unnamed/flagged) |
| HSE Officer | ✓ (`JD_HSE_Officer.docx`) | **Campaign D — none.** Deliberately untouched. Backup only. | — | Unused; candidates available but not uploaded. |

People created for the demo (all `@qchem-demo.example`, all synthetic): Layla Haddad
(Recruiter), Yusuf Al-Marri (Hiring Manager, Campaign A), Noora Al-Thani (Hiring Manager,
Campaign B, though Campaign B role has changed), Imran Qureshi (Admin / budget holder).

**Named live-demo candidate for the fresh walkthrough (Campaign C): Suresh Nair** — his CV is
the scanned PDF, and OCR genuinely read it (see §6). Do **not** feature the third Process
Operator candidate live — his name extraction failed on a deliberately hard-to-parse CV and he
is correctly flagged `requires_review`, which is honest but not the story to tell live; Hana
Al-Emadi is a safe second choice if Suresh's card is somehow unavailable.

Also seeded on top of the 45 pre-existing dev/test campaigns already in this database — those
are untouched (no destructive reset), and stay out of the way: use the **filter box on Start
Campaign** (type "QChem Demo") to show only Campaigns A/B/C.

## 1. Startup (morning of)

```powershell
$env:QUEUE_BACKEND = "inline"
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
Second terminal:
```powershell
cd web
python -m http.server 8124
```

**This exact QUEUE_BACKEND step matters and was not theoretical today**: the API process
already running when this session started had been launched without it, and a live batch
upload against it sat `QUEUED` forever. Confirm the terminal that starts `uvicorn` is the one
where `$env:QUEUE_BACKEND` was just set, in the same shell, same session — it does not persist
across terminals or reboots.

## 2. Go/no-go checklist

- [ ] `QUEUE_BACKEND=inline` confirmed set in the API terminal (check: upload a test file and
      confirm its job leaves `QUEUED` within a few seconds — a real batch response's
      `"queue_backend"` field reads `"inline"`)
- [ ] `.\venv\Scripts\python.exe -m pytest -q` → 802 passed, 1 warning in 1199.63s (verified
      2026-09-14, see readiness doc evidence log; re-run once more this morning if desired)
- [ ] Azure OpenAI key valid — `.env` has `AZURE_OPENAI_*` set; a real extraction/evaluation
      call returns (proven repeatedly today building Campaigns A/B/C)
- [ ] `rapidocr` installed (`.\venv\Scripts\python.exe -c "import rapidocr"` — must not error).
      **This was missing at the start of today's session** and has been installed; if the demo
      runs from a different venv/machine, confirm this there too
- [ ] **Browser hard-reload done at least once on the demo machine before the client call** — 
      asset version strings were bumped today (`app.js?v=17`, `campaign-list.js?v=17`,
      `journey.js?v=2`) to defeat service-worker and browser caching. A normal reload may still 
      serve a stale cached copy (this happened during today's own verification and hid recent 
      fixes). Press Ctrl+Shift+R (or Cmd+Shift+R on Mac) to force-reload; if pages still show 
      old state, unregister the service worker and clear site data before the session.
- [ ] Start Campaign, filtered to "QChem Demo", shows exactly Campaigns A and B with their
      correct distinct stage labels ("Interview scheduled" / "Offer sent, awaiting response") —
      **verify the labels match THIS MACHINE's seeded state, not Ankush's original session**
- [ ] No console errors on: start-campaign.html, jd-library.html, leaderboard.html,
      candidate.html, approvals.html, offer.html, interview.html, pipeline.html
- [ ] **Stray campaign verification**: `Start Campaign` should show exactly Campaigns A (Maintenance 
      Engineer) and B (Process Engineer) when filtered to "QChem Demo". A third campaign 
      ("QChem Demo - Campaign C - Process Operator") was created during verification work and was 
      deliberately deleted (RC20260914-25591, id 017110bb-f6c3-430a-a561-0fedb36d2c4b). If it 
      reappears, note that Process Operator is reserved for live walkthrough only and must not be 
      seeded ahead of time.
- [ ] Fallback recording available (see §7) in case anything above fails live

## 3. The 30-minute path

1. **Start Campaign** (2 min). Open filtered to "QChem Demo". Point at the two real, distinct
   stage labels on Campaigns A and B — this is live API state, not a mock. Mention the JD
   library link.
2. **JD library** (2 min). Open `jd-library.html`. Four saved JDs, all QChem-branded. Click
   "Use for a new campaign" on Process Operator — this is exactly how Campaign C started
   today.
3. **Campaign C, live setup** (5 min). Role/site/hiring-manager fields already prefilled from
   the library selection; fill vacancies/hiring manager/BU/recruiter live, save. Move to
   "Read the description" → rubric review → approve. (This exact sequence was run for real
   on THIS machine: Process Operator role, JD 2,628 chars, rubric approved in one pass.)
4. **Upload the 3 Process Operator CVs live** (3 min) — `.pptx` (Hana Al-Emadi), a poorly
   formatted `.docx`, and the **scanned PDF** (Suresh Nair). Run the evaluation.
5. **Screening / OCR moment** (2 min). While the run completes, say plainly: the scanned PDF
   goes through OCR, not a manual fallback — verified today, Suresh Nair's real CV text ("seven
   years on a live DCS console") shows up correctly in his evidence, not blank.
6. **Leaderboard** (3 min). Real ranked scores, evidence-backed. Point out the third candidate's
   honest "Unknown"/flagged state as a feature, not a bug — screened and shown, not silently
   dropped (this is X35's fix, live).
7. **Candidate 360 — Suresh Nair** (3 min). Evidence trail, rubric breakdown, AI interview
   questions, CV viewer (opens the scanned PDF inline, does not download it).
8. **Decision** (2 min). Shortlist Suresh Nair. Mention override-the-AI is always available.
9. **Switch to Campaign A or B for the Review & Hire phase** (5 min) — do **not** re-run this
   on Campaign C live; use the pre-seeded, already-progressed campaigns:
   - **Campaign A → Interview** (`interview.html?campaign=5618904f-c91c-4e87-8975-35a76fc04ab0`): 
     Abdulrahman Al-Sada (Maintenance Engineer), interview already scheduled. Show the schedule, 
     then record feedback live (`PROCEED`) — this is the one live state change to make against 
     seeded data, and it is reversible only by re-running `seed_demo.py`'s idempotency check 
     reporting "already progressed", so do this **only once**, in rehearsal or in the real demo, 
     not both.
   - **Campaign B → Approvals** (`approvals.html?campaign=4a16f573-b7f8-40ac-bded-5c759e8f00da`): 
     **Process Engineer** role (not Instrumentation & Control), already past this stage, so instead 
     open it to show the **illustrative BU budget envelope** feature (BU, cost centre, budget holder, 
     fiscal year, approved headcount, approved salary band, all QAR, all clearly labelled illustrative) 
     — pick any candidate reaching that step live if time allows, or explain the pattern from 
     Campaign B's history via the audit trail.
   - **Campaign B → Offer** (`offer.html?campaign=4a16f573-b7f8-40ac-bded-5c759e8f00da`): Fahad 
     Al-Kuwari's offer (Process Engineer), sent, awaiting response. Say plainly: "sent" here means 
     recorded-as-sent, not necessarily delivered by a live mail server — `email_backend` is 
     `simulated` today (see §5).
10. **Pipeline / Timeline / Audit** (3 min). Open `pipeline.html`, then `timeline.html` and
    `audit.html` for either seeded campaign — full traceable history, actor/timestamp on every
    step.

Time target: ~30 minutes as above, discussion after.

## 4. Optional branches to fill 45 minutes

- FinOps tab (`developer.html`) — real measured LLM cost from today's actual campaign builds.
- What-if analysis (`whatif.html`) on any REVIEW-stage campaign — real weight sliders, real
  proposal API (note: the "propose for approval" UI section was deliberately removed 2026-09-14
  per direct instruction; the sliders and live re-rank still work).
- Compare candidates (`compare.html`) on a larger existing campaign (e.g. any `HSE OFFICER`
  campaign with a full candidate set) to show the paginated table at scale.
- Cost-centre / budget conversation: walk through why the envelope is BU-approved
  pre-recruitment, not invented at hiring time (see 04-KNOWN-DEFECTS.md and DECISIONS.md,
  2026-09-14 entries).

## 4b. Outlook configuration and integration guard

**Real Outlook email and calendar sends are ENABLED and VERIFIED WORKING on this machine.**

- **What changed today (2026-09-14):** Real COM calls to the signed-in Outlook account now send
  mail and calendar invites. Every send is guarded by an allowlist (`app/core/mail_guard.py`)
  that permits only the five approved recipients. Sender identity is resolved at runtime from
  whichever Outlook account is signed in on this machine, or from explicit env var
  `OUTLOOK_SENDER_ADDRESS` if set. `.env` has `EMAIL_BACKEND=outlook` and
  `CALENDAR_BACKEND=outlook`.
- **CRITICAL — approved recipients only** (five addresses): daipayan.r@protivitiglobal.in,
  ankush.saxena@protivitiglobal.in, chiranjib.sarma@protivitiglobal.in,
  preetam.c@protivitiglobal.me, subhadeep.m@protivitiglobal.in. Any attempt to send to any
  other address (including the seeded demo addresses like `@qchem-demo.example`) is rejected
  with HTTP 422 before the mail adapter is called. The frontend's recipient field on
  `web/comms.html` and `web/decisions.html` pre-populates and suggests approved colleagues
  by name; the CV-extracted candidate email appears as a grey placeholder to explain why it
  is not auto-selected.
- **Operational constraint 1 — seed script timing:** `scripts/seed_demo.py` MUST be run with
  `CALENDAR_BACKEND=simulated`. In real mode, the interview-schedule seeding fails (fictional
  actors are not in the approved recipient list) and leaves inconsistent state. Order:
  `seed_demo.py` with `CALENDAR_BACKEND=simulated`, then switch `.env` to `outlook` afterward.
  This has been done.
- **Operational constraint 2 — demo sender identity:** The person selected as "acting
  person" / hiring manager when arranging an interview must be the signed-in Outlook account
  holder (you). Seeded fictional managers are rejected with 422. This is deliberate — the
  audit trail must name someone who actually sent the email. If in doubt, pick yourself in
  the UI rather than a synthetic demo person.
- **Portability for Ankush:** He pulls the repo with no environment changes and the app
  discovers his own Outlook account automatically. No hardcoding. If Outlook is not signed
  in or not installed, the API replies 422 "No Outlook account was found to send from" rather
  than silently sending as the wrong identity.

## 5. What is simulated — say this plainly if asked

- **Email and calendar sends are REAL on this machine** (see §4b above). Previous builds and
  other machines use `email_backend`/`calendar_backend` = `"simulated"` in `.env`/`app/core/config.py`.
- **Budget/cost-centre figures are illustrative, synthetic demo values** — clearly labelled
  `ILLUSTRATIVE` on screen. They represent the shape of a real BU pre-approval workflow, not a
  live ERP or workforce-planning feed.
- **The JD library is a small, real, saved-JD repository** — genuinely persisted (see §8), but
  deliberately minimal: no versioning, no approval workflow on the JD itself.
- Never claim a "sent" offer or message was received — the product's own language already says
  "recorded as sent," which is accurate; keep using that phrase.

## 6. Known, already-documented, non-blocking items

See `04-KNOWN-DEFECTS.md` for full detail. Nothing below blocks the path above:

- **X32** (CI red) — fixed today (Node-harness stubs for `documentElement`/`location.replace`).
- **X26** (rapidocr missing) — fixed today (installed; numpy pinned back to 1.26.4 afterward to
  avoid breaking spaCy — see DECISIONS.md).
- Campaign C's third Process Operator candidate has a genuinely blank extracted name
  (`requires_review=True`) — a real, honest instance of the same name-extraction gap `X1`
  documents for a different CV. Not a bug to fix live; a feature to point at (flagged, not
  hidden) if it comes up, but simplest to just not dwell on that specific card.
- `decisions.html` has a silent fallback to static shipped-example rows if its live calls fail
  — confirm a real run exists before relying on this page live (true for all three demo
  campaigns as of this writing).

## 7. Fallback if something fails live

- **Azure/LLM call fails or is slow**: the three campaigns' screening is already complete and
  persisted — pivot to Campaign A/B (no new LLM call needed) and describe Campaign C's setup
  from the JD library without waiting on a live re-run.
- **OCR/scanned PDF fails**: fall back to Hana Al-Emadi's `.pptx` CV as the "unusual format,
  still read correctly" moment instead.
- **Browser/frontend breaks**: reload; if the service worker is suspected, unregister it
  (`navigator.serviceWorker.getRegistrations()` → `unregister()`) and hard-reload — this exact
  symptom (stale cached JS silently serving old behavior) happened during today's own build and
  verification session (see readiness doc).
- **API process dies**: restart per §1; all seeded data is in `tis_app.db` on disk and survives
  (verified today — see readiness doc's persistence evidence).
- **Nothing works**: no recorded video fallback exists yet for this specific session's build —
  if this is a hard requirement, record one during rehearsal before the client call, walking
  exactly the 30-minute path in §3.

## 8. Reset / reseed policy

`scripts/seed_demo.py` is idempotent and safe to re-run at any time — it detects Campaigns A and
B by their exact `name` and the JD templates by `role_title`, and skips anything already present.
It never deletes or resets existing data. If Campaign A's interview feedback gets recorded
during rehearsal, the "left at: interview scheduled, awaiting feedback" state is real and gone —
re-seed does not undo it. If a second, distinct rehearsal-quality Campaign A is wanted, that
requires a manual campaign under a different name; do not modify the script to force
re-creation of the same name.

**On THIS machine**, Campaigns A and B are already seeded with specific UUIDs and fresh LLM
scores from the 2026-09-14 seeding run. Re-running the script will detect them as already-seeded
and skip them; the UUIDs will not change. Campaign C was built live via browser (not seeded by
script) and has no re-seed logic.

**If you need to re-seed:** Set `CALENDAR_BACKEND=simulated` in `.env` before running
`scripts/seed_demo.py`. Real calendar mode will reject the seeded fictional managers and abort
the script partway. After the script finishes, you may switch `.env` back to
`CALENDAR_BACKEND=outlook` for demo time.
