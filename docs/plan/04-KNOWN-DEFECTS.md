# Known defects

## X18 — Campaign setup duplicates campaign; draft save is cosmetic · CLIENT-VISIBLE · FIXED IN THE UI

Recorded in the 2026-09-12 restored session: JD extraction creates a draft, final
assessment creates another campaign, and Save as draft only changes button text.
B14 remediation and recovery acceptance scenarios are specified in
`07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md`.

**Reproduced 2026-09-12** in `web/new-campaign.html` against a live API, from a clean
baseline of zero drafts. Three separate symptoms, not one:

1. Read the description, reload the page, read it again — two `DRAFT` campaigns for one
   role. The id lived in a page variable that a reload discarded.
2. Save as draft set its own label to "Draft saved". No request was sent and nothing
   was stored.
3. The hiring manager, business unit, recruiter and closing date were never sent. The
   draft the first step created held blanks in all four columns.

**Fixed 2026-09-12** in the UI, using the campaign API that already existed. One
`POST /api/campaigns` remains in the page; every later step calls `PATCH`.

A review of that first fix found it still duplicated, by a different route: three
handlers call the save, each disables only its own button, so "Save as draft"
followed by "Read the description" put two creates in the air at once and both
saw no id yet. Saves are now queued and run one after another. Verified in the
browser 2026-09-12 by firing both handlers in the same tick: one
`POST /api/campaigns` `201`, then a `PATCH` on that id, one draft row.

- [x] Reproduce in canonical `web/new-campaign.html` before implementation
- [x] Reuse one campaign and persist draft fields/progress through existing APIs
- [~] Verify close/reopen, failed save and lost-response retry without duplicates.
      Close/reopen: verified, role details restored from the server. Failed save: verified
      against a dead port — the button reverts, the message says nothing was stored, and the
      remembered draft id survives, so the work is still there when the server returns.
      **Lost-response retry is NOT covered.** If the very first create succeeds but its
      response never arrives, the browser holds no id and the next attempt creates a second
      campaign. Only server-side replay protection closes that, and that is Ankush's lane.


Last verified 2026-09-12 against branch `consolidated` at `dd7c62a`. Test suite: 491 passed,
0 failed. Backlog audited against the code the same day. X13-X16 were added the same evening,
after the timeline, PowerPoint and SharePoint-link work landed.

Severity key: **CLIENT-VISIBLE** = a client could hit it on Monday · **INTERNAL** = it will
not show in the demo.

---

## X1 — A real CV loses its candidate name · CLIENT-VISIBLE · FIXED 2026-09-12, verified 2026-09-13

`extract_identity` returns `full_name=''` for
`Resume_ProcessEngineer_DanielCruz_Unstructured.docx`.

The first line of that CV is:

```
Daniel Cruz — Doha, Qatar — daniel.cruz1988@example.com — +974 5567 1122
```

The name is there. The em-dash-packed header defeats `_looks_like_name`.

**Behaviour:** it warns honestly ("Candidate name could not be determined") and the UI renders
"Unknown". Nothing crashes.

**Why it matters:** 1 of 3 real CVs is affected. A leaderboard with "Unknown" at the top looks
broken, whatever the warning says.

**Not a py313 regression.** Pre-existing.

**Where:** `app/core/document_intake.py`.

**Fix shape:** split the first line on em dash, en dash, pipe, and bullet before testing each
fragment. Take the first fragment that looks like a name and is not an email, phone number, or
location. Write the test red first with this exact CV as the fixture.

- [x] Fixed — commit `8fdbc32`, `app/core/document_intake.py:409` splits the header on em/en
      dash, pipe or bullet before testing each fragment
- [x] Test added with the real CV as the fixture — `tests/test_processing.py`,
      `test_em_dash_packed_header_still_yields_a_name`, uses the exact fixture text from this
      writeup. Re-run this session: 1 passed.
- [ ] Re-run against all three real CVs — the physical demo CV files are not present in this
      environment to re-run against; only the unit fixture above has been verified this
      session

---

## X2 — 32 of 40 criteria return INSUFFICIENT_EVIDENCE · CLIENT-VISIBLE · option 2 built, decision recorded 2026-09-13

`parse_jd` produced **40 requirements** from one JD. Every candidate then came back with 32 of
them marked `INSUFFICIENT_EVIDENCE`.

The leaderboard reads "confirmed on 6 of 40". That makes good candidates look bad.

**This is a granularity problem, not a failure.** The scoring is working. The JD was split into
too many separate requirements for any real CV to evidence individually.

**Options, in order of preference:**

1. **Cap and group.** Cap extraction at roughly 10–15 scored criteria. Group the rest as
   supporting detail under a parent criterion. This matches how a human reads a JD.
2. **Separate scored from informational.** Keep all 40 extracted, but only score the mandatory
   and preferred ones. Show the informational ones without a verdict. The
   `RequirementCategory` enum already exists in `app/db/models.py` — use it.
3. **Change the denominator on screen.** Report "confirmed on 6 of 12 scored criteria" rather
   than 6 of 40. Cheapest, but it hides the underlying granularity problem rather than fixing
   it.

Recommendation: do option 2 first, because the data model already supports it, then option 1
if the count is still high. Do not ship option 3 alone.

This overlaps `B07` (scoring and weight correction). Fix them together.

- [x] Granularity decision taken and recorded in `docs/DECISIONS.md` — option 2, 2026-09-13
- [x] Re-run the demo campaign and check the confirmed count — `RequirementType`-based zero
      weighting (`requirement_service.py`) and the excluded-denominator narrative
      (`evaluation_service.py`, commit `59834c5`) verified this session via
      `test_narrative_confirmed_count_excludes_informational_criteria`: 1 passed. This is the
      fixture JD, not a re-run of the literal ~40-row real demo JD, which was not re-verified
      against real data this session.
- [ ] Leaderboard wording reviewed — `web/leaderboard.html` is Subhadeep-owned; flagged, not
      done, per `08-TWO-PERSON-DELIVERY.md`

---

## X3 — spaCy loads at import · INTERNAL

`app/utils/document_parser.py:7` loads spaCy at module import. The project gotchas say it
should be lazy. It slows startup.

- [ ] Made lazy

---

## X4 — Pydantic class-based Config warning · INTERNAL

`app/core/config.py:5` uses a class-based `Config`. Pydantic wants `ConfigDict`.
Non-fatal warning.

- [ ] Migrated to `ConfigDict`

---

## X5 — `.pptx` rejected at intake · RESOLVED 2026-09-12

The decision was to support it, not to confirm the rejection. `.pptx` now extracts text from
shapes, table cells and slide notes, and maps slide N to page N so evidence still cites a
page. Commit `174a511`. `.ppt`, the old binary format, stays rejected with a message naming
`.pptx`, because `python-pptx` cannot read it.

Verified on the real demo file `Resume_ProcessOperator_HanaAlEmadi.pptx`: 1348 characters,
4 pages, name `Hana Al-Emadi`. She is no longer a held file.

- [x] Decided and built

---

## X6 — Emoji prints remain in two CLI paths · INTERNAL

`app/core/manage_tenants.py` and `app/auth.py` still print emoji. On a Windows cp1252 console
this raises `UnicodeEncodeError`. Both are CLI or fallback paths, and the
`configure_utf8_output()` call at `app/main.py` import covers them at runtime.

Low risk. Clean up when convenient.

- [ ] Cleaned

---

## X7 — 14 modified files are uncommitted · PROCESS RISK · fix today

Branch `py313-upgrade` has 14 modified files and 3 untracked paths
(`app/core/console.py`, `tests/test_console_encoding.py`, `docs/`).

All of the py313 upgrade work, the cp1252 crash fix, and these plan documents are unprotected.
This is the cheapest risk on the list to remove.

- [ ] Committed

---

## X8 — Three defects in a lifecycle build · WITHDRAWN, code discarded

These were real and were fixed, but the implementation they were in was thrown away when
Ankush's lifecycle (`77d3c49`) was taken instead. Kept for the lessons, which still apply:

1. **Do not derive current state from the latest timestamp.** Two rows in one clock tick tie,
   and the tie-break is arbitrary. Ankush's design stores the operative row instead, which
   avoids this by construction — one reason his implementation was the right one to keep.
2. **A bootstrap that only handles "no history" gets stuck** the moment something else creates
   the first row.
3. **An enum name must not leak into an error message,** not just into an audit summary.

- [-] Withdrawn 2026-09-12. The code was discarded; see `X10`.

---

## X10 — Two people built the same feature in the same two hours · PROCESS · fix the process

On 2026-09-12 a recruitment lifecycle state machine was built twice in parallel: Ankush's
`77d3c49` on `azure-provider`, and a second one locally. Same six files, same names
(`app/core/lifecycle.py`, `app/services/lifecycle_service.py`, `tests/test_lifecycle.py`,
the `models.py` block, the `web/audit.html` label), and **two Alembic heads off the same
parent** — which makes `alembic upgrade head` refuse until one is rebased.

Roughly 1,000 lines were discarded. Ankush's was kept: it has the API, users and roles,
handover and manager review, and a better current-state design.

Cause: no fetch before building, and no shared statement of who was taking which item.

Fixes:

- [x] `CLAUDE.md` now requires `git fetch origin && git log --oneline HEAD..origin/azure-provider`
      before starting work
- [x] `CLAUDE.md` records that `main`, `phase-b`, `phase-c`, `phase-d` are ancestors of
      `azure-provider` with zero unique commits, so only one branch is ever tracked
- [ ] Agree who owns which plan ID before the next build. Not yet done — deliberately held.

---

## X11 — The funnel is sorted by size, not by stage · CLIENT-VISIBLE when the screen is built

`funnel()` in `app/services/lifecycle_service.py:142` sorts by `-count`, and builds its
counts only from states that have at least one candidate.

Two consequences:

1. **A funnel sorted by size is a bar chart.** A recruitment funnel has to read in stage
   order — shortlisted, with the hiring manager, interview, feedback, approval, offer, hired
   — or it tells the reader nothing about flow or drop-off.
2. **Stages with nobody in them vanish.** A funnel with holes hides exactly the stages where
   everyone is getting stuck, which is the thing a funnel exists to show.

Not a regression; it has always been this way, and no screen renders it yet, so nothing is
broken today. It becomes client-visible the moment the timeline or dashboard is built, and
it directly affects `B19`.

**Fix shape:** order by a declared stage sequence in `app/core/lifecycle.py`, and emit every
non-terminal stage with a zero count rather than omitting it. Terminal outcomes (hired,
not proceeding, withdrawn, closed) belong in a separate outcome group, not in the funnel
body.

- [x] Stage order declared in `app/core/lifecycle.py`
- [x] Zero-count stages emitted by `lifecycle_service.funnel()`
- [~] Off-ramps flagged in the API and displayed after the journey spine; a dedicated
      outcome chart remains to be added

---

## X12 — The leaderboard fetches every evaluation, then slices in Python · SCALE

`app/api/evaluations.py:202` calls `.all()` on the evaluation query and then applies
`[:limit]` at line 206. The whole result set is loaded into memory before being truncated.

At demo scale (3-12 CVs) nothing is visible. The stated design target is **10,000 CVs a
month**, and `B16` asks for a comparison page built for 10,000-20,000. At that size this
loads every row of a campaign to show ten.

**Fix shape:** push the limit and offset into the query. The ordering is already computed in
SQL, so this is a `.limit().offset()` rather than a redesign.

Related: `B16` asks the comparison page to default to the top 10 and to avoid a
full-population render. Same root cause, same fix.

**2026-09-13 correction, found while rebuilding `web/compare.html` for B16:** the `/leaderboard`
route (`app/api/evaluations.py:172-212`) already delegates to `evaluation_service
.ranked_evaluations()`, which does push `.limit()` into SQL — that route is no longer the
unbounded one. The endpoint `compare.html` actually calls, `GET /api/campaigns/{id}
/evaluations` (used to list every candidate for the new search/filter/paginate table), has
**no** `limit`/`offset`/search param at all and still runs an unbounded `.all()`. Same defect,
different route than the line numbers above cite — the fix still applies, just here instead.

- [ ] Leaderboard uses SQL limit/offset
- [ ] `GET /api/campaigns/{id}/evaluations` gets SQL `limit`/`offset` (and ideally a name
      search param), so `web/compare.html`'s candidate table stops loading a whole
      campaign's evaluations client-side before paging them in JS
- [ ] Comparison page defaults to the top 10
- [ ] Benchmarked against a campaign with more than 1,000 candidates

---

## X13 — A SharePoint link resolves on the path tail alone · PILOT RISK, not a demo risk

`SyncedFolderSource._resolve_url` in `app/core/cv_source.py` decodes the URL path into
segments, then shrinks from the left until a suffix matches a directory chain under one of
the OneDrive sync roots. The tenant and the site are never checked.

Proved by hand on 2026-09-12: a **fabricated** URL,
`https://protiviti-my.sharepoint.com/personal/x/Documents/Work/Resume-Screening/CV-Repository`,
resolved to the real `CV-Repository` folder, because only the tail matched.

For Monday this fails in the safe direction — a link the user pastes will resolve. The risk
is a client machine with several synced libraries whose folder names end the same way. The
resolver would open the wrong one and report success. A recruiter would not notice.

**Fix shape:** two parts. Match the tenant host and the site or drive segment against the
sync root's own identity before accepting a tail match, and refuse when more than one root
matches instead of taking the first. The registry already carries enough per-account
information to do the first part. This lands naturally with the Graph work, which knows the
site identity for certain.

**Partially fixed 2026-09-12** in commit `313c069`. `_max_discardable_prefix` in
`app/core/cv_source.py` now puts a floor under the shrink-from-the-left search: it may never
drop past a URL's own site identity (`personal/<user>` or `sites/<name>`), which is exactly
how the fabricated URL above used to slip through. A tie between more than one sync root is
now refused outright rather than silently taking whichever root was checked first. Verified
this session by reading the code and re-running the regressions that reproduce this
writeup's exact scenario:
`tests/test_cv_source.py::test_a_fabricated_url_naming_a_different_site_does_not_match_by_tail_alone`
and `::test_two_synced_roots_matching_the_same_tail_is_refused_as_ambiguous`.

**Still genuinely open:** the tenant/account identity check itself. `313c069`'s own commit
message says why it stopped short — doing this without guessing at a naming convention needs
real per-tenant OneDrive registry data (e.g. an account's tenant claim alongside the
`UserFolder` value `_default_sync_roots` already reads), and no machine with more than one
tenant synced has been available to verify against in any session so far.

- [x] An ambiguous match is refused rather than resolved to the first hit — `313c069`
- [x] The screen has something to show which sync root was matched —
      `POST /discovery/resolve` already returns `resolved_folder` and `source_kind`
      (`app/api/discovery.py:123-124`). Whether `web/discover.html` displays it is
      Subhadeep's `web/**` lane and was not checked here.
- [ ] Tenant and site checked against the sync root's own account identity, not just a
      site-marker floor on the URL path — blocked on a real per-tenant OneDrive machine to
      build and verify against

---

## X14 — The timeline's B01 step mapping is unconfirmed · NEEDS A REVIEW, NOT A FIX

`web/timeline.html` renders the ten numbered `B01` journey steps. No written source pins one
`LifecycleStatus` to each numbered step. The mapping for steps 3-10 was made by hand from the
gap table in `02-LIFECYCLE-MODEL.md` and recorded in `docs/DECISIONS.md`.

It is defensible. Nobody has confirmed it. A different, equally defensible mapping exists.
Because the timeline is the screen the whole demo journey is told through, a wrong mapping
shows up as the story not matching the states.

- [ ] Walked step by step against the lifecycle map by a second person
- [ ] Confirmed or corrected in `docs/DECISIONS.md`

---

## X15 — The ON_HOLD resume gate was never exercised · UNTESTED PATH

The timeline infers where an `ON_HOLD` candidate came from by walking the transition history
backwards to find `held_from`. No `ON_HOLD` candidate existed in the live data, so the branch
has never run against a real record.

If it is wrong, an on-hold candidate's timeline shows the wrong prior stage, or nothing.

- [ ] A real candidate put ON_HOLD and the timeline checked
- [ ] Resume from hold checked as well as entry to hold

---

## X16 — UNC paths are shape-recognised, not verified · UNTESTED PATH

`SyncedFolderSource.resolve` accepts `\\server\share\...` by pattern, without a filesystem
existence check, because no network share was available to test against. A local path is
checked; a UNC path is not.

So a mistyped UNC path is accepted and fails later, at listing or import, rather than at the
point the user pastes it. The error the user sees is further from the cause.

**Existence check built and tested 2026-09-12** in commit `313c069`. `resolve()` now calls
`unc_path.is_dir()` before accepting a UNC path, exactly like the local-path branch, and
raises the same-shaped `CVSourceResolutionError`. Verified this session by reading
`app/core/cv_source.py` and re-running
`tests/test_cv_source.py::test_accepts_a_unc_path_that_exists` and
`::test_a_unc_path_that_does_not_exist_gets_the_same_honest_error_as_local` — both pass, but
both monkeypatch `Path.is_dir` because no real network share exists in this environment.
They prove the code path, not a real UNC resolution.

- [x] Existence checked at resolve time, with the same honest error a local path gets —
      `313c069`, `app/core/cv_source.py::SyncedFolderSource.resolve`
- [ ] Tested against a real network share — still genuinely blocked, no share available in
      any environment this has run in

---

## X19 — Two setup tabs share one draft id · CLIENT-VISIBLE · FIXED

Found 2026-09-12 by an adversarial review of the X18 fix, not by a user report.

`web/new-campaign.html` remembered the draft campaign id under a single
`localStorage` key, `recruitment360.campaignDraft.v1`. The key was not scoped to a
role. Setup opened in two browser tabs for two different roles wrote to the same
campaign: the second tab's save overwrote the first role's title, hiring manager
and closing date.

This is not the X18 defect. X18 was two campaign rows for one role; this is one
row for two roles. It was left open rather than folded into that fix.

Fixed 2026-09-12. The `campaign_id` in this tab's own URL is now the only source
of which draft the tab edits. `saveDraftNow()` stamps the new id into the URL with
`history.replaceState` after the create, so a reload finds the same draft and the
link is shareable. The shared `localStorage` key is deleted, not scoped: the
"Not finished yet" band on `web/campaigns.html` already finds a draft after the
tab is closed, and it reads the server rather than one browser.

The URL was chosen over the two other options because `AGENT-START-HERE.md` §5
requires deep-link context and working browser Back. A per-role key keeps one
global key and cannot be scoped before the role exists; refusing a second tab
contradicts the parallel campaign work the UX proposal asks for.

- [x] Decide the intended behaviour: the `campaign_id` in this tab's URL is the
      only source. Recorded in `docs/DECISIONS.md`
- [x] Reproduce with two tabs before implementing — two tabs, two roles, against
      the live API: `062bf404` "X19 Tab A Welder" / Manager A and `501af657`
      "X19 Tab B Electrician" / Manager B stayed two separate DRAFT campaigns,
      and tab A's fields were not overwritten
- [x] Verify that an existing single-tab draft still resumes after the change —
      reload restored the id from the URL and refilled every role field
- [x] Four guards in `tests/browser/test_campaign_draft_contract.py`, each
      mutation-tested: re-introducing its defect fails that test

## X20 — An early save can blank a restored draft · CLIENT-VISIBLE · FIXED

Found 2026-09-12 while verifying X19. Not a regression from it: the same window
existed while the id came from `localStorage`.

`restoreDraft()` is not awaited and the buttons are live as soon as the page
parses. `roleFields()` reads the form and falls back to `job_title: 'New role'`
when the title box is empty. So a save clicked on a `?campaign_id=` page before
the restoring GET answers sends a `PATCH` built from empty boxes, and overwrites
a good draft's title and job description with placeholder text.

X19's fix closed the neighbouring hole — that same early click no longer creates
a second campaign, because `saveDraftNow()` now reads the id from the URL. It
does not stop the blank overwrite.

Reproduced 2026-09-12 through a throwaway proxy that held `GET /api/campaigns/{id}`
open for four seconds. The failure is worse than the reading above suggested. The
form does not open empty: it ships prefilled sample values. An early save therefore
wrote demo data over a real draft, not a `'New role'` placeholder.

| Field | Saved draft | After the early save |
|---|---|---|
| `job_title` | X20 Probe Operator | Control Room Operator |
| `job_description` | "Original job description text…" | "" |
| `location` | North Plant | Coastal Terminal |
| `vacancies` | 3 | 8 |

Fixed by making the restore the first thing in the existing save queue:
`draftQueue = restoreDraft().catch(...)`. Every save already runs through
`draftQueue`, so an early click now waits for the restore and then saves the
restored values. This covers all three save callers at once and disables no
button, so the page never looks broken while it loads.

- [x] Reproduce with a delayed or throttled campaign GET — 4-second proxy, all four
      fields overwritten
- [x] Decide the fix — queue the save behind the restore. Rejected: disabling the
      save controls (three buttons to manage, and a dead-looking page on a slow
      network) and sending only filled boxes (the create path still needs the
      `job_title` fallback, so the hole would only narrow)
- [x] Verify the same early click against the fixed page — all four fields survived
- [x] Verify a normal single-tab draft still saves with no extra click blocked —
      no `campaign_id`, one campaign created, id stamped into the URL, the button
      reported "Draft saved" and re-enabled
- [x] Guarded by `test_a_save_cannot_run_before_the_restore_settles` and
      `test_the_restore_promise_is_not_dropped` in
      `tests/browser/test_campaign_draft_contract.py`

## X22 — A campaign past setup vanishes, then is overwritten · CLIENT-VISIBLE · PARTLY FIXED

Found 2026-09-12 from a user question: "I will upload the CVs later." Reproduced
against the running app with a campaign whose role was described in full, whose
rubric was approved, and which had no CVs.

Three failures on one journey:

1. The campaign disappears from `web/campaigns.html`. That page asks for two
   things only, `?status=DRAFT` and `/api/runs`. A campaign past setup is no
   longer a draft, and with no CVs it has no run, so it falls between them.
2. Opening it by its own URL restores nothing. `restoreDraft()` returns early on
   `campaign.status !== 'DRAFT'`, so the form keeps its prefilled sample values.
3. The first save then overwrites the real campaign. Observed: an `APPROVED`
   campaign became `job_title: 'Control Room Operator'`, `vacancies: 8`,
   `location: 'Coastal Terminal'`, `job_description: ''`.

This is X20's damage through a door X20's fix does not cover. X20 made the save
wait for the restore; here the restore runs and gives up.

- [x] `restoreDraft()` loads the campaign whatever its status. Never PATCH a
      record that was not read. No policy decision needed — see `DECISIONS.md`.
      Fixed 2026-09-12: the `status !== 'DRAFT'` early return is gone, and the
      restore message now names the stored status when the role is past setup.
      Browser-verified against an `APPROVED` campaign — role details restored,
      the notice read "This role is already past setup (approved)", and the save
      that used to destroy it left every field and the status unchanged. The
      plain draft path still restores its own fields with its own message.
- [x] `web/campaigns.html` lists every campaign, not drafts plus runs. Fixed
      2026-09-12: one `GET /api/campaigns` with no status filter, joined with
      `GET /api/runs?limit=100` on `campaign_id`. A campaign no run covers gets
      a card from its own stored status. Browser-verified against a fixture
      `APPROVED` campaign with no CVs — before the change it appeared nowhere;
      after it reads "Ready for CVs · No CVs uploaded yet" with an upload link.
      Progress never depends on the capped runs list, because the number of
      campaigns is unbounded — see `DECISIONS.md`, 2026-09-12
- [ ] Past rubric approval, apply the per-field editability rule decided
      2026-09-12: administrative fields editable, job description and
      requirements read-only with a "Change the job description" action that
      creates a new rubric version
- [ ] Guard all three in `tests/browser/test_campaign_draft_contract.py`

## X23 — Six campaign cards are hardcoded sample HTML · CLIENT-VISIBLE · PARTLY FIXED

Found 2026-09-12 alongside X22. `web/campaigns.html` lines 159-257 hold six
static `<article class="camcard">` blocks — Process Engineer, Control Room
Operator, HSE Advisor, Rotating Equipment Engineer, Instrumentation Technician,
Turnaround Planner. Live cards from `/api/runs` are appended beside them, so the
page mixes fiction with real records and a recruiter cannot tell which is which.
A live run for Process Engineer currently renders twice, once real and once not.

- [x] They no longer stand beside real campaigns. Fixed 2026-09-12: hiding the
      `data-mock-only` bands moved out of `renderRuns` into `hideMock()`, called
      whenever any real campaign exists. Before, the hide fired only when a
      *run* existed, so a recruiter with campaigns and no CVs yet — the "I will
      upload the CVs later" case — saw six fictional campaigns beside her own.
      Browser-verified: four real campaigns, zero visible mock bands.
- [ ] Still open: with no campaigns at all the six cards render unlabelled, and
      a reader cannot tell they are sample data. Either label them in place or
      replace the empty state with one that says the list is empty. An empty
      API currently looks like a busy recruiter's dashboard.

## X21 — Restoring a draft blanks a location the form cannot show · FIXED ON SUBODHIP

Found 2026-09-12 while verifying X20. Not caused by it; the same loss existed
before.

`f-site` is a `<select>` with exactly three options: North Plant, Coastal Terminal,
Head Office. `setField()` assigns `campaign.location` to `select.value`. A value
that is not one of the three is silently rejected by the browser and the box reads
empty. The next save then writes that empty string back, so the campaign loses its
location permanently.

Observed: a draft stored with `location: "Mesaieed"` restored as an empty select and
the following save persisted `location: ""`.

A recruiter using only this form can pick one of the three, so the round trip
usually holds. A campaign created through the API, imported, or made before the
option list changed does lose its location.

- [x] Add an option for the saved site when it is outside the fixed list.
- [x] Restore the stored value rather than a blank; browser-verified with Mesaieed.
- [ ] Add an automated form round-trip regression (current evidence is browser verification).

## X17 — Manager verdict blocked actual scheduling · FIXED

`manager_review(PROCEED)` moves a candidate into `INTERVIEW_SCHEDULED` before an
appointment is recorded. The first version of the interview route then tried to make
the same transition and returned 422. It also allowed feedback or rescheduling when
no appointment existed.

- [x] First appointment can be recorded after the manager's verdict
- [x] Duplicate round uses the reschedule route
- [x] Feedback and reschedule require a recorded appointment
- [x] Regression tests and shortlist-to-hire integrated path pass

## X24 — Four different Python versions are named as canonical · FIXED

`CLAUDE.md` states the environment is "built and verified on Python 3.13.5." Every other
place in this repo that names a Python version disagrees with it and with each other:

| Source | Value |
|---|---|
| `CLAUDE.md` | 3.13.5 (claimed) |
| `.github/workflows/ci.yml:20` | `python-version: "3.12"` |
| `venv/` in this checkout, verified 2026-09-13 (`.\venv\Scripts\python.exe --version`) | `Python 3.12.10` |
| `.python-version` at repo root | `3.11` |

`.python-version` is leftover from before the 3.13 upgrade: `git log` puts its last change at
`7248808`, 2026-06-07, "force python 3.11 for Streamlit Cloud" — a different deployment
target, not this one. Nothing has updated or removed it since.

Flagged across several prior sessions' notes (most recently `ankush_reconciliation_2026-09-13`
in `docs/SESSION-STATE.md`) but never filed here until now.

**Why it matters:** CI validates every PR against 3.12, not the 3.13.5 the docs promise, so a
3.13-only regression can pass CI and still break for anyone who provisions per `CLAUDE.md`.
The stale `.python-version` can silently steer a `pyenv`/`asdf`-managed shell to 3.11, a
version nothing here has ever been verified against.

**Fix shape:** decide the one true version — the actual `venv`'s 3.12.10 is the cheapest
choice unless there's a specific reason to move it — then make `CLAUDE.md`,
`.github/workflows/ci.yml` and `.python-version` agree. Not done as part of filing this: a
pinned CI/runtime version is a deliberate decision, not a side effect of a defect-filing pass.

- [x] One canonical Python version decided and recorded in `docs/DECISIONS.md`: 3.12,
  matching the verified venv (3.12.10).
- [x] `CLAUDE.md`, `.github/workflows/ci.yml` and `.python-version` all updated to agree.
  `ci.yml` was already correct; `CLAUDE.md` and `.python-version` changed to match.
- [x] Full suite re-run against the chosen version to confirm nothing regresses — see
  `docs/SESSION-STATE.md` for the observed result.

## X25 — The what-if weight-slider screen never calls the proposal API · CLIENT-VISIBLE

Found auditing B07 item 5 (2026-09-13): `web/whatif.html:117-137` has real
`<input type="range" min="0" max="100">` sliders for all five weight bands, and the backend
they should drive — `whatif_service.propose()`, `POST
/api/campaigns/{campaign_id}/what-if/proposals` — is built and tested (B17, 16 passing
tests, see `docs/SESSION-STATE.md`). But the page's "Propose these weights for approval"
button (`web/whatif.html:426-428`) only does this:

```js
proposeBtn.addEventListener("click", function(){
  confirmMsg.style.display = "inline";
});
```

It shows a static confirmation message and never fetches the proposals endpoint, never reads
the current slider values, and never sends anything to the backend. A recruiter who drags the
sliders and clicks Propose sees a success-shaped message with nothing recorded — no
`WhatIfProposal` row, no audit event, no route to the hiring manager who is supposed to
approve it.

**Why it matters:** this is the entire reason B17's proposer/approver/audit workflow exists,
and the one screen meant to drive it doesn't. B07's "Allow HR override and custom criteria"
and "Replace unrestricted text inputs with sliders" both read as done from the UI widget
alone; neither is usable end-to-end until this is wired up.

**Fix shape:** `web/whatif.html`'s click handler needs to collect the five slider values,
`POST` them to `/api/campaigns/{campaign_id}/what-if/proposals` with a proposer/approver
selection, and reflect the real response (including the object-of-errors shape
`_fail_whatif` returns on a 422) instead of the static message. This is `web/**` — Subhadeep's
file per `08-TWO-PERSON-DELIVERY.md` — not fixed here.

- [x] Slider values are read from the DOM and sent to `POST .../what-if/proposals` on click
      (2026-09-13) — `web/whatif.html`'s handler now redistributes each band slider across
      its constituent `criterion_key`s (proportional to their existing weight inside the
      band), normalises to 100, and posts `{weights, proposed_by, approver_id}`. Proposer/
      approver are picked from two new selects, populated from `/api/users` and
      `/api/users?role=HIRING_MANAGER` — same pattern as `web/handoff.html`.
- [x] The real API response (success or 422) is shown in place of the static confirmation
      (2026-09-13) — success renders "Sent to `<approver>` for a decision."; a 422 renders
      `detail.message` plus `detail.errors` when present (`_fail_whatif`'s shape); other
      failures (404, network) show a plain message. Verified live against the real API,
      including a real 422 (`bogus_key` weight rejected with the exact message).
- [x] A regression/browser check confirms a proposal row and audit event are created
      (2026-09-13) — live browser run against campaign `24da8b3f-…`: POST returned 201 with
      a real `WhatIfProposal` (`id: 6cc6785f-…`, `status: PROPOSED`, weights summing to 100).
      No dedicated pytest added — this is a pure `web/**` static-page change with no new
      backend code path; `pytest -k "whatif or what_if"` (24 passed) confirms the backend
      side this wiring depends on is unaffected.

## X26 — `rapidocr` is not installed in this checkout's verified venv · CLIENT-VISIBLE · DEMO RISK

`CLAUDE.md` says "OCR now installs from `requirements.txt` in one pass" and
`01-DEMO-MONDAY.md` records OCR on a real scanned CV as verified live on 2026-09-12 (1168
chars extracted via `text_source=ocr`, 11.7s). Checked directly against **this** checkout's
venv while confirming X24's re-run (2026-09-13):

```
.\venv\Scripts\python.exe -c "import rapidocr"
ModuleNotFoundError: No module named 'rapidocr'
```

`requirements.txt` does list `rapidocr>=3.4.0`; it is simply not installed in this venv. The
full suite's own 6 skips confirm it independently: every `tests/test_document_quality.py` OCR
test reports "the OCR package is not installed" rather than running.

**Why it matters:** demo script step 3 — "Show the scanned PDF being read by OCR — this is a
strong moment and it is genuinely working" — cannot work in this environment as it stands. Per
the requirements-ocr.txt comment, when `rapidocr` is missing, "OCR turns itself off and
image-only files are held" — i.e. the scanned demo CV would go to an exception/hold state
live in front of the client instead of extracting text, not crash outright, but still a
visible failure of the one step the script calls out as strong.

**2026-09-14 update, see X35:** the consequence described above no longer applies. A file
still under `MIN_TEXT_CHARS` after OCR (or with OCR unavailable, exactly this defect) is no
longer held out of the batch at all — it is screened on whatever text exists and flagged
`NO_TEXT_EXTRACTED`, `requires_review=True`. So even with `rapidocr` missing, the scanned demo
CV would not go to an exception/hold state; it would show a (likely low-scoring) assessment
with a visible flag instead. This does not fix the missing package — the demo script's "OCR
reads it" moment is still not literally demonstrated without `rapidocr` — but it removes the
worse visible failure (a file vanishing into the exceptions panel instead of being screened).

**Fixed 2026-09-14** (this checkout is the demo machine): `pip install rapidocr` — it pulled in
`numpy 2.5.3` as a dependency, which broke `spacy`/`thinc` (`ValueError: numpy.dtype size
changed, may indicate binary incompatibility` — `thinc` was compiled against numpy 1.x's ABI).
Reverted to `numpy==1.26.4` immediately; `rapidocr`'s own constraint (`>=1.19.5,<3.0.0`) is
satisfied by 1.26.4, so both packages coexist once the resolver's default (newest-satisfying)
choice is overridden back down. `opencv-python 5.0.0.93` (a `rapidocr` transitive dependency)
still declares `numpy>=2` in its own metadata and pip prints a dependency-conflict warning on
every install/uninstall touching numpy — cosmetic only; `import cv2`, `import spacy`, `import
rapidocr` and the full test suite all verified working at `numpy==1.26.4`. See
`docs/DECISIONS.md`, 2026-09-14.

- [x] `rapidocr` installed and confirmed importable
- [x] `tests/test_document_quality.py` re-run: 18 passed, 0 skipped (previously 6 skipped for
      "OCR package is not installed")
- [x] Full suite re-run after the numpy revert: 787 passed, 0 failed (see `SESSION-STATE.md`)
- [x] Verified against a real scanned CV in this session's own demo build — Suresh Nair's
      scanned Process Operator CV (`Resume_ProcessOperator_SureshNair_ScannedPDF.pdf`) produced
      a correctly-named candidate with real extracted evidence ("Seven years on a live DCS
      console"), not a blank/held file — see `DEMO-RUNBOOK-2026-09-14.md` §6

## X27 — A failed same-origin asset fetch silently served the wrong page · CLIENT-VISIBLE · FIXED 2026-09-13

`web/sw.js`'s fetch handler fell back to `caches.match('index.html')` for **any** failed
same-origin GET, not only page navigations. When a transient network hiccup made
`assets/app.js?v=16` (or `campaign-list.js`, `app.css`, …) fail, the service worker handed
back cached `index.html` HTML *as if it were that script's response*. The browser then tried
to parse HTML as JavaScript (`Uncaught SyntaxError: Unexpected token '<'`), the rest of that
script never ran, and every global it defines silently stayed `undefined` — reproduced this
session as `window.CampaignSteps` being missing on `start-campaign.html`/`campaigns.html`,
which froze the "which stage is this campaign on" resume label at "Checking saved stage…"
forever (the B14/X18 durable-resume feature, otherwise confirmed working end-to-end). No
console error pointed at the real cause; it looked like the resume feature itself was broken.

**Fixed:** `web/sw.js`'s catch branch now only substitutes `index.html` for a navigation
request (`e.request.mode === 'navigate'`); a failed script/style/asset request instead falls
back to that same URL's own cache entry, or fails visibly (`Response.error()`) if there isn't
one — never someone else's content. Cache version bumped `v20` → `v21`.

- [x] `web/sw.js` fetch handler scopes the `index.html` substitute to navigations only
- [x] Verified in-session: after the fix (and clearing the previously-poisoned cache once),
      `window.CampaignSteps` loads and the resume label renders correctly on repeated
      reloads of `start-campaign.html`
- [ ] Not verified against a real client network/proxy — only against this dev checkout

## X28 — A manually added requirement had no weight field and no save path · CLIENT-VISIBLE · FIXED 2026-09-13

`web/new-campaign.html`'s "Add a requirement" button (step 3, mandatory list) appended a row
with only a text input — no `.wt` weight input and no `criterion_key`. `weightedRows()` /
`currentWeightItems()` only ever read rows that already have both, so anything typed into a
manually added row was silently discarded: not included in the weight total, not sent by
`PUT .../weights` on Approve, and never persisted by Save as draft (which does not touch
weights at all). A recruiter typing a requirement here saw no error and no indication it
would not be kept.

**Fixed:** the row now gets an **Apply** button. Apply calls the rubric service's existing
`POST /api/campaigns/{id}/rubric/versions/{v}/weights` (`rubric_service.add_weight`,
previously wired only into What-if/B07's HR-override path) to mint a real `criterion_key`
for the typed label, then turns the row into a normal weighted row that Approve/Save already
know how to persist. Also this session: weights across Must-have + Preferred now auto-adjust
to keep the group at 100 pts as a weight is typed, added or removed
(`autoBalanceWeights`/`redistributeAfterRemoval`), instead of only flagging the imbalance and
waiting for a manual "Normalize to 100" click. 2026-09-13, later, on direct instruction: that
button (previously moved to the top of the card as an explicit reset for rounding drift) was
removed from `new-campaign.html` entirely — auto-balancing is now the only path to 100.

- [x] Add a requirement now has an Apply action that creates the criterion server-side
- [x] Weights auto-rebalance to 100 on type/add/remove
- [x] Normalize to 100 button removed (2026-09-13) — superseded, no longer needed
- [ ] Not covered by an automated test — verify manually before the next demo rehearsal

## X29 — "What the checking agent found" printed twice on Candidate 360 · CLIENT-VISIBLE · FIXED 2026-09-13

Found from a user screenshot of `web/candidate.html`. The static band around the challenge-agent
card already carries its own `<div class="label"><h2>What the checking agent found</h2></div>`;
`renderChallenge()` in the page's inline `<script>` then overwrote `#c-challenge`'s innerHTML with
a *second*, JS-built `<div class="label"><h2>What the checking agent found</h2>...</div>` nested
inside it (both the empty-findings branch and the real-findings branch built their own copy). The
collapsed band summary and the expanded card both showed the same heading, and the finding-count
aside ("2 points raised across 2 kinds of check") lived only on the throwaway JS copy.

**Fixed:** the static label gained an empty `<span class="aside" id="c-challenge-aside">`;
`renderChallenge()` now calls `set('c-challenge-aside', …)` for the count text and `set('c-challenge', …)`
with only the card content (lead paragraph + finding groups, no repeated label/h2, no redundant
nested `.card.pad-lg`).

**Verified live** against a real evaluation (browser session, real `/api/evaluations/{id}` data,
campaign `6726bbe3-…`, candidate Tariq Al-Naimi — the same "5 years claimed vs. 7.67 years dated"
contradiction as the reporting screenshot): exactly one `<h2>What the checking agent found</h2>`
in the rendered DOM, aside reads "2 points raised across 2 kinds of check".

- [x] Static label carries the aside placeholder; JS no longer builds its own label/h2
- [x] Browser-verified against a real evaluation with real findings (2 points, 2 check kinds)
- [ ] Zero-findings branch (`c-challenge-aside` should read "nothing to raise") reviewed in code
      only — not exercised live against a real evaluation with no challenge findings this session

## X30 — Two raw enum values reached the Candidate 360 decision panel · CLIENT-VISIBLE · FIXED 2026-09-13

Found while rewriting the disposition comment-box draft on user request. `web/candidate.html`'s
`renderDecision()` set `#c-decision-status` to a sentence ending "Next action: " +
`evaluation.next_action` — the raw `NextAction` enum value (e.g. `MANUAL_REVIEW`) printed straight
to the reader, not the plain-words map `CLAUDE.md`'s conventions require for every enum a reader
can see. The same function's action-recording handler had the identical bug one line below:
"Latest recorded disposition: " + `latest.disposition` (e.g. `HOLD`), also unmapped.

**Fixed:** added `dispositionText()` (mirrors the backend's own `DISPOSITION_WORDS` map in
`app/services/disposition_service.py`) and routed both call sites through it. The user separately
asked for the whole "AI recommends; a person decides. Current assessment: … Next action: …" line
removed outright, so the `next_action` half of the bug is now moot — that line and its raw-enum
tail are gone rather than reworded; the disposition-side leak (post-decision confirmation text)
still needed the fix since that text stayed.

**Verified live** against a real evaluation (Tariq Al-Naimi, HSE Officer campaign): the decision
panel now falls back to the existing static human copy ("This score is a recommendation. A person
decides…") until a disposition is recorded, with no enum value in the DOM.

- [x] `dispositionText()` added and wired into both call sites in `web/candidate.html`
- [x] Browser-verified: clicked "Hold" against a real evaluation (Tariq Al-Naimi) and read
      `#c-decision-status` — "Decision recorded — put on hold. The audit trail has been
      updated.", no raw enum string in the DOM
- [ ] Not re-run against every `Disposition`/`NextAction` value the server can send — only the
      `HOLD` case this evaluation actually returned

## X31 — "Open the original CV" downloaded the file instead of showing it · CLIENT-VISIBLE · FIXED 2026-09-13

Reported by the user directly. `/api/evaluations/{id}/cv` already sends
`Content-Disposition: inline` (`app/api/exports.py`), which is correct for a PDF — but no
browser has a built-in renderer for a `.docx`/`.doc`/`.pptx` file, so `inline` makes no
difference for those: the browser just downloads it, exactly as reported. This is a demo CV set
that is mostly Word documents, so the case the user hit is the common one, not an edge case.

**Fixed:** `web/candidate.html`'s "Open the original CV" link now opens `web/cv-viewer.html`
(a new page) instead of the raw API URL. The viewer fetches the file client-side and renders it
inline in the tab rather than letting the browser navigate straight to the binary:
- PDF → a blob URL in an `<iframe>` (the browser's native PDF viewer — pagination, zoom, all of it)
- DOCX → converted to HTML client-side by `mammoth.browser.min.js` (loaded from cdnjs) and
  injected into the page
- Anything else (`.doc`, `.pptx`, unknown) → says plainly that no preview exists yet for that
  type, with a real download link — no attempt to fake an embed for a format nothing here can
  render; converting arbitrary legacy-`.doc`/`.pptx` files to a faithful preview needs a
  document-conversion service (e.g. LibreOffice headless) this environment does not have
  installed, so this is a known remaining gap, not silently hidden.

File-type detection reads `Content-Type` (safelisted for a cross-origin `fetch()`) rather than
trusting `Content-Disposition`'s filename, because `Content-Disposition` is *not* on the CORS
response-header safelist — a cross-origin `fetch()` (the static UI on 8124 calling the API on
8000) got `null` back from `response.headers.get('content-disposition')` until `app/main.py`'s
`CORSMiddleware` was given `expose_headers=["Content-Disposition"]`. Both fixes landed together;
the viewer still works from `Content-Type` alone if that header is ever unavailable again.

**Verified live** against two real evaluations: a `.docx` CV (Tariq Al-Naimi, HSE Officer)
rendered as readable formatted text in the tab, and a `.pdf` CV (Suresh Nair, Process Operator)
rendered in an embedded page-by-page viewer — neither triggered a download.

## X32 — GitHub Actions CI has been red on every push to `consolidated` since `2020c9f` · CLIENT-VISIBLE (CI) · FIXED 2026-09-14

Confirmed 2026-09-13 via the GitHub Actions API (`.github/workflows/ci.yml`'s `test` job):
`Install dependencies` and `Alembic upgrade` steps pass; `Run test suite` (`pytest -q`) fails,
on every run back through `2020c9f` — including `c107ebc`, a docs-only commit with zero `app/`
or `web/` changes. This proves the failure is not caused by any particular commit's content;
it has been broken since whatever landed between `af5f398` (last green run) and `2020c9f`
(first red run), and stayed red through this session's two pushes (`55e6e54`, `d419b2f`).

**Root cause, reproduced locally** (`pytest -q tests/browser/test_campaign_chooser_label.py
tests/browser/test_campaign_resume.py`, 9 failed): each test spawns a `node -e` subprocess with
a hand-built fake `document` (`{querySelector, querySelectorAll, addEventListener, readyState}`,
no `documentElement`) and `require()`s `web/assets/app.js` directly. The B22 portal-gate IIFE at
the top of `app.js` (`document.documentElement.classList.add('auth-pending')`, added for the
real-login work) throws immediately against that mock, before either test's own
`CampaignSteps`/label logic ever runs — `CalledProcessError`, exit 1, same signature in all 9.

**Not this session's fault, but not safe to ignore either:** CI has silently been reporting
every push as failed for at least four commits/one full session before this one; nobody
appears to have been looking at the badge. This is exactly the kind of build-report-claims-green
gap `CLAUDE.md` warns about, inverted — here the report was honestly red and nobody read it.

**Re-confirmed 2026-09-13, later, in an unrelated frontend-polish/export session:** same 9
failures, same signature, independently reproduced with the exact `node -e` command pytest
runs (`TypeError: Cannot read properties of undefined (reading 'classList')` at
`app.js:17`); `git blame` confirms that line predates this session and `git status` shows
`app.js` untouched — still not caused by any commit in between.

**Fixed 2026-09-14**, the harness option (the two tests exist specifically to run `app.js`
without a browser, so stubbing the harness is more honest than guarding the gate line itself):
both fake `document` objects (`tests/browser/test_campaign_chooser_label.py`,
`tests/browser/test_campaign_resume.py`) now carry a stub `documentElement: {classList: {add,
remove}}`. That surfaced a second, previously-masked crash one line further in — `toLogin()`
calls `location.replace(...)`, and the fake `location` had no `replace` — stubbed the same way.
Both stubs are no-ops; they exist only so the harness can run `app.js`'s B22 portal-gate IIFE
without throwing, not to assert anything about login behaviour.

- [x] Node harness's fake `document`/`location` given stub `documentElement.classList` and
      `location.replace` (this cross-boundary fix was made directly this session — solo
      full-stack demo-prep authorized by the user, recorded in `08-TWO-PERSON-DELIVERY.md`'s
      handoff note rather than as a hand-off request)
- [x] Full suite re-run: `tests/browser/test_campaign_chooser_label.py` and
      `tests/browser/test_campaign_resume.py` — 9 passed, 0 failed. Full suite: 787 passed,
      0 failed, 0 skipped
- [ ] Confirm the CI badge itself goes green on the next push to `origin/consolidated` (not
      verified from this session — only the local reproduction is confirmed fixed)
- [ ] Check whether any push notification/Slack integration exists that should have caught this
      four commits ago, and if not, whether one is worth setting up — not investigated this
      session, out of scope for today's demo-prep

- [x] `web/cv-viewer.html` added; `web/candidate.html`'s CV link points at it
- [x] `Access-Control-Expose-Headers: Content-Disposition` added in `app/main.py`
- [x] Browser-verified against a real `.docx` and a real `.pdf` evaluation — both embedded, no download
- [ ] `.doc` (legacy binary) and `.pptx` fall back to "no preview, download it" — not a real
      preview, and not exercised live this session (no `.doc`/`.pptx` demo CV found to test against)
- [x] 2026-09-13, later: the DOCX renderer itself (`mammoth.browser.min.js`) was replaced with
      `docx-preview` — mammoth only ever produced semantic HTML, dropping the document's real
      fonts/colours/spacing/layout, which is a *different* complaint ("shows only the text of
      that cv") than X31's original "downloads instead of previewing" — see B18 in
      `00-MASTER-BACKLOG.md`.

---

## X33 — JD extraction's first weight render could total 99 or 101, blocking screening entirely · CLIENT-VISIBLE · FIXED 2026-09-13

Reported by the user directly: after reading a job description on `web/new-campaign.html`,
clicking through to run CVs for screening failed with an error resembling "rubric [does not]
match[es]" — in practice the backend's generic **"Rubric version failed validation and cannot
be submitted"**, thrown by `POST .../rubric/versions/{v}/submit` and never reaching CV
screening at all.

**Root cause: not the auto-balance feature the user suspected.** `autoBalanceWeights`
(`web/new-campaign.html:576-594`) and `redistributeAfterRemoval` (`:599-613`) — the functions
that keep Must-have + Preferred weights at 100 as a recruiter types, adds or removes a
row — are careful: whichever field changes keeps its new value, the remainder is spread
proportionally across the others, and the *last* field absorbs whatever rounding leaves over,
so the displayed total is always an exact integer 100. Neither of these was the bug.

The actual bug was in two **other**, older code paths that render weights independently
without that redistribution step:

1. `makeReqRow` (`:526-536`), called from `refreshWeightsFromVersion` (`:678-701`) — the very
   first render of Must-have/Preferred rows immediately after JD extraction, seeded from the
   backend's `RubricVersion.weights`. Each row's weight was `Math.round()`-ed on its own. Three
   criteria seeded at 33.33/33.33/33.34 (a perfectly valid 100-point split server-side) each
   *display* as 33, totalling **99** — before the recruiter has touched anything.
2. `applyWeights` (`:624-634`), called by `suggestWeights` (`:636-...`) — the automatic
   AI-weight-suggestion step that runs immediately after `refreshWeightsFromVersion` in the
   real "Read the description" flow (`:1057-1075`). Same independent-rounding bug, so even if
   (1) were fixed alone, this second call could reintroduce a 99/101 total moments later.

Backend behaviour is correct and by design: `RubricVersion.weight_total`/`is_balanced`
(`app/db/models.py:306-312`) require the sum to be within 0.01 of 100 because
`evaluation_service`'s overall-score formula (`(raw/max) * weight`, summed) is only guaranteed
to land on a 0-100 scale when that invariant holds (`app/services/evaluation_service.py:402-
409`) — `submit_version`/`validate_version` (`app/services/rubric_service.py:691-703,770-780`)
correctly refuse an unbalanced rubric rather than silently score against one. The bug was
purely in the two frontend render paths handing the backend a total that was never actually
100 to begin with.

**Fixed:** both `refreshWeightsFromVersion` and `applyWeights` now call the existing
`redistributeAfterRemoval()` after populating rows, which scales the displayed set back to an
exact 100 the same way a manual edit already would. Also hardened the frontend's error
handling (`api()`, both copies in `new-campaign.html`) to include the backend's specific
`detail.errors` (e.g. "weights sum to 99, not 100") in the thrown message, so a future
validation failure of any kind is diagnosable on screen rather than only a generic sentence.

**Verified live end-to-end:** created a real campaign with a 9-requirement job description,
ran "Read the description" (JD extraction → AI weight suggestion, the exact automatic
sequence that used to be able to leave a stale total), and confirmed `weight-total-note` read
"Total: 100 pts" — 12 seeded criteria, values summing exactly to 100 — before any manual edit.
Throwaway campaign deleted after (`DELETE /api/campaigns/{id}` → 204).

- [x] Root cause identified in both render paths, not just the one the user suspected
- [x] `refreshWeightsFromVersion` and `applyWeights` both redistribute to an exact 100
- [x] Backend validation error detail surfaced on screen instead of a generic message
- [x] Verified live against a real JD, exercising both the initial render and the automatic
      AI-suggestion overwrite
- [ ] Not covered by an automated browser test — verify manually before the next demo
      rehearsal (same gap as X28, which this shares a file with)

## X34 — Saved-campaign cards on `start-campaign.html` appearing to show the same resume stage · REPORTED · NOT REPRODUCED, WORKING AS DESIGNED

Reported by the user: several cards under "Your campaigns" showed "Review the shortlist" for
what looked like every card, as if the resume link were not reflecting where they had actually
left off.

**Investigated 2026-09-13 against the live API (44 real campaigns).** `web/assets/campaign-
list.js` calls `window.CampaignSteps.resolve()` (`web/assets/app.js:613-652`) once per card,
which reads that specific campaign's own `status` and, for anything past `DRAFT`, fetches that
campaign's own `/evaluations/runs` to find its own latest run and status — there is no shared
or cached state across cards. Read the rendered page directly (accessibility tree, not a
screenshot) and confirmed each "Review the shortlist" link carries a distinct `run_id` in its
href (12 checked, all different UUIDs; see `web/assets/app.js`'s `href()` building
`leaderboard.html?run_id=...`), and a fresh reload minutes later showed several cards' labels
had changed independently (some "Review the shortlist" → "Review the scoring rules" and vice
versa) as their background assessments progressed — exactly the "where you actually left off"
behaviour B14 asks for, not a shared/stuck value.

**Most likely explanation for the report:** many of the 44 saved campaigns are near-identical
bulk/demo test data ("HSE OFFICER — Coastal Terminal · HSE OFFICER intake" repeated across a
dozen cards, `RC36-01` … `RC36-33`) that were genuinely created and advanced together, so a run
of cards legitimately sharing one label at a given moment is expected, not a bug — combined
with each card briefly showing "Checking saved stage…" while its own resolve() call is still in
flight (`campaign-list.js:19`), which could read as "stuck" mid-load on a slow connection.

- [x] Reproduce against the live API before assuming the resolve logic is wrong — not
      reproduced; each card's href/label is independently correct for its own campaign
- [ ] If this recurs, capture the exact card row (short id) and timestamp rather than a
      general screenshot, so a genuinely stuck/incorrect card (vs. two campaigns that are
      legitimately at the same real stage) can be told apart
- [-] No code change made — nothing in `CampaignSteps.resolve()` reproduced as incorrect this
      session

## X35 — Scanned CVs, no-identity CVs and duplicates were held out of screening instead of being screened and flagged · CLIENT-VISIBLE · FIXED 2026-09-14

On direct instruction from a screenshot of `index.html`'s "Held, and holding up" band: a
photographed/scanned CV (`NO_TEXT_EXTRACTED`) and a CV with no name/email/phone at all
(`INCOMPLETE_CONTENT`, the fully-empty case) were both hard failures — `ProcessingJob.status =
FAILED`, no `Candidate` row created, excluded from every evaluation run
(`evaluation_service._candidates_for_batch` only selects `COMPLETED`/`DUPLICATE` jobs). The only
offered next step was a manual one ("Send for scanning" / "Read by hand"). A duplicate
application (`DuplicateType.SAME_CANDIDATE_EMAIL/PHONE/NAME`) was already screened and already
auto-attached to the existing `Candidate` record — i.e. already auto-merged — but the UI still
showed a "Merge them" button implying pending manual work.

**Fixed:**
- `app/core/document_intake.py::extract_document` — text under `MIN_TEXT_CHARS` (even after
  OCR) no longer raises `DocumentRejected(NO_TEXT_EXTRACTED, ...)`. It returns the
  `ExtractedDocument` with a new `low_text: bool` flag instead.
- `app/services/processing_service.py::process_job` — `low_text` sets
  `requires_review=True` + `error_code=NO_TEXT_EXTRACTED` and appends a plain-English note,
  but processing continues. The `identity.is_empty` case (previously an early `FAILED` return)
  now falls through to the same `Candidate`-creation path as the existing partial-identity case
  (a name but no email/phone), with its own note and `error_code=INCOMPLETE_CONTENT`. Both
  candidates are created (full_name may be `""`) and reach evaluation like any other. The
  duplicate branch's `error_message`/`requires_review` are now appended/OR'd rather than
  overwritten, so a file that is both low-text (or no-identity) *and* a duplicate keeps every
  flag rather than the duplicate message silently replacing it.
- `app/core/analytics.py::kpis()` — new `exceptions.screened_by_reason`: a `by_reason`-shaped
  breakdown, but over jobs that are flagged (`requires_review`) and NOT `FAILED` — i.e. screened
  anyway. `by_reason` (the existing field) is unchanged in shape but now only ever contains
  genuinely blocking codes, since `NO_TEXT_EXTRACTED`/`INCOMPLETE_CONTENT` can no longer produce
  a `FAILED` job on their own.
- `app/api/compat.py::serialize_run` — `held_files` narrowed to `status == FAILED` only (true
  holds, unchanged shape: `reason`/`action`/`can_retry`). New `flagged_files` list for
  `requires_review` jobs that aren't `FAILED` (`note` + `merged: bool`, no action/retry — there
  is nothing to do).
- `web/index.html` — the "Held, and holding up" band's `HELD_WORDS` map (action-required, from
  `by_reason`) dropped `NO_TEXT_EXTRACTED`/`INCOMPLETE_CONTENT`; a new `FLAG_WORDS` map renders
  `screened_by_reason` as plain rows with a "Flagged" tag, no button. Duplicates render as
  "…automatically merged into the existing profile(s)" with a "Merged" tag, no button.
- `web/campaigns.html` — per-campaign card's held-files block reads the new `flagged_files`
  list separately (new `.flagged` note styling, `--ink-3`), never offering a retry link or an
  action for a file that was already screened.
- `app/api/compat.py::extract_text` (`POST /api/documents/extract-text`, used to read a **job
  description** file into the compose box, not a CV) explicitly rejects `extracted.low_text`
  itself with the same 422 as before. This endpoint has no screening/flagging concept to fall
  back to — a JD that cannot be read has nothing downstream to flag it against — so it keeps the
  old reject-at-422 behaviour on direct purpose, not an oversight.

Tests: `tests/test_processing.py` (renamed/rewritten:
`test_scanned_pdf_with_no_text_is_still_screened_and_flagged`,
`test_document_with_no_identity_completes_but_is_flagged`, plus the mixed-batch and
skills-line-name tests updated for the new status split), `tests/test_document_quality.py`
(the two OCR-off/broken-OCR tests now assert `extracted.low_text` instead of a raised
exception), `tests/test_analytics.py` (new `test_scanned_cv_is_screened_and_flagged_not_held`;
existing fixture's forced exception switched from a blank scan to a genuinely corrupt file, so
it still exercises `files_held`/`by_reason` for a real hard failure), `tests/
test_frontend_integration.py` (`test_scanned_files_are_flagged_not_held_with_a_plain_english_reason`,
renamed and rewritten from `test_unreadable_files_are_held_with_a_plain_english_reason`). Full
suite: 766 passed, 6 skipped, 9 failed — the 9 are the pre-existing X32 Node-harness failures,
unrelated. Not yet browser-verified against a freshly restarted API process in this session (see
`docs/SESSION-STATE.md`) — the shared dev server on port 8000 belongs to another session and was
not restarted; the *frontend* half (no fake action buttons, real "automatically merged" copy)
was confirmed live against that server's still-old backend responses.

**2026-09-14 update:** this session did restart the API process (see `X39`) as part of demo
prep, and separately confirmed the X35 backend behaviour live end-to-end while building the
Process Operator demo campaign — a scanned CV with a genuinely blank extracted name completed
normally and was flagged `requires_review=True` rather than held or crashing.

## X36 — `lifecycle_service.py` self-commits, violating the routes-commit convention · INTERNAL · FOUND, ACCEPTED NOT FIXED

Found 2026-09-14 auditing the demo path's backend modules. `CLAUDE.md`'s stated convention is
"Services `db.add()` and `db.flush()`. Routes commit. No service commits itself." Three
functions in `app/services/lifecycle_service.py` violate it: `create_user` (line 81),
`transition` (line 380), and `record_manager_review` (line 472) all call `db.commit()`
themselves.

This is not just a style violation in `record_manager_review`: it calls `db.commit()` to persist
the `ManagerReview` row and its audit event at line 472, then calls `transition(...)` afterward,
which does its own separate `db.add()`/`db.flush()`/`record_audit()`/`db.commit()`. A failure in
that second `transition()` call (an invalid state move) would leave the manager review
permanently committed with no corresponding lifecycle transition — a real partial-write risk,
not a cosmetic one.

**Accepted 2026-09-14 as a known limitation, not fixed for demo day.** This is a backend
refactor (moving three commits up into their callers, and confirming every caller of 
`create_user`/`transition`/`record_manager_review` still commits correctly afterward) that 
touches a heavily-used, correctness-critical service file. Changing it hours before a client 
session carries more risk than the defect itself. Refactoring is safer as a post-demo task 
with its own regression tests. Risk is documented and accepted.

- [ ] Move the three `db.commit()` calls out of `lifecycle_service.py` and into their route
      callers in `app/api/lifecycle.py` — post-demo task
- [ ] Add a regression test asserting a failed `transition()` after a successful
      `record_manager_review()` does not leave an orphaned committed review row

## X37 — `decisions.html` and `candidate.html` silently showed fabricated data on any load failure · CLIENT-VISIBLE · FIXED 2026-09-14

Found 2026-09-14 auditing the demo path. `web/decisions.html`'s `load()` function's `catch`
block (around line 531) left the page's pre-existing static HTML (ten fake shortlist rows —
"Haitham Al-Otaibi", "Reem Al-Suwaidi", etc.) on screen if any of its live API calls failed,
only changing the headline text to note "What follows is the shipped example." Separately,
`web/candidate.html`'s `renderUnavailable()` displayed the fabricated hero card
(name "Haitham Al-Otaibi", score "91") on any evaluation fetch failure.

**Fixed 2026-09-14:** `decisions.html` now clears the rows on live-fetch failure and renders
"Live decisions could not be loaded. No candidate data is shown." `candidate.html`'s
`renderUnavailable()` now neutralises the hero card with neutral content (name "Not available",
score "—") instead of the fabricated candidate. Candidate.html's twin defect had never been 
logged separately; combining them here prevents accidental re-discovery later.

- [x] `decisions.html` clears rows and shows honest failure message on API failure
- [x] `candidate.html` shows neutral hero card instead of fabricated candidate on API failure
- [x] Browser-verified live against real API failures (network disconnect, slow response)

## X38 — Dead/unreachable code in `app/api/interviews.py`'s calendar-invite path · INTERNAL · FOUND, NOT FIXED

Found 2026-09-14 auditing the demo path. `app/api/interviews.py`'s `_send_calendar_invite`
has an unreachable `return invite.simulated, invite.detail` at line 192, after the real
`return get_calendar_adapter()...` on line 187 already returns. Harmless — dead code only,
never executed — but worth a cheap cleanup pass post-demo.

- [ ] Remove the unreachable line

## X39 — Start Campaign's saved-campaign cards froze at "Review the shortlist" for any candidate past the shortlist stage · CLIENT-VISIBLE · FIXED 2026-09-14

Found while seeding today's two demo campaigns: `web/assets/app.js`'s `CampaignSteps.next()`
(the "coarse rule," per its own comment) only maps `Campaign.status` through `REVIEW` →
`'shortlist'`. Everything past shortlisting — handoff, interview, HR/budget approval, offer,
hired — lives on `CandidateLifecycle`, a separate per-candidate record `CampaignSteps` never
read. The result: a saved-campaign card on `start-campaign.html` read "Review the shortlist"
forever, even for Campaign B whose one candidate already had an offer sent. A client could
reasonably ask "didn't we already interview someone here?" against a card that looks frozen at
day one.

**Fixed:** `CampaignSteps.resolve()` now does one additional read, `GET
/api/campaigns/{id}/lifecycle`, whenever the coarse rule lands on `'shortlist'` — the same
per-campaign-detail-read pattern the file's own comment already accepted for the setup-phase
steps ("the number of campaigns is unbounded... the stored status already separates them"). It
picks the furthest-progressed candidate by a rank table mirroring `LifecycleStatus`'s own
declaration order in `app/db/models.py` (the same "declared stage sequence" convention `X11`
established for the funnel), and overrides the label/destination accordingly (e.g. "Interview
scheduled" → `interview.html`, "Offer sent, awaiting response" → `offer.html`). A campaign with
no lifecycle rows past shortlisting (the other 45 pre-existing dev/test campaigns) is unaffected
— the lifecycle read returns nothing rankable and the original "Review the shortlist" label
stands, unchanged.

Asset cache-busting version bumps (`app.js?v=16→17`, `campaign-list.js?v=16→17`, first-time
`journey.js?v=2`) shipped alongside this fix — a stale cached copy of the old logic served wrong
data during this session's own browser verification, caught only by an explicit no-store
cache-bypass check.

- [x] `CampaignSteps.resolve()` reads campaign lifecycle state and overrides the shortlist-stage
      label/destination when any candidate has progressed further
- [x] Verified live: Campaign A (`97d3d161-…`) now reads "Interview scheduled" linking to
      `interview.html?campaign=97d3d161-…`; Campaign B (`ddc1098a-…`) reads "Offer sent,
      awaiting response" linking to `offer.html?campaign=ddc1098a-…`
- [x] Verified the other 45 pre-existing campaigns' labels are unchanged (spot-checked several
      `DRAFT`/`REVIEW` cards still read their original setup-phase labels)
- [x] `tests/browser/test_campaign_resume.py` (which exercises `CampaignSteps.resolve()`
      directly) still passes unchanged — the new lifecycle read is wrapped in a try/catch that
      falls through to the original behaviour when the fake test harness's `read()` throws on an
      unrecognized path
- [ ] Not covered by a new automated test asserting the override itself (only the pre-existing
      resume tests were re-run) — verify manually before any future demo rehearsal

## X40 — Missing COM apartment initialization in `calendar_adapter.py` real-send calls · INTERNAL · FOUND, FIXED 2026-09-14

Found 2026-09-14 during real Outlook calendar integration verification. `app/core/
calendar_adapter.py`'s `OutlookCalendarAdapter.send_invite()` calls COM methods directly
(`Outlook.Application.GetNamespace().GetDefaultFolder()...`) without per-thread apartment
initialization. FastAPI runs sync request handlers on worker threads, and COM requires
`pythoncom.CoInitialize()` on each thread before any COM calls are made, or calls fail with
marshalling errors on multithreaded servers.

**Fixed:** `send_invite()` is now wrapped in `pythoncom.CoInitialize()` /
`CoUninitialize()` guards, bracketing the real COM calls. Standalone/single-threaded
environments (like `uvicorn --workers=1`) would not have failed, but a production deployment
with multiple workers would have. This is a genuine correctness bug, not a rare edge case.

Verification: direct COM test on this machine (2026-09-14, 08:38:59 UTC) — real calendar
event created and confirmed present in Outlook default folder, then deleted as cleanup.

- [x] `pythoncom.CoInitialize()/CoUninitialize()` guard added around the real COM calls
- [x] Direct COM test against real signed-in Outlook account — worked without error
- [x] No new automated test — the real COM call is not exercisable in a unit-test double

## X41 — Three mail routes had no allowlist guard before calling the mail adapter · INTERNAL · FOUND, FIXED 2026-09-14

Found 2026-09-14 during mail integration security audit. `app/api/messages.py`,
`app/api/reports.py`, and `app/api/offers.py` each call the mail adapter with an address
supplied directly from the UI or derived from stored data, with no guard preventing a real
send to any address once `EMAIL_BACKEND=outlook` is enabled. A recruiter typing any email
address in a UI field would have caused a real email to be sent to that person without
explicit approval or an allowlist check.

**Fixed:** centralized approved-recipient allowlist in `app/core/mail_guard.py`
(`APPROVED_MAIL_RECIPIENTS` set + `ensure_approved_mail_recipients()` function). All three
routes now call the guard immediately before invoking the mail adapter. Guard is a no-op
unless `email_backend == "outlook"`, so simulated sends stay unrestricted. Allowlist is the
single source of truth; if the list changes, one place changes it.

Verification: attempt to send to non-approved address `abdulrahman.alsada@example.com`
(a candidate's CV-extracted email from seeded data) returned HTTP 422 with detail naming the
rejection. Same-moment verification of an approved address in the list (subhadeep.m@
protivitiglobal.in) sent successfully and confirmed in Outlook Sent Items.

- [x] Centralized allowlist created and guarded
- [x] All three previously-unguarded routes (`messages.py`, `reports.py`, `offers.py`) call
      the guard
- [x] Frontend pre-fills with approved addresses and offers a datalist of colleagues by name
      (`web/comms.html`, `web/decisions.html`)
- [x] Live verification: rejected address returns 422; approved address sends successfully

## X42 — Send-mode badges hardcoded, hiding real mail/calendar sends · CLIENT-VISIBLE · FIXED 2026-09-14

Found during 2026-09-14 verification: several pages displayed a hardcoded "SIMULATED — INTEGRATION PENDING" badge next to buttons that now actually transmit real mail and calendar invites (when `email_backend`/`calendar_backend` are set to `"outlook"`). A presenter reading the badge as "simulated" could click a button and send a real email without knowing. Also found at the same time: `web/comms.html` loaded its own inline script before loading `assets/app.js`, so the shared helper `window.__r360ApplySendBadge` was undefined when the page tried to call it.

**Fixed:** 
- New endpoint `GET /api/config/send-modes` (file `app/api/config.py`, registered in `app/main.py`) returns only `{"email_backend": ..., "calendar_backend": ...}` — no secrets, no sender address, no credentials. Test `test_send_modes_exposes_nothing_else` asserts exactly those two keys and never leaks extra data.
- Badges on `comms.html`, `interview.html`, and `offer.html` now fetch from this endpoint via `window.__r360ApplySendBadge()` helper in `web/assets/app.js`. Badge text reflects the actual backend: `"SENDS FOR REAL — OUTLOOK LIVE"` when mail/calendar backends are outlook; `"RECORDED ONLY"` when simulated. Each page also adds explanatory notes (e.g., "email transmits, SMS and phone note never do" for comms.html).
- Failure branch deliberately fails loud: if the endpoint cannot be reached, badge reads `"SEND MODE UNKNOWN"` with a cautionary note `"Could not confirm how this environment sends. Treat this action as if it may transmit for real."` Never defaults to claiming "simulated."
- Script-order bug fixed: `web/comms.html` now loads `assets/app.js` before its own inline script, so the shared helper is defined when called.
- Reused existing CSS `.tag` class for badges; added no new component.

Verified 2026-09-14 on both `simulated` and `outlook` backend configurations.

- [x] `GET /api/config/send-modes` endpoint created and secured to expose only backend names
- [x] `test_send_modes_exposes_nothing_else` confirms no credential/identity leaks
- [x] Badges on `comms.html`, `interview.html`, `offer.html` wired to the endpoint
- [x] `web/comms.html` script-load order fixed
- [x] Failure case deliberately shows `SEND MODE UNKNOWN` rather than defaulting to safe

## X43 — Grammar and copy fixes found during verification · FIXED 2026-09-14

Found while reverifying the demo path end-to-end:
- `web/assets/campaign-list.js`: "1 vacancies" → "1 vacancy" (singular/plural).
- `web/assets/journey.js`: "1 offers recorded as sent" → "1 offer recorded as sent".
- `web/index.html`, Today page: "Nothing is held" directly above "Held back for a person to read" about the same data — two contradictory uses of "held" on the same screen. Rewrote to "Screened, then flagged for a person to read."
- `web/start-campaign.html`, footnote: claimed everything was simulated, which became false once real Outlook sending was enabled. Reworded to state that send mode depends on configuration and that each page declares its own before you act.

- [x] Singular/plural fixed on the count display
- [x] Contradictory "held" meanings resolved on the Today page
- [x] Outdated simulation claim removed from setup footnote
- [x] Browser-verified before demo

## X44 — Offer recorded as sent when the recipient was rejected · CLIENT-VISIBLE · FIXED 2026-09-14

`app/api/offers.py` transitioned the candidate to `OFFER_SENT` **before** calling
`ensure_approved_mail_recipients`. When the allowlist rejected the address, the 422
left the candidate reading "Offer with the candidate" with no letter ever sent — the
record claimed a send that did not happen, which is what the repository's own audit
rules forbid. Found live: an offer showed `OFFER_SENT` while the only send attempt
had returned 422.

Fixed by moving the guard above the transition. Regression test:
`test_a_rejected_recipient_leaves_the_candidate_not_sent`.

## X45 — Offer letter could never be sent in real Outlook mode · CLIENT-VISIBLE · FIXED 2026-09-14

`OfferSendIn` carried only `actor_id`, and the recipient was hard-wired to
`candidate.email`. Every demo candidate address is CV-extracted and therefore never on
the allowlist, so with `EMAIL_BACKEND=outlook` the offer was unsendable. `comms.html`
already solved this with a proxy picker; the offer screen had none.

Fixed by adding an optional `recipient` to `OfferSendIn` (blank keeps the old
behaviour) and a matching picker in the offer send fold. Two tests added.

## X46 — Templated messages unsendable to a candidate whose name did not extract · CLIENT-VISIBLE · FIXED 2026-09-14

`web/comms.html` treated `candidate_name` as always known, so it rendered no input for
it. For a `requires_review` CV with a blank name the server answered "Not filled in
yet: candidate_name" and there was nowhere to type it — a dead end on exactly the
candidate the demo is built to showcase. Unknown placeholders such as `message` did get
an input; only `candidate_name` was excluded.

Fixed by offering the field when the selected candidate has no name, and rebuilding the
extra fields on a candidate change as well as a template change.

## X47 — Previous stage from the shortlist landed on a page nobody had visited · CLIENT-VISIBLE · FIXED 2026-09-14

The stage list in `web/assets/app.js` placed `discover.html` between "Upload CVs" and
"Candidate shortlist". The real flow never goes there: `new-campaign.html` redirects
straight to `leaderboard.html` after scoring. Going back from the shortlist therefore
landed on `discover.html`, whose heading reads "Paste a SharePoint link or a folder
path" — reported as a ghost page. Nothing else in the app linked to it, and the
folder-import it offers is already available inline on the CVs step.

Fixed by removing it from the linear chain. Back now goes to Upload CVs.

## X48 — Stage ticks tracked pages visited, not work completed · CLIENT-VISIBLE · FIXED 2026-09-14

A stage only ticked when the user clicked "Mark this page done". Genuinely finished
stages looked untouched. Worse, the `campaign-changed` handler reassigned
`doneStages` from browser storage and repainted, so any tick not stored there was
wiped — and the campaign selector fires that event on load.

Fixed by deriving completion from the API (rubric approved, run completed, candidates
present, lifecycle reached, interviews, messages, offers) and re-deriving after the
campaign changes. The stored map remains a manual override for stages the backend
cannot know about. Verified discriminating: a campaign with CVs but no lifecycle shows
six ticks; the fully-progressed campaign shows fourteen.

## X49 — JD library button used a light-background style on the maroon banner · COSMETIC · FIXED 2026-09-14

`start-campaign.html` used a bare `.ghost`, which paints a surface-coloured pill. On
the maroon arch it read as a stray white blob beside the cream primary. The
`.ghost.onmaroon` variant already existed for exactly this case.

Fixed by applying it and matching the primary radius and padding.

## X50 — Inconsistent asset cache versions hid fixes behind stale JavaScript · INTERNAL · FIXED 2026-09-14

Eighteen pages loaded `assets/app.js` with no version string, two used `?v=17`, one
`?v=20`. A changed `app.js` was therefore served stale on most pages, which is the real
cause behind the runbook repeated warning to hard-reload before presenting. It cost
real debugging time during this session.

Fixed by normalising every page to one version and bumping the service-worker cache.

## X51 — A live-built campaign cannot reach Review and Hire by clicking · CLIENT-VISIBLE · FOUND, NOT FIXED

`POST /lifecycle/{candidate_id}/enter` moves a shortlisted candidate into the hiring
process, and **no page in `web/` calls it** — only `scripts/seed_demo.py` does. A
campaign created live in the browser therefore dead-ends at "Decisions and export";
Manager review, Interviews, Approvals and Offers all stay empty.

This is why the runbook says to switch to a pre-seeded campaign for the Review and Hire
segment. The 2026-09-14 end-to-end run got past it by calling the endpoint directly.

Not fixed: it needs a product decision about where the control belongs, most naturally a
"Send to hiring manager" action on the Decisions page beside the disposition buttons.

## X52 — Acting-person change is ignored once a row is open · INTERNAL · FOUND, NOT FIXED

`web/handoff.html` reads the acting person when a candidate row is expanded. Changing
the dropdown afterwards does not update it, so the action posts the previous actor and
fails with "Your role does not allow you to move a candidate to…" — a message about
permissions when the real problem is a stale selection. Workaround: set the acting
person before opening a row, or reload.

## X53 — Shortlist header shows a placeholder count before data arrives · COSMETIC · FOUND, NOT FIXED

`decisions.html` renders "The shortlist 24" from static markup until the live count
replaces it, roughly a second later. Harmless if the page is allowed to settle, but a
client watching a three-candidate campaign can see "24". Documented in the demo guide
as a reason to wait for the page to settle before narrating.

## X54 — Hiring-manager shortlist email carried no report attachment · CLIENT-VISIBLE · FIXED 2026-09-14

`POST /api/campaigns/{id}/reports/email-to-hiring-manager` sent a plain-text summary
only. The hiring manager received a one-line-per-candidate list with no way to open a
candidate's actual Candidate 360 assessment. `app/api/exports.py` already built the
same "Shortlisted Candidates PDF" zip for the download route
(`GET /reports.zip`) — the email route did not reuse it.

Fixed by extracting the zip-building loop into `build_shortlist_zip(db, campaign,
format="pdf")` in `app/api/exports.py`, called by both `shortlisted_reports_zip` and
the email route in `app/api/reports.py`. `MailAdapter.send()` gained an optional
`attachments: list[tuple[str, bytes]] | None` parameter; `OutlookMailAdapter` writes
each attachment to a temp file and attaches by path (Outlook COM cannot attach from
bytes), cleaned up in `finally`. A campaign with decided-but-not-shortlisted
candidates still sends the email, with zero attachments — the zip helper returns
`None` rather than raising, so the email path does not turn into a 422.

## X55 — `cv-viewer.html` was a navigation dead end · FIXED 2026-09-14

`web/cv-viewer.html` carried no `<nav>` and no back control. `candidate.html:828` opens
it in the SAME tab, so a user who opened a CV could only leave with the browser's own
back button. Every other page except `login.html` (pre-auth, correct) has the shared
nav with `Start Campaign -> start-campaign.html`, verified across all 23 files.

Fixed with a `← Back` link in the viewer's top bar: `history.back()` when there is
history (returns to the exact candidate), falling back to `start-campaign.html` for a
pasted or bookmarked link.

Root note, not fixed: the nav is copy-pasted verbatim into all 23 HTML files rather
than sourced from one partial. That is why a page could silently miss it. A shared
nav is the real fix and is deliberately deferred — it is a refactor, not a demo blocker.

## X56 — FinOps run table reads $0.0000 although spend is recorded · FIXED 2026-09-14 (cause 2 still open)

Reported as "cost is always zero". The page is not broken and cost IS accumulating.
Measured against `tis_app.db` on 2026-09-14 via `app/api/developer.py::metrics`:

    llm_call_count 21 · total_tokens 28,219 · total_estimated_cost_usd $0.1413
    cost_per_candidate_usd $0.011778 · projected_cost_10000_cvs_usd $117.78
    cost_configured true ($2.50 in / $10.00 out per 1M, bundled Azure fallback)
    by call_type: jd_extraction 12 / $0.0563 · weight_suggestion 6 / $0.0722
                  screening 3 / $0.0128

Three real causes of the zero-looking figures:

1. **Only 3 of 21 `llm_call_logs` rows carry a `run_id`.** `llm_usage.track()` is opened
   with `run_id` only in `app/services/evaluation_service.py:904`; the JD-extraction and
   weight-suggestion contexts (`requirement_service.py:27`, `rubric_service.py:583`) pass
   `campaign_id` only. `app/api/developer.py:46` buckets by `run_id`, so 18 real calls
   land in no run row. Three of four runs therefore show 0 calls / $0.0000, and the
   page's headline tile (`average cost per run`) reads $0.0032.
2. **The screening LLM step fails silently.** `evaluation_service.py:832-840` catches
   every exception from `refine_criterion_scores`, logs a warning and keeps the
   deterministic scores. `scoring_agent.py:267-272` also returns before any model call
   when no criterion is refinable. Both produce a completed run with zero LLM cost, and
   nothing distinguishes "the model was not needed" from "the model call broke".
3. **`DATABASE_URL` defaults to `sqlite:///./tis_app.db`, relative to the process CWD**
   (`app/db/session.py:18`). Start uvicorn from any other directory and a new empty DB
   is created, at which point the FinOps page genuinely is all zeros. This is the
   likeliest cause of a completely blank reading.

Also cosmetic: `campaign_costs` returns 12 campaign IDs while only 4 campaigns exist —
8 rows point at deleted campaigns and render as bare UUIDs.

**Fixed 2026-09-14 for causes (1) and (3-adjacent cosmetic).**

Threading `run_id` into the JD-extraction and weight-suggestion `track()` calls was
rejected: those calls happen at campaign-setup time, before any `EvaluationRun` row
exists, so there is no run to attribute them to. The run rows were never wrong - they
really did make no LLM calls. The page was wrong, because it showed only run-attributed
spend and hid the rest.

- `app/api/developer.py` now reports `setup_call_count`, `setup_total_tokens` and
  `setup_estimated_cost_usd` for every call with no `run_id`, and `web/developer.html`
  prints that under the average-spend tile. The run rows plus the setup figure now
  reconcile exactly to `total_estimated_cost_usd`.
- Rows for deleted campaigns are named "Deleted campaign" rather than rendered as a
  bare UUID. They are deliberately NOT dropped: that spend really happened, and
  removing the rows would stop `campaign_costs` summing to the total.
- Run rows and campaign rows carry `campaign_name`, so the table reads in words.

Measured against the real `tis_app.db` after the fix: $0.1413 total = $0.0128 across
runs + $0.1285 across 18 campaign-setup calls. Before the fix, $0.1285 of $0.1413 was
invisible on the page.

Covered by `tests/test_developer_metrics.py::test_campaign_setup_spend_is_reported_and_reconciles`
and `::test_spend_on_a_deleted_campaign_is_named_not_dropped`.

**Still open - cause (2).** `evaluation_service.py:832-840` swallows every exception
from `refine_criterion_scores` and keeps the deterministic scores, so a completed run
with zero LLM cost cannot be told apart from a run where the model call broke. Fixing
that changes run behaviour - a run that completes today could start reporting a failure -
so it needs a decision, not a quick patch.

---

## X57 — `CANDIDATE_HIRED` audit action was defined and labelled but never emitted · FIXED 2026-09-14

Requested as "build the backend for handoffs/interviews/approvals/offer-and-hire" on the
premise that none of it existed. It does: `app/api/handoff.py`, `app/api/interviews.py`,
`app/api/approvals.py`, `app/api/offers.py` are complete, registered in `app/main.py`, and
`web/handoff.html` / `web/interview.html` / `web/approvals.html` (via `journey.js`) /
`web/offer.html` (via `journey.js`) already call them. Verified in the browser this session
against a live campaign on `consolidated`: offer.html loaded real campaigns and lifecycle
rows from the running API with no stub data. Confirmed with `tests/test_handoff_api.py`,
`test_interviews_api.py`, `test_approvals_api.py`, `test_offers_api.py`, `test_lifecycle.py`
— 138 passed this session. "Hire" has no dedicated screen/endpoint by design: it is the
generic `POST .../lifecycle/{candidate_id}/transition` to `HIRED`, exactly like `CLOSED`.

One real gap found while verifying: `AuditAction.CANDIDATE_HIRED` existed in the enum
(`app/db/models.py`) and had a label in `web/audit.html:321`, but `lifecycle_service.py`'s
`_write()` action-mapping dict had no entry for `LifecycleStatus.HIRED`, so a hire was
recorded as the generic `STATUS_CHANGED` instead of a distinct, filterable action.

- [x] Fixed — `app/services/lifecycle_service.py`, added
      `LifecycleStatus.HIRED: AuditAction.CANDIDATE_HIRED` to the action map
- [x] Matching label added to `ACTION_WORDS` in `app/api/decisions.py`
- [x] Regression test — `tests/test_lifecycle.py`, asserts the last audit event on a hired
      candidate carries `AuditAction.CANDIDATE_HIRED`, not `STATUS_CHANGED`. 37 passed.

---

## X58 — Nothing in the UI ever calls `lifecycle/{id}/enter`, so shortlisted candidates never reach the handoff queue · CLIENT-VISIBLE · FIXED 2026-09-15

Asked to verify B01 step 4 (hiring-manager handoff) end to end. Confirmed the backend
(`app/api/handoff.py`, `POST .../lifecycle/{id}/send-to-manager` in `app/api/lifecycle.py`)
and the frontend (`web/handoff.html`) are both built and correctly wired to each other —
proved this by entering a real shortlisted candidate into the lifecycle directly via the API
(`ea32958d-db58-43a1-895e-3016b7389370` / `0026170d-39b1-4877-a0a5-8665fda8cb55`), watching
it appear under "Ready to send", sending it to a hiring manager through the actual
`web/handoff.html` form, and confirming both the lifecycle timeline
(`SHORTLISTED` → `WITH_HIRING_MANAGER`, note text preserved) and `audit_events`
(`STATUS_CHANGED` then `SENT_TO_HIRING_MANAGER`) recorded it, with plain-word labels on
`web/audit.html`.

The gap: `lifecycle_service.enter()` (`app/services/lifecycle_service.py:161`) requires a
candidate to already carry a `SHORTLIST`/`INTERVIEW` disposition, and is only reachable
through `POST /api/campaigns/{id}/lifecycle/{candidate_id}/enter`
(`app/api/lifecycle.py:359`). Grepped every `web/*.html` file for a caller of that endpoint —
none exists. `candidate.html` sets the `SHORTLIST` disposition but never calls `/enter`.
Concretely: a recruiter can shortlist a candidate today and it will never show up in
`handoff.html`'s queue, or anywhere else the lifecycle drives, unless something calls
`/enter` for it first — which nothing in the product does. The three campaigns that showed
real data in the queue during this session's testing only had rows because a prior session
or seed script called the API directly.

- [ ] Decide where the trigger belongs: automatic on the `SHORTLIST`/`INTERVIEW` disposition
      write (`app/services/disposition_service.py`), or an explicit recruiter action (e.g. an
      "Add to hiring process" button on `candidate.html` or the shortlist list view). This is
      a product-flow decision, not a bug fix — raised with the user, not resolved this session.
- [ ] Once decided, wire the call and add a regression test asserting a freshly shortlisted
      candidate appears in `GET .../handoff/queue` without a manual API call.

2026-09-15: `candidate.html`'s disposition buttons were carried over verbatim into the new
`web/candidate-assessment.html` (see B15/B16/B18 notes and `DECISIONS.md`) — same
POST-only call to `/disposition`, still no call to `/enter`. This defect now applies to
`candidate-assessment.html`'s Overview tab instead of (or in addition to, while
`candidate.html` still exists unlinked) the old page. Not fixed as part of that merge —
still a product-flow decision, not a bug fix.

**Fixed 2026-09-15, later, on direct instruction.** User hit this exact gap while rehearsing
the demo journey ("till decisions and export part i have done everything, after that from
handoffs no data is visible") — the product decision this defect was left open for is now
made: entry is automatic on the `SHORTLIST` write, not a separate recruiter action. Both
current shortlist-setting call sites now also call
`POST .../lifecycle/{candidate_id}/enter?actor_id=<signed-in user's real id, window.__r360Me.id>`
immediately after a successful `SHORTLIST` disposition:

- `web/decisions.html`'s `#d-rows button[data-act]` click handler
- `web/candidate.html`'s `#c-actions [data-disposition]` click handler

Both are safe by construction, not just in practice: `lifecycle_service.enter()`
(`app/services/lifecycle_service.py:161`) only accepts a candidate whose disposition is
already `SHORTLIST`/`INTERVIEW` — true at the call site, since the disposition write just
above it is what sets that — and is idempotent (returns the existing row if already
entered), so calling it on every `SHORTLIST` click is never wrong, whether or not the
candidate was somehow already in the lifecycle. A failure on this second call (network, or
any other reason) is swallowed rather than surfacing as an error on top of a disposition
that already saved — the primary decision is never undone by a secondary side effect
failing. `HOLD`/`REJECT` do not call `/enter` (matching `enter()`'s own precondition).
`web/candidate-assessment.html` (unlinked, per the B15/B16/B18 revert) was not touched —
out of scope while it stays unlinked from navigation.

Browser-verified live against the real `HSE Officer · Coastal Terminal` campaign: clicked
Shortlist on an undecided candidate on `decisions.html`, confirmed both
`POST .../disposition → 201` and the follow-up `POST .../lifecycle/{id}/enter?actor_id=...
→ 201` in the network log, then loaded `handoff.html` for the same campaign and confirmed
"1 candidate in this campaign's hiring process" / "Ready to send: 1" — previously empty.
`node --check` on both files' extracted inline scripts passed. No backend change; no plan
ID other than `X58`/`B01` itself, since the backend and screens were already built and
audited.

- [x] Trigger decided: automatic on the `SHORTLIST` disposition write, not a separate
      recruiter action — direct instruction, 2026-09-15.
- [x] Wired on both `decisions.html` and `candidate.html`; browser-verified a freshly
      shortlisted candidate reaches `GET .../handoff/queue`.
- [ ] No automated regression test added (`web/*.html` has no test harness in this repo, per
      existing convention — browser-verified only). Consider one at the `app/**` layer
      instead if this needs a permanent regression guard: e.g. an integration test asserting
      the *screens'* documented call sequence, or leave as browser-verified per convention.

---

## X59 — The floating campaign-stage nav bar silently didn't render on `candidate-assessment.html` · FOUND AND FIXED

The B15/B16/B18 merge of `leaderboard.html`/`candidate.html`/`compare.html` into
`web/candidate-assessment.html` (2026-09-15) never updated `web/assets/app.js`'s campaign
journey bar (the floating "Set up · Shortlist · Handoff · …" strip and its "Mark this page
done" button, `B14`/`B08`). That script derives which stage a page belongs to from
`location.pathname`'s filename (`page.replace('.html','')`), with explicit rewrites for a
couple of legacy names (`rubric`→`rules`, `leaderboard`→`shortlist`). `candidate-assessment`
matched none of the known stage ids, so `stages.findIndex(...)` returned `-1` and the whole
IIFE returned early — the entire bar, including the done button, never appeared on the one
page the shortlist/compare/decide workflow now actually lives on.

- [x] `web/assets/app.js`: added `if (current === 'candidate-assessment') current = 'shortlist';`
      alongside the existing `leaderboard` rewrite, and repointed the `shortlist` stage's own
      url from `leaderboard.html` to `candidate-assessment.html` (the page that stage now
      actually resolves to). Browser-verified live: the bar (six stops, current-stage red dot,
      "Set up" green tick, "Mark this page done" button) renders correctly on
      `candidate-assessment.html` against a real campaign.
- [x] Bumped the `assets/app.js?v=` cache-busting suffix (33→34) across all 22 `web/*.html`
      pages that load it — the static-file server this project runs against sends no
      cache-control headers, so without the bump the browser kept serving the pre-fix `app.js`
      from its own HTTP cache even after the file changed on disk. Not a defect in the fix
      itself, but worth recording: any future `app.js` edit needs the same version bump to
      actually reach a browser that already loaded the page once.

## X60 — Campaign-card "Review shortlist" deep link still sent recruiters to the old `leaderboard.html` · CLIENT-VISIBLE · FOUND AND FIXED 2026-09-15

The B15/B16/B18 merge (X59 above) repointed the journey nav's `shortlist` stage and the
static CTAs on `index.html`/`campaigns.html`/`start-campaign.html` to
`candidate-assessment.html`, but missed a second, separate URL builder:
`web/assets/app.js`'s `href(campaign, run, step)` (~line 825, the function that computes the
"next step" link shown on a campaign's Today/Campaigns card once it reaches `REVIEW` status)
still had `if (id === 'shortlist' ...) return 'leaderboard.html?run_id=' + ...`. Reported by
the user: opening a campaign's shortlist from its card landed on the pre-merge ranked-list
page (`leaderboard.html`), which still links each row on to the old standalone
`candidate.html?evaluation=...` — none of the merged compare/decide-in-place UI was visible.

- [x] `web/assets/app.js:833`: `leaderboard.html?run_id=` → `candidate-assessment.html?run_id=`
      (that page already reads `run_id` from the query string — `web/candidate-assessment.html:1210`).
      `web/leaderboard.html`/`candidate.html`/`compare.html` remain on disk, superseded but
      unlinked from any nav/CTA, per the B15 note in `00-MASTER-BACKLOG.md`.
- [x] Bumped `assets/app.js?v=` 34→35 across all `web/*.html` pages (same cache-busting
      requirement X59 documented).

## X61 — Candidate-assessment checkbox selection auto-opened compare before the recruiter finished picking · CLIENT-VISIBLE · FOUND AND FIXED 2026-09-15

`web/candidate-assessment.html`'s checkbox `change` handler (added with B16's compare-in-tab
work, see `00-MASTER-BACKLOG.md`) called `openCompareInTab()` the instant a *second* checkbox
was checked. A recruiter who wanted to compare three candidates had no way to pick the third
before the tab/navigation for the first two already fired — reported by the user as "when I
try to compare candidates it opens [immediately]; I want to select first, then click Compare."

- [x] Removed the auto-open-at-two-selected branch in the checkbox `change` handler
      (`web/candidate-assessment.html`, `wireRowEvents`). The existing sticky "Compare
      candidates" button (`ca-compare-btn`, disabled until 2+ selected) is now the only trigger —
      a recruiter can select up to 3 candidates at their own pace before opening the comparison.
      Renamed the button from "Compare selected" to "Compare candidates" per direct instruction.
      Browser-verified: checking two candidates leaves the list in place with the button enabled;
      clicking it opens the criterion-by-criterion compare view.

## X62 — Expanded candidate panel clipped content instead of scrolling · CLIENT-VISIBLE · FOUND AND FIXED 2026-09-15

Reported by the user with a screenshot: the expand overlay cut off "Key information" partway
through (Location/Source never visible) with no scrollbar. Root cause: `.ca-tabpane`'s
`flex:1;overflow-y:auto` (meant to make only the tab content scroll, under a fixed header) had
no effect because its parent, `#ca-panel-body`, was never made a flex container — it's the
`.ca-panel` flex column's actual child, but `#ca-panel-body` itself had no `display:flex`, so it
sized to its content's natural height instead of filling `.ca-panel`'s bounded height. The
excess then hit `.ca-panel`'s own `overflow:hidden` and was clipped rather than scrolled — in
both the docked 400px panel and the expanded near-full-screen overlay.

- [x] `web/candidate-assessment.html`: added `#ca-panel-body{display:flex;flex-direction:column;
      flex:1;min-height:0}` (with `[hidden]{display:none}` to still hide it correctly) and
      `min-height:0` on `.ca-tabpane`, so the visible tab pane now has a real bounded ancestor to
      scroll within. Browser-verified: `scrollHeight` (790px) now exceeds `clientHeight` (528px)
      on the active tab pane, and scrolling reveals Email/Phone/Location/Source and everything
      below the fold in both the expanded overlay and the normal docked panel.

---

**2026-09-15, later, on direct instruction: X59–X62 are moot.** `web/candidate-assessment.html`
— the page all four defects were found on and fixed in — is deleted; the B15/B16/B18 merge that
created it is reverted (see `00-MASTER-BACKLOG.md`'s B15 note and `DECISIONS.md`). Shortlist,
Candidate 360, compare and decisions/export are separate pages again, none of which had these
defects. Left `[x]`/FOUND AND FIXED above as the historical record of what was found and fixed
in the page that no longer exists, rather than rewritten.

## X63 — AI-start CVs were dropped when the recruiter chose "review it manually" · CLIENT-VISIBLE · FIXED 2026-09-17

Reported by the user: starting a campaign with AI and choosing CVs on `web/start-campaign.html`,
then clicking "Or review it manually →" instead of the one-click "Approve rubric and start
screening" path, landed on `new-campaign.html`'s step 3 with "No applications chosen" — the
File objects picked in `campaign-ai-start.js`'s `resumeContext.folderFiles` only ever lived in
that page's own JS memory and could not ride along in the manual-review link's URL, so the
recruiter had to re-pick the same CVs from disk.

`app/api/processing.py::create_batch` requires an approved rubric (`RubricNotApprovedError`),
so the files cannot simply be uploaded to the campaign ahead of the manual review step — the
rubric is not approved yet at that point. The fix keeps the files client-side and carries them
across the full-page navigation instead.

- [x] Added `web/assets/pending-resumes.js`: a small IndexedDB-backed store (File/Blob values
      survive structured clone) keyed by campaign id, with `save(campaignId, files)` and a
      `take(campaignId)` that reads and deletes in one transaction so a later reload of the
      manual-review step never replays a stale selection.
- [x] `web/assets/campaign-ai-start.js`: the "Or review it manually →" link now stashes
      `resumeContext.folderFiles` (when any were chosen) before navigating to
      `new-campaign.html?campaign_id=...#step3`.
- [x] `web/new-campaign.html`: on load, after the draft resolves, takes any pending resumes for
      the campaign id in the URL and feeds them through the existing `describeChoice()` path (the
      same one `resume-input`/`resume-folder` already use), so the upload control is untouched —
      a recruiter can still add more files or replace the carried-over ones from the same
      "Choose applications"/"Choose a folder" controls.
- [x] Browser-verified end to end against the live API: submitted the AI-start form with one CV
      attached, clicked "Or review it manually →", and `new-campaign.html` step 3 showed
      "1 application chosen: john_doe.txt" with the informational note, without any re-upload.
      Confirmed the IndexedDB record is consumed (empty `getAllKeys()`) and a real reload
      (`location.reload()`) afterward correctly shows "No applications chosen." rather than
      replaying the same files indefinitely.

## X64 — Rubric weight editing on `new-campaign.html` could silently push the server-side total past 100, failing screening with no visible cause · CLIENT-VISIBLE · FIXED 2026-09-17

User asked for three things on the Must-have/"Counts in their favour" weight editor: (1)
increasing/decreasing one weight should auto-adjust the others to keep the group at 100, (2)
deleting a requirement should redistribute its weight back into the remainder, (3) starting
screening should never fail because of the rubric. (1) and (2) were already implemented and
browser-verified working (`autoBalanceWeights`/`redistributeAfterRemoval`, `web/new-campaign.html`).
(3) was not — two separate, previously-invisible gaps let the on-screen "Total: 100 pts" note
diverge from what the server actually validates against on Submit, both traced with real API
calls against a live draft campaign, not assumed from reading the code:

- [x] **Delete did not sync to the server.** The `.rm` remove button only ever removed the row
      from the DOM and redistributed the remaining rows' weights locally — it never called
      anything to deactivate the corresponding `RubricWeight` row server-side. `bulk_set_weights`
      (`app/services/rubric_service.py:517`) only updates the criterion_keys it is given; a
      deleted-on-screen criterion stayed active in the database at its old weight. Fixed by
      tracking each row's `weightId` (`makeReqRow`'s new 4th argument, set from `w.id` in
      `refreshWeightsFromVersion` and from `created.id` in `applyRequirementRow`) and calling
      `DELETE /rubric/versions/{v}/weights/{weightId}` from the remove handler when a row has one.
      Verified live: deleting a row fired the DELETE (network log showed `204`), and the
      criterion no longer appeared as active on the version afterward.
- [x] **The AI weight suggestion silently weighted rows this screen never renders.**
      `POST .../weights/suggest` assigns and persists a weight to every active criterion on the
      version, including `requirement_type: INFORMATIONAL` duty/responsibility lines pulled out
      of the JD alongside the Must-have/Preferred ones — `refreshWeightsFromVersion` only ever
      builds rows for `MANDATORY`/`PREFERRED`, so these never appear on screen and the recruiter
      has no way to see or edit them. Reproduced live: after "Read the description", the version
      carried two such rows at weight 1 each (`Seniority level: Mid`, `Perform electrical
      maintenance`) alongside a Must-have/Preferred total that correctly read 100 on screen — the
      server's real active-weight total was 102, and `POST .../submit` rejected it with
      `"Active criterion weights sum to 102.0 — they must sum to exactly 100."`, a message with no
      visible cause since the offending rows were never shown. Fixed in the Approve click handler:
      right before the weights PUT, it now re-fetches the version, finds any active criterion not
      among the rows on screen, and adds it to the same PUT at weight 0 — zeroing exactly the
      criteria the recruiter can't see or control, without touching the visible Must-have/Preferred
      proportions. Verified live end to end (PUT → Submit → Approve, same real API, same draft
      campaign the failure was reproduced on): `weight_total: 100`, `is_balanced: true`,
      `status: SUBMITTED` then `APPROVED`.
- Considered and rejected: calling `POST .../weights/normalize` before Submit as a blanket
  safety net. `00-MASTER-BACKLOG.md`'s B07 records an explicit 2026-09-13 instruction that removed
  the manual "Normalize to 100" button from this exact screen so that "auto-balancing is now the
  only way weights reach 100" — a normalize call would also rescale the invisible informational
  rows proportionally (keeping them non-zero and silently eating into the recruiter's visible
  100-point pool) rather than zeroing them, and conflicts with that recorded decision. The
  targeted zero-out fix above needs no normalize call and leaves the recruiter's chosen weights
  untouched.
- Not touched: `app/services/rubric_service.py`/`app/agents/weight_suggestion_agent.py` (why the
  suggestion agent assigns non-zero weight to informational criteria in the first place is a
  backend question, Ankush's lane per `08-TWO-PERSON-DELIVERY.md`) — this fix makes the failure
  unreachable from the screen regardless of what the agent does.

## X65 — `rubric.html` Must-have/Counts-in-favour sections silently dropped almost every real criterion, and the approval strip left a blank gap · CLIENT-VISIBLE · FIXED 2026-09-17

Direct instruction from a screenshot of `rubric.html` (Set up → Scoring rules, reached from the
shortlist screen). Reproduced live against a real screened campaign
(`5212142d-6150-4ecc-b2c7-9e97d8e31312`, via `GET /api/campaigns/{id}/rubric/active`) before and
after the fix, not assumed from reading the code:

- [x] **Approval strip left a blank gap right of "Weights total".** `.approvalstrip`
      (`web/rubric.html`'s local `<style>`) was `display:flex` with no `flex` on its `.figure`
      children — unlike the codebase's shared `.figures` grid pattern, flex children only take
      their content width, so the container's remaining space showed through as an empty band.
      Changed `.approvalstrip` to `display:grid;grid-template-columns:repeat(4,1fr)` (matching
      `.figures`), so the four cards now fill the row evenly. Verified: `getComputedStyle` on the
      live element reports four equal-width grid tracks, no leftover space.
- [x] **"Must have" only ever showed the one hard-fail eligibility rule**, hiding all the real
      mandatory weighted criteria. `renderMustHave` rendered `disqualification_rules` only —
      `app/services/requirement_service.py` sets `disqualifying=True` solely on the minimum-years
      row, so every campaign's must-have list read as a single line no matter how many mandatory
      skills/quals were actually scored (the live campaign above has 27). Rewired to render every
      active `MANDATORY` `RubricWeight`, each with its weight; rows whose `requirement_id` matches
      a `HARD_FAIL` rule are tagged "Not eligible if missing", the rest "Mandatory". Verified live:
      all 27 rows render with weights, tag counts match the one real gate.
- [x] **"Counts in their favour" only showed items with `weight > 0`**, and
      `requirement_service.extract_and_store_requirements` seeds every preferred skill at
      `weight=0.0` by default (only raised by the separate, unwired weight-suggestion agent) — so
      the section silently dropped most or all preferred criteria. Removed the `weight > 0` filter
      from `renderPreferred`; it now lists every active `PREFERRED` criterion with its true weight,
      zero included. Verified live: 10 of 10 preferred criteria now render (previously 4).
- [x] **"How the score is built" enhanced per request, kept to one line** — added a single static
      sentence under the legend ("Each part's weight is how much it can move the final number — a
      CV's score is just these parts added up."); does not touch the live-rendered stackbar/legend.

Not filed against a `B`/`D`/`X` plan ID before starting — this was a direct instruction against a
screenshot with no backlog item naming this page's display gaps; recorded here after the fact per
`AGENT-START-HERE.md`'s evidence-based reconciliation rule, rather than left undocumented.

**Follow-up check (2026-09-17, same day), closing the "Left/next" note above:** verified the
zero-mandatory and zero-preferred empty-state branches in `renderMustHave`/`renderPreferred`
against the live `rubric.html` for campaign `991776ef-9bda-494f-b20f-8596122fdcf7` — patched
`window.fetch` in-page to return `weights: []`/`disqualification_rules: []` from
`/rubric/active` and re-ran the page's own inline script (not a separate hand-written harness),
then read the resulting DOM. Both fallback messages ("No mandatory requirements are recorded on
this version…" and "No preferred requirements are recorded on this version…") render cleanly
with no error, and the approval-strip grid fix holds unrelated to weight count. Also checked
`renderComposition`'s own `if (!weights.length) return` early-out, which would leave the static
shipped-default stackbar/legend ("Five parts, out of 100": Mandatory 45/Skills 20/Experience
18/Qualifications 10/Certifications 7) showing as if real — confirmed this branch cannot occur
on any version that passed approval, since approval requires `weight_total === 100`, which forces
at least one active weight `> 0` to exist. Not a live bug; no code change made. No backend/`app/**`
touched, no pytest run needed (frontend-only, read-only verification).

---

## X66 — "Ready to send" on `handoff.html` was a second, disconnected send action, so the manager-owned row a recruiter needed never existed after `decisions.html`'s own send · CLIENT-VISIBLE · FIXED 2026-09-17

Direct instruction, same shape as `X58`: the user had already used `web/decisions.html`'s
"Email the shortlist to hiring manager" (B10) and expected `web/handoff.html`'s "With the
hiring manager" group to reflect that — instead the candidate sat in "Ready to send" forever,
because that email (`POST .../reports/email-to-hiring-manager`, `app/api/reports.py`) only ever
sent mail and wrote a campaign-level `SENT_TO_HIRING_MANAGER` audit event; it never touched
`CandidateLifecycle`. The *only* thing that moved a candidate to `WITH_HIRING_MANAGER` and set a
named owner was `handoff.html`'s own separate "Send to hiring manager" button
(`POST .../lifecycle/{id}/send-to-manager`) — a second, manual, per-candidate action the
recruiter had to additionally remember to click after already emailing the report.

Asked to remove "Ready to send" from `handoff.html`'s grouping outright ("I already sent it in
decisions and export"). Flagged before removing it that doing so with no replacement would
permanently strand every shortlisted candidate at `SHORTLISTED` — nothing else in the codebase
calls `send-to-manager`. Resolved on instruction: the decisions.html email *becomes* the handoff
trigger, so no manual click is needed at all.

**Fix (`app/api/reports.py`):** `email_shortlist_to_hiring_manager` now calls a new
`_handoff_to_manager` helper after a successful send. It resolves `payload.recipient` against
`User.email` (must be `HIRING_MANAGER`/`ADMIN`); if found, every reported candidate whose current
disposition is `SHORTLIST`/`INTERVIEW` (the same gate `lifecycle_service.enter()` already
enforces — a `HOLD`/`REJECT` included via `decided_only=false` is never handed to a manager) is
moved to `WITH_HIRING_MANAGER`, owned by that manager, via the existing
`lifecycle_service.send_to_hiring_manager`. A recipient that matches nobody in the system still
gets the email (informal copies to an outside address are not blocked) but moves no one.
`EmailReportOut` gained `moved_to_manager`/`manager_name` so `web/decisions.html`'s send
confirmation can say so.

**A second, pre-existing mismatch found and fixed in the same change:** `EmailReportIn.actor_id`
is, in the one real caller, the signed-in person's *name* (`window.__r360ActorName()`, matching
every other free-text `actor` field on that page), but `lifecycle_service.transition` needs a
real `User.id` belonging to someone whose role is actually allowed to make this specific move
(`RECRUITER`/`ADMIN` — never the hiring manager themselves, per
`app/core/lifecycle.ALLOWED_ROLES`). Added `_resolve_actor_id`: try the value as a real id, then
match it by name against a known account, then fall back to any recruiter/admin account — so the
pre-existing name/id mismatch never blocks the handoff; `None` only if no such account exists at
all, in which case the email still sends and nobody moves.

`web/handoff.html`: removed the `ready_to_send` entry from the `GROUPS` array driving both "Where
the queue stands" and "By group" (one list feeds both), and the now-unreachable
"Send to hiring manager" button branch in `renderRow`. `returned`'s own "Send back to manager"
button (same `send` action, different group) is untouched. The backend queue endpoint
(`app/api/handoff.py`) still computes and returns `ready_to_send` — nothing reads it on this
screen any more, but no contract changed for any other caller.

Verified: `tests/test_reports_api.py` — 5 new tests (moves a known manager's shortlisted
candidate; an unrecognised recipient still sends and moves nobody; re-sending to the same
manager is not an error; a `REJECT`ed candidate in a `decided_only=false` report is never moved;
`moved_to_manager`/`manager_name` present on the response). Full suite: 832 passed. Live-checked
`handoff.html` against a real running campaign with data in `ready_to_send`/`returned`
(`b22491f9-ac73-4980-93d9-9264f619ca80`) — "Ready to send" no longer appears in either the chart
or the group list; "By group" now opens directly on "With the hiring manager". Did not exercise
the positive move path against that same live server, since its `email_backend` is configured to
`outlook` and the campaign's real hiring-manager accounts are not on `mail_guard`'s approved-
recipient list — covered instead by the pytest suite against the simulated backend.

- [x] `reports.py`'s email send now performs the manager handoff (move + owner), not just the mail
- [x] Actor-id/name mismatch resolved with a real-id → name-match → role-fallback chain
- [x] "Ready to send" removed from `handoff.html`'s chart and group-by list
- [x] 5 new backend tests; full suite re-run clean (832 passed)
- [x] Positive end-to-end path verified live, same day, once the user hit it for real (see
      follow-up below).

**Follow-up (2026-09-17, later, same day), closing the "positive path" gap above.** User
actually exercised this against a real running campaign (`5212142d-6150-4ecc-b2c7-9e97d8e31312`,
4 shortlisted candidates) and reported it still not moving after resending and restarting the
server. Two real causes found, neither a regression in the fix above:

1. **The first two sends predated the server restart.** Confirmed by reading the audit trail
   directly (`GET .../audit?action=SENT_TO_HIRING_MANAGER`): the `after` payload from the
   candidate's actual attempt (08:48) had no `moved_to_manager` key at all — the key this fix
   always writes — proving that request hit the pre-fix process. `GET /openapi.json`'s
   `EmailReportOut` schema (missing `moved_to_manager`/`manager_name` at first, present after a
   real restart) is a reliable live check for "is the running server actually on this code."
2. **The address used, `ankush.saxena@protivitiglobal.in`, was the user's own account —
   registered as `RECRUITER`, not `HIRING_MANAGER`.** `User.email` is unique, so no second
   account could exist at that address to receive the handoff; the only two real
   `HIRING_MANAGER` accounts on file (`noora.althani@qchem-demo.example`,
   `yusuf.almarri@qchem-demo.example`) are on a domain `mail_guard`'s approved-recipient list
   (real `email_backend=outlook` sends only) does not include — so no single address was both a
   registered manager and an allowed real recipient. Asked the user directly rather than
   guessing; they wanted their own address to keep working (they can see the real mail land in
   Outlook) rather than switching to a demo `@qchem-demo.example` address or simulated sending.

**Fix:** added `PATCH /api/users/{id}/role` (`app/api/lifecycle.py`, `users_router`;
`lifecycle_service.update_user_role`) — no prior endpoint could change a user's role at all.
Promoted the user's own account from `RECRUITER` to `ADMIN`. Checked
`app/core/lifecycle.WHO_MAY` first: `ADMIN` is a superset of `RECRUITER` in every entry (never
the reverse), so this only adds capability, never removes one the account already had — and
`ADMIN` satisfies `_handoff_to_manager`'s manager-role check (`HIRING_MANAGER`/`ADMIN`) as well
as `_resolve_actor_id`'s mover-role check (`RECRUITER`/`ADMIN`), so the same account can now
both send the report and receive the handoff.

**Verified live, in that order, on the real campaign:** confirmed via `/openapi.json` that the
restarted server carried the new `/api/users/{id}/role` path; `PATCH`'d the user's own account to
`ADMIN` (`200`, `role_label: "Administrator"`); re-sent the report to
`ankush.saxena@protivitiglobal.in` — response now `moved_to_manager: 4`, `manager_name: "Ankush
Saxena"`, `simulated: false`, `send_detail: "Sent via local Outlook to
ankush.saxena@protivitiglobal.in."` (a real send, not simulated); reloaded `handoff.html` for
that campaign and confirmed "With the hiring manager" now reads 4, with all four rows showing
"Owner: Ankush Saxena." New tests: `tests/test_lifecycle.py` —
`test_a_persons_role_can_be_changed`, `test_changing_an_unknown_persons_role_is_refused`. Full
suite: 834 passed.

- [x] `PATCH /api/users/{id}/role` added; changes only role, never name/email (those identify
      the account)
- [x] Promoted the user's real account to `ADMIN`; verified it kept every recruiter capability
      (superset check against `WHO_MAY`) while gaining hiring-manager eligibility
- [x] Live-verified end to end on the real campaign the user was working: 4 candidates now show
      "With the hiring manager," owned by the user's own account, via a real (non-simulated)
      Outlook send
- [x] 2 new tests; full suite re-run clean (834 passed)

**Second follow-up (2026-09-17, later, same day): the `returned` group's own "Send back to
manager" never actually told the manager anything.** Direct instruction: on `web/handoff.html`'s
"Returned, with a question" row, (1) the manager dropdown should offer real named people the same
way the `with_manager` flow now does — not just the two `@qchem-demo.example` accounts, (2) the
recruiter needs somewhere to write the actual answer to the manager's question, and (3) confirming
should really email that manager, at the same real address already proven to work for X66's first
fix, not just move the lifecycle row silently.

Root cause: `POST .../lifecycle/{id}/send-to-manager` (`app/api/lifecycle.py`) only ever called
`lifecycle_service.send_to_hiring_manager` — a pure state transition, no mail. It is the same
endpoint behind both the very first handoff and this answer-and-resend, so it could not simply
always email (the first handoff has no question to answer yet, and the manager already knows a
report is coming). `web/handoff.html`'s manager dropdown (`loadManagers`) also only ever fetched
`role=HIRING_MANAGER`, so an account promoted to `ADMIN` for the first X66 fix (the user's own
`ankush.saxena@protivitiglobal.in`) never appeared as a choice here, despite already being an
eligible manager per `send_to_hiring_manager`'s own role check.

**Fix:**
- `app/api/lifecycle.py`'s `send_to_manager` now looks up the candidate's most recent
  `ManagerReviewOutcome.QUESTION` reason (`_last_question`, mirroring `handoff.py`'s own private
  helper of the same name — kept separate rather than shared, since one is the read-side queue and
  this is the write-side action). Only when a question is actually on file does it also send a
  real email to the chosen manager (`mail_guard.ensure_approved_mail_recipients` +
  `outlook_adapter.get_mail_adapter().send`), quoting the question and the recruiter's note as the
  answer. `LifecycleOut` gained `mail_sent`/`mail_detail` (both `None` when no question existed to
  answer, so the first, question-free handoff is unaffected).
- `web/handoff.html`: `loadManagers` now fetches `role=HIRING_MANAGER` and `role=ADMIN` and merges
  them (deduped by id), so an admin-promoted stand-in shows up here exactly as it already does for
  the `with_manager` send in `decisions.html`. The `send` action's note field is relabelled "Your
  answer to the manager's question (sent to them by email)" when `entry.question` is present, and
  is now required in that case (empty answers are still fine for the first, question-free
  handoff). On confirm, a green line reports `mail_detail` (and whether it was a real, non-
  simulated send) for a moment before the fold reloads.
- Created a third real account, `Subhadeep` (`subhadeep.m@protivitiglobal.in`, `HIRING_MANAGER`),
  via the running server's own `POST /api/users` — that address was already on
  `mail_guard.APPROVED_MAIL_RECIPIENTS` (added for calendar-invite self-testing before this
  session), it just had no `User` row yet, so it could not previously be chosen as a lifecycle
  owner or receive a real send.

**Verified live** against the real campaign (`5212142d-6150-4ecc-b2c7-9e97d8e31312`,
`AHMED KARIM AL-SAYED`, already `RETURNED_TO_RECRUITER` with a question on file): restarted the
dev server (`QUEUE_BACKEND=inline`, port 8000) so it carried this code, confirmed via
`/openapi.json` that `LifecycleOut` now has `mail_sent`/`mail_detail`; in the browser, opened
"Returned, with a question," saw both "Subhadeep" and "Ankush Saxena" in the manager dropdown
alongside the two demo accounts, wrote an answer, chose Ankush, and confirmed — got back "Mailed
the manager: Sent via local Outlook to ankush.saxena@protivitiglobal.in." (a real, non-simulated
send); the candidate reappeared under "With the hiring manager," owned by Ankush Saxena, and
"Returned, with a question" read 0. Confirmed via `GET .../handoff/queue` directly, not just the
screen.

New tests (`tests/test_lifecycle.py`): `test_answering_a_managers_question_emails_them_the_answer`
(hand over → manager asks a `QUESTION` → answered send-to-manager emails that manager, address
present in `mail_detail`); extended `test_a_candidate_is_handed_to_a_named_manager` to assert
`mail_sent`/`mail_detail` are `None` on a first, question-free handoff. Full suite: **835 passed**.

- [x] `send-to-manager` emails the manager for real when it is answering an on-file question
- [x] `handoff.html`'s manager dropdown includes `ADMIN` accounts, matching the backend's own
      eligibility rule
- [x] Answer field required and clearly labelled when there is a question to answer
- [x] Real `Subhadeep` hiring-manager account created against an address already mail-approved
- [x] 1 new test + 1 extended assertion; full suite re-run clean (835 passed)
- [x] Live-verified end to end: real Outlook send, confirmed via both the screen and the queue API

## X67 — Stage pages (`leaderboard.html`/shortlist and others) sometimes rendered `index.html`'s ("Today") body under the correctly-highlighted journey rail · FOUND 2026-09-18

User reported: screening candidates from the Shortlist stage (and reportedly other stages) shows
the campaign journey rail correctly highlighting "Shortlist," but the content below it is
`index.html`'s "Your recruitment work, at a glance" Today-page body instead of the shortlist page.

Investigated the journey rail (`web/assets/app.js` ~275-560): it is not a client-side router — it
builds real `<a href="...">` links per stage from the URL's filename
(`app.js:300-302`,`351-356`,`534-536`) and lets the browser do an ordinary full-page navigation
(`navigate()`, `app.js:362-381`, no `preventDefault()`). It does not swap page content and is not
the cause.

Root cause is `web/sw.js`'s network-first-with-offline-fallback service worker. On a failed
`fetch()` for a navigation request whose exact URL isn't already cached, it falls back to
`caches.match('index.html')` (`sw.js:47-51`) — landing the Today page's body under whatever stage
the rail thinks it's on. This exact mechanism was already found and scoped once before, in `X27`
(fixed 2026-09-13, restricted the substitution to `e.request.mode === 'navigate'` only). The code
on disk already has that fix and lists `leaderboard.html` in `SHELL` (`sw.js:6`), so a *fresh*
install of the current worker should not reproduce this. The likely trigger is a browser tab still
running an **older, previously-installed service worker** (predating `X27`, or predating
`leaderboard.html`/other stage pages being added to `SHELL`) that a long-lived tab never re-checked
or activated — service workers only take over control on a later navigation, and browsers throttle
re-fetching the worker script, so a stale instance and its old `qchem-talent-v<old>` cache can keep
running indefinitely without a hard reload.

**Fix:** bumped `CACHE` in `web/sw.js` (`v23` → `v24`), the same cache-busting convention already
used for `app.js` (`X50`/`X59`/`X60`), so any stale worker instance is forced to install the current
script and purge its old cache on next load, rather than silently continuing to run old fetch logic.

- [x] `web/sw.js` cache version bumped to force stale service-worker instances to update
- [ ] Not yet reproduced live against a genuinely stale pre-`X27` worker — recommend the user hard
      refresh (or DevTools → Application → Service Workers → Unregister, then reload) to confirm
      the stale-SW theory and close this out
- [ ] Consider whether `activate` should also proactively notify/reload already-open clients so a
      long-lived tab doesn't need a manual hard refresh to pick up future `sw.js` fixes
