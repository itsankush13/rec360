# Two-person delivery — Subhadeep and Ankush

Date: 2026-09-12. Plan IDs: B01–B24, related D/W/X items. This allocates remaining work and maintenance; it does not reopen completed features or authorize pushing the held branch.

## 1. Split by files, coordinate by API contract

**Subhadeep: portal UX, browser acceptance, product requirements, reporting presentation and plan integration.**

**Ankush: backend/API, scoring, persistence, migrations, integrations, backend verification and deployment implementation.**

Why this boundary: lifecycle, offers, interviews, approvals and metrics share `app/db/models.py`, `lifecycle_service.py`, `disposition_service.py` and router registration. Dividing those features between people would still collide on the same backend files. Portal navigation repeats across HTML pages and shares `web/assets/app.js`, `journey.js`, `app.css` and `web/sw.js`; give that whole surface one editor.

Tradeoff: backend work is likely the bottleneck. Frontend can progress against agreed contracts using existing APIs and explicitly labeled development fixtures; unfinished integration must not be called done. Rebalance by transferring a complete bounded file set for one PR, never by both editing the same shared file. No architecture rewrite or new framework is needed for this division.

## 2. File ownership — applies to every task

Paths relative to canonical `talent-intelligence-system/`. More-specific rules override broad rules. Ownership includes fixes, formatting, generated changes and tests, not just features.

| Files | Sole editor | Other person's contribution |
|---|---|---|
| `web/**`, including every HTML page, shared assets, navigation, manifest and service worker | Subhadeep | Ankush supplies API contract, labels and error semantics |
| `app/**`, including `app/main.py`, agents, workers, schemas, DB models, utilities and backend/core modules | Ankush | Subhadeep supplies behavior/acceptance requirements |
| `alembic/**`, `alembic.ini`, backend dependency/runtime/deployment manifests and future `.github/workflows/**` | Ankush | Subhadeep reviews deployment/product constraints |
| Existing Python `tests/**`, including `conftest.py`, `test_frontend_integration.py` and `test_recruitment_360_journey.py` | Ankush | Subhadeep supplies consumer assertions/browser scenarios; filenames saying frontend/journey are currently API tests |
| Future isolated `tests/browser/**` | Subhadeep | Ankush reviews cross-boundary coverage; shared runner/dependency changes remain Ankush-owned |
| `docs/plan/**`, `docs/DECISIONS.md`, `docs/SESSION-STATE.md`, `AGENT-START-HERE.md`, `CLAUDE.md`, root README and product/context maps | Subhadeep | Ankush supplies PR evidence and precise checklist deltas; no parallel central-document edits |
| Future `docs/contracts/<plan-id>-<topic>.md` | Ankush authors, Subhadeep reviews | Settle shape before dependent UI work; comments/proposed changes through PR review |
| Future `docs/handoffs/ankush/**` | Ankush | Per-PR evidence and session handoff; Subhadeep consolidates central status |
| Future `docs/handoffs/subhadeep/**` | Subhadeep | Per-PR evidence and session handoff |
| `.github/CODEOWNERS`, future `.github/PULL_REQUEST_TEMPLATE.md` | Subhadeep | Obtain both exact GitHub handles before enabling review routing |
| Any unlisted root/shared file | Assign one editor in task/PR before editing | No implicit shared ownership |

Emergency cross-boundary fix: ask the file owner to make it, or record an explicit temporary transfer covering exact paths and PR. Owner pauses edits until merge; ownership returns afterwards. Reviewer can suggest code without committing into the author's working branch.

## 3. Entire B01–B24 allocation

Lead coordinates acceptance and dependencies; file ownership above still controls edits. Both halves are required where a feature crosses the boundary.

| ID | Lead | Subhadeep deliverable | Ankush deliverable |
|---|---|---|---|
| B01 complete recruitment journey | Subhadeep | Campaign-centered navigation and complete browser story | Consistent transitions and integrated API journey |
| B02 lifecycle/timeline | Ankush | `timeline.html` clarity, owner/waiting/hold display | Stored states, valid transitions, SLA/reminder mechanics and tests |
| B03 semantic repository discovery | Ankush | `discover.html`, selected-CV preview, understandable source/errors; coordinate client access | `discovery.py`, `cv_source.py`, relevance ranking, source identity and import path |
| B04 audit | Ankush | `audit.html` search, readable detail, export access | Complete event coverage, actor/identity/evidence, export semantics |
| B05 AI decisioning | Subhadeep | `decisions.html`: suggestion/rationale, explicit human confirmation/override | Recommendation contract, validation, persisted decision and audit |
| B06 AI JD | Ankush | `new-campaign.html`: accept/edit/upload/override, uncertainty display | Generation/reuse service, extraction contract and validation |
| B07 scoring/weights | Ankush | `rubric.html`: bounded controls, clear categories and explanations | Correct calculation, criteria granularity, normalization and score tests |
| B08 UX polish | Subhadeep | All portal hierarchy, text, colors, responsiveness and accessibility | Stable plain-language error/status data where needed |
| B09 team review/demo readiness | Subhadeep | Coordinate review, browser rehearsal, findings and go/no-go | Backend readiness, fixtures, defect fixes and test evidence |
| B10 email/replies | Ankush | `comms.html` compose/status and simulation-to-live presentation | Send/receive adapters, application correlation, failures/retries/audit |
| B11 interviews | Ankush | `interview.html` schedule/reschedule/feedback experience | Calendar integration, recorded appointment, response/feedback handling |
| B12 offers | Ankush | `offer.html` HR review, package/revision/response display | Approved template generation, delivery, outcome persistence/audit |
| B13 approvals/governance | Ankush | `approvals.html`, `handoff.html`, policy explanations; collect business rules | Roles, approval chain, cost-centre/policy enforcement and evidence |
| B14 campaign setup/ingestion | Subhadeep | One-ID guided setup, real save/resume, uploads, recovery, contextual workspace | Draft/partial-save contracts, retry protection, version/conflict checks, ingestion |
| B15 candidate reuse/backups | Ankush | Reuse/backup surfaces and prior-outcome visibility | Eligibility/retention/exclusion rules, persistent reuse and backup retrieval |
| B16 comparison/scale | Subhadeep | `compare.html`/`leaderboard.html`: top ten, filters, pagination | Bounded SQL/API queries and scale verification |
| B17 what-if | Subhadeep | `whatif.html`: explicit preview, proposal/approval flow | Preview/proposal/version APIs, separate actors and audit |
| B18 Candidate 360 | Subhadeep | `candidate.html`: progressive evidence, material findings, complete deep dive | Evidence, discrepancy and interview-question completeness |
| B19 dashboard/reporting | Subhadeep | Today, campaigns, `pipeline.html`, `performance.html`: action-first summaries/drill-down | Metrics/action-read contracts, period filters, correct denominators/counts |
| B20 identifiers | Ankush | Copy/search/display and client terminology confirmation | Persistent public IDs/application identity, migrations, correlation/search contracts |
| B21 HR FinOps | Subhadeep | `developer.html` → HR FinOps presentation, volumetrics and business cost comparison | Measured usage/cost data contract and calculation implementation |
| B22 hosting/security/residency | Ankush | Coordinate client/Chiranjib decisions and acceptance constraints | Auth, tenant boundary, approved deployment/runtime, CI and technical evidence |
| B23 commercial positioning | Subhadeep | Coordinate Chiranjib/Kallol, asset-versus-product decision, positioning/cost narrative | Technical feasibility, constraints and implementation estimates |
| B24 continuing roadmap | Subhadeep | Central priorities, checklist reconciliation, decisions/session state | Backend estimates, dependencies and evidence of merged capabilities |

External business/security approvals remain with the named stakeholders; this allocation assigns coordination and implementation, not authority to decide for them.

## 4. Demo/wide-pass and defect ownership

| Items | Allocation |
|---|---|
| D1; W-T/W-A/W-B/W-C/W-D/W-E | Ankush backend state/integration, Subhadeep corresponding timeline/handoff/interview/approval/offer/comms UI |
| D2 / W-F | Ankush search/import backend; Subhadeep discovery UI and client source validation |
| D3 / X2 | Ankush granularity/scoring correction; Subhadeep rubric/leaderboard wording after contract settled |
| D4 / X1 | Ankush identity extraction and regression fixtures; Subhadeep browser acceptance |
| D5 / D6 / D8 | Subhadeep FinOps, colors, comparison UI; Ankush any required cost/query API changes |
| D7 | Ankush JD generation; Subhadeep setup UI |
| W-G | Ankush metric computation; Subhadeep performance/dashboard display |
| X3, X4, X6 | Ankush parser/config/CLI fixes and tests |
| X5, X8, X9, X17 | Retain resolved/withdrawn/historical status where supported; Ankush owns regression/runtime checks, no rebuild from stale plan prose |
| X7 | Subhadeep coordinates safe baseline publication; each author identifies their changes; do not resurrect discarded branch work |
| X10 | Subhadeep integration coordination; both follow branch/path ownership; Ankush sole migration editor |
| X11 | Ankush stage-order/count correctness; Subhadeep outcome chart/display remainder |
| X12 | Ankush SQL limit/offset and scale tests; Subhadeep paginated/top-ten views |
| X13, X16 | Ankush source identity/UNC checks; Subhadeep source-resolution feedback and browser validation |
| X14 | Subhadeep maps ten-step presentation; Ankush reviews state semantics; record agreed mapping centrally |
| X15 | Ankush hold/resume API test; Subhadeep real-record timeline walkthrough |
| X18 | Subhadeep removes duplicate create/cosmetic save in UI; Ankush fills verified draft/retry contract gaps |

Future defects follow affected file ownership. A cross-boundary defect has two linked subtasks, not two editors on one file.

## 5. Common-baseline gate — before parallel development

Publication update, 2026-09-12: user explicitly authorized publishing `consolidated`;
push succeeded to `origin/consolidated` at `eb0fcb6` (planning commit). Branch now tracks
the remote. Bootstrap PR and merge into `azure-provider` remain pending. Subsequent
handoff-document commits may advance consolidated; compare current remote SHAs before
integration. No repository settings changed. Steps below describe the complete gate;
the publication portion is now complete.

Observed locally on 2026-09-12: `consolidated` HEAD `24ec93b`; pending planning edits exist. Local remote refs list `origin/azure-provider`; `origin/HEAD` points to `origin/main`. Remote refs were not freshly fetched in this planning-only pass. Verify again before publishing.

1. Subhadeep inventories and commits only reviewed intended work; preserve unrelated changes. Ankush shares/fetches latest `azure-provider` work. Inspect differences before deciding bootstrap merge contents.
2. With explicit authorization to publish held work, push `consolidated` and open a bootstrap PR **targeting `azure-provider` explicitly**. Resolve conflicts, validate migration chain and tests, review, then merge. Do not use a blind force push or discard the other person's commits.
3. Record the resulting shared `origin/azure-provider` SHA. Both start from that exact accepted baseline. Until this lands, the local `consolidated` rule remains active and there is no shared two-person baseline.
4. After bootstrap, `azure-provider` becomes the shared integration target; `consolidated` is a historical bootstrap branch, not a second live line. Short task branches replace direct development on the shared branch. This supersedes the old work-only-on-consolidated instruction only when bootstrap is recorded complete.
5. Proposed GitHub configuration: protect `azure-provider`, require one review and actual required CI checks, disallow direct/force pushes, and set default PR base appropriately. Settings are not configured by this document. A merge button/default branch is not evidence of the correct target.

## 6. Branches, contracts and merge order

- Separate clones/worktrees; never two people/agents editing one checkout. Each uses their own local database, uploads and runtime state; never commit those or credentials.
- One short-lived branch per bounded slice: suggested `subhadeep/b14-draft-ux`, `ankush/b14-draft-api`. These are naming examples, not branches already created. No permanent “my branch” accumulating unrelated features.
- Every PR targets `azure-provider` after bootstrap. Prefix title with existing plan IDs. List changed paths, dependencies, contract changes, test/browser evidence and exact remaining work.
- Contract-first for a cross-boundary slice: Ankush records route/method, input/output, errors, IDs, pagination, permissions, state/version/retry semantics and sample fixtures; Subhadeep reviews consumption. No mock response treated as a delivered API.
- Prefer additive, backward-compatible API changes. Merge API PR first, then update UI branch from integration and merge UI PR. Feature stays partial until integrated path passes. Breaking changes require an explicit staged migration; do not land an intermediate broken UI.
- While API work runs, Subhadeep can implement independent navigation/disclosures against current APIs and prepare contract-driven UI behind truthful development boundaries. Do not release live-looking controls backed only by fixtures.
- One merge at a time. After first merge, second branch incorporates latest integration (merge or rebase an unshared personal branch), reruns relevant checks, then merges. No blanket ours/theirs conflict resolution.
- Ankush exclusively serializes model/migration changes. Check one Alembic head and upgrade behavior before schema PR merges; do not create parallel migration heads off a stale base.
- Each author runs targeted checks. Ankush owns backend/full-suite evidence; Subhadeep owns browser acceptance. Full suite runs on the integration candidate at release/required merge gate; old counts are not sufficient. CI must be made reproducible by Ankush, not merely named as a required check that never runs.
- Reciprocal review: Ankush reviews API compatibility in UI PRs; Subhadeep reviews user behavior/acceptance in API PRs. Each author remains responsible for technical correctness; a review does not substitute for tests.

## 7. Avoid conflicts in the plans themselves

Subhadeep alone edits central plan checklists, decisions and shared session state. Ankush includes checklist deltas and evidence in PR body or `docs/handoffs/ankush/<plan-id>-<topic>.md`; Subhadeep incorporates them after verification/merge. Both can mark their own PR status, but only central integrator marks the feature done in the master plan.

This ownership-specific handoff replaces the generic instruction for every agent to edit central documents directly during concurrent work. It preserves the requirement to report progress in the same turn without creating markdown conflicts. Unmerged completed work is reported as “verified on branch; not integrated”, not product done.

Cross-boundary completion checklist:

- [ ] Contract agreed; paths owned; dependency PRs linked
- [ ] API and UI merged into same integration baseline
- [ ] Relevant tests and real browser path pass
- [ ] Failure/recovery and permissions verified as applicable
- [ ] No hidden simulated integration or missing evidence
- [ ] Central B/D/X status updated with actual integrated evidence

## 8. First parallel wave

| Subhadeep | Ankush | Merge dependency |
|---|---|---|
| Review B14/X18 UX, define minimal fields/step states and browser acceptance | Verify draft/PATCH/version/retry capabilities; publish precise B14 contract | Agree contract before dependent UI assumptions |
| Fix one-campaign reuse and real save/resume in `web/new-campaign.html`; update campaign links | Implement only missing B14 API guarantees and regressions | API before dependent UI |
| Refine Today/campaign/candidate disclosure using existing API responses | Independently fix confirmed X1/X2/X12 in separate focused PRs | UI wording/query consumption follows changed contracts |
| Maintain source checklists and rehearse integrated slice | Verify migration/runtime/API suite on merged candidate | Both must accept complete user path |

Do not start every B-item concurrently. After first wave, choose next slice from agreed priority/dependency order, retaining the same file boundary.

## 9. Revised Subhadeep queue — direct Start Campaign flow, 2026-09-12

This update supersedes section 8's initial UX tasks and the older mandatory-rail / separate-upload-page interpretation. File ownership and integration gates remain unchanged. User requested alignment with the implemented Start Campaign structure; this is a plan update, not evidence that remaining work is complete.

**Current entry contract:** Today → Start Campaign → create a campaign or choose an existing card. Each card has one primary maroon action naming the next unfinished saved stage. Completed stages lead forward; unfinished stages reopen with saved inputs. All campaign workspaces remains secondary. Preserve current top navigation; do not add a new Campaigns/Candidates/More hierarchy as a prerequisite.

**Already verified locally, not integrated:** direct create/list/resume cards; role/JD save with one campaign ID; saved-stage deep links; approved-to-upload and completed-run-to-shortlist navigation; maroon header; HR profile tags on all 21 app pages. Do not schedule these as unbuilt features.

| Priority / IDs | Subhadeep remaining deliverable | Acceptance / Ankush dependency |
|---|---|---|
| 1 — B14 | Complete saving/restoring edited requirements and rubric work; clear save failures and unsaved-work handling | Leave an unfinished stage, reopen via its card, recover saved edits. Existing role/JD save does not cover edited scoring rows or selected local files. Use agreed APIs; Ankush fills missing persistence/conflict guarantees. |
| 2 — B14 / B13 | Correct approval/version continuation and field editability | Explicit approval uses the correct version; no version-1 assumption, duplicate setup or fictitious approver. Completed/locked work is viewable; revisions follow version rules. Ankush owns API enforcement and identity contract. |
| 3 — B14 | Make upload/assessment recovery work within campaign context | Save setup without CVs; return later through Upload CVs; preserve campaign/batch/run identity; handle held files, retries and interruptions. A standalone upload page is NOT required. Browser-selected files are not called uploaded until server confirms. |
| 4 — B01 / B09 / B14 | Prove full campaign continuation, including failure recovery | Create → save → leave → resume → approve → upload → assess → exact shortlist. Verify two campaigns stay isolated; failed reads never imply empty/completed stages. Existing navigation tests do not prove this whole path. |
| 5 — B18 / B05 / B16 | Continue candidate work from the selected campaign | Contextual Candidate 360, recommendation/rationale controls, shortlist comparison filters/pagination/top ten. Cross-campaign finder is secondary, independent work; no required global navigation redesign. Backend query/recommendation contracts from Ankush. |
| 6 — B19 / B21 / B08 | Reporting, FinOps and remaining UX acceptance | Campaign/date filters, drill-down, business-cost presentation, accessibility and consistent loading/error states. Retain completed header/profile work. Measured metrics/pricing inputs need backend/client confirmation. |
| Ongoing — B24 / integration | Review and commit intended local work, coordinate bootstrap integration and evidence | Shared baseline, reciprocal review, integrated tests/browser checks, current central plans. Publishing remains separately authorized. Client volumes/hosting/commercial coordination remains open. |

**Deferred optional enhancement:** campaign stage rail. Stage visibility is already provided by each card's action and destination. Do not block persistence/recovery or create a mandatory rail task without a demonstrated navigation need.

**Scale follow-up:** cards currently use bounded concurrent detail reads, not a proven large-scale list solution. Validate search/pagination needs; coordinate any summary/pagination API with Ankush. Do not claim that returning all campaign rows scales merely because creation has no cap.
