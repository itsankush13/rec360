# Master backlog

Source: consolidated review, 2026-09-12. IDs are stable. Never renumber.

Engineering allocation, 2026-09-12: [08-TWO-PERSON-DELIVERY.md](08-TWO-PERSON-DELIVERY.md)
supersedes earlier engineering owner labels below. Subhadeep owns portal/product/central
plans; Ankush owns backend/integrations/migrations. Existing stakeholder approvals remain
unchanged. The matrix assigns every B-item and relevant D/W/X item without changing status.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done and verified · `[-]` dropped

**Audited 2026-09-12 against branch `consolidated` (474 tests passing).** Every `[x]` below
has a file:line behind it. Where a backend exists but no screen calls it, the box is `[~]`
and says which half is missing — a route nobody calls is not a feature.

---

## P0 — before the Monday demo (2026-09-14)

### B01 — Demonstrate the complete journey of one candidate
Owner: Ankush + Subhadeep · Priority: highest

- [x] 1. CV imported — batch upload, OCR for photographed CVs. **Discovery** from a repository is not built (`B03`)
      2026-09-14, on direct instruction (see `X35`): a photographed/scanned CV, a CV with no
      name/email/phone at all, and a repeat application are all screened along with every other
      CV now, never held out of the batch — each is flagged (`requires_review` + a plain-English
      note) instead. Previously the first two were hard failures excluded from evaluation
      entirely, and the third (already auto-merged into the existing candidate) was presented as
      needing a manual "Merge them" action it didn't actually need.
- [x] 2. AI screens the CV — real Azure run, evidence quoted to page or section
- [x] 3. Shortlist / Hold / Reject — `set_disposition`, append-only, audited
- [x] 4. Hiring-manager handoff — real endpoint `POST .../send-to-manager`, named owner, audited.
      2026-09-15: re-verified end to end against a live campaign — entered a real shortlisted
      candidate into the lifecycle, sent it to a hiring manager through `web/handoff.html`'s
      own form, confirmed the lifecycle timeline and `audit_events` both recorded it correctly.
      **Found `X58` while doing this: nothing in the UI ever calls the `/enter` endpoint that
      step 3 needs to feed step 4** — a recruiter shortlisting a candidate on `candidate.html`
      today does not put them in the handoff queue. The endpoint and screen this box covers
      both work; the missing link is upstream, between B01 steps 3 and 4.
      **`X58` fixed 2026-09-15, later, on direct instruction** (user hit the gap live while
      rehearsing: "till decisions and export part i have done everything, after that from
      handoffs no data is visible"): both places that set a `SHORTLIST` disposition
      (`web/decisions.html`, `web/candidate.html`) now also call
      `POST .../lifecycle/{id}/enter` right after, so step 3 now actually feeds step 4 with no
      manual API call. Browser-verified: shortlisted a candidate on `decisions.html`, watched
      both the disposition and the `/enter` call succeed, then loaded `handoff.html` for the
      same campaign and saw "1 candidate in this campaign's hiring process" where it had been
      0. See `04-KNOWN-DEFECTS.md` (`X58`) for the full write-up.
      **2026-09-17, on direct instruction (`X66`):** the same gap one step later — sending the
      report from `web/decisions.html` (`B10`) did not move the candidate to
      `WITH_HIRING_MANAGER`; only `handoff.html`'s own separate "Send to hiring manager" button
      did that. That button (and its "Ready to send" group) is now removed; sending the report
      *is* the handoff — `app/api/reports.py::email_shortlist_to_hiring_manager` resolves the
      recipient to a `HIRING_MANAGER`/`ADMIN` account and moves every `SHORTLIST`/`INTERVIEW`
      candidate in the report to `WITH_HIRING_MANAGER`, owned by that manager, via the existing
      `lifecycle_service.send_to_hiring_manager`. Full write-up, including the actor-id/name
      resolution fix this required, in `04-KNOWN-DEFECTS.md` (`X66`).
      **2026-09-17, later, same day — live-verified once the user actually hit it.** No address
      was both a registered `HIRING_MANAGER` and approved for the live server's real Outlook send
      (the user's own account, the one address they could receive real mail at, was `RECRUITER`,
      and `User.email` is unique so a second account can't share it). Added
      `PATCH /api/users/{id}/role` (`app/api/lifecycle.py`; no prior endpoint could change a
      role at all) and promoted the user's own account to `ADMIN` — a strict superset of
      `RECRUITER` in every `app/core/lifecycle.WHO_MAY` entry, so no existing capability was
      lost. Re-sent the report to that same address: `moved_to_manager: 4`,
      `send_detail: "Sent via local Outlook to ankush.saxena@protivitiglobal.in."` (a real,
      non-simulated send), and `handoff.html` for that campaign confirmed "With the hiring
      manager: 4," each row owned by that account. Full write-up in `04-KNOWN-DEFECTS.md` (`X66`
      follow-up).
      **2026-09-17, later still, same day — the reverse direction (`returned, with a question`)
      never emailed anyone.** `handoff.html`'s own "Send back to manager" (the only user of
      `POST .../lifecycle/{id}/send-to-manager`) moved the state but sent no mail, and its manager
      dropdown only listed `HIRING_MANAGER` accounts, so the just-promoted `ADMIN` account never
      appeared as a choice there. Fixed: that endpoint now emails the chosen manager for real
      (`mail_guard` + `outlook_adapter`) whenever a `QUESTION` is actually on file to answer, and
      the dropdown now unions `HIRING_MANAGER` and `ADMIN`. Added a third real account,
      `Subhadeep` (`subhadeep.m@protivitiglobal.in`), against an address `mail_guard` already
      approved. Live-verified: answered a real question on `AHMED KARIM AL-SAYED`, chose Ankush
      Saxena, got "Sent via local Outlook to ankush.saxena@protivitiglobal.in." back, and the
      candidate moved to "With the hiring manager." Full write-up in `04-KNOWN-DEFECTS.md` (`X66`
      second follow-up).
- [~] 5. Interview scheduled — `web/interview.html` records time, panel and state; local Outlook invite path is configured for the four-address demo, with real delivery not yet verified
- [x] 6. Interview feedback received — `web/interview.html` captures verdict and audit detail
- [~] 7. HR discussion — `web/approvals.html` routes named approvals and budget sign-off; policy integration pending
- [~] 8. Offer drafted or sent — `web/offer.html` records package and send; letter and delivery simulated
- [~] 9. Candidate accepts or declines — response is recorded; external reply ingestion pending
- [x] 10. Hired / Completed—Unsuccessful — `web/handoff.html` records terminal outcome
- [~] Campaign workspace navigation — floating previous/next arrows and collapsible stage list retain campaign context; browser-verified for Upload CVs → Interviews → empty Approvals, with other pages covered by shared `web/assets/app.js`. 2026-09-13: dock moved from bottom-right to top-right (`web/assets/app.css`), and the stage list now marks each earlier stage with a green tick and the current stage with a red dot (`web/assets/app.js`) — browser-verified live on Candidate 360 against a real campaign/evaluation.

**Now demonstrable end to end with proxy actions.** `web/pipeline.html` links every stage;
`web/timeline.html` reads recorded moves. Steps 5-9 write real state and audit detail;
email, offer letter and reply ingestion remain simulated; calendar sending is an opt-in Outlook path and has not been live-delivery-verified.

### B02 — Recruitment lifecycle / timeline view
Owner: Ankush + Solution Team · See `02-LIFECYCLE-MODEL.md`

- [x] Show gates, current stage, completed steps, pending owner, timestamp — `web/timeline.html`,
      the "Current stage" band and the spine, reading `GET .../lifecycle/{candidate_id}` and
      `GET .../timeline`. Verified live against a real campaign and candidate.
- [x] Show one candidate journey; design supports all candidates later — `web/timeline.html`
      renders one candidate by `?campaign_id=&candidate_id=`; a candidate picker fed by
      `GET /campaigns/{id}/lifecycle` lists every candidate in the lifecycle when only a
      campaign is given.
- [x] Implement all 14 required states — 17 members, validated transition map,
      `app/db/models.py` + `app/core/lifecycle.py`
- [~] Add SLA reminders and escalations — 2026-09-13: `app/core/lifecycle.SLA_HOURS`
      (placeholder per-stage durations, no client-approved policy yet), `sla_service.py`
      (`sla_status()` derived at read time, `evaluate()` writes idempotent
      `SLA_REMINDER_SENT`/`SLA_ESCALATED` audit events), `POST /api/lifecycle/sla/evaluate`.
      `LifecycleOut` now returns `sla_status`. Backend and 7 new tests done
      (`tests/test_sla.py`); no scheduler calls `evaluate()` automatically yet (nothing in
      this environment can run a recurring job). 2026-09-13: `web/timeline.html`'s "Due" cell
      now renders a `.tag` badge (teal/gold/red for `ON_TRACK`/`DUE_SOON`/`OVERDUE`) driven by
      `sla_status` — contract in
      `docs/handoffs/ankush/2026-09-13-b02-sla-reminders-escalations.md`.
- [x] Show the lifecycle capability even where the backend is incomplete — `web/timeline.html`
      renders all ten `B01` steps and shows uncompleted steps as "Has not happened yet".

### B03 — Semantic CV search demo
Owner: Subhadeep + Ankush · **Tier 1 built; relevance-ranking backend now built and merged,
screen not wired to it yet.** A SharePoint or OneDrive link resolves to the synced folder
and imports through the normal ingestion path. There is still no Graph or MSAL code. The
ranking API exists (below); `web/discover.html` still shows an unranked list and manual
ticking.

- [x] Connect or simulate a SharePoint repository — `app/core/cv_source.py` resolves a
      SharePoint/OneDrive link, a UNC path or a local path to the locally synced folder;
      `POST /discovery/resolve` and `POST /discovery/import` in `app/api/discovery.py`;
      screen at `web/discover.html`. Import reuses `processing_service.create_batch`, so
      exceptions, duplicates and audit rows are identical to an upload. Graph is deferred
      to the pilot — see `docs/DECISIONS.md`.
- [~] Find role-relevant CVs automatically — **backend built and merged** (was reported
      unmerged in a 2026-09-12 handoff; verified this session actually on `consolidated`,
      commit `59f4709`). `POST /discovery/resolve` takes an optional `campaign_id`, scores
      each file's coverage of the campaign's active rubric terms
      (`app/core/cv_relevance.py`, reusing the same matcher as real evaluation), and returns
      `relevance_score`/`recommended` per file sorted best-first; silently
      `ranking_available: false` with no approved rubric yet, not an error.
      `tests/test_discovery.py`, 7 passed, re-ran this session. `web/discover.html` — the
      screen — does not yet send `campaign_id` or show the score; still manual ticking only.
- [ ] Small demo: 5 CVs in, 2 relevant selected
- [ ] Target story: 200 CVs in, 15–20 relevant identified
- [ ] Support a mixed-role repository
- [ ] Use retention and consent metadata tags
- [ ] Show the selected CVs before screening starts
- [ ] Contact Mukesh Yadav for SharePoint help if required

### B04 — Audit trail demonstration
Owner: Ankush

- [x] Log every lifecycle transition — `lifecycle_service._write()` calls `record_audit` in
      the same unit of work
- [~] Show recruitment/application ID, campaign ID, candidate ID — 2026-09-13: campaign and
      candidate ids are now rendered on every `web/audit.html` log row (`logRow()`), not just
      carried in the API response. **There is no application/recruitment ID yet** (`B20`)
- [x] Show campaign and candidate names — resolved in batch, `app/api/decisions.py:151`
- [~] Show actor, action, status, timestamp, comments, approval evidence — all present
      except **approval evidence**, which has no artefact to point at
- [~] Event coverage — **5 of 10 confirmed**:
      CV received `BATCH_UPLOADED` · screening result `EVALUATION_RUN_COMPLETED` ·
      decision `DISPOSITION_SET` · hiring-manager response `MANAGER_REVIEWED` ·
      final outcome (terminal states). **Absent:** email sent · interview scheduling ·
      interview result · offer status. **Generic only:** HR decision (`STATUS_CHANGED`)
- [x] Make the audit UI readable and searchable — filters by action and actor plus free
      text, day grouping, before→after rendering, CSV export
- [ ] Review the completed module with Devben and Subhadeep

### B05 — AI recommendation and decisioning
Owner: Ankush

- [ ] Auto-select the recommended action — `effective_recommendation` is returned and shown
      as information; the buttons are not pre-selected
- [x] Auto-fill the rationale/comment — 2026-09-13: `effective_recommendation` now returns
      `suggested_rationale`, a draft comment built from the evaluation's own top
      evidence-backed criteria (empty string with no evaluation). A draft, not an
      auto-submitted decision — the recruiter still edits and saves it.
      `web/candidate.html` prefills the comment box from this field (only when the box is
      still empty, so it never clobbers an in-progress edit).
      2026-09-13, later, on direct instruction: `_suggested_rationale`
      (`app/services/disposition_service.py`) now genuinely calls an LLM
      (`app/core/llm_provider.get_cached_chat_model`, same pattern as
      `app/core/summary_generator.py`) to rewrite the deterministic draft into a brief,
      non-technical summary — previously "AI" in name only (pure string-templating, no model
      call). The numeric score line is still generated in Python and always appears verbatim
      (never handed to the LLM to restate); the literal phrase "AI assessment" is stripped
      defensively even if the model ignores the system prompt. Any provider/network failure
      falls back to the original deterministic bulleted draft rather than a 500. Result is
      cached on a new `Evaluation.ai_rationale_summary` column (migration `b17e8cfa48d8`) the
      first time it's generated for a given evaluation — an `Evaluation` is write-once, so the
      summary never goes stale, and this avoids re-billing the LLM on every Candidate 360 page
      view (the caching question a prior session left open — resolved this way rather than
      asked again, since the user asked for the LLM call itself to proceed). `GET
      .../candidates/{id}/recommendation` (`app/api/decisions.py`) now commits after the
      service call, since the cache-fill is real persisted work, not a side effect of a read.
      Verified live against a real evaluation (Tariq Al-Naimi): a real LLM call produced "Score:
      46 out of 100 — one to review." followed by a two-sentence plain-language summary, and a
      second page load returned the identical cached text with no second LLM call.
      `tests/test_decisions.py`: 2 existing tests updated to stub the LLM call (this repo's
      suite never calls a real LLM — see `test_evaluations.py::
      test_deterministic_run_makes_no_llm_calls`), 2 new tests added (cached-after-first-call,
      falls back to template when the LLM is unavailable). 47/47 passed in that file.
      Contract: `docs/handoffs/ankush/2026-09-13-b19-filters-quality-of-hire-b05-rationale.md`.
- [x] 2026-09-13, later, on direct instruction — the "Your decision" comment-box draft could
      read as one bare line ("Score: N out of 100 — {fit}.") whenever an evaluation had no
      criterion qualifying as a named strength or concern, since `_template_rationale`
      (`app/services/disposition_service.py`) previously built nothing else in that case and
      the LLM had only that one line to compress. Rewritten so the deterministic draft is
      always a full, continuous-prose paragraph (never a bulleted list, never a bare score):
      it now always adds a plain-language verdict sentence ("Overall, this looks like a
      strong/workable match...") and falls back to the evaluation's own narrative when no
      criterion is specific enough to name. `_RATIONALE_SYSTEM_PROMPT` now explicitly asks for
      2-4 sentences of continuous prose ending in a plain suitability statement. A cached
      `Evaluation.ai_rationale_summary` written before this fix (a bare one-liner, or the old
      "- item" bulleted shape) is detected as stale (`_is_stale_rationale`) and regenerated
      once rather than kept forever, so already-assessed candidates get the fuller paragraph
      on their next view without a migration. `tests/test_decisions.py` (rationale tests) still
      pass, 4/4.
- [x] 2026-09-13, later, on direct instruction — bulk report export from `web/decisions.html`:
      new `GET /api/campaigns/{campaign_id}/reports.zip?format=pdf|docx`
      (`app/api/exports.py::shortlisted_reports_zip`) zips every `Disposition.SHORTLIST`
      candidate's existing Candidate 360 report under one named folder ("Shortlisted
      Candidates PDF"/"...Word") instead of one download per person. The two top-of-page
      download buttons (`d-report-pdf`/`d-report-docx`) now point at this endpoint and are
      restyled to look identical (same neutral outline, same size — previously one was a
      filled maroon `.cta` and the other an outline `.ghost`). The "Download the shortlist as a
      spreadsheet" link was removed from this page on direct instruction (the backend
      `export.xlsx` endpoint itself is untouched and still serves other callers). The hiring
      manager email/CC fields now use the site's shared `.form`/`.fld` component instead of
      inline-styled bare `<input>`s, matching every other form on the site. Verified live: the
      zip endpoint returns 3 files (Fahad Al-Kuwari, Daniel Cruz, Carlos Mendes) under
      "Shortlisted Candidates PDF/" and "...Word/" respectively against the real HSE Officer
      campaign; `tests/test_exports.py`/`test_decisions.py` (55 passed, 1 skipped) unaffected.
- [x] 2026-09-14, on direct instruction — the prose-paragraph rewrite above (2026-09-13) read
      as one dense block; reversed back to a bulleted brief, this time with a hard floor: at
      least 120 words, and the single most important point (the overall call) written first and
      bolded so it is the first thing a recruiter reads, ahead of the supporting detail.
      `_template_rationale` (`app/services/disposition_service.py`) now always emits
      `"- "`-prefixed bullet lines — headline verdict bolded (`**...**`) first, then confirmed
      strengths, gaps to probe, years of experience, and confidence band, each grounded in the
      evaluation's own fields (`experience_years_total/_relevant`, `overall_confidence`,
      `confidence_band`) rather than invented, with a final grounding bullet appended only if
      still short of 120 words. `_RATIONALE_SYSTEM_PROMPT` updated to match (bullet lines, first
      one bold, 120-word floor). `_is_stale_rationale` flips back to flagging a cached
      continuous-prose paragraph (no bullets) as stale so already-scored candidates pick up the
      new shape on next view, without re-validating word count on every read (a legitimate
      slightly-short brief still gets reused, not re-billed to the LLM).
      `web/candidate.html`'s `#c-comment` box changed from a plain `<textarea>` to a
      `contenteditable` `div` so the bold headline and bullet list actually render (a textarea
      cannot display markup) — a new `renderRationale()` helper escapes the AI text first, then
      converts `"- "` lines to `<li>` and `**bold**` to `<strong>`, so no evaluation- or
      LLM-authored text can inject markup of its own; disposition submit now reads
      `#c-comment`'s `innerText` instead of `.value`. Verified live against the same real
      evaluation (Tariq Al-Naimi, HSE OF campaign): a real LLM call produced a 9-bullet, ~190
      word brief, bolded headline first, rendering correctly as a bulleted list in the browser;
      typing into the box still works. `tests/test_decisions.py` updated (one mock rewritten to
      return bulleted text, matching the new prompt contract) — 45/45 passed.
- [x] Explain score, calculations, evidence, and weights — evidence citations with criterion
      label and CV page, `web/decisions.html:229`
- [x] Allow a human override — `override_recommendation`, reason required
- [x] Add a Save action; persist the final human decision — `set_disposition`
- [ ] Fix incomplete control wiring and incorrect selection styling
- [~] Standardise terminology — "Shortlist" is used for candidates and "Approve" only for
      rubrics. That split is coherent; confirm it is intended, then close

2026-09-15, later, on direct instruction: decisions-and-export (this section) merged into the
compare tab opened from `web/candidate-assessment.html` (see the B16 row above), alongside a
new "choose who goes to the hiring manager" workflow — not a new plan ID, an extension of this
one and `B10`'s existing send-to-hiring-manager endpoint. Three selection paths, all writing
into one "Ready to send" list: (1) drag a name from the compare table's column header onto the
ready zone (native HTML5 drag/drop); (2) paste/type candidate names, one per line, matched
case-insensitively against the campaign's loaded candidates; (3) a plain rule
("score 90 and above", "top 5", "shortlisted") matched client-side against the already-fetched
scores — **not an LLM call**, deliberately not labelled "AI" (see this file's own B05 history
above: a feature that says "AI" but makes no model call was treated as a defect and fixed once
already; the same standard applies here). A "Check my decisions for gaps" button runs a
similar deterministic check (undecided candidates, 80+ scores not shortlisted, shortlisted
candidates under 60, ready-list members not yet shortlisted) and lists what it found — again a
plain rule check, not a model read of the campaign. "Send to hiring manager" first sets
`SHORTLIST` (via the existing `/disposition` endpoint) on anyone in the ready list not already
shortlisted, then calls the existing `POST .../reports/email-to-hiring-manager` (`B10`) exactly
as `web/decisions.html` already does — there is no per-selection send endpoint, so this
honestly sends the *campaign's whole shortlist*, not only the ready-list subset, and the UI
copy says so. The PDF/Word bulk-download buttons reuse the existing `GET .../reports.zip`.
Browser-verified live against the real HSE Officer campaign end to end: applying the rule
"top 2" matched and added 2 candidates to the ready list, "Check my decisions for gaps"
correctly reported undecided candidates, and "Send to hiring manager" shortlisted both,
called the real endpoint, and returned "Sent via local Outlook to
daipayan.r@protivitiglobal.in." A prior empty-shortlist attempt correctly surfaced the
backend's own real error ("There is nothing to report yet…") rather than a fake success.

### B06 — AI-generated JD
Owner: Ankush · Corrected 2026-09-15: this section previously read "Nothing built. No
JD-generation code in the tree," which was false — `app/agents/jd_agent.py`,
`app/services/jd_generation_service.py` and `app/core/jd_templates.py` already existed, wired
to a live route (`POST /api/campaigns/{id}/jd/generate`) and covered by
`tests/test_jd_generation.py` (5 tests). Re-verified this session: file contents read in full,
5/5 tests re-run and passing, and the route browser-verified live end to end (see the new
AI-campaign-start item below, which drives this exact route).

- [x] Generate a JD after role entry — `app/agents/jd_agent.py:generate_jd`, live LLM call
      (Azure), template floor via `app/core/jd_templates.py` when the model is unavailable.
- [x] Learn from prior campaigns: role, grade, experience, skills, responsibilities,
      remuneration — `jd_generation_service._similar_campaigns` passes up to 3 prior
      same-title campaigns' saved descriptions to the model as few-shot examples.
- [x] Use an industry-standard template for new common roles — `jd_templates.match_template`,
      6 built-in roles, loose substring match.
- [x] Flag uncertainty and request input for niche roles — `JDGenerationResult.uncertain` /
      `uncertainty_reason`, set when no template and no prior campaign match.
- [x] Let the user accept, edit, delete, paste, upload, or override — `new-campaign.html`
      step 2 (upload/paste tabs, AI generate, free edit); generation itself is a preview only,
      accepted by an ordinary `PATCH /api/campaigns/{id}`, never auto-saved.
- [x] Pitch it as a company-learning feature, not random internet generation — the few-shot
      prior-campaign context above, plus the company baseline template passed as
      `reference_template` for the model to adapt rather than invent from scratch.

**New, same session — "AI should start the campaign"**: a natural-language entry point on top
of this and B07, not a new plan ID (it is B06's own "Generate a JD after role entry" extended
one step earlier, from a role field to one free sentence, plus wiring straight into requirement
extraction and rubric seeding). `POST /api/campaigns/ai-start` — recruiter free text →
`app/agents/campaign_request_agent.py` (new, same shape as `jd_agent`) extracts structured
hiring intent → `campaign_service.create_campaign` (DRAFT) → `jd_generation_service` →
`requirement_service.extract_and_store_requirements` → `rubric_service.create_version` +
`suggest_weights`. Every step degrades independently (try/except with a floor) rather than
aborting the whole request; only an unparseable/roleless request is rejected outright (422).
Campaign lands at plain `DRAFT` with an unsubmitted rubric version — no new `CampaignStatus`,
no new `RubricStatus`, no migration. New audit action `AI_CAMPAIGN_DRAFTED` (labelled in both
`app/api/decisions.py::ACTION_WORDS` and `web/audit.html`'s `ACTION_WORDS`, per the existing
"an enum value never reaches a reader" convention). Frontend entry point on
`web/start-campaign.html` ("Tell AI what you need to hire" → review card showing what AI
understood, the generated JD and the proposed rubric weights → "Review & approve" hands off
into the *existing* `new-campaign.html` step-3 screen via the existing `CampaignSteps.resolve`
continuation logic — no parallel approval path, no auto-activation). 9 new backend tests
(`tests/test_campaign_ai_start.py`: happy path, audit event, empty request, missing field,
AI-understanding failure creates nothing, malformed/roleless AI output rejected, JD-generation
failure still yields a usable draft, requirement-extraction failure still yields a usable
draft, idempotency-key replay does not duplicate) — all passing. Full suite re-run clean after
the change (no regressions). Browser-verified live end to end against the real configured
Azure OpenAI deployment (not mocked): a real request ("Hire a Senior Data Engineer with 5+
years of experience, strong Python and SQL skills, AWS experience, and experience building
data pipelines.") produced a DRAFT campaign, a full generated JD, 45 extracted requirements and
an LLM-tailored rubric; the "Review & approve" link opened the campaign on the existing
`new-campaign.html` step-3 screen exactly as a manually-built campaign would; the audit trail
showed `AI_CAMPAIGN_DRAFTED` plus the normal `CAMPAIGN_CREATED`/`CAMPAIGN_UPDATED`/
`RUBRIC_VERSION_CREATED` events; the test campaign was deleted afterward via the existing
`DELETE /api/campaigns/{id}`.

**2026-09-15, on direct instruction — resumes now optional on the same form, and the AI-start
review can carry the campaign through to a scored candidate list without a detour through
`new-campaign.html`.** No new backend route: `web/start-campaign.html`'s "Tell AI what you need
to hire" form gained a folder picker (`<input type="file" webkitdirectory>`, same control
`new-campaign.html` step 3 already uses) and a SharePoint-link/folder-path text field. When
either is filled in, the AI-start review (`web/assets/campaign-ai-start.js`) replaces the
"Review & approve →" link with an inline "Approve rubric and start screening" button that runs
the exact same submit → approve → upload/import → run sequence `new-campaign.html`'s own
"Approve and start screening" button already runs (see that button's code comment on the same
one-approval-click shortcut) — rubric submit/approve
(`POST .../rubric/versions/{v}/submit`, `.../approve`), then either a `multipart/form-data`
`POST /api/campaigns/{id}/batches` for a picked folder, or `POST /discovery/resolve` +
`POST /discovery/import` for a pasted link/path, then `POST /api/campaigns/{id}/evaluations/runs`,
then `location.href` straight to `candidate-assessment.html?run_id=...`. The recruiter still
makes the one rubric-approval click this repo's architecture requires (see this file's own "AI
never submits or approves the rubric" note above) — nothing after that click needs manual
navigation. Leaving both fields empty preserves the exact prior behaviour (link to
`new-campaign.html` step 3). Browser-verified end to end against the real API: a request plus a
folder path containing two `.docx` resumes produced a DRAFT campaign, approved its rubric on
one click, imported and scored both resumes, and landed on Candidate Assessment showing "2
Total candidates".

**2026-09-17, X63 fix — "review it manually" no longer drops the CVs chosen on this form.**
The "Or review it manually →" branch (taken when a rubric review has no resume context, or the
recruiter opts out of the one-click screening button) previously linked straight to
`new-campaign.html` step 3 without the files the recruiter had already chosen, since `File`
objects cannot travel in a URL. Fixed client-side only (`web/assets/pending-resumes.js`, an
IndexedDB stash keyed by campaign id, taken back once by `new-campaign.html` on load) because
`create_batch` requires an approved rubric and the manual path defers that approval — see X63 in
`04-KNOWN-DEFECTS.md` for the full description and verification.

### B07 — Scoring and weight correction
Owner: Ankush · Audited 2026-09-13 against code and tests (a 2026-09-12 handoff,
`docs/handoffs/ankush/2026-09-12-b07-scoring-audit.md`, had already done this once;
independently re-verified rather than trusted this session).

- [ ] Separate category weight from good-to-have bonus points — PREFERRED ("good-to-have")
      criteria still draw from the same fixed 100-point pool as MANDATORY criteria, not an
      add-on bonus (`app/services/rubric_service.py:236-256`,
      `app/core/rubric_presets.py:110-159`). Raised with the user in the prior handoff, who
      chose to leave it pending a client conversation — it touches the weights-sum-to-100
      invariant everywhere. Still an open product decision, not a gap in effort.
- [x] Validate the backend calculation — `tests/test_evaluations.py:859-866`
      (`test_overall_score_is_the_sum_of_weighted_contributions`) asserts
      `overall_score == sum(weighted_score)` and the 0–100 bound; re-ran it this session, passes.
- [x] Use a bounded scale (0–10, 0–100) — `app/schemas/rubric.py:35,47,77`,
      `weight: float = Field(ge=0.0, le=100.0)`, enforced server-side regardless of UI.
- [x] Keep the normalised total constant across roles — `RubricVersion.is_balanced` /
      `weight_total` (`app/db/models.py:306-312`), enforced in
      `rubric_service.validate_version`/`submit_version`/`approve_version`. Re-ran
      `tests/test_rubrics.py tests/test_rubric_presets.py` this session: 45 passed.
- [x] Replace unrestricted text inputs with sliders — the actual weight-editing screen,
      `web/whatif.html:117-137`, already uses `<input type="range" min="0" max="100">` for
      all five weight bands. (`web/rubric.html` is a read-only review page with no inputs;
      the item doesn't apply there.) See **X25** below: the slider UI itself isn't wired to
      the real proposal API yet. 2026-09-17: that read-only page's Must-have/Counts-in-favour
      sections were themselves silently dropping almost every real criterion — see **X65**.
- [x] AI-prefill industry-standard weights — done as a deterministic template, not a live
      LLM call: `app/core/rubric_presets.py`'s `MARKET_STANDARD` preset, served via
      `GET /rubrics/weightings` and applied through `rubric_service.create_version:400-403`.
      Flagging the "AI" word choice in case a literal LLM-generated prefill was intended.
- [~] Allow HR override and custom criteria — backend fully supports it:
      `add_weight`/`update_weight`/`bulk_set_weights` (`rubric_service.py:479-530`) take
      arbitrary labels/categories, and the named-approver override workflow
      (`whatif_service.propose/approve/reject/create_rubric_draft`,
      `app/db/models.py:413-449` `WhatIfProposal`, routes in `app/api/analytics.py:284-380`)
      is real and tested (B17, 16 passing tests). X25 closed (2026-09-13) — the propose
      button now drives this end-to-end; usable, though approve/reject/create-draft still
      have no screen (backend only).
- [ ] Test the generated weights against the actual demo JD — no demo JD fixture exists in
      this repo (checked `sample_cvs/` and all of `tests/`); the real client JD lives outside
      git per the prior handoff. Blocked on that JD being made available, not on code.
- [x] Manually added requirements in the main setup screen (`new-campaign.html` step 3) now
      reach the weight system — see **X28**. Previously `add_weight` was only reachable from
      the What-if HR-override path; this session gave the everyday "Add a requirement" flow
      an Apply action onto the same service call. Weights across Must-have + Preferred now
      auto-adjust to keep the group at 100 pts on type/add/remove. 2026-09-13, later, on direct
      instruction: the manual "Normalize to 100" button removed from `new-campaign.html`
      entirely (button, its `#normalize-weights-btn` wiring and the `weights/normalize` call
      site) — auto-balancing is now the only way weights reach 100; the backend
      `.../weights/normalize` endpoint itself is untouched (Ankush-owned, still reachable via
      API if needed elsewhere).
- [x] **X33** (found and fixed, 2026-09-13) — screening could not be run at all after JD
      extraction; see `04-KNOWN-DEFECTS.md`.
- [x] **X64** (found and fixed, 2026-09-17) — deleting a Must-have/Preferred row never told the
      server, and the AI weight suggestion silently weighted invisible `INFORMATIONAL` rows; both
      could push the real server-side total past 100 with the on-screen note still reading
      "100 pts", failing Submit with an untraceable error. Both closed without reintroducing the
      removed Normalize button; see `04-KNOWN-DEFECTS.md`.
- [x] Penalize overqualified candidates on a years-of-experience criterion (2026-09-17) —
      `app/core/criterion_scorer.py`'s `_coverage_for_years` discounts coverage once effective
      years exceed 2x the requirement, floor 0.5 at 5x (e.g. a role needing 2 years no longer
      scores a 10-year candidate as an ideal fit). User-directed: criterion-score-only (no new
      eligibility rule), gradual/capped curve. See `docs/DECISIONS.md`, 2026-09-17 B07. New test:
      `tests/test_evaluations.py::test_experience_criterion_penalizes_overqualification` — passes,
      along with the full `tests/test_evaluations.py`, `test_rubrics.py`, `test_requirements.py`,
      `test_rubric_presets.py` (99 + 49 passed, re-run this session).

### B08 — Critical UX polish
Owner: Ankush

- [~] Colour semantics **for status indicators only**: green = confirmed/success ·
      amber = attention · red = critical · grey/muted = low-priority information.
      Brand chrome (nav, headers, KPI anchors) stays maroon. The defect being fixed is
      that a confirmed/positive state currently renders maroon, and maroon demands caution
      rather than reading as positive. There is no red token in `app.css` today.
      2026-09-13: "Confirmed" now reads green on `candidate.html` — the rubric hbar chart
      (`s1`→`teal` class, `.hbars`/`.legend` in `web/assets/app.css`) and the per-criterion
      `.verdict` pills (new `.verdict.good`, reusing the existing `--teal`/`--teal-soft`
      "good" tokens rather than repointing the shared ordinal `--v-strong` scale, which other
      pages — `handoff.html`, `interview.html` — reuse for non-good/bad magnitude). Scoped to
      `candidate.html` only; amber/red/grey semantics and a sitewide rollout are still open.
      Browser-verified live against a real evaluation (Tariq Al-Naimi, HSE Officer campaign).
      2026-09-15: extended to `web/compare.html`'s score-driven pills (page-scoped `.fit`
      class, not a repoint of the shared `.verdict`/`--v-strong` scale) — see the `B16` row
      below. Still not a sitewide rollout; `handoff.html`/`interview.html` untouched.
      2026-09-13, later, on direct instruction: a recruiter's own SHORTLIST/HOLD/REJECT
      disposition (a different concept from the AI's ordinal verdict scale above) now reads
      green/yellow/red everywhere it's shown. Added `--red`/`--red-soft`/`--red-ink` tokens
      (`web/assets/app.css`) — there was no red in the palette at all before this. Fixed a real
      inconsistency on `web/decisions.html`: `.abtn.done` was shared by SHORTLIST *and* REJECT,
      so a rejected candidate's pill rendered identically to a shortlisted one (only HOLD had
      its own colour); REJECT now gets its own `.abtn.done.reject` (red). The pre-decision
      Shortlist/Hold/Not now buttons on that page, and the SHORTLIST/HOLD/REJECT buttons on
      `candidate.html`, now tint to their own colour always (not just on hover), a lighter fill
      for the AI-recommended one (`.primary`), and a solid fill for the recruiter's actually
      recorded decision (new `.selected` state, applied both from history on load and from a
      fresh click — previously nothing visually marked which button was clicked). Browser-
      verified live: `decisions.html`'s "Shortlisted" pill computed to `--teal`
      (`rgb(44,107,98)`); `candidate.html`'s three buttons computed correctly against a real
      recorded decision (SHORTLIST `.selected` solid teal, HOLD `.primary` light gold matching
      the AI's own recommendation, REJECT plain with red outline/text).
      2026-09-13, later, on direct instruction: the pre-decision REJECT button on
      `decisions.html` read "Not now" (its `.abtn.reject` styling already matched SHORTLIST/
      HOLD's plain disposition-name labels — only REJECT's text was a euphemism) and the
      recorded-decision label read "Not taken forward" instead of a plain past-tense match to
      the other two ("Shortlisted", "On hold"). Both now read "Reject" (button) and "Rejected"
      (recorded state) in `renderRows()`'s `DONE` map, `web/decisions.html`. Browser-verified
      live: clicking Reject on a real candidate (Carlos Mendes, HSE Officer campaign) recorded
      the disposition and rendered "Rejected"; a previously-rejected candidate (Tariq Al-Naimi)
      also now reads "Rejected" on reload.
- [~] Use professional, simple headers — 2026-09-13: added a page-state kicker (name + one-line
      explanation) above the fold on `candidate.html`, `compare.html`, `leaderboard.html`, the
      three journey pages that had no page-level title at all (every other journey page already
      carries this via its `.arch`/`.date` banner). Browser-verified live. Later the same day,
      on direct instruction: the kicker text (the page's actual name — "Candidate 360",
      "Compare candidates", "Candidate shortlist") was a 12.5px uppercase eyebrow label smaller
      than the 14.5px explanation paragraph under it — backwards for something that is the page
      title, not a label above one. `.page-state .kicker` is now 26px/ink/title-cased, the `<p>`
      13.5px, in `web/assets/app.css`. Browser-verified live. Not done: the other B08
      header/hierarchy bullets below.
      2026-09-13, later: audited every `web/*.html` page for "name of the page + a one-line,
      non-technical explanation of what it does" — 22 of 23 pages already had one (via `.arch`
      or `.page-state`); the one gap was `new-campaign.html`'s "Start a new role" title, which
      had no explanation at all. Added one. Also bumped `.arch h1` (200→600 weight, its `<b>`
      inner span 500→800) and `.page-state .kicker` (500→700) sitewide — both read as visibly
      thin/medium rather than bold at the previous weights, on direct instruction that every
      page's name should be "bold and visible". Same banner/brand styling (maroon, lattice
      pattern) otherwise untouched.
      2026-09-13, later, on direct instruction: `.page-state` itself (the "Candidate 360" /
      "Candidate shortlist" kicker, on `candidate.html` and `leaderboard.html`) now carries the
      same maroon background and lattice pattern as the hero banner beneath it — previously a
      plain light strip sitting on the sand background above the maroon hero, now merged into
      one continuous band. Scoped to these two pages' own `<style>` blocks (not the shared
      `.page-state` rule in `app.css`), since `compare.html`'s instance was not part of this
      instruction and keeps its existing light styling. `.page-state .kicker` on these two pages
      is bumped 26px→34px, white. Browser-verified live on both pages.
- [~] Clarify page blocks and hierarchy — 2026-09-13: removed a duplicated "What the checking
      agent found" heading on `candidate.html` (the static band label and the JS-rendered
      challenge-agent card each printed their own copy; JS now only fills the shared aside).
      Browser-verified live with a real evaluation. Rest of this bullet not scoped this session.
- [x] Align the rubric hbar chart's bars — 2026-09-13, direct instruction from a screenshot: each
      `.hbar` row was its own independent grid, so a row's label/track boundary sat wherever
      *that row's* label text ended — "REQ-06 Ethylene/olefins experience" pushed its bar's
      start well right of "REQ-02 Diploma"'s. `.hbars` (`web/assets/app.css`) is now the single
      grid and every `.hbar` contributes its three children via `display:contents`, so the
      label/track/value columns are shared and every bar starts at the same x position
      regardless of label length. Applies to every page using this shared component
      (`candidate.html`, `handoff.html`, `interview.html`), not just Candidate 360. Mobile
      stacked layout (≤600px) adjusted to match. Browser-verified live at desktop width.
- [ ] Reduce whitespace, horizontal width, and scrolling
- [x] Make the campaign stage immediately visible — 2026-09-13: the floating campaign-stage dock
      moved from bottom-right to top-right (`web/assets/app.css`), and its stage list now shows a
      green tick on every completed stage and a red dot on the current one
      (`web/assets/app.js`). Browser-verified live on Candidate 360.
- [~] Design for easy QChem / Arabic-account comprehension — 2026-09-13: the disposition
      comment-box draft (`app/services/disposition_service.py::_suggested_rationale`) no
      longer opens with the literal label "AI assessment" or a dense run-on sentence
      ("Confirmed: … Flagged: …"); it is now a short plain-language bulleted draft — "Score:
      42 out of 100 — one to review." / "What's confirmed:" / "Worth a closer look:" — for a
      non-technical hiring manager to read or edit as-is. Also removed the raw-enum leak this
      surfaced: `web/candidate.html`'s decision-status line was printing
      `evaluation.next_action` (e.g. `MANUAL_REVIEW`) and `latest.disposition` verbatim,
      against the `AuditAction`-label convention in this file's own conventions section; both
      now go through a plain-words map (`dispositionText()`), and the "AI recommends; a
      person decides…Next action: …" line the user asked removed is gone — the panel falls
      back to the existing static human copy until a decision is made.
      `tests/test_decisions.py` updated for the new rationale copy, 43/43 passed.
- [ ] Functional journey work comes before cosmetic polish
- [x] 2026-09-13, later, on direct instruction — several UI removals/reworks on
      `candidate.html`, `decisions.html`, `new-campaign.html`:
      1. Removed the "Where he stands on the rubric" `.hbars` chart from `candidate.html`
         chunk 1B entirely (that chart was static sample markup, never wired to live data —
         confirmed by reading the page's own render code). This makes the 2026-09-13
         "align the rubric hbar chart's bars" / "Confirmed reads green" bullets above no
         longer applicable to `candidate.html`'s chunk 1B specifically; both fixes still
         apply where they were also verified — the per-criterion `.verdict` pills further
         down the same page, and `handoff.html`/`interview.html`'s own `.hbars` charts,
         untouched by this change.
      2. The "Strongest reason to see him" / "Biggest gap" sentence that sat below that
         chart is kept, but split onto two separate lines and boxed in a new
         `.rubric-callout` component (`web/assets/app.css`) — sand background, gold left
         border, one line per fact, matching the visual language `decisions.html`'s
         `.confirm-box` already used elsewhere in the app.
      3. Removed "Ask for more" (`REQUEST_REVIEW`) — the one live button on
         `candidate.html`'s decision row, and the seven static sample-only occurrences on
         `decisions.html` (dead markup replaced by `renderRows()` once live data loads, but
         visible before that / on load failure).
      4. Removed the static line "This score is a recommendation. A person decides —
         Fatima Al-Rashid, or whoever the campaign is assigned to — never the system." from
         `candidate.html` entirely, per direct instruction — the element (`#c-decision-status`)
         stays in the DOM empty, since the same element is still how the page reports "Decision
         recorded…" after a click.
      5. Every hardcoded `'Fatima Al-Rashid'` actor/approver string in `candidate.html`,
         `decisions.html` and `new-campaign.html` now reads the real signed-in user
         (`window.__r360ActorName()`, new helper in `web/assets/app.js`, backed by
         `window.__r360Me` from the existing `/api/auth/me` session — B22 phase 1). Test
         fixtures under `tests/**` were left alone: they are arbitrary sample identities for
         API tests, not a "logged-in user" concept, and changing them would not test anything
         different. `web/DATA.md`'s "Signed-in user" line updated to describe this instead of
         naming a fixed person; its rubric-approval-history line (a past, dated event) is left
         as recorded.
      Not browser-verified live this session — see `docs/SESSION-STATE.md`.
- [x] 2026-09-13, later, on direct instruction — a "Mark this page done" button, bottom-right,
      on every page carrying the campaign-stage floating nav (`web/assets/app.js`'s stage
      switcher). The nav's green tick previously marked every stage the person had merely
      navigated past (`position < index`); it now marks only a stage whose done button was
      actually clicked (`localStorage`, keyed by campaign id), so opening a later stage no
      longer implies the earlier ones are finished. Not browser-verified live this session.

### B09 — Sunday review
- [ ] Schedule the Sunday review at 14:00 IST (2026-09-13)
- [ ] Validate the demo before the Monday client session
- [ ] Assign a calendar-invite owner
- [ ] Review major gaps while correction time remains

---

## P1 — complete the product after the demo

### B10 — Email integration
Owner: Ankush + Subhadeep (confirm)

**Outbound half built this session (worktree `agent-a94d5c415bcf5c508`); fake-COM and API
tests pass, live send against a real signed-in mailbox is still unverified.** `web/comms.html`
composes templates and records a message in `AuditEvent`; when `email_backend="outlook"` is
set, `app.core.outlook_adapter.OutlookMailAdapter` now attempts a real send (CC support, an
explicit `email_sender_address` account matched the way B11's calendar invite already does,
`pythoncom` init/uninit around the COM call). A new endpoint,
`POST /api/campaigns/{campaign_id}/reports/email-to-hiring-manager` (`app/api/reports.py`,
wired to a button on `web/decisions.html`), sends the campaign's shortlist report the same
way and records it through the existing `AuditAction.SENT_TO_HIRING_MANAGER`. Every outbound
subject carries `app.core.mail_ref.ref_tag`'s `[REF-{campaign_id}]` /
`[REF-{campaign_id}:{candidate_id}]` tag, the fixed contract a parallel, separate piece of
work (inbound reply reading) matches against. Inbound — parsing replies and updating the
candidate stage from them — is that separate work, not covered here; see
`docs/SESSION-STATE-b10-outbound.md` for the evidence-based done/left split.

Local / demo implementation:
- [x] Use the local Outlook mailbox through `pywin32` — `app/core/outlook_adapter.py`,
  fake-COM tests pass (`tests/test_outlook_adapter.py`); live mailbox still unverified
- [x] Send the shortlisted-candidate report to the hiring manager —
  `POST /api/campaigns/{campaign_id}/reports/email-to-hiring-manager` (`app/api/reports.py`),
  tests pass (`tests/test_reports_api.py`)
- [x] 2026-09-17, on direct instruction (`X66`): this send now doubles as the `B01`/lifecycle
  handoff — it resolves the recipient to a known `HIRING_MANAGER`/`ADMIN` account and moves
  every `SHORTLIST`/`INTERVIEW` candidate in the report to `WITH_HIRING_MANAGER`, owned by
  that manager (`_handoff_to_manager`, reusing `lifecycle_service.send_to_hiring_manager`).
  `handoff.html`'s separate "Ready to send"/"Send to hiring manager" button is removed —
  there is no other trigger for that move now. See `04-KNOWN-DEFECTS.md` (`X66`) and B01 item 4.
- [x] Formal pre-written email text, with a bulleted per-candidate summary table before the
  zip attachment — `app/api/reports.py`'s `_report_html_body`/`_summary_table_html` build a
  greeting/context/closing HTML message with a Candidate/Overall Score/Why This
  Score/Strength/Weakness/Overall Feedback table (bullet lists per cell, from
  `Evaluation.narrative`, `.strengths`, `.gaps`), sent via a new `MailAdapter.send(html_body=)`
  parameter (`OutlookMailAdapter` sets `mail.HTMLBody`, plain `body` kept as the fallback);
  tests pass (`tests/test_reports_api.py`, `tests/test_outlook_adapter.py`)
- [x] Attach the shortlisted candidates' Candidate 360 PDFs to that email as one zip —
  `X54`, `app.api.exports.build_shortlist_zip` (shared with the `GET /reports.zip` download),
  `MailAdapter.send()` gained an optional `attachments` parameter; tests pass
  (`tests/test_outlook_adapter.py`, `tests/test_reports_api.py`, `tests/test_exports.py`)
- [x] Put the recruitment/application ID in the subject — `app.core.mail_ref.ref_tag`, used by
  both the candidate-message path and the hiring-manager report; tests pass
  (`tests/test_mail_ref.py`, `tests/test_messages_api.py`)
- [x] Parse replies where the subject is unchanged — `app/core/reply_ingestion.py`'s
  `InboxReader` reads the local Outlook Inbox and matches the `[REF-{campaign_id}]` /
  `[REF-{campaign_id}:{candidate_id}]` tag as a substring of the subject (so an "RE:"
  prefix never breaks the match), gated on `email_backend == "outlook"` exactly like the
  send-side adapters. 18 tests, `tests/test_reply_ingestion.py`, fake-COM-double only —
  unverified against a live mailbox, same caveat as B10's mail adapter and B11's calendar
  adapter.
- [x] Update the candidate stage from the reply — `app/services/reply_service.py` classifies
  each reply (`app/core/reply_classifier.py`, deterministic rules + LLM fallback) and always
  records it as a proposed decision; when `settings.auto_apply_reply_decisions` is explicitly
  turned on (default off, same opt-in shape as `email_backend`), a hiring manager's
  approve/decline/need-more-info reply is applied through the existing
  `lifecycle_service.record_manager_review` call — nothing else is auto-applied (see B11 note
  below and `docs/DECISIONS.md`). 12 tests, `tests/test_replies_api.py`.

Deployed implementation — not required for the local demo. Define later:
- [ ] SMTP or email service
- [ ] General / service mailbox
- [ ] Authentication
- [ ] Reply ingestion
- [ ] Deployment and security controls

### B11 — Interview scheduling
**Local Outlook demo path added; live delivery unverified.** `web/interview.html` records
schedule and feedback with real lifecycle and audit rows. Its sender is Subhadeep's
signed-in Outlook account; schedule recipients are limited to Daipayan or Ankush plus
Chiranjib or Preetam. Candidate CV addresses are excluded for this demo. The API records
whether Outlook accepted the invite for sending, and shows failure separately from simulation.

- [~] On schedule-form submit, send a calendar invite through `pywin32` to the selected approved demo recipients; fake-COM and API tests pass, live send still unverified

- [ ] On hiring-manager approval, create an invite automatically (current demo sends when schedule form is submitted)
- [ ] Block the interviewer and candidate calendars
- [ ] Do not require a Teams link initially
- [ ] Track invite status: sent, accepted, declined
- [ ] Link the invite to the recruitment/application ID
- [~] Capture interview feedback from the reply or the workflow — B10's reply classifier
  (`app/core/reply_classifier.py`) can read approve/decline/need-more-info off a reply on a
  candidate thread and, opt-in, apply it as a hiring-manager verdict via
  `lifecycle_service.record_manager_review`. It deliberately does NOT auto-fill the
  structured post-interview feedback form (`InterviewRecommendation` + scores/strengths/
  concerns in `app/api/interviews.py`'s `/feedback` route) — an email reply doesn't reliably
  contain those fields, so that stays a proposed decision a person fills in by hand. See
  `docs/DECISIONS.md` (B10) for the reasoning.

### B12 — Offer management
**Proxy built, document integration pending.** `web/offer.html` records package drafts,
revisions, simulated send and candidate response in audit rows. No offer-letter template.

- [ ] Create an approved offer-letter template — `email_sender.py` has a basic selection
      template, not an offer letter
- [ ] Populate candidate, role, salary, declaration, joining terms, other approved fields
- [ ] Generate a draft for HR review
- [ ] Send it to the candidate — `send_email()` exists but no offer workflow calls it
- [~] Track accepted / declined / pending — lifecycle and UI work; external reply ingestion pending
- [x] Update the final hiring outcome — accepted offer can be recorded as hired in handoff
- [x] Preserve the offer and response in the audit trail — structured `AuditEvent.after`

### B13 — Hiring approvals and governance
Owner: Ankush + Solution Team

**Proxy built, cost-centre and delegation now real, remaining governance policy pending.**
`web/approvals.html` requests named approval, routes cost-centre sign-off, grants or returns
with reasons. State and audit rows are real. 2026-09-13: a `CostCentre` registry
(`app/db/models.py`) now backs the cost-centre step — `app/services/cost_centre_service.py`
validates the code and the claimed budget holder against it before `app/api/approvals.py`
moves anyone, and the registry's own holder becomes the record's owner rather than whatever
the caller sent. `CandidateLifecycle.cost_centre_id` stores which budget a hire is against,
carried forward the way `campaign_rank` already is. A `DelegationGrant` ledger
(`app/services/delegation_service.py`) now backs `on_behalf_of_id`: the three approval write
routes accept an optional `on_behalf_of_id` and refuse the move unless an active, unrevoked
grant for the "approval" scope exists. New endpoints: `POST /api/cost-centres`,
`POST /api/cost-centres/{code}/close`, `GET /api/cost-centres`, `POST /api/delegations`,
`POST /api/delegations/{id}/revoke`, `GET /api/delegations`. Migration `b4f7c9a1e3d2`. Tests:
`tests/test_cost_centre_delegation.py`, 11 passed; `tests/test_approvals_api.py` updated to
seed a real cost centre (3 tests previously asserted the unvalidated behaviour), 10 passed;
`tests/test_recruitment_360_journey.py` updated the same way, 1 passed. Multiple approval
levels by seniority, external approval messages and the remaining governance items below are
still open.

- [ ] Route hiring-manager and business approvals
- [ ] Support multiple approval levels by seniority
- [x] Apply cost-centre controls — `CostCentre` registry validates code + budget holder;
      `CandidateLifecycle.cost_centre_id` stores it. See above.
- [x] Apply delegation-of-authority rules — `DelegationGrant` ledger checked against
      `on_behalf_of_id` before an approval move is made. See above.
- [ ] Capture mandatory approval evidence through email or system
- [ ] Record interviewers and approvers
- [ ] Add a critical behavioural/integrity flag
- [ ] Support "do not consider for future recruitment"
- [ ] Assess payroll / HR-system integration
- [~] Show a BU-level pre-approved budget envelope at the cost-centre step, per the business's
      framing that recruitment works within a prior-year, BU-approved allocation rather than
      inventing a budget at hiring time (2026-09-14, demo-readiness pass). `CostCentre` extended
      with `business_unit`, `currency`, `fiscal_year`, `role_grade`, `approved_headcount`,
      `salary_band_min/max` (migration `e1a2b3c4d5f6`, all nullable/additive). `web/approvals.html`
      (via `assets/journey.js`) replaces the free-text cost-centre code with a picker over the
      real registry, auto-fills the budget holder from the chosen centre (removing a
      previously-possible mismatch against `cost_centre_service.validate`), and renders the
      envelope — BU, cost centre, budget holder, fiscal period, approved requisition/headcount,
      approved salary band — clearly labelled `ILLUSTRATIVE — synthetic pre-approved allocation
      for this demo, not a live ERP feed`. Deliberately does **not** attempt a running
      multi-hire budget ledger or any USD/QAR conversion — the seeded demo cost centre states
      its own values in QAR throughout, so no cross-currency comparison is ever needed. Tests:
      `tests/test_cost_centre_delegation.py` (2 new), `tests/test_jd_library.py`. Browser-
      verified live against a throwaway campaign reaching the cost-centre step: envelope card
      rendered with real registry data (BU "Technical Services", holder "Imran Qureshi", band
      "QAR 180,000 – 220,000"). Remaining: no running total across multiple hires against one
      centre's envelope (out of scope — see the readiness doc's rationale).

### B14 — Campaign creation and CV ingestion

**Current remaining-work order:** 08-TWO-PERSON-DELIVERY.md section 9 supersedes older proposed navigation/rail/upload-page requirements below. Card actions expose the saved stage; priority is persistence, approval/version correctness, recovery and complete browser acceptance.

- [x] Start Campaign directly lists saved campaigns beside Create a campaign. Each maroon
      action names and opens the saved next stage. Verified on local `Subodhip`, 2026-09-12:
      role-only draft → JD; saved JD → read JD; persisted requirements → review rules;
      approved → CV upload; completed run → its exact shortlist. Detail reads are bounded
      to four campaigns at a time on Start Campaign; failures offer Retry. Empty lists
      show no samples. Existing campaigns cards also resolve their button from saved records.
      Full suite: 589 passed; final frontend suite: 37 passed. Desktop/mobile inspected.
      New setup has a Save progress action before extraction; no sample title/date/vacancies.
      This supersedes the earlier status-only approximation below. No full new screening
      run was performed; candidate stages after shortlist remain individual workflows.
      **2026-09-14 update (X39):** "candidate stages after shortlist remain individual
      workflows" is no longer true for the saved-campaign card's own resume label — see X39 in
      `04-KNOWN-DEFECTS.md`. `CampaignSteps.resolve()` now reads per-campaign lifecycle state
      and surfaces the furthest-progressed candidate's real stage ("Interview scheduled", "Offer
      sent, awaiting response", etc.) instead of freezing at "Review the shortlist" the moment a
      campaign reaches `REVIEW`. Verified live against two real seeded campaigns.

Owner: Ankush · Not fully audited.

- [x] Refine campaign-journey design brief against B01–B24 and user-requested progressive disclosure — `07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md`, 2026-09-12; document reviewed, no implementation implied.
- [~] Review and implement durable setup, recovery and contextual workspace slices from that proposal; preserve demo priorities.
      Navigation scaffold, 2026-09-12: five top tabs (Today · Start Campaign · What-if Analysis · Audit · FinOps)
      across all pages, and a new `web/start-campaign.html` grouping the workspace into Set up · Assess ·
      Review & hire · Track outcomes with direct Candidate 360 access. Today's duplicate launcher band removed.
      Durable one-campaign draft and resume landed 2026-09-12 (X18): `web/new-campaign.html` creates the
      campaign once and updates it by `PATCH` from every later step, and restores the saved role details
      on reopen. `web/campaigns.html` shows a "Not finished yet" band listing each draft with a
      Continue link.
      Draft identity moved to the URL 2026-09-12 (X19): the `campaign_id` in a tab's own URL is the only
      source of which draft that tab edits, stamped in by `history.replaceState` after the create. The
      shared `localStorage` key is gone, so two setup tabs are now two campaigns. Two-tab browser run
      and twelve source guards in `tests/browser/test_campaign_draft_contract.py`.
      An early save on a resumed draft no longer overwrites it 2026-09-12 (X20): the restore is now the
      first entry in the save queue, so a click made while the draft is still loading waits and then
      saves the restored values. Reproduced first through a four-second proxy, which showed the page's
      prefilled sample values replacing a real draft's title, description, site and vacancies. Fourteen
      source guards in `tests/browser/test_campaign_draft_contract.py`.
      A campaign past setup is no longer destroyed when it is reopened 2026-09-12 (X22): `restoreDraft()`
      loads the campaign whatever its status, so the form no longer keeps its sample values and the save
      that CV upload runs before posting a batch no longer overwrites an approved role. Browser-verified.
      Still absent: the Campaigns page still lists only drafts and runs, so a campaign that is set up and
      waiting for CVs appears nowhere (X22, remaining), six campaign cards on that page are static sample
      HTML (X23), and there is no standalone CV upload page — upload lives inside the setup wizard.
      Still absent: server-side replay protection for a lost response, and campaign versioning. Both are
      backend work (Ankush). No backend change was made in this slice. X21 is open: restoring a stored
      location that is not one of the site select's three options blanks it, and the next save persists
      the blank.

- [~] Setup and CV ingestion must be independently resumable within one campaign. Early role/JD save and Upload CVs deep links exist; complete approval/version handling and upload recovery. A separate upload page is not required (08 section 9).
      2026-09-17: reopening Upload CVs on a campaign that already has batches (e.g. via the
      Shortlist journey stop's "Upload CVs" link) used to still say "No applications chosen",
      giving no sign whether choosing a file would add to or replace what was already screened.
      `web/new-campaign.html` now lists every already-uploaded filename (`GET
      /api/campaigns/{id}/batches` then `GET /api/processing/batches/{id}/jobs` per batch)
      above the file pickers, so "Choose applications" reads as adding more. Browser-verified
      against a live REVIEW campaign with 20 uploaded CVs across three batches.
- [x] Save the campaign before importing CVs — the campaign is created when the description is read and
      updated in place from then on; CV upload runs against that same record. Browser-verified 2026-09-12.
- [x] Support drafts — `CampaignStatus.DRAFT` plus a durable draft the recruiter can leave and continue.
      Verified 2026-09-12 in the browser: one draft after reload and a second read, role details restored
      on reopen, save reports the server outcome and keeps the draft through a server outage.
- [ ] Reuse a recurring campaign or JD
- [ ] Do not reuse old CV attachments automatically
- [x] Accepted CV formats — `.pdf`, `.docx`, `.doc` and `.pptx`. PowerPoint added 2026-09-12
      (`B14`, commit `174a511`): text from shapes, table cells and slide notes, slide N
      mapped to page N so evidence still cites a page. `.ppt`, the old binary format, is
      rejected with a message naming `.pptx`.
- [ ] Store requirements and the approved rubric with the campaign
- [ ] Link the repository later, when CVs become available

**Acceptance criteria, 2026-09-12, from the user's stated requirement** — a recruiter starts
a campaign, leaves, comes back later to upload CVs, runs several campaigns at once, and sees
every campaign with its progress. Covers X22's remainder and X23; proposed shape, not yet
agreed with the user:

- [x] `web/campaigns.html` lists every campaign whatever its status (X22 remainder) — a
      campaign that is approved and waiting for CVs must appear. `GET /api/campaigns` with
      no `status` parameter already returns all of them; the page previously asked for
      `?status=DRAFT`. No backend change: `app/api/campaigns.py:27` makes `status` optional.
      Landed 2026-09-12, browser-verified against a fixture `APPROVED` campaign with no CVs
- [x] Per-campaign progress is derived by joining that list with `GET /api/runs` on
      `campaign_id`, client-side. The run carries `count`, `submitted_count` and `status`
      (`serialize_run`, `app/api/compat.py:300-318`); `CampaignOut` carries no counts, so
      the join is what supplies progress. A campaign with no run reads as waiting for CVs,
      not as zero progress. No new `current_step` field, and no per-campaign fetch loop.
      Landed 2026-09-12. The card's own tag now reads the campaign's stored status through
      a plain-words map, so a finished run no longer claims the campaign is finished when
      someone still has to decide
- [ ] **The number of campaigns is unbounded** (user requirement, 2026-09-12: "we should be
      able to create as many campaigns as possible"). Nothing caps creation today — no
      unique constraint on `Campaign.name`, no limit in `create_campaign`, and
      `list_campaigns` (`app/services/campaign_service.py:87`) returns every row with no
      pagination. Returning all rows is not evidence of scale; list/search/pagination and bounded detail reads need validation
- [ ] Progress never depends on a campaign appearing in the capped runs list. `/api/runs`
      defaults to `limit=20` and caps at 100, so past 100 runs a campaign would render as
      "waiting for CVs" while it is actually running — a real record shown as absent, the
      same class of defect as X22. `campaign.status` is the authoritative progress signal
      and it lives on the campaign row itself (`DRAFT → AWAITING_RUBRIC_APPROVAL →
      APPROVED → PROCESSING → REVIEW → CLOSED`). Run counts enrich a card when the run is
      in hand; their absence never downgrades what the status already states
- [ ] If counts are later wanted for every campaign regardless of scale, that is a backend
      item for Ankush — progress counts on the campaign list response — not an N+1 fetch
      loop from the page. Not scheduled here
- [x] Every setup step is reachable by its own deep link, so a recruiter can leave after
      approval and return straight to CV upload without restarting the wizard. Landed
      2026-09-12 (B14 slice 2, commit `6f5ba5c`). A card links to
      `new-campaign.html?campaign_id=<id>#<step>`, where the step id comes from the
      next-step rule, now shared in `web/assets/app.js` so both pages read one rule. Each
      step is a hash, so deep links and browser Back are the browser's own behaviour
      (`AGENT-START-HERE.md` §5); a `hashchange` listener moves the page when only the
      hash changes. Landing on band 3 reads the campaign's requirements back first and
      opens the collapsed band before it scrolls. Browser-verified across four statuses
      including Back between steps. Not covered: `assess` has no destination (nothing to
      act on), and there is still no separate rubric-approval screen, so `#rubric` opens
      the band that holds the rules
- [ ] Verify interrupted uploads and concurrent campaign isolation. Keep campaign/batch/run context and honest local-file versus uploaded-file state. No standalone upload page prerequisite (08 section 9).
- [x] The "where did I leave off" resume label (this feature) was intermittently stuck on
      "Checking saved stage…" forever — not a gap in the resume logic itself, but `web/sw.js`
      silently substituting the wrong cached page for a failed script fetch. Fixed as **X27**.
- [x] Campaign cards on `start-campaign.html`/`campaigns.html` and the setup header on
      `new-campaign.html` now show the campaign's `short_id` (B20, `RC36-01`-shaped),
      alongside the existing job-title/location line, on user request.
- [~] The six static sample cards (X23) are removed or unmistakably labelled as sample data,
      so a live and a fictional card are never shown as the same thing. Half landed
      2026-09-12: they go whenever any real campaign exists, not only when a run exists.
      With no campaigns at all they still render unlabelled — see X23

### B29 — Clicking a saved campaign lands each role on its own next action

Direct instruction, 2026-09-23: HR reopening a campaign must land on the exact page where
they left off; a hiring manager clicking a campaign must land on the page that needs *his*
action, not wherever the furthest-progressed candidate happens to be (a different candidate
in the same campaign can be further along than the one waiting on him).

- [x] Fixed a real bug in the existing "where did I leave off" resume logic (`B14`) that this
      request exposed: `web/campaigns.html`'s `renderRuns()` built its `campaign` object from
      `run.campaign` (the embedded summary), which carries no `id` field — only `run.campaign_id`
      does. `resolveButton()` requires `campaign.id` and silently no-ops without it, so every
      completed-run card was stuck on the hardcoded "Review the shortlist" → `leaderboard.html`
      default even once the campaign had actually moved on to handoff/interview/offer. This is
      exactly HR's "I did till handoff and left it" complaint. Fixed by stamping
      `run.campaign_id` onto the campaign object before use. Browser-verified: run-based cards
      now correctly resolve to `handoff.html`, `interview.html`, `offer.html`, `pipeline.html`
      per the campaign's furthest lifecycle stage, matching draft/waiting cards' existing
      behaviour.
- [x] Added the hiring-manager-specific override: `web/campaigns.html` now builds one shared
      per-campaign `/api/campaigns/{id}/lifecycle/funnel` read (`fetchAwaitingMap`, replacing
      `B28`'s `markAwaitingHisDecision`'s own separate fetch of the same data, which would
      otherwise race the card's own `resolveButton()` resolution) and, only when
      `window.__r360Locked()` is true, `resolveButton()` overrides the generic furthest-stage
      result with a direct link to his own pending action — `handoff.html` ("Record your
      shortlist verdict") when a candidate is `WITH_HIRING_MANAGER`, else `interview.html`
      ("Record interview feedback") when one is `INTERVIEW_SCHEDULED`. HR's own resolution is
      untouched. Browser-verified live: signed in as `subhadeep.m@protivitiglobal.in`
      (`HIRING_MANAGER`), every campaign tagged "waiting on you" now opens directly on his
      pending decision; signed back in as HR (`ankush.saxena@protivitiglobal.in`) and confirmed
      no regression to the furthest-stage resume behaviour.
- [ ] Not verified: a campaign where the hiring manager's own funnel counts are all zero but a
      draft-stage recruiter view is open concurrently (drafts are hidden for him already, `B28`)
      — no case found where this matters, not specifically tested.

Owner: Subhadeep (`web/**`).

### B15 — Historical candidate reuse
**Nothing built.** No waitlist, backup-candidate or next-ranked code.

2026-09-15, on direct instruction: the candidate-shortlist list view itself (formerly
`web/leaderboard.html`) was merged into the new `web/candidate-assessment.html`, alongside
B16 (compare) and B18 (Candidate 360) — one page/URL instead of three, styled to the site's
existing maroon/Readex Pro theme, not the two reference mockups supplied (one of which
already matched `start-campaign.html`'s real UI; the other did not match this project at
all). This runs against `07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md` §5's recommendation to keep
Candidate 360 scoped/separate from a candidate list — flagged to the user before building;
they chose to proceed and supersede it. See `DECISIONS.md`. `web/leaderboard.html` itself is
unchanged and still present but no longer linked from any nav/CTA (superseded, not deleted).

2026-09-15, later, on direct instruction: the merge above is reverted. `web/candidate-assessment.html`
is deleted; the shortlist stage points back at `web/leaderboard.html` everywhere (`app.js`'s
stage table and `CampaignSteps.href`, `campaign-ai-start.js`'s post-screening redirect,
`start-campaign.html`'s workspace directory, `pipeline.html`, `index.html`, `campaigns.html`,
`new-campaign.html`, `discover.html`, `decisions.html`'s "Open full shortlist" links). Shortlist,
Candidate 360, comparison and decisions/export are four separate pages again, unchanged from
before the 2026-09-15 merge. See `DECISIONS.md`.

- [ ] Preserve the campaign ranking
- [ ] Keep backup and waitlisted candidates
- [ ] If a selected candidate declines or does not join, surface the next ranked candidate
- [ ] Retain prior outcomes and exclusion flags during future searches

### B16 — Comparison page
Owner: Ankush

2026-09-15: the criterion-by-criterion compare table and its search/filter/pager toolbar
(all `[x]` items below) were carried over into `web/candidate-assessment.html`'s compare
mode (checkbox-select 2-3 rows → "Compare selected" replaces the detail panel with the same
table). `web/compare.html` itself is unchanged but no longer linked from nav — see the B15
note and `DECISIONS.md`. The two open scale items below (`[ ]` — full-population fetch, no
server-side paging) are unresolved in the new page too; nothing here fixes `X12`.

2026-09-15, later, on direct instruction: the merge is reverted — see the B15 note. `web/compare.html`
is linked from nav again (`start-campaign.html`, `pipeline.html` via the shortlist page) and is
once more the only place the compare table lives.

- [x] Display the job role prominently — `web/compare.html:175`
- [x] Use one compact table — rebuilt 2026-09-13 as a real `#/Candidate/Score/
      Experience/Skills/Evidence/Decision` list (`web/compare.html:220`), replacing the
      old fixed 2-3-column dial table. The criterion-by-criterion table is preserved as a
      detail view for whichever 2-3 rows a recruiter selects (`web/compare.html:246`),
      not the page's default rendering.
- [x] Add filters and pagination — search box plus Status/Score/Experience/Skills filters
      (`web/compare.html:183`) and a page-number pager, 25 rows/page (`web/compare.html:236`).
      Verified in-browser against the live `HSE OFFICER · Coastal Terminal` campaign:
      search narrowed 3→1, checkbox selection + "Compare selected" rendered the real
      42-criterion table via `/api/campaigns/{id}/compare`. Filtering/paging is
      **client-side** over the fetched set, not server-side — see the scale item below.
- [x] 2026-09-13, later, on direct instruction — `compare.html`'s header now uses the same
      maroon/lattice `.page-state` band as `candidate.html`/`leaderboard.html`, superseding the
      same-day decision to leave it on the plain light styling (see `docs/DECISIONS.md`, B16
      row). Added a fifth, purely client-side "Sort" filter (`#cx-f-sort` — score high/low,
      experience, skills, name) alongside the existing four, reusing the already-fetched
      `state.evals` array; no new backend call. Browser-verified: header renders maroon
      matching the other two pages at both desktop and mobile widths, and selecting "Name: A to
      Z" re-sorts the visible table immediately.
- [~] Default to shortlisted / top candidates — the list now sorts by score descending
      by default (best candidates lead) and no longer requires explicit `candidate_ids`
      to render something useful, but it still lists the whole campaign, not only the
      shortlisted subset. No default "shortlisted only" filter is applied.
- [x] Show the top 10 first — 2026-09-14, on direct instruction: `PAGE_SIZE` in
      `web/compare.html` dropped from 25 to 10, and the pager text now reads "Page X of Y"
      (`pages = Math.max(1, Math.ceil(total / PAGE_SIZE))`, unchanged formula, just a smaller
      page and an explicit page count so a 7-candidate campaign reads "Page 1 of 1", not an
      inflated page count). Browser-verified live against the real HSE OF campaign (7
      candidates → "Page 1 of 1"); a 12+-candidate campaign to verify the 2-page split was not
      available live this session, but the pager math is unchanged from the already-tested
      25/page version. 2026-09-15, on direct instruction: dropped the leading "start–end of
      total ·" range prefix (e.g. "1–2 of 2 ·") — with only 10/page it was redundant clutter,
      not added information; the pager now shows just "Page X of Y". Browser-verified live
      against the HSE Head · Coastal Terminal campaign (2 candidates → "Page 1 of 1").
- [ ] Design for 10,000–20,000 CV scale — unchanged. `GET /api/campaigns/{id}/evaluations`
      still returns the full result set in one call (no `limit`/`offset`); the new frontend
      does its filtering/sorting/paging in JS over whatever that call returns, so a
      10,000-20,000-row campaign still loads its entire evaluation set into one browser
      response before the table can page it. Real fix is server-side, per `X12`.
- [ ] Avoid full-population fetch/render — same root cause as above; **not fixed this
      session.** One improvement made in the frontend: the recruiter's recorded Decision
      (`GET .../candidates/{id}/recommendation`, no bulk endpoint exists) is now fetched
      only for the current page's rows (≤25 requests), not once per candidate in the whole
      campaign. The main evaluations fetch itself is still unbounded — see `X12`.
- [ ] Add dedicated population analytics only if required

2026-09-15, later, on direct instruction: checkbox-select in `web/candidate-assessment.html`
now opens the comparison in its own browser tab instead of replacing the detail panel in
place — selecting a second candidate's checkbox calls `window.open()` from inside that same
`change` handler (a synchronous user gesture, so it isn't popup-blocked in a real browser),
to `candidate-assessment.html?campaign=<id>&view=compare&candidate_ids=<id>&candidate_ids=<id>`.
The bootstrap script recognises `view=compare` + 2+ `candidate_ids` on load, hides the list
column (`.compare-tab-mode` on `#ca-layout`), and renders the same criterion-by-criterion
table full-width, directly — no extra click needed in the new tab. The sticky "Compare
selected" button still works the same way for a 2nd/3rd pick. Browser-verified live against
the real `HSE Officer · Coastal Terminal` campaign; note the automated browser-preview tool
used for verification blocks non-trusted-event `window.open()` calls and falls back to
same-tab navigation — confirmed the URL/bootstrap contract works correctly either way, real
Chrome allows the popup from a genuine click.

2026-09-15, later still, on direct instruction — two changes to `web/compare.html`'s checkbox
selection and its criterion-by-criterion compare table (the older bullets above describing a
"2-3"/"cap 3" selection limit are now historical; the cap itself is gone):

- [x] Removed the 3-candidate selection cap. `wireRowEvents`'s checkbox `change` handler no
      longer blocks a checkbox once 2 others are selected (`web/compare.html`); the sticky
      selection-bar label dropped its hardcoded "of 3" (now "N candidates selected"). The
      `GET /api/campaigns/{id}/compare` backend route already accepted "two or more" ids with
      no server-side cap, so no backend change was needed. Browser-verified live against the
      real `HSE Officer · Coastal Terminal` campaign (4 candidates, its full roster): selected
      all 4 (previously impossible past 3), "4 candidates selected" showed on the sticky bar,
      and "Compare candidates" rendered all 4 as columns in the compact table.
- [x] Key skills tags in the compact compare table are now expandable. `tagsCell()` still shows
      the first 4 matched-skill tags, but the previously-inert "+N" pill is now a real toggle
      button: clicking it reveals the remaining tags in place and relabels itself "Show less";
      clicking again re-collapses them. Browser-verified live on the same campaign: a "+7" tag
      expanded to the full skill list and collapsed back on a second click.

Neither change touched the `[ ]`/`[~]` scale items above (full-population fetch, no
server-side paging) — out of scope for this slice.

2026-09-15, later still, on direct instruction ("words like potential fit 100% should be
green instead of red") — color semantics fix, overlapping `B08`:

- [x] Score-driven colour now follows the number, not the category label. Browser-verified
      the exact complaint first: a real 100% "Experience match" cell and a "Potential fit"
      compact-compare column-header pill both rendered in the site's maroon/pink ordinal
      tone, which reads as a warning colour on a top score, not a positive one. Added a new
      page-scoped `.fit` pill class (green `>=80`, amber `60-79`, red `<60`, grey/not-scored)
      driven by `fitTier(score)`, and repointed the compact-compare header's fit-status badge,
      the five "Overall/Skills/Experience/Education/Certification match" percentage cells, the
      score dial's ring colour, and the main list's Score/Skills numbers onto it. The Evidence
      column (AI confidence in its own read — strong/mixed/weak) is untouched, still the
      sitewide maroon/gold/grey ordinal scale, since it is a documented separate axis (see the
      code's own comment in `web/compare.html`). Also a general visual pass on the same table:
      subtle row striping, a sticky first column and header background on the compact-compare
      table, slightly bolder dial/candidate-name type. Browser-verified live against the real
      HSE Officer campaign — a 100% "Experience match" cell now renders green, a below-60%
      score/status renders red, at both desktop and mobile widths; `node --check` on the
      extracted inline script passed. See `docs/DECISIONS.md`, 2026-09-15 (B16/B08).
      2026-09-15, later, on direct instruction — thresholds changed from >=80/60-79/<60 to
      **>=70 green / 40-69 amber / <40 red** (`fitTier()` in `web/compare.html`). Browser-
      verified against the same real campaign: 59%/57%/56%/54% now render amber, 30%/24%/17%/
      11% render red.

2026-09-16, on direct instruction ("improve the candidate comparison UI, selected candidates
only, grouped sections") — the compact compare table (`renderCompact` in `web/compare.html`)
now groups its existing rows into five section-header rows (colspan `<tr class="cmp-section">`,
new CSS block) rather than one flat list: **Overall Performance** (overall score, rank in
campaign — new, derived from `state.evals`' existing sort order, not fabricated — AI
confidence, status), **Skills & Qualifications** (skills/education/certification match, key
skills), **Experience** (experience match, years), **Candidate Details** (location), and a new
**Evaluation Insights** section (strengths, gaps, review flags = `missing_information` +
`contradictions`, AI evaluation summary = `evaluation.narrative`). The insights section required
one new fetch per selected candidate, `GET /api/evaluations/{id}` (already used by
`candidate.html` for the same fields — no backend change), added alongside the existing
per-candidate location fetch in the "Compare selected" click handler. Reused `candidate.html`'s
`itemText()` extraction (`.text||.description||.label||.detail`) since `strengths`/`gaps` are
lists of `{criterion_key,label,score,weight}` dicts, not the assumed shape. Fields the request
asked for that this data model has nothing behind (culture fit, notice period, current role,
work authorization/arrangement) were deliberately left out rather than padded with permanent
"Not available" rows — consistent with the X37 "no shown-but-fake fields" rule this page's own
code comment already documents for the same reason. No change to candidate selection, the
`/api/campaigns/{id}/compare` or `/evaluations` routes, the shortlist page, or Candidate 360.
Browser-verified live against the real `HSE Officer · Coastal Terminal` campaign (4-candidate
roster): selecting 3 rendered exactly 3 columns and 5 sections with real data; selecting 2
rendered exactly 2 columns; no `undefined`/`NaN`/`[object Object]` in `#c-table`'s rendered
HTML (checked via `javascript_tool` regex, not just eyeballing); all three new
`/api/evaluations/{id}` requests returned 200. `tests/test_frontend_integration.py` (30 tests,
includes the page-listing check that covers `compare.html`) still passes.

2026-09-16, later, on direct instruction ("blank white screen looking odd") — the compact
table's empty top-left header cell (above the row-label column, beside the candidate-column
headers) now reads "Comparison Criteria" instead of blank, on the same sand background as the
rest of the header row (`.cmp thead th:first-child` in `web/compare.html`). Verified via DOM
inspection against the live campaign (screenshot capture in the browser-preview tool was
unreliable this session; confirmed instead via `getComputedStyle`/`textContent` checks).

2026-09-17, on direct instruction ("wherever weak is written... make it red everywhere") —
the Evidence axis's bottom tier (`.verdict.no`, label "Weak"/"Not recommended"/"Not shown")
switched from grey to red across the site: `--v-no` in `web/assets/app.css` now equals
`--red` instead of the old grey `#B8AFA4`, and `.verdict.no` uses `--red-soft`/`--red-ink`
(matching the `.fit.poor`/`.dcell.reject` red pattern already in `web/compare.html`). This
is the shared token behind the compare-page Evidence column, the candidate-page per-criterion
"Not shown"/"Not enough in the CV to judge" bars, and the leaderboard's spread bar/legend/
"Not recommended" group — all now red without per-page edits. The old grey `#B8AFA4` is kept
as a new `--v-nodata` token for the two usages that were never "weak", just "no data yet"
(`.fit.muted` and `.dcell.pending` in `web/compare.html`), so pending decisions did not turn
red by accident. Browser-verified live: HSE Officer campaign's `compare.html` Weak pills,
`leaderboard.html`'s "Not recommended" spread segment/legend, and a candidate's per-criterion
"Not enough in the CV to judge" bars all render red; the "Pending" decision dot stayed grey.
See `docs/DECISIONS.md`, 2026-09-17 (B08).

2026-09-17, later, on direct instruction (a reference screenshot of the intended campaign
journey rail) — the sitewide `.cjourney-bar` (injected by `web/assets/app.js` on every campaign
workspace page) was restyled to match: each of the six stops (Set up/Shortlist/Handoff/
Interview/Approvals/Offer & hire) now carries its own stage icon (inline SVG, `currentColor`)
inside the circle instead of a plain coloured dot; a finished stop is a solid `--maroon-deep`
fill with a white icon (was green); the current stop is a light `--maroon-soft` fill with a
`--maroon` ring and maroon icon (was a solid red dot inside a maroon ring); a pending stop stays
`--sand-2`/grey. The text-chevron connectors (`>>>>>>>>`) between stops are replaced with a
plain dotted `--maroon-mid` line, drawn the same regardless of done/pending (previously green/
red). `web/assets/app.js` (`STOPS`/`ICONS`, `repaint()`) and `web/assets/app.css`
(`.cjourney-circle`, `.cjourney-arrow` and states). Bumped the sitewide cache-busting query
(`app.js?v=36→37`, `app.css?v=26→27`) across every `web/*.html` page that references them, since
the browser was otherwise serving the pre-edit versions from disk cache under the unchanged
`?v=` URL. Browser-verified live on `candidate.html` and `leaderboard.html` against the real
`HSE Officer · Coastal Terminal` campaign: icons, fill/ring colours and dotted connectors render
as designed; the per-stop caret dropdown (Shortlist → Candidate 360/Compare/Decisions) still
opens and links correctly. No backend change. See `docs/DECISIONS.md`, 2026-09-17 (B08).

### B17 — What-if analysis
Owner: Ankush

- [x] Keep changes preview-only — returns `"persisted": false`, `app/core/analytics.py:288`
- [x] Do not alter the approved ranking before approval — same
- [x] Send proposed weight changes to the correct hiring manager/team — 2026-09-12:
      `app/services/whatif_service.py` + `WhatIfProposal` (`app/db/models.py:413`), five routes
      under `/api/campaigns/{campaign_id}/what-if/proposals`, migration `9d3f6b1a4c72`, 11 tests
      passing. This line in the plan doc was stale; corrected here 2026-09-13.
- [x] Separate the proposer from the approver — `whatif_service.propose()` rejects
      proposer == approver and requires the approver hold `HIRING_MANAGER`/`ADMIN`. Same
      staleness correction.
- [x] Remove the hardcoded approver — none in the backend; the name in the HTML is display copy
- [x] Audit both the proposed and the approved versions — `propose()` and `approve()` each
      write their own `AuditEvent`; the approved event can carry amended weights distinct from
      the proposed snapshot. Same staleness correction.
- [x] Wire an approved proposal into a real `RubricVersion` draft — 2026-09-13:
      `whatif_service.create_rubric_draft()` + `POST .../proposals/{id}/create-draft`. Deliberately
      a separate, explicit step from approval (never auto-submitted/approved — see
      `docs/DECISIONS.md`), surfaces `rubric_service`'s one-draft-in-flight conflict as a 422
      rather than overwriting or queuing. `WhatIfProposal.draft_version_id` (new column,
      migration `b4f7c9a1e3d2`) records the link and blocks a second draft from the same
      proposal. Tests: `tests/test_whatif_proposals.py`, 16 passed (5 new).
- [ ] Re-scoring every CV once a wired draft is submitted and approved is not triggered here —
      the draft still goes through the pre-existing, separate submit/approve/re-evaluate steps
- [-] 2026-09-14, on direct instruction — the "Propose these weights for approval" section
      (actor/approver selects, propose button, confirm/error text, and the JS that called
      `POST .../what-if/proposals`) removed entirely from `web/whatif.html`. The page is now
      preview-only end to end: move a slider, see the two ranked lists move, nothing else. This
      is a UI-only removal — `whatif_service.propose/approve/reject/create_rubric_draft` and the
      five `/api/campaigns/{id}/what-if/proposals` routes above are untouched and still exist;
      no screen currently calls them. Dropped rather than done, since this reverses the
      "proposal/approval flow" half of B17's UI scope recorded in
      `08-TWO-PERSON-DELIVERY.md`'s allocation table — flagged there for reconciliation. See
      `docs/DECISIONS.md`.
- [x] 2026-09-24, on direct instruction — a *reversed* proposal UI re-added to `web/whatif.html`:
      the hiring manager (signed in as `HIRING_MANAGER`) now sees a "Send weights to HR" panel
      under the sliders and can post his current band weights as a proposal to a named HR
      approver; HR sees a notification banner ("<manager> suggested these weights") the next
      time they open `whatif.html` for that campaign, with buttons to load the suggested weights
      onto its own sliders, approve, or return with a reason. This is not the same UI the
      2026-09-14 entry above dropped (that was HR proposing to the hiring manager) — the
      direction is flipped, so `whatif_service.propose()`'s approver-role check
      (`app/services/whatif_service.py`) now branches on the proposer's role: a hiring-manager
      proposer must send to `RECRUITER`/`ADMIN`, everyone else must still send to
      `HIRING_MANAGER`/`ADMIN`, unchanged from before. `app/services/auth_service.py`'s
      `display_identity()` now includes `counterpart.id` so the HM's share panel can default to
      his actual HR counterpart. No new backend routes, no migration — reuses the existing five
      `/api/campaigns/{id}/what-if/proposals` routes and `WhatIfProposal` model from the earlier
      B17 work. Still flagged against `08-TWO-PERSON-DELIVERY.md`'s allocation table, same as the
      dropped entry above. Tests: `tests/test_whatif_proposals.py`, 18 passed (2 new). See
      `docs/DECISIONS.md`.
- [x] Live-verified in the browser, both directions, against the real `HSE Officer` campaign:
      signed in as Subhadeep (`HIRING_MANAGER`), dragged the Skills slider, sent to Ankush
      Saxena (his auto-selected counterpart); signed in as Ankush (`ADMIN`), saw the banner,
      clicked "Use these weights" (sliders updated), "Approve" (proposal moved to `APPROVED`,
      audit event written), and separately "Return" on a second test proposal (moved to
      `REJECTED`). Found and fixed a real bug while doing this: `whatif.html`'s new
      `bandCriteria()` helper (translates a slider band to the per-criterion weights the API
      stores) matched criteria by `category` alone, so a category like `SKILL` that also holds
      plenty of `MANDATORY`-type criteria (common — this campaign's rubric has 20 `MANDATORY`
      criteria under `SKILL` and 8 truly-optional ones) had those mandatory criteria's weight
      double-counted into the redistribution base, e.g. sending Skills=18 actually proposed
      Skills≈3.7/Mandatory≈96.3 instead of the correct Skills≈16.1/Mandatory≈83.9. Fixed by
      excluding `requirement_type === 'MANDATORY'` from every non-mandatory band's criteria set,
      matching `buildBands()`'s own split exactly. Caught only because the math was checked
      against the actual stored `WhatIfProposal.proposed_weights`, not just that the banner
      rendered — a build report claiming this worked from the UI alone would have missed it.

### B18 — Candidate 360
Owner: Ankush · **The strongest area of the product.**

2026-09-15: the hero score, rubric chart, strengths/gaps, full criteria-to-evidence trace,
challenge-agent findings, score breakdown and the SHORTLIST/HOLD/REJECT decision controls
below were carried over into `web/candidate-assessment.html`'s right-hand detail panel
(Overview/Skills/Experience/Resume tabs), opened by clicking a row in the same page's
candidate list rather than as its own URL. `web/candidate.html` itself is unchanged but no
longer linked from nav — see the B15 note and `DECISIONS.md`. `X58` (shortlist never calls
`/enter`) now applies to the new page's Overview tab too — see `04-KNOWN-DEFECTS.md`. Moot as
of the B15/B16/B18 merge revert (`candidate-assessment.html` deleted); `X58` itself is fixed
on the surviving `candidate.html`/`decisions.html`, see `04-KNOWN-DEFECTS.md`.

**2026-09-15, later, on direct instruction — the expanded panel was missing pieces the old
`candidate.html` carried, and the recruiter noticed at full-screen size.** Overview tab: added
the narrative sentence (`evaluation.narrative`, already returned by `/api/evaluations/{id}`,
previously fetched and unused) and the candidate's email/phone/location/source
(`/api/processing/candidates/{id}`, same story — fetched for `renderDetail` already, only
`full_name` was read) to "Key information"; added a "Rank N of M" prefix next to the role line,
computed client-side from `state.filtered`. Skills tab: added a "Suggested questions" block
reading `evaluation.validation_questions` — the same AI-generated, finding-traceable questions
`app/core/candidate_360.py:validation_questions` always produced and `candidate.html` displayed
(`c-ask-questions`), which the merge onto `candidate-assessment.html` had stopped rendering.
No backend change — every field used was already in an existing response. Browser-verified live
against a real "Maintenance Engineer" run: narrative, rank, email/phone/location/source and 8
real suggested questions all rendered in both the docked panel and its expanded overlay.

2026-09-15, later, on direct instruction: the merge (including the narrative/rank/suggested-
questions additions above, which existed only inside `web/candidate-assessment.html`) is
reverted — see the B15 note. `web/candidate.html` is linked from nav again and is once more the
only Candidate 360 page.

- [x] Trace every JD requirement to CV evidence — `app/api/evaluations.py:234`
- [x] Keep the AI-generated interview questions — `candidate_360.validation_questions()`
- [x] List every discrepancy, not one — returns all `ChallengeFinding` rows, no truncation
- [x] Classify severity — `ChallengeSeverity` HIGH / MEDIUM / LOW / INFO
- [x] Highlight employment-duration, experience, qualification and other contradictions —
      verified 2026-09-13 by reading `app/core/challenge_engine.py` and
      `app/core/experience_engine.py`. Every contradiction reaches a `CONTRADICTION` finding
      through one of two paths: `_check_contradiction` fires for any criterion — skill,
      experience, qualification or certification — whose outcome is
      `CriterionOutcome.CONTRADICTORY_EVIDENCE` (this is the qualification/other path);
      `_check_evaluation` surfaces every entry `experience_engine.analyse()` records:
      `EMPLOYMENT_GAP`/`OVERLAPPING_ROLES` (duration),
      `EXPERIENCE_CLAIM_MISMATCH`/`UNVERIFIED_EXPERIENCE_CLAIM`/`STALE_EXPERIENCE`
      (experience), `REVERSED_DATE_RANGE`/`FUTURE_START_DATE` (other/structural). Nothing is
      silently dropped.
      Remaining gap for whoever builds `candidate.html` (Subhadeep's lane): the per-evaluation
      path's `observed.type` already names which of these it is, but the per-criterion path's
      `Finding` carries no `category` field of its own — grouping a "qualification
      contradiction" apart from a "skill contradiction" on screen needs a join back to the
      criterion's `category` via `criterion_id`, not a direct field today.
- [x] Preserve explainability for the ranking and final recommendation
- [x] 2026-09-13, on direct instruction — "Open the original CV" now renders the real Word
      document's own layout instead of flattened text. `web/cv-viewer.html`'s DOCX branch
      swapped `mammoth.browser.min.js` for `docx-preview` (both client-side, no backend
      change): mammoth only ever produced semantic HTML (paragraphs, a few heading levels,
      bold/italic, simple tables) and dropped everything else — fonts, colours, spacing,
      headers — by design, which is what read as "just text, not the CV as it is". docx-preview
      renders the document's own paginated layout (page size, margins, headers/footers, fonts).
      Hosted viewers (Google Docs/Office Online) were ruled out — they need a public HTTPS URL
      to fetch the file, which would mean sending every candidate's CV to a third party.
      Server-side conversion (LibreOffice headless) was ruled out as a new system dependency
      this stack doesn't have. Browser-verified live against a real `.docx` evaluation (Tariq
      Al-Naimi) — headings, rules and structure now match the source document.
- [x] 2026-09-16, on direct instruction ("open cv should open in the same format, PDF as PDF,
      Word as Word") — superseded the `cv-viewer.html`/docx-preview approach above with a
      direct link. `web/candidate.html`'s "Open the original CV" now points straight at
      `GET /api/evaluations/{id}/cv` (`app/api/exports.py`'s `candidate_cv` route, unchanged —
      already served the right `Content-Type`/inline `Content-Disposition` per file) instead of
      routing through `cv-viewer.html`'s conversion. A PDF now opens in the browser's own PDF
      viewer tab, unmodified; a Word file opens/downloads as an actual `.docx`, not an
      HTML/canvas re-rendering of one — closer to "the same format" than even the accurate
      docx-preview layout was. `cv-viewer.html` is left in place, unlinked, not deleted.
      Browser-verified the link's `href`/`target` and the endpoint's headers live against a
      real evaluation (confirmed `Content-Type: application/vnd.openxmlformats...` +
      `Content-Disposition: inline; filename="...docx"`); the actual new-tab open could not be
      observed inside the automated browser-preview tool (it blocks the non-trusted-event
      `target="_blank"` navigation the same way this repo's `decisions.html` `window.open()`
      note already documents — real Chrome does not have this restriction).
- [x] 2026-09-16, later, on direct instruction — **reverted the row immediately above.** User
      clarified after that change shipped: a direct link to a `.docx` has no browser-native
      inline renderer, so it downloaded the file instead of showing it — "i have to manually
      click on it and then open word... i want to just view the original cv in another tab."
      `web/candidate.html`'s "Open the original CV" points at `cv-viewer.html` again, which
      already renders DOCX inline via docx-preview (see the 2026-09-13 row above) with no
      download step. Browser-verified live against the same real `.docx` evaluation (Fatima
      Noor Rashid) — the CV's actual heading, contact line and section content render directly
      in the new tab.
- [x] 2026-09-13, on direct instruction — the "Where he stands on the rubric" bar chart,
      removed earlier the same session as static/unwired (see B08 above), restored on
      `candidate.html` — this time bound to the evaluation's real `criteria` array (the same
      data already feeding the text-based requirement list further down the page), not the old
      hardcoded example rows. Found and fixed a real layout bug while restoring it: a real
      criterion label (JD wording, e.g. "Working in petrochemical, oil and gas, or heavy
      industrial environments") is far longer than the old placeholder rows ("REQ-01 Right to
      work"), and the shared `.hbars` grid's label column was `minmax(96px,auto)` — unbounded
      `auto` sizing let one long label's max-content width consume nearly the entire row,
      squeezing the bar track down to 0px. Capped the label column at `minmax(96px,240px)`
      (`web/assets/app.css`) and let it wrap. Verified via computed geometry (`getBoundingClientRect`)
      that bar widths are non-zero and colour-coded correctly (teal/gold/red/grey by outcome)
      against a real evaluation with 30 real criteria.
- [x] 2026-09-13, later, on direct instruction — two follow-ups to the Candidate 360 hero and
      rubric chart, browser-verified live against Tariq Al-Naimi (HSE Officer):
      1. The hero (`.hero` in `candidate.html`'s page-specific `<style>`) had drifted from the
         sitewide `.arch` banner it visually stands in for — its own one-off inline-SVG lattice
         at a different opacity/tile size, and lighter font weights than the "bold and visible"
         masthead treatment `.arch h1`/`.page-state .kicker` already got sitewide (see the B01
         bullet above). Now reuses the shared `assets/pattern-arch.svg` lattice at the same
         opacity/size as `.arch`, and `.hero-id h1`/`.hero-pill`/`.hero-say`/`.herodial .n` are
         bumped to bold weights (400/300/200→700/600/400/600) to match.
      2. `renderRubricChart()` (`web/candidate.html`) now caps "Where he stands on the rubric" at
         a fixed 6 bars (`RUBRIC_CHART_MAX_BARS`), highest-weight first, instead of one bar per
         weighted criterion — a real campaign can carry 30+, which read as a wall of bars. This
         does not reopen the B08 "static/unwired" removal above: the chart stays bound to live
         `evaluation.criteria`, just truncated to the top 6 by weight.
- [x] 2026-09-13, later, on direct instruction — three more polish fixes, browser-verified live
      against Tariq Al-Naimi (HSE Officer):
      1. `.page-state .kicker` on `candidate.html`/`leaderboard.html` bumped 34px/700 → 46px/800
         and uppercased ("CANDIDATE 360"/"CANDIDATE SHORTLIST"), and the gap between the maroon
         band and the white card beneath it tightened (`.page-state` margin-bottom 16px→14px on
         both pages; `leaderboard.html`'s next `.band` margin-top 36px→20px) — the name should
         read as the biggest thing on the screen with minimal air before the next box.
      2. `.rubric-callout` (`web/assets/app.css`) gained `margin-top:26px` — the "Strongest
         reason to see him"/"Biggest gap" box previously sat flush against the rubric bars
         above it.
      3. See the B16 row above for the matching `compare.html` header change.
- [x] 2026-09-14, on direct instruction, reversing the 2026-09-13 bullet immediately above —
      `candidate.html`/`compare.html`/`leaderboard.html`'s `.page-state .kicker` (each page's own
      local override, not the shared `app.css` rule) brought back in line with the sitewide
      `.arch h1` masthead used on `Today`/`Start Campaign`/`whatif.html`: 46px/800/uppercase →
      42px/600/mixed-case (`.arch h1`'s own values), and the subtitle `<p>` matched to `.arch p`
      (17.5px/300). User's instruction was literally "same text, same boldness... as this page",
      pointing at the Start Campaign hero. The maroon/lattice banner background itself (from the
      2026-09-13 B16/B08 rows above) is unchanged — only the title's size/weight/casing reverted,
      so these three pages now read as the same title treatment as every other page rather than
      a heavier one-off. Browser-verified live: "Candidate 360", "Compare Candidates", "Candidate
      shortlist" all render mixed-case at the shared weight against the real HSE OF campaign.
- [x] 2026-09-14, on direct instruction — a real backend-connected page briefly showed realistic
      -looking sample/fake data before the live fetch resolved and replaced it (reported as
      "static frontend for 1-2 seconds, then real values"). Fixed on the two worst offenders and
      the one already flagged as a known gap:
      1. `web/leaderboard.html` had ten fully-written fake candidate rows (names, scores,
         evidence sentences) baked into `#candidate-list`, plus fake headline numbers
         ("622 people applied... 24 are worth your time") and a pre-filled progress ring — all
         unconditionally overwritten by `render()` once the real fetch resolves, and unconditionally
         cleared on failure too, so the fake markup served no fallback purpose at all. Replaced
         with a plain "Loading…" placeholder and neutral defaults. Also found "How all 622 came
         out" and "Why these 24, and not the other 598" (chunks 4/5) and the `.sig` line are
         *always* hidden by `render()` once real data loads (dead sample sections, never actually
         shown live) — now `hidden` by default too, so they cannot flash in first either.
      2. `web/decisions.html`'s `#d-rows` (ten fake shortlist rows) has a real second purpose:
         `renderRows()` deliberately leaves this exact markup in place, labelled "the shipped
         example", when the live fetch fails — so it could not simply be deleted. Given `hidden`
         by default instead, unhidden only once we know the real answer (real rows replace it on
         success; the original example markup is revealed, unchanged, on failure) — the flash
         is gone but the intentional fallback still works.
      3. `web/candidate.html`'s hero (static "Haitham Al-Otaibi", score "91") has the same
         shipped-example fallback (`renderUnavailable()`) and was **not** touched this session —
         a safe hide/reveal treatment needs to distinguish "still loading" from "shown as the
         example" without leaving a stuck "Loading…" label on genuine failure, which needs more
         care than this slice covered. Left as a known remaining gap, not fixed.
      Browser-verified live (leaderboard.html, decisions.html) against the real HSE OF campaign:
      no fake row ever appears, real data loads directly into the loading-placeholder's place.
- [x] 2026-09-15, later, on direct instruction — the detail panel on `web/candidate-assessment.html`
      (400px column) gained an expand button (top-right of the hero) that turns it into a
      near-full-screen overlay (`.ca-panel.expanded`, `top/left/right/bottom` inset with a
      dimmed backdrop) so a recruiter can read a full assessment without the column squeeze.
      Found and fixed a real stacking-context bug while building it: `.page` carries its own
      `position:relative;z-index:1` (for the crown/lattice background art), which traps any
      z-index set on a nested descendant inside that local context — the expanded panel could
      never out-rank a body-level backdrop no matter what z-index it was given. Fixed by
      reparenting the panel node to `<body>` while expanded (and back to its original spot on
      collapse), the standard fix for a modal escaping an ancestor's stacking context.
      Browser-verified live: expand renders the full hero/tabs/score-breakdown above a dimmed
      backdrop against a real evaluation (Ahmed Karim Al-Sayed, HSE Officer campaign); collapse
      restores the panel to its column.

---

## P2 — dashboards, FinOps, platform strategy

### B19 — Recruitment 360 dashboard
Owner: Ankush

- [~] Filters for campaign/role and last 3 months / 6 months — 2026-09-13: the backend half
      is built. `GET /api/analytics/kpis` takes `role` (matches `Campaign.job_title`,
      case-insensitive; no match returns zero campaigns, not every campaign), and
      `months`/`since`/`until` for a period window on both the global and per-campaign KPI
      routes. Every response now carries a `period` block (`since`/`until`/`months`/`label`)
      instead of a placeholder — `label` is one of "All campaigns to date", "Last N months",
      "Custom reporting window". `web/performance.html` still needs the filter controls
      themselves and to read `period.label` instead of its hardcoded string — Subhadeep's
      half, contract in
      `docs/handoffs/ankush/2026-09-13-b19-filters-quality-of-hire-b05-rationale.md`.
      `tests/test_analytics.py`, 5 new tests, 37/37 passed.
- [x] Metrics — screening KPIs plus lifecycle funnel, flow, completed stage time,
      bottleneck, outcomes and now quality of hire exist in `app/api/metrics.py` and
      `app/core/analytics.py`. 2026-09-13: `quality_of_hire` added to
      `GET /api/campaigns/{id}/metrics/outcomes` — a proxy from `CandidateLifecycle
      .campaign_rank` (B15's stored shortlist/waitlist rank) for every currently-`HIRED`
      candidate, explicitly labelled as a proxy and not a post-hire outcome; `null` with no
      hires. New `lifecycle_service.hired_candidates()`. `tests/test_metrics_api.py`, 3 new
      tests, 12/12 passed. **Still absent, and out of scope here:** interview invite
      acceptance/decline — cannot be measured until that external event is recorded (email
      reply ingestion, `B10`).
      Earlier screening metrics in `app/core/analytics.py` include:
      CVs discovered · CVs screened · shortlisted/held/rejected · time saved ·
      time per candidate · hours per campaign · campaign efficiency.
      Current-position and transition-derived metrics cover most journey stages.
- [~] Top-level charts plus drill-down — `pipeline.html` plots current lifecycle counts
      and reveals raw positions/timing on demand; `performance.html` still needs its filter
      UI wired to the now-built API (see above) — Subhadeep's half

### B20 — Identifier model
See `03-IDENTIFIER-MODEL.md`. Campaign identifier built 2026-09-13, on direct user request
(the client asked for this literal shape, not the doc's `CMP-7K4Q` suggestion — confirmed and
recorded in `docs/DECISIONS.md`). Format revised twice the same day, both times on direct
instruction — see below. Candidate/Application/Run identifiers remain unbuilt.

- [x] Short autogenerated IDs — campaigns only. Revised 2026-09-13 (second revision, same day):
      `RC` + creation date (`YYYYMMDD`) + a random number, e.g. `RC20260913-58204`
      (`Campaign.short_id`, `campaign_service._next_short_id`) — supersedes the same-day
      "running number" shape (`RC20260913-34`), which supersedes the earlier fixed-prefix
      `RC36-01`, `RC36-02`, … shape from migration `1364a83bb0b4`. Existing rows keep whatever
      shape they already have; only new campaigns get the random-number shape. Uniqueness is
      checked against the database (retry on collision, not merely assumed from the random
      range). 2026-09-13, later, on direct instruction — extended to assessment runs:
      `EvaluationRun.short_id`, same `RC` + creation date + random-number shape and
      collision-check pattern (`evaluation_service._next_run_short_id`), migration
      `ac9341168537` (existing runs backfilled from their own `created_at` date). Chosen over
      the doc's own `RUN-5T1V` suggestion below because the user asked for the literal
      campaign shape reused, not a new one. `web/leaderboard.html` and `web/campaigns.html` now
      show it (falling back to the old 8-char UUID slice only if `short_id` is ever null) —
      "assessment run cdc651b4" is now e.g. "assessment run RC20260913-09455". Candidate/
      Application identifiers, and the doc's `CND-3M8X`/`APP-9R2D` shapes, remain unbuilt.
- [~] Searchable — stored and displayed; no list screen's search box accepts it yet.
- [x] Stored in the DB — additive column alongside the existing UUID primary key, per the
      doc's migration note (UUID stays the FK target).
- [ ] Included in email subjects, calendar events, reports, audit entries
- [ ] Stop calling both the campaign and the candidate-JD combination "recruitment ID"

### B21 — HR FinOps
Owner: Subhadeep + Chiranjib (frontend); backend calculation contract below — Ankush

- [x] Rename the Developer tab to HR FinOps — nav label, page title and identity chip now read
      "FinOps" across all 21 `web/*.html` pages, 2026-09-12. Calculations below are unchanged.
- [x] Calculations — 2026-09-13: this line was more absent than stated — `web/developer.html`
      called `/api/developer/metrics`, which did not exist anywhere in `app/`, and no LLM call
      was instrumented for tokens or cost at all. Now built: `app/core/llm_provider.py`'s
      `_InstrumentedChatModel` wraps every chat-model call once (not each of the ~14 agent call
      sites) and records usage via `app/core/llm_usage.py`; `requirement_service` and
      `evaluation_service.execute_run` open the tracking context so JD extraction and screening
      calls are billed to a campaign/run; `LLMCallLog` (new table, migration `b4f7c9a1e3d2`)
      persists each call. `app/core/pricing.py` prices from an explicit config or a bundled
      last-verified Azure retail fallback — not a live call to the Azure Retail Prices API, see
      `docs/DECISIONS.md`. New `GET /api/developer/metrics` (`app/api/developer.py`) serves the
      exact shape `web/developer.html` already expects, plus `operating_cost_to_date_usd`,
      `cost_per_candidate_usd` and `projected_cost_10000_cvs_usd` — average cost per CV,
      operating cost and the 10,000-CV scenario this line asked for, all computed from real
      `LLMCallLog` rows rather than the hand-measured constants in the table below. `campaign
      cost` is the additive `campaign_costs` array in the same response. Tests:
      `tests/test_developer_metrics.py`, 11 passed. Not done: a live Azure Retail Prices API
      fetch (deliberately, see decision) and re-verifying `web/developer.html` renders these
      new fields correctly in a browser — that screen is Subhadeep's file.
- [ ] Use Azure Foundry pricing
- [ ] Evaluate a cost-minimising stack
- [ ] Present business cost, not Azure jargon
- [ ] Compare market alternatives
- [ ] Confirm with the client: average CVs per campaign/role · peak batch size ·
      daily/period volume · campaign count · PDF/Word/scanned-PDF mix
- [ ] Validate the old ~200 CVs figure from 2022
- [ ] If unavailable, document the 250–300 assumption and ask the client to correct it
- [ ] Follow up with Alrana for volumetrics

**The numbers already exist** (measured 2026-09-12 from real token counts, GPT-5.6-terra
Global Standard, $2.00/M input, $12.00/M output):

| Item | Prompt | Completion | USD |
|---|---|---|---|
| JD requirement extraction (once per campaign) | 767 | 504 | $0.0076 |
| Criterion refinement (once per candidate) | 4406 | 365 | $0.0132 |

Campaign cost = $0.0076 + ($0.0132 × candidates).
10 CVs $0.14 · 50 CVs $0.67 · 200 CVs $2.65 · 1000 CVs $13.20 · 10,000 CVs $132.01.
`DETERMINISTIC` mode makes no LLM call at all.

### B22 — Hosting, security, data residency
Owner: Chiranjib + Subhadeep · Nothing started; all external decisions.

- [ ] Confirm Qatar data-residency rules
- [ ] Confirm the approved hyperscaler: Azure or AWS
- [ ] Check Qatar-region availability for every service
- [ ] Test moving the current deployment to Qatar
- [ ] Ensure no storage or processing leaves the required geography
- [ ] For a long-term hosted product define: tenant isolation · authentication ·
      secure customer profiles · protected infrastructure · data access controls ·
      service mailbox · customer onboarding

### B23 — Commercial positioning
Owner: Chiranjib + Kallol

Immediate QChem model:
- [ ] Bespoke / white-labelled asset
- [ ] Plug-and-play base with client customisation
- [ ] Position the current solution as an upgrade to the earlier QChem automation
- [ ] Research SmartRecruiters pricing and KPIs
- [ ] Compare against SmartRecruiters and UiPath/Maestro
- [ ] Use the prior dashboard and screenshots
- [ ] Reuse familiar QChem terminology
- [ ] Prepare a clear indicative cost
- [ ] Chiranjib leads product positioning

Long-term model — decision required after the demo:
- [ ] Choose: bespoke project/asset model, or multi-customer subscription product
- [ ] A subscription model requires customer onboarding, login/profile management,
      tenant security, hosted infrastructure, and ongoing operations.
      Do not imply these exist today.

### B24 — Post-demo roadmap
- [x] Publish consolidated to origin with user authorization, 2026-09-12; bootstrap PR/merge into azure-provider still pending.
- [x] Allocate B01–B24 and related D/W/X work between Subhadeep and Ankush, with exclusive file ownership and staged GitHub baseline/PR workflow — `08-TWO-PERSON-DELIVERY.md`; planning only, no push/settings changes.
- [x] Create single agent planning/execution entry with full read order and done/left reconciliation — `../../AGENT-START-HERE.md`; documentation only, 2026-09-12.
- [ ] Continue development after the Monday demo
- [ ] Complete real email automation
- [ ] Complete interview scheduling
- [ ] Complete the offer workflow
- [ ] Complete the end-to-end lifecycle for every candidate
- [ ] Move proxy screens to functional integrations
- [ ] Treat the demo as the first product increment, not the endpoint

### B25 — JD library

Owner: Ankush · **New 2026-09-14**, added by direct instruction during the QChem demo-readiness
pass (not part of the original B01–B24 set; appended rather than assigned an existing number,
per the "never renumber a plan ID" rule). See `DEMO-READINESS-2026-09-14.md` and
`docs/DECISIONS.md` for the full rationale.

- [x] The smallest honest reusable saved-JD path: a standalone `JDTemplate` model/table
      (migration `e1a2b3c4d5f6`), independent of `Campaign` — a JD is visible/retrievable
      without ever creating a campaign to hold it. `app/services/jd_library_service.py`,
      `app/api/jd_library.py` (`GET/POST /api/jd-library`, `GET /api/jd-library/{id}`).
- [x] `web/jd-library.html` lists saved JDs; "Use for a new campaign" deep-links to
      `new-campaign.html?jd_template_id=<id>`, which prefills the role title and JD text (never
      overwriting an existing draft — the prefill is skipped whenever the page already has a
      `campaign_id`). Linked from `start-campaign.html`'s hero.
- [x] Four QChem JDs seeded (HSE Officer, Maintenance Engineer, Process Operator,
      Instrumentation & Control Engineer) via `scripts/seed_demo.py`.
- [x] Tests: `tests/test_jd_library.py` (4 tests). Browser-verified live: library page lists all
      four, "Use for a new campaign" correctly prefilled a real new campaign (`Process
      Operator`, 2,628-char JD) with no console errors.
- [ ] No versioning, no edit/delete route, no per-template ownership or approval workflow — this
      is deliberately minimal, not a full JD-management feature. Documented as a limitation, not
      silently claimed as more than it is.

### B26 — Role-based interface (HR / hiring manager / budget approver)

Owner: Ankush · **New 2026-09-22**, added by direct instruction (not part of the original
B01–B24 set or B25; appended rather than assigned an existing number, per the "never
renumber a plan ID" rule). Resumes an RBAC design discussion from an earlier session
(recorded in this assistant's memory, not previously written to this repo) — three
operational roles, walked through as seven sequential logins: HR sends a shortlist to the
hiring manager, the hiring manager records a shortlist verdict, HR schedules the interview,
the hiring manager scores/records feedback, HR requests approval and routes to the cost
centre, the budget approver grants the budget, HR sends the offer. See `docs/DECISIONS.md`
(2026-09-22 row) for the full rationale.

- [x] Repurpose the unused `REVIEWER` `UserRole` as "Budget approver" — label only
      (`app/api/lifecycle.py::ROLE_WORDS`), no enum value or migration change.
- [x] `WHO_MAY` (`app/core/lifecycle.py`): `RECRUITER` added to `PENDING_COST_CENTRE` (HR
      routes to the cost centre as its own "proceed" step) and `REVIEWER` added to `APPROVED`
      (the budget approver grants). Existing capabilities (`ADMIN`, `HIRING_MANAGER`) untouched.
- [x] Three fixed demo logins, one per role — `scripts/seed_role_logins.py` (same
      fixed-password convention as `scripts/seed_demo_login.py`): `hr@demo.local`
      (RECRUITER), `hm@demo.local` (HIRING_MANAGER), `budget@demo.local` (REVIEWER),
      password `Demo12345!` for all three. Created live in the local dev database this
      session.
- [x] Frontend role gate (`web/assets/app.js`, `web/assets/journey.js`): a signed-in
      `REVIEWER` is redirected to `approvals.html` from every other page before it paints
      (portal-gate check), the sitewide nav and campaign-stage dock are hidden for that role,
      and `approvals.html` narrows its candidate list and action form to only the
      budget-approval step for them, with a read-only "waiting on the budget approver" message
      shown to every other role instead of the grant form. Every other role (HR, hiring
      manager, admin) sees the full site unchanged — the hiring manager was explicitly *not*
      narrowed, on direct instruction, superseding the more restrictive design floated in the
      earlier RBAC discussion.
- [x] Actor auto-select: the "Acting person" dropdown on the approvals workspace now defaults
      to (and, for the budget approver, locks to) the signed-in user, so the recorded actor
      matches who is actually signed in rather than requiring a manual pick every time.
- [x] Live-verified end to end: HR routed a real `PENDING_APPROVAL` candidate to
      `PENDING_COST_CENTRE`; the budget approver was redirected straight to `approvals.html`
      with nav/dock hidden, saw only that one candidate, and granted it to `APPROVED` through
      the real UI button; HR and the hiring manager logins both landed on `index.html` with
      the full nav and dock intact. Targeted suite (`test_lifecycle.py`,
      `test_approvals_api.py`, `test_cost_centre_delegation.py`, `test_auth_api.py`): 69
      passed. Full suite: 835 passed, no regressions.
- [ ] `on_behalf_of_id` delegation (`B13`) not re-verified against the new `WHO_MAY` entries —
      existing delegation tests still pass, but no new delegation scenario was added for the
      budget approver specifically.
- [x] **2026-09-23**: `handoff.html`'s "With the hiring manager" group no longer lets HR
      record the hiring manager's verdict — HR sees a read-only "Pending" tag instead of the
      "Record verdict" button; the button is still shown (and still posts to
      `/lifecycle/{id}/review`) for `HIRING_MANAGER` and `ADMIN`, gated client-side on
      `window.__r360Me.role` (set by the portal gate in `web/assets/app.js`). By direct
      instruction ("HR should not have action over HM"), narrowing the earlier "no screen
      change beyond `approvals.html`" note above. The "returned, with a question" and "ready
      to close" groups are unchanged — replying to a manager's question and closing the file
      after a decision remain HR actions. Live-verified in the running app: signed in as
      `ankush.saxena@protivitiglobal.in` (RECRUITER) saw "Pending" with no control; signed in
      as `subhadeep.m@protivitiglobal.in` (HIRING_MANAGER) still saw and could open "Record
      verdict" on the same two candidates.
- [x] **2026-09-23**: Same role gate extended to `interview.html`'s "Scheduled" group — a
      row awaiting feedback no longer opens the "Record interview feedback" form for HR;
      it shows a read-only "Awaiting hiring manager's feedback" tag instead (`canRecordFeedback()`,
      same `HIRING_MANAGER`/`ADMIN` check as the handoff gate above). By direct instruction
      ("the hr should not have the feedback option only the hm should have it"). Live-verified:
      signed in as `ankush.saxena@protivitiglobal.in`, clicking the row left `feedback-section`
      hidden; signed in as `subhadeep.m@protivitiglobal.in`, the same row opened the feedback
      form as before.

### B27 — Close a campaign

Owner: Ankush · **New 2026-09-23**, added by direct instruction ("add option to close
campaign at the end") — appended rather than reusing an existing ID, per the "never
renumber a plan ID" rule. No prior plan ID covered closing a campaign as a whole (as
opposed to a candidate's own `CLOSED` lifecycle status, which is `B02`/`02-LIFECYCLE-MODEL.md`).

- [x] Added a "Close campaign" control to `web/pipeline.html` — the campaign-level overview
      page ("The complete journey," showing the whole campaign's current position), at the
      end of the "Current position" card, right before the "Workspaces" grid. Clicking it
      opens an inline confirmation ("This ends the campaign for good — a closed campaign
      cannot be reopened…") with Confirm/Cancel, matching the existing inline-confirm
      convention used elsewhere (`web/handoff.html`'s "Record as hired"/"Close the file").
      Confirming calls the transition endpoint that already existed and needed no backend
      change: `POST /api/campaigns/{id}/status {"status": "CLOSED"}`
      (`app/api/campaigns.py::transition_status` → `campaign_service.transition_status`,
      which already wrote a `CAMPAIGN_STATUS_CHANGED` audit event and bumped `version`).
      `Campaign.can_transition_to()` (`app/db/models.py`) already made every non-`CLOSED`
      state able to reach `CLOSED`, and `CLOSED` itself terminal (no transition out) —
      the control is hidden, not merely disabled, once a campaign is already closed
      (`renderCampaignClose()`, `web/assets/journey.js`), and replaced with a plain
      "Campaign closed" tag. Bumped `journey.js`'s cache-busting query
      (`?v=4` → `?v=5`, on `pipeline.html`/`approvals.html`/`offer.html`, all three pages
      that load it) and the service-worker `CACHE` version (`web/sw.js`, `v24` → `v25`),
      per the existing convention (`X50`/`X59`/`X60`/`X67`) for any changed shared asset.
- [ ] No role gate on this control — unlike `B26`'s handoff/interview-feedback gates, HR,
      the hiring manager and admin all see and can use it alike (the budget approver is
      already redirected away from every page but `approvals.html`, per `B26`). Not
      requested to be restricted to HR only; flagged here since it is a real, if minor,
      difference from the "HR should not have action over HM" pattern established the same
      day, in case that turns out to matter later.
- [x] Live-verified end to end against the real API (not just inline test IDs): created a
      disposable test campaign via `POST /api/campaigns`, drove the real UI control through
      open → cancel (form closed, no request sent) and open → confirm (button hid, tag
      flipped to "Campaign closed"), confirmed server-side via `GET /api/campaigns/{id}`
      that `status` was `CLOSED` and `version` had incremented, then deleted the disposable
      campaign (`DELETE /api/campaigns/{id}`). Separately confirmed the button renders
      correctly (open, then cancelled — never confirmed) against the real, populated
      `HSE Officer — Coastal Terminal` campaign used throughout this session's demo data,
      since `CLOSED` is terminal and that campaign's data was not disposable.
- [ ] No automated test added (`tests/test_campaigns_api.py` or similar) for this specific
      UI flow — the underlying transition endpoint was already covered before this session
      (see whatever existing `test_campaigns_api.py` coverage predates `B27`); this row is
      pure frontend wiring onto an already-tested endpoint.

### B28 — Hiring manager: view-only site, no campaign creation, own "Campaign" nav

Owner: Ankush · **New 2026-09-23**, added by direct instruction ("the Hiring manager should
have all other options locked other than he is working on but he can see the things not act",
"the hiring manager should not have option to start a campaign instead remove start a campaign
for him", "add option of Campaign where existing campaigns are there and waiting for his
decisions") — appended rather than reusing an existing ID, per the "never renumber a plan ID"
rule. Reverses `B26`'s "the hiring manager should see the whole site, unrestricted" decision for
everything except his own two actions; also resolves the open flag `B27` left on "Close
campaign" having no role gate.

- [x] Nav: the hiring manager's "Start Campaign" link is swapped for a "Campaign" link
      (`web/assets/app.js`, `applyHiringManagerNav()`, on `r360-auth-ready`) pointing at
      `campaigns.html`. Any other entry point into starting a campaign (`campaigns.html`'s own
      "Start a new campaign" button, `index.html`'s empty-state "New campaign" link) is hidden
      for him via a shared `data-campaign-create` marker.
- [x] `start-campaign.html`/`new-campaign.html` themselves redirect a signed-in hiring manager
      straight to `campaigns.html` (portal-gate `applyRoleGate()`, same mechanism `B25` uses to
      keep the budget approver on `approvals.html`) — reaching the create flow directly by URL
      is refused too, not just hidden from the nav.
- [x] `campaigns.html` (now his "Campaign" destination): the "Not finished yet" draft band is
      hidden for him (finishing HR's unfinished setup isn't his job either), and every campaign
      with a candidate actually awaiting his decision (`WITH_HIRING_MANAGER` or
      `INTERVIEW_SCHEDULED`, read live per campaign from the existing
      `/api/campaigns/{id}/lifecycle/funnel` endpoint — no backend change) is tagged "N
      decisions waiting on you" and floated to the top of the list.
- [x] Everywhere else, a new `window.__r360Locked()` helper (`app.js`, true only for
      `HIRING_MANAGER`) gates every mutating control that isn't his: `web/handoff.html`'s
      "Send back to manager"/"Record as hired"/"Close the file" (his own "Record verdict" is
      untouched — already `HIRING_MANAGER`/`ADMIN`-only per `B26`); `web/interview.html`'s
      "Schedule interview" row-action (his own "Record feedback" untouched, same `B26` gate);
      `web/candidate.html`'s Shortlist/Hold/Reject; `web/decisions.html`'s
      Shortlist/Hold/Reject and "Email the shortlist"; `web/discover.html`'s "Find CVs"/"Import
      selected CVs"; `web/comms.html`'s "Record message"; and, in the shared
      `web/assets/journey.js` (covers `pipeline.html`/`approvals.html`/`offer.html`),
      "Close campaign", the approvals request/cost-centre/return forms, and the offer
      draft/revise/send/response forms. Every one of these shows the underlying data and a
      plain read-only message in place of the control, rather than hiding the section outright
      — "he can see the things, not act."
- [x] Bumped the shared cache-busting query on `app.js`/`journey.js` (`v=38→39`, `v=5→6`)
      across every page referencing them, and `web/sw.js`'s `CACHE` (`v25→v26`), per the
      existing convention (`X50`/`X59`/`X60`/`X67`/`B27`).
- [x] Live-verified in the running app (both API and web dev servers were already up):
      signed in as `subhadeep.m@protivitiglobal.in` (`HIRING_MANAGER`) — nav showed "Campaign"
      not "Start Campaign"; `start-campaign.html` redirected to `campaigns.html`;
      `campaigns.html` showed no draft band, "Start a new campaign" hidden
      (`node`-confirmed via `outerHTML`/`hidden`), and correctly tagged/floated campaigns with
      real `WITH_HIRING_MANAGER`/`INTERVIEW_SCHEDULED` counts read live from
      `/api/campaigns/{id}/lifecycle/funnel` (e.g. "14 campaigns are waiting for your
      decision", each tagged "N decision(s) waiting on you"); `handoff.html`'s "ready to
      close" row showed "HR to close" instead of a button; `interview.html`'s waiting rows
      showed "HR to schedule"; `candidate.html`'s three decision buttons rendered `disabled`;
      `decisions.html`'s "Email the shortlist" was disabled; `pipeline.html`'s close-campaign
      confirm produced "View only — closing a campaign isn't your decision to make." with no
      `/status` request sent (confirmed via the network log). Signed back in as
      `ankush.saxena@protivitiglobal.in` (`RECRUITER`) and confirmed no regression: nav still
      showed "Start Campaign", `decisions.html`'s send button was enabled again. Found and
      fixed two real bugs during this pass: (1) `renderRuns()`/`markAwaitingHisDecision()` used
      a run's embedded `campaign.id`, which the `/api/runs` payload never sets (the real id is
      `run.campaign_id`) — silently skipped 90%+ of campaigns from the funnel check; (2)
      `discover.html`'s (and similarly `candidate.html`'s) initial lock check ran synchronously
      at parse time, before the portal gate's async `/api/auth/me` had necessarily resolved
      `window.__r360Me` — fixed by re-applying the lock on the existing `r360-auth-ready` event
      (and, for `candidate.html`, re-checking at click time too) rather than only once at parse
      time. No automated test added — every change here is client-side role gating with no new
      backend behaviour (the funnel endpoint it reads already exists and is already tested via
      the pipeline workspace).

---

## Where the product actually stands, 2026-09-12

**Strong and real:** screening, OCR, evidence traced to a CV page, the challenge engine,
Candidate 360, dispositions and overrides, the audit trail, the lifecycle state machine and
its API including a real hiring-manager handoff and manager verdict.

**The single biggest gap is not a feature, it is a screen.** The lifecycle has a full
backend and no UI. `B01`, `B02` and half of `B19` all unblock the moment a timeline view
exists. That is the highest-value next task by a wide margin.

**Second biggest:** every absent dashboard metric is a lifecycle metric. They became
computable today and nothing reads them yet.

**Honest count of the ten demo journey steps:** 5 work end to end, 4 have states but no
mechanism, 1 has nothing. And none of the ten can be *shown* without the timeline.

---

## Final execution order (agreed)

1. Candidate journey + audit trail — `B01`, `B02`, `B04`
2. Semantic SharePoint CV search — `B03`
3. AI JD / recommendation / decisioning — `B06`, `B05`
4. Scoring correction — `B07`
5. Demo proxy screens and local communication flow — `B10`, `B11`, `B12` (proxy only)
6. Campaign / comparison UX — `B14`, `B16`, `B08`
7. Analytics and FinOps — `B19`, `B21`
8. Hosting / commercial model — `B22`, `B23`
9. Full post-demo workflow automation — `B24`
