# Demo video script (~145s)

Originally a 120-second script for a human to read while manually screen-recording. Updated
2026-09-16 per live feedback on the first recorded cut (`demoankfinl.mp4`) — the Candidate 360
section ran long and looped the same clip once narration reached the follow-up questions, the
Compare section cut away before showing the actual side-by-side result, and Decisions & Export
was too rushed to land. Content grew to close those gaps, so the total is no longer exactly
120s. This file is now also the **source of truth for `scripts/demo_video/segments.py`** —
the automated pipeline that records each screen with Playwright and narrates it with Sarvam
TTS (voice `ritu`, English). If you edit the narration or flow here, update that file's
`SEGMENTS` list to match, and vice versa.

Companion to [01-DEMO-MONDAY.md](01-DEMO-MONDAY.md) — same honesty rule applies: **anything on
screen that is a proxy must show its grey `SIMULATED` badge**, and the narration must say
"proxy" or "simulated" out loud when that screen appears. Do not silently skip the badge just
because it's a recording instead of a live call.

One named demo candidate and one named demo campaign throughout — reuse whatever the team
already used in rehearsal (see `docs/SESSION-STATE.md` for the most recent live-verified run,
e.g. the Maintenance Engineer / HSE Officer campaigns already used in this session's browser
verification). For the Compare section you need at least two candidates from that same
campaign.

Screens referenced by file name so whoever records can pre-open tabs in order:
`start-campaign.html` → `new-campaign.html` (JD/rubric) → `discover.html` → `leaderboard.html`
→ `candidate.html` → `compare.html` → `pipeline.html` (timeline) → `handoff.html` →
`interview.html` → `offer.html` → `decisions.html` / `audit.html`.

**Why the old cut looped a clip:** the Candidate 360 segment's screen recording was shorter
than its voiceover, so whatever played the file back looped it to fill the gap — the fix isn't
a narration tweak, it's making sure each segment's recorded clip is at least as long as its own
audio. `scripts/demo_video/assemble.py` enforces this automatically (it pads video to the
narration's measured duration, it never loops), but if this script is ever re-recorded by hand,
keep the same rule: never end a recording before its voiceover line finishes.

---

## Timing table

| Time | Screen | Voiceover | On-screen action |
|---|---|---|---|
| 0:00–0:10 | `start-campaign.html` | "This is a recruitment platform that runs a candidate from job requirement to hire — with AI doing the screening, not just the paperwork." | Show the "Tell AI what you need to hire" box; type one sentence, e.g. "I need a Maintenance Engineer for a plant in Doha." |
| 0:10–0:20 | `new-campaign.html` (AI-drafted JD + rubric) | "One sentence, and it drafts the job description, the requirements, and the scoring rubric — no blank form." | Show the generated JD requirements list and rubric criteria; click Approve. |
| 0:20–0:30 | `discover.html` | "Instead of a recruiter scrolling CVs, it searches a resume repository semantically and pulls in the candidates who actually match." | Point at the folder/link input, show matched CVs pulled in. |
| 0:30–0:50 | `leaderboard.html` | "This is the screening engine. Every CV — including scanned, photographed, badly formatted ones — goes through OCR and a real LLM evaluation against the rubric, and comes back ranked with a confirmed-requirement count, not a black-box score." | Show the ranked list, scores, confirmed-requirements column. Call out one badly-formatted or scanned resume scoring correctly. |
| 0:50–1:05 | `candidate.html` (Candidate 360) — evidence | "Drilling into one candidate: the evidence for every score, an AI narrative summary, and suggested interview questions generated straight from the gaps it found — so the interviewer knows exactly what to probe." | Scroll the score breakdown, narrative, and suggested-questions panel. |
| 1:05–1:12 | `candidate.html` — close | "And that's the AI assessment and the recommended decision for this candidate." | Hold on the recommendation pill/verdict at the top of the page — no further scrolling — then cut. This line replaces lingering on the follow-up-questions panel; it's the hard stop for this section before moving to Compare. |
| 1:12–1:20 | `compare.html` — full table | "Here's the full shortlist for this campaign, side by side." | Show the candidate table at the top of the page (all rows, checkboxes visible) before touching anything. |
| 1:20–1:28 | `compare.html` — select | "Selecting the two finalists I want to compare." | Click the checkboxes for two candidates in that table. |
| 1:28–1:38 | `compare.html` — result | "And here's the criterion-by-criterion comparison for just the two I picked." | Scroll down to the generated comparison table and hold on it. |
| 1:38–1:53 | `pipeline.html` (timeline) | "Every decision — shortlist, hold, reject — writes a real state change and a real audit event. This is the full lifecycle for one candidate, end to end, and nothing here is a mockup." | Show the timeline with completed states ticked. |
| 1:53–2:08 | `handoff.html` → `interview.html` | "From shortlist, it hands off to the hiring manager, schedules the interview, and captures structured feedback — strengths, concerns, a recommendation — all tied back to this candidate's record. Calendar send is a simulated step in this build, clearly marked, but the state and the feedback form are real." | Show handoff screen briefly, then interview scheduling + feedback form; make sure the grey SIMULATED badge is visible on screen for at least 1 second and say the word "simulated." |
| 2:08–2:18 | `offer.html` | "Offer drafting, revisions, and the candidate's response are tracked the same way — proxy for the actual letter and email today, real for everything the recruiter needs to keep moving." | Show offer package + accept/decline capture; grey badge visible. |
| 2:18–2:40 | `decisions.html` | "This is the Decisions and Export page — you can take the final call on each candidate from right here. And as we scroll down, you can send the shortlisted candidates straight to the hiring manager." | Hold on the shortlist/decision list first, long enough to read it; then scroll down to the "Send the report to the hiring manager" section and hold there too — this section runs longer than the others on purpose. |
| 2:40–2:45 | `audit.html` | "Every one of those steps — screening, shortlist, handoff, interview, offer — lands in one audit trail, filterable and exportable, so nothing here is a black box." | Show the audit log scrolling past entries for the demo candidate; end on a clean frame. |

---

## Narration script (read straight through, ~145s at a natural pace)

> This is a recruitment platform that runs a candidate from job requirement to hire — with AI
> doing the screening, not just the paperwork.
>
> One sentence, and it drafts the job description, the requirements, and the scoring rubric —
> no blank form to fill in.
>
> Instead of a recruiter scrolling through CVs, it searches a resume repository semantically
> and pulls in the candidates who actually match.
>
> This is the screening engine. Every CV — including scanned, photographed, badly formatted
> ones — goes through OCR and a real LLM evaluation against the rubric, and comes back ranked
> with a confirmed-requirement count, not a black-box score.
>
> Drilling into one candidate: the evidence behind every score, an AI-written narrative
> summary, and suggested interview questions generated straight from the gaps it found — so the
> interviewer knows exactly what to probe.
>
> And that's the AI assessment and the recommended decision for this candidate.
>
> Here's the full shortlist for this campaign, side by side.
>
> Selecting the two finalists I want to compare.
>
> And here's the criterion-by-criterion comparison for just the two I picked.
>
> Every decision — shortlist, hold, reject — writes a real state change and a real audit event.
> This is the full recruitment lifecycle for one candidate, end to end.
>
> From shortlist, it hands off to the hiring manager, schedules the interview, and captures
> structured feedback — strengths, concerns, a recommendation. Calendar and email delivery are
> simulated in this build and marked as such on screen; the state, the feedback and the
> approval trail behind them are real.
>
> Offer drafting, revisions and the candidate's response are tracked the same way.
>
> This is the Decisions and Export page — you can take the final call on each candidate from
> right here. And as we scroll down, you can send the shortlisted candidates straight to the
> hiring manager.
>
> And every one of those steps — screening, shortlist, handoff, interview, offer — lands in one
> audit trail, filterable and exportable. Nothing here is a black box.

---

## What NOT to say

Per the demo-plan honesty rule (section 5 of `01-DEMO-MONDAY.md`), do not describe any of
these as done or automatic, because they are not, as of 2026-09-15:

- Calendar invites and offer emails actually arriving in someone's inbox unattended — Outlook
  send is real code but **only verified against a fake COM double**; a live signed-in-mailbox
  send is unverified. Say "simulated" or "proxy," never "automatically sent."
- Candidates replying and the system reading that reply to move state — inbound reply
  classification exists in the backend but is **not wired into any screen yet** (`B10`).
- SharePoint integration — `discover.html`'s search runs over a local folder standing in for
  SharePoint; there is no Microsoft Graph/SharePoint code in the repo at all. Say "a resume
  repository," not "SharePoint."
- SLA reminders/escalations — not built.
- Multi-level approval workflows — not built; `handoff.html` covers hiring-manager
  review/approval, not a multi-level chain.

## Recording checklist before hitting record

Same as the go/no-go list in `01-DEMO-MONDAY.md` section 7:
- `QUEUE_BACKEND=inline` set, API and web servers both up.
- Demo campaign's rubric already approved, demo candidate has a real name and a sensible
  score/confirmed-count — don't discover a data problem while the camera is rolling.
- At least two candidates in the demo campaign, for the Compare segment.
- Every proxy screen shows its grey `SIMULATED — INTEGRATION PENDING` badge before you start
  narrating over it.
- No console errors on any of the screens in the timing table above.

## Automated pipeline

`scripts/demo_video/` regenerates the recording end to end instead of a human doing a live
screen capture: it drives each screen with Playwright per the timing table above, generates the
matching narration audio with Sarvam TTS, and muxes each segment's video to its own audio's
measured length (padding, never looping) before concatenating the final file. See
`scripts/demo_video/README.md` for how to run it. Fill in `scripts/demo_video/config.json`
(copy from `config.example.json`) with the live campaign/candidate ids for whichever campaign
you're using that day — they are not hardcoded because they change per rehearsal.
