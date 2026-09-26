# Recruitment 360: campaign journey UX proposal

**Status:** Updated 2026-09-12 after direct Start Campaign implementation. Current delivery contract and remaining queue: `08-TWO-PERSON-DELIVERY.md` section 9. Older proposals below are historical where they conflict; rail and standalone upload page are not prerequisites.
**Date:** 2026-09-12  
**Canonical code:** `talent-intelligence-system`, branch `Subodhip`
**Plan links:** `B01` end-to-end recruitment, `B14` campaign creation and CV ingestion, `B19` dashboard

## Original problem statement — historical, before save/resume fixes

Today already works well as the portal's landing page. A recruiter starting a new job, however, sees many peer navigation tabs and a separate Pipeline hub. The product exposes its internal screens before explaining what to do next. A new campaign currently spans role setup, job-description extraction, rubric approval, CV upload and assessment without a dependable resume path. In `web/new-campaign.html`, “Save as draft” only changes button text; reading the job description creates one campaign, while the final assessment action creates another. The same job can become two records.

The intended experience is: **open Today for immediate work; start or resume a campaign; follow one visible next action through the recruitment story; open specialist tools directly when needed.** Keep all existing capabilities. Reorganize entry points rather than deleting screens.

## Design principles

1. **Today stays familiar.** Preserve existing content and visual hierarchy. Add a small “Needs attention” area only when real persisted events support actionable items. No invented urgency or notification count.
2. **One campaign, one durable story.** New-job setup creates one campaign ID. Each completed step persists before the next step opens. Closing and reopening the portal resumes from saved server state.
3. **One primary action per task.** Setup carries a single Continue flow. After assessment, show prioritized action groups for candidates progressing independently. Completed work shows summaries; deeper details remain directly accessible.
4. **Progress is visible without becoming a maze.** Show four broad phases, with the current task clearly named. Reveal the full step list only when requested. Do not make a large grid of all workspaces the default path.
5. **Shortcuts remain.** Experienced users can jump to Candidate 360, rubric, discovery, timeline, audit, analytics, or a particular campaign stage. A shortcut never creates a second copy of campaign data.
6. **Truthful state.** Draft, awaiting approval, running, blocked and completed labels must come from persisted records. Existing external email/calendar/offer actions remain marked simulated until integrated.

## Information architecture

| Surface | Default purpose | Primary action | Secondary access |
|---|---|---|---|
| **Today** | Existing overview plus genuine pending work | Open highest-priority action | Existing details and campaign links |
| **Start Campaign** | Create and list saved campaigns directly | Create a campaign / stage-specific resume button | All campaign workspaces; future search/filter |
| **Candidates** | Find a person across work | Open Candidate 360 | Campaign-specific candidate list |
| **More** | Specialist destinations | None | Performance, Record, Timeline, Discover, Pipeline overview, Developer/FinOps and other existing tools |

Top bar remains **Today · Start Campaign · What-if Analysis · Audit · FinOps**, with HR profile designation. Direct URLs remain valid. Specialist destinations stay under All campaign workspaces and contextual campaign links. A cross-campaign finder is optional secondary access, not a prerequisite navigation redesign.

Do not replace Today's content wholesale. The current “Jump to” row can remain during the first navigation change; assess duplication in browser review before changing it.

## Campaign journey

The plan's `B14` campaign setup is the beginning of a new job. Candidate lifecycle begins only after shortlist; it must not be mistaken for the start of the whole campaign.

| Phase shown on campaign | Guided sequence | Completion evidence |
|---|---|---|
| **Prepare** | Describe role → add job description → review extracted requirements → review and approve rubric | One campaign draft, saved JD/requirements, approved rubric version |
| **Screen** | Add or discover CVs → inspect import/held files → start assessment → view results | Batch and evaluation run tied to same campaign |
| **Select** | Review evidence and shortlist → send to hiring manager → schedule interview → record feedback | Candidate disposition and lifecycle/audit events |
| **Hire** | Route approvals → draft/send offer → record response → record joined or unsuccessful outcome | Candidate lifecycle and audit events |

The screen leads through the next valid task, not necessarily every listed action for every candidate. Held, rejected and withdrawn candidates branch to their truthful outcome. Actions after shortlist are candidate-specific even though the campaign remains the organizing workspace.

### Campaign workspace layout

1. Header: role title, location, vacancies, plain-language status; breadcrumb back to Campaigns.
2. Compact phase navigation: Prepare / Screen / Select / Hire. These are navigation groups, not sequential campaign states or a percent-complete bar. Show candidate counts across active phases and outcomes separately.
3. During setup, “Next for this campaign” offers **Continue**. After assessment, show grouped work such as “Review 12 candidates”, “Handle 2 unreadable CVs”, and “Record 3 interview feedbacks”, with owners and blockers.
4. Current task content: only fields and explanations needed now. During setup, **Save and leave** and **Continue** are distinct; neither claims success until the server confirms it.
5. “Previous work” disclosure: brief completed-step summaries with edit/view links. “All stages” disclosure gives direct access to the full story. Candidate 360 and other specialist links appear in context.

Example: after saving role and job description, a returning recruiter sees “Control Room Operator — Continue: review scoring rules” on Campaigns. Opening it lands on that step with saved role/JD visible as a collapsed summary. The recruiter does not need to find Rubric in the global navigation.

## Save and resume contract

- First successful save from role details, through **Continue** or **Save and leave**, creates one `DRAFT` campaign through `POST /api/campaigns`; URL thereafter contains that campaign ID. Later actions reuse it.
- Later edits use `PATCH /api/campaigns/{id}` or the existing requirement/rubric/batch APIs. Reopening loads server records and suggests a valid task. Operative lifecycle status remains stored, as required by `02-LIFECYCLE-MODEL.md`; never infer it from the latest timestamp. A suggested UI task is not a second workflow state. Browser `sessionStorage` is not the source of truth.
- **Save and leave** persists changes made in the current step and returns to Campaigns. If a step is incomplete, its card says “Continue setup”; it does not claim completion.
- Rubric review and approval are explicit. The existing “Approve and start screening” shortcut must not silently auto-approve as a named person. CV ingestion follows the approved rubric gate; a campaign may wait for CVs and resume later.
- Re-entering an earlier step remains possible. Changing a JD or rubric after scoring must use the existing version/re-evaluation rules or clearly warn and require a new run; prior results must not silently change meaning.
- Errors keep the user on the current step, preserve entered data where possible, and name the failed action. No forward navigation after a failed save.

## Today: optional action feed

Keep existing Today modules. If added, a compact “Needs attention” list should pull only from real states: draft awaiting completion, rubric awaiting a named approver, completed assessment ready for review, manager verdict or interview feedback pending, approvals/offer waiting on an owner, held CVs needing manual handling. Show the campaign/person and a direct action link. Sort by genuine due time and severity where available; never manufacture an SLA or badge count from a static fixture. Empty state can simply omit the list.

## Reference patterns and application

- [GOV.UK — Navigate a service](https://design-system.service.gov.uk/patterns/navigate-a-service/): navigation should expose major destinations rather than act as a site map. This supports reducing the top bar and keeping deep links in context.
- [GOV.UK — Task list](https://design-system.service.gov.uk/components/task-list/): task lists suit work users can do in flexible order. Its guidance recommends save-and-continue for a required-order journey spanning sessions. This campaign setup should therefore lead with **Continue**, not a wall of unordered tasks.
- [GOV.UK — Complete multiple tasks](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/): when a longer transaction genuinely has multiple tasks, group them into comprehensible stages and show completion state. This informs the optional expanded phase view, not the primary new-campaign screen.

These are interaction patterns, not a proposal to copy GOV.UK's visual style. Preserve the portal's current visual language.

## Acceptance scenarios for later implementation

1. Start a new job from Today or Campaigns. Save role details. Close browser. Reopen Campaigns: exactly one draft appears with a working **Continue** link and saved fields.
2. Add JD, inspect extracted requirements and approve the actual rubric version. Close and reopen: the same campaign resumes at CV ingestion; no duplicate campaign exists.
3. Upload CVs and run assessment. Campaign view shows results and the next review action. A held file has a clear handling link without blocking the whole campaign.
4. Shortlist one candidate. Open Candidate 360 directly, then return to the same campaign and continue handoff/interview/approval/offer/outcome.
5. Navigate every existing specialist screen through More or contextual links. Direct existing URLs remain functional.
6. Today retains current useful content. Any new pending item opens the exact campaign/candidate action and disappears or changes state after the action succeeds.
7. At desktop and narrow widths, main next action remains obvious; keyboard users can operate More, disclosures and progress links; statuses are understandable without color alone.

## Scope boundaries and decisions still to validate

- No removal of current screens or backend recruitment capabilities.
- No real email, calendar, offer-letter delivery, candidate reply ingestion, or invented notification service in this UX pass.
- Confirm whether **Candidates** merits its own top-level entry after testing; Today and Campaigns are the two essential ones. If search covers candidate access well, Candidates could move into More without losing a direct campaign link.
- Confirm which roles may approve rubrics and whether editing an already approved rubric should force a new version before implementation.
- Do not add a new persistent `current_step` field unless deriving it from existing saved records proves insufficient.

## Independent review prompt

> Review this Recruitment 360 UX proposal as a product designer and workflow architect. Evaluate whether a first-time recruiter can start a job and reach shortlist without hunting across tabs, then close and resume at any step. Identify misleading completion states, missing branches, overloaded surfaces, accessibility gaps, and places where the plan's 10 candidate journey steps conflict with campaign setup. Challenge the four-phase grouping and top navigation; propose a simpler alternative if better. Rank findings by user impact. Do not implement code. Treat the stated existing API and current defects as constraints, and distinguish what can be done with existing persisted records from what needs a new backend contract.

## Progressive disclosure: Act → Understand → Inspect

The user's 20/80 rule is the organizing principle: default to the small set of information needed for most routine work. Treat field frequency as a hypothesis to validate with recruiters, not a literal percentage quota. Less information must still support a sound decision.

| Level | Question answered | Content | Access |
|---|---|---|---|
| 1 — Act | What needs me, and what can I do? | Person/role context, saved status, immediate task, essential evidence summary, blocker/owner, primary action | Default surface |
| 2 — Understand | Why, and what are my options? | Relevant criteria, discrepancies, explanations, stage-filtered candidates, recent activity | Named disclosure or contextual page: “Review 3 evidence gaps” |
| 3 — Inspect | Show the underlying record | Source CV/JD citations, complete calculations, rubric/run versions, timeline, audit, advanced reporting | Dedicated deep link; preserved context and breadcrumb |

Level 3 must be directly reachable, not buried behind nested accordions. Routine paths use at most one expansion before opening the full record. Browser Back restores campaign, candidate, filters and list position. Completion returns to the same work context.

**Never hide material facts:** failed/unsaved changes, missing approval, blocked next action, material contradiction, incomplete assessment, stale results, permission restrictions, simulated delivery and preview-only status. Summaries disclose hidden counts: “2 high-priority findings; 6 more findings”. Unknown, absent, loading, failed and zero are different states.

Initial content budgets, subject to walkthroughs:

- Today: up to five personal action items, with counted “View all work”; urgent overflow stays visibly counted.
- Active campaign: up to three grouped next actions and compact stage counts. Avoid a default metric-card grid.
- Candidate overview: recommendation, evidence coverage, material concerns, latest human decision and valid action. Complete criterion table one level deeper.
- Comparison: up to ten candidates initially, with server-side pagination/search. Fetching all records then hiding most does not satisfy B16/X12.
- Keep readable spacing and touch targets. Reduce competing content before shrinking whitespace. Avoid hover-only facts, icon-only actions and nested drawers.

### Surface contract

| Surface | Act: frequent essentials | Understand: focused detail | Inspect: complete record |
|---|---|---|---|
| Today | Preserve existing hierarchy; genuine personal pending work, context, reason and action | All my work; waiting on others | Exact campaign/candidate task and history |
| Campaigns | Role/site, filled versus vacant positions, status, next task, last saved time | Filters, closed roles, campaign details | Campaign workspace |
| Setup | Current step, minimal required fields, saved indicator, next action | Previous-step summaries, optional role details, extraction issues | Original JD, criterion mapping, rubric versions |
| Campaign workspace | Role/vacancies, action groups, stage counts, relevant blockers | Stage-filtered candidates, batches, owners, recent activity | Timeline, rubric history, analytics, audit |
| Candidate list | Name, role context, assessment summary, gaps, human decision/stage | Filters, shortlist, selection for comparison | Candidate 360 for selected campaign/run |
| Candidate 360 | AI recommendation separate from human decision; evidence coverage; material findings; valid action | All criteria/discrepancies, interview questions, recent events | Source citations, calculations, versions, audit |
| Compare | Selected candidates and decisive job-related criteria; evidence gaps | More criteria and explanations | Each candidate's cited evidence |
| Handoff/interview/approval/offer | Person + role, task, owner, essential inputs, blocker, delivery status | Relevant earlier feedback, package details, reasons | Complete timeline, approval evidence, communication record |
| Reporting / HR FinOps | Campaign/period and a few defined business measures | Stage/campaign breakdown and denominators | Exports, cost assumptions and technical provenance |

Group More into Review tools, Reporting and Operations. Contextual links remain the normal access path. Keep Candidates top-level provisionally: finding a known person is a distinct task. Cross-campaign search must select the relevant application before any hiring action; never silently act on the newest campaign.

### Example active campaign, illustrative copy only

> Control Room Operator · 1 of 2 positions filled  
> **Review 12 assessed candidates**  
> Handle 2 unreadable CVs · Record feedback for 3 interviews  
> Waiting on manager: 4 candidates · View all work  
> Campaign details ▸ · Progress and outcomes ▸

Use real records for production counts. Action counts may overlap stage counts; do not sum them as a population total. Four phases organize navigation while candidates progress independently. New batches may be screened during interviews. Separate joined/withdrawn/unsuccessful outcomes from active-stage counts; expanded charts retain stage order and zero-count stages.

Offer accepted is not joined. One filled vacancy does not complete a multi-vacancy campaign. Closure/cancellation/reopening requires explicit permission and a policy for outstanding candidates; verify existing campaign transitions before proposing new ones.

## Alignment with the complete roadmap

| Backlog | Contextual home | Disclosure and dependency rule |
|---|---|---|
| B01–B02 journey/lifecycle | Campaign → candidate task → timeline | Complete ten-step journey remains reachable; setup stays outside shortlist lifecycle; X14 mapping still requires review |
| B03 discovery | CV step: Upload / Find in repository | Show actual source and selection method; manual folder selection is not semantic discovery |
| B04 audit | Recent activity → full audit | Actor/result near action; full IDs/history deeper; evidence required for an approval stays in its task |
| B05–B07 AI/JD/scoring | Setup and candidate decision | Generated text reviewable; AI suggestion separate from saved decision. Grouping criteria visually must not conceal X2 or silently change scoring |
| B08 clarity | Every surface | Plain labels, accessible text/status, existing brand language; simplify content hierarchy |
| B10–B13 integrations/governance | Current candidate task | Simulation label beside action. Integrations later replace delivery mechanics; necessary approval policy precedes real offer sending |
| B14 drafts/reuse | Campaign setup | One saved campaign. Explicit role/JD reuse; no automatic old-CV carryover |
| B15 historical reuse | Decline/no-join follow-up | Later show eligible backups and prior outcomes; no invented automatic selection now |
| B16 compare | Candidate selection → Compare | Top ten, bounded reads, filters/pagination; X12 remains backend work |
| B17 what-if | Scoring rules → Explore alternatives | Preview-only label always visible; authorized approval/new run separate from exploration |
| B18 Candidate 360 | Review evidence | Every discrepancy reachable; material findings visible immediately |
| B19 analytics | Campaign progress → Reporting | Current position counts distinct from cohort conversion; period/denominator explicit; unavailable metrics remain unavailable |
| B20 identity | Context and record detail | Existing campaign/candidate UUID links now; no fabricated public Application IDs. Resolve application correlation before real outbound threading |
| B21 FinOps | More → HR FinOps | Business costs first; assumptions/provenance deeper. No new pricing claim in this pass |
| B22–B24 platform/commercial | Operations and roadmap | Preserve scope; no implied tenant/security/integration capability from rearranging UI |

## Reliability and workflow refinements

- Define retry-safe draft creation and assessment submission. Disabled buttons improve feedback but cannot prevent duplicates after a lost response. Server replay protection is a prerequisite to the no-duplicate acceptance claim; current support is unverified.
- Verify partial-draft support. Save and leave persists incomplete work where supported; otherwise state minimum required fields and propose the narrow contract change. Never report cosmetic success.
- Detect stale writes. Preserve entered text on conflict; offer reload/reconcile. If another reviewer already completed the task, refresh state and prevent duplicate action.
- Keep approval-before-ingestion for the first slice. Optional later relaxation: accept CVs while approval waits, but gate assessment on approved rubric. This needs policy/API review and is not silently adopted here.
- JD/scoring-rule edits follow versioning and reapproval. Prior results stay labeled with original rubric; materially changed criteria require an explicit new assessment. Define metadata-only versus score-affecting edits before implementation.
- Suggested work uses operative saved records and actual role/ownership. Sort recorded overdue tasks first, then actionable blockers and ready work, with stable ordering. Waiting on another owner is separate; no invented SLA or urgency. Missing owner means Unassigned.
- Held CV affects that file, not all valid CVs. Partial results show assessed/held/failed counts and targeted recovery. Failed refresh retains last known data with a stale label; it must not become a false empty state.
- Server revalidates permission and workflow gates on submission. A hidden action is not authorization enforcement. Approval identity must come from actual user identity.

| Contract area | Evidence and required work |
|---|---|
| Campaign create/PATCH, rubric, batches, evaluations, lifecycle | Reported existing in restored state; inspect exact API/callers before implementation |
| Contextual links, disclosures, campaign ID reuse | Expected composition of existing capabilities, not a new state machine |
| Partial drafts, extraction persistence, invalidation, conflict detection, retry protection | Verify support; specify narrowly scoped additions where absent |
| My work / next action | Read-only presentation from operative records; a shared server projection only if existing reads prove inadequate |
| Application identity, campaign closure/reopening | Confirm B20 and current transition contracts; no inferred new stored state |
| Reminders, real sends/calendar/offer delivery, semantic ranking | Separate backlog work; keep truthful capability labels |

## Proposed delivery slices

These are slices under existing IDs, not new IDs, deadlines or implemented features.

| Order | Slice | Exit evidence |
|---|---|---|
| 1 | B14 durable setup/recovery | Same campaign across role/JD/approval/upload/run; close/reopen restores saved work; retry creates no duplicates; failed saves preserve inputs |
| 2 | B01/B08/B14 contextual workspace/navigation | Today preserved; setup resumes task; active campaign supports parallel candidate actions; URLs and Back preserve context |
| 3 | B05/B16/B18 progressive evidence review | Compact decision surface; full criteria/source reachable; material gaps visible; bounded list queries |
| 4 | B01/B02/B10–B13 task continuity | Candidate reaches joined/unsuccessful with owners/events; hold/resume and return-for-changes work; proxy labels remain visible |
| 5 | B19/B21 focused overview | Scoped measures drill into matching records; Today items change only after saved resolution |

Before Monday, preserve agreed D1–D4 and whole-journey rehearsal. Take only a rehearsable slice; do not trade end-to-end reliability for a portal-wide redesign. Existing functional routes remain until replacements pass review.

Post-demo sequencing proposal: pull durable B14 setup/resume ahead of real integrations rather than leave it entirely in Increment 3. Establish B20 application correlation before live send/reply processing, and required B13 approval gates before real offers. Broader governance, reuse, analytics, FinOps and commercial/platform work retain existing roadmap homes. This changes proposed dependencies, not agreed delivery dates.

## Validation of helpfulness

Compare current flow and revised prototype using novice and experienced recruiters. Proposed targets, not measured outcomes:

1. Identify next valid action within ten seconds, without coaching, on Today/setup/campaign/candidate review.
2. Start role, leave during JD/rubric work, reopen without re-entering saved fields or creating another campaign.
3. Reach source citation from candidate overview within two interactions; full timeline directly without nested disclosures.
4. Handle multiple vacancies, mixed-stage candidates, second batch and held file without losing context.
5. Correctly distinguish missing evidence from failed criteria, AI recommendation from human decision, accepted offer from joined, simulated send from real delivery.
6. Exercise save failure, lost response/retry, concurrent completion, stale data, permission denial and all-held batch. No navigation after failed save.
7. Complete routine work without More; expert still reaches every specialist URL and returns to exact context.
8. Keyboard supports menus/disclosures and logical focus; save/errors announced; status understood without color. Narrow screens keep task before detail without hiding blockers; long/localized labels remain readable.

Record unassisted completion, wrong turns, backtracking, repeated entry and missed blockers. Revise the assumed essential 20% from observations. During implementation, run targeted API/journey tests, browser walkthrough, then required full suite. Historical 552-pass result is not validation of current HEAD or this design.

Remaining implementation decisions: approval roles/invalidation, partial-save semantics, task ownership/due-date sources, closure/reopening policy, application identity and any ingestion-before-approval relaxation. Resolve against actual contracts and domain owners; document refinement need not wait for these answers.

---

## The campaign rail and the next-step rule — proposal, 2026-09-12

Raised by the user after `web/campaigns.html` began listing every campaign: a
campaign needs a visible spine. Its stored status says *where* it is in one word.
It does not say what is done, what is left, or how to get back to any of it.

This section proposes two things and deliberately separates them, because one is
a rule and one is a picture of that rule. The rule is the part worth building
first. Proposal, not agreed.

### 1. The next-step rule — derived, never stored

One function answers: *given a campaign, which step is it on, and what is next?*
It reads saved records only. It adds no field.

| Step | Done when | Evidence read |
|---|---|---|
| Describe the role | `job_title` and `location` and `vacancies` are set | `Campaign` row |
| Add the job description | `job_description` is non-empty | `Campaign` row |
| Review requirements | the campaign has requirements | `JobRequirement` rows |
| Approve the rubric | a `RubricVersion` is `LOCKED` | `RubricVersion`, `RubricStatus` |
| Upload CVs | a `ProcessingBatch` exists with at least one job | `ProcessingBatch` |
| Assess | an `EvaluationRun` has completed evaluations | `EvaluationRun` |
| Decide | campaign status is `REVIEW` or later | `Campaign.status` |

The next step is the first one that is not done. A step that is started but
incomplete — a job description saved with no requirements extracted — is the
next step, not a finished one.

**`current_step` is not added to the model.** `02-LIFECYCLE-MODEL.md` requires
operative state to be stored and forbids a second workflow state alongside it.
A derived next-step is presentation. A stored one is a rival state machine that
will disagree with `Campaign.status` the first time anything is edited out of
order.

Prove the rule on the existing campaign card as one line — `Next: upload CVs` —
before drawing anything. If the line is right for every campaign in the list,
the rail is then only a picture of a rule already trusted. If the rule is wrong,
that is far cheaper to find on one line of text than inside new furniture.

### 2. The rail — deferred optional proposal, not required delivery

A vertical list of the campaign's steps down one side of the campaign workspace,
each step a rounded marker plus its name, in the order above. Always visible, so
the recruiter can see the whole campaign while working inside one step of it.

Each step is in exactly one of four states, and they must look different:

| State | Means | Click does |
|---|---|---|
| Done, revisitable | recorded, and changing it cannot change what a score means | opens it, editable |
| Done, locked | recorded, and changing it would change what a score means | opens it **read-only**, with the action that creates a new rubric version |
| Next | the first step not done | opens it, editable — this is where a click on the campaign lands |
| Not reached | an earlier step is not done | nothing; it is not a link |

The locked state is not decoration. `DECISIONS.md`, 2026-09-12 decided that past
rubric approval the job description and requirements are read-only in place,
changed only through a new rubric version, while administrative fields stay
freely editable. A rail whose steps all look alike promises editing it cannot
deliver, and the recruiter learns the rules are arbitrary.

**The rail shows what is recorded. It never shows a count or a percentage.**
This document already states it at `Campaign workspace layout` item 2, and
`AGENT-START-HERE.md` §5 repeats it: the phases are navigation groups, "not a
replacement state machine or false completion percentage". Four of seven markers
filled is a completion percentage wearing circles.

### 3. Opening a campaign lands on the next step

A click on a campaign card opens the workspace at the step the rule names, not
at a summary the recruiter must read before acting. The rail travels with it, so
landing deep never costs the overview — that is the whole reason the rail and
this behaviour are proposed together.

Deep links and browser Back keep working: the landing step is a real URL, and
every rail marker is a real URL. `AGENT-START-HERE.md` §5 requires both.

### 4. Two stage vocabularies — pick one for the rail

The word "stage" already means two things in this product:

- **Campaign steps** — the seven above, describing one role's setup and run.
- **CV processing stages** — Arrived → Read → Assessed → Checked → Ranked, per
  file, currently static sample markup in `web/campaigns.html`.

The rail is the **campaign's** steps. CV processing is detail shown inside the
Upload CVs and Assess steps. Leaving both unnamed makes every later conversation
about "the stages" ambiguous.

### 5. Candidate 360 — one name doing two jobs

The user reported this as confusing to think about. It is confusing because two
different questions share one name:

| Question | Needs | Proposed name |
|---|---|---|
| "Show me this candidate **for this role**" | campaign and application context — a score is meaningless without the rubric it was scored against | **Candidate 360**, always opened from a campaign, always scoped |
| "Show me this person **across everything**" | cross-campaign history for one person | a candidate **finder** — a search that leads *into* a scoped Candidate 360 |

`AGENT-START-HERE.md` §5 already requires that candidate actions retain campaign
and application context. One screen that tries to be both breaks that rule for
the half of its traffic that arrives without a campaign. Two names, two entry
points, and the confusion goes away.

### Current order — supersedes the earlier rail-first sequence

1. Preserve implemented direct cards and saved-stage destinations.
2. Complete stage persistence, approval/version handling and upload recovery.
3. Verify the complete resumed screening path and campaign isolation.
4. Continue contextual candidate, comparison and reporting work.
5. Consider a rail only if later usability evidence justifies it; it is not a gate.

See `08-TWO-PERSON-DELIVERY.md` section 9 for owners, acceptance and dependencies. Remaining earlier layout/slice proposals are options, not newly authorized implementation.
