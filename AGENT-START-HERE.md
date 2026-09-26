# Recruitment 360 — agent start and execution guide

**Purpose:** Read the complete plan, reconcile what exists, advance the next authorized slice, verify it, and update what is done versus left. This is the single entry document; linked plans remain the authoritative checklists. Do not create a second competing backlog here.

**Two-person work:** first identify whether you are acting for Subhadeep or Ankush and read [ownership and GitHub workflow](docs/plan/08-TWO-PERSON-DELIVERY.md). Its file ownership and central-status handoff rules govern concurrent execution. If identity is unknown, read/review freely but establish the lane before editing product files. Do not switch or publish branches merely by reading these instructions.

## 1. Establish the correct project

### Required every-session checkpoint: TWO-PERSON-OWNERSHIP

Restore this checkpoint after a new session, context reset or handoff, before product edits:

1. Read `docs/plan/08-TWO-PERSON-DELIVERY.md`; restore its file ownership and merge rules.
2. Establish acting developer from explicit session context. This originating user is Subhadeep; a task explicitly assigned to Ankush uses Ankush's lane. Do not infer identity from Git author configuration or machine username. Ask only if identity remains unknown.
3. Restore lanes: **Subhadeep = `web/**`, browser acceptance, product and central plans. Ankush = backend `app/**`, migrations, integrations and Python tests.** Exact exceptions are in 08.
4. Verify branch/working tree and bootstrap status. **The current branch is `Subodhip`** — confirm with `git branch --show-current` before editing. It was branched from `consolidated`, which is the parent and not the place to work. After recorded bootstrap, use owner/task branches targeting `azure-provider`. Never assume publication happened or push automatically.
5. Name acting developer, selected plan IDs and owned paths in the starting status. Crossing ownership requires an explicit bounded transfer; reading/reviewing another lane is allowed.
6. Preserve this checkpoint and the 08 read reference whenever saving/compacting session state. Ankush reports central-checklist deltas through his PR/handoff; Subhadeep consolidates them. Contract-first, API-before-dependent-UI merge order remains active.

- Work only in `talent-intelligence-system`, on branch **`Subodhip`**. Read [CLAUDE.md](CLAUDE.md) for project constraints and current runtime commands.
- Ignore sibling prototypes: `app/`, `app-v2/`, `talent-intelligence-system-final/`, `Recruitment-360-Delivery/`. Their session states are obsolete. The canonical project's own `app/` is backend code, not the sibling prototype.
- Read [session state](docs/SESSION-STATE.md) on `Subodhip` for handoff context, then verify the branch and working tree. Preserve existing uncommitted work. Three other files in this workspace look like a session state and are dead: `../docs/SESSION-STATE.md`, `../Recruitment-360-Delivery/docs/SESSION-STATE.md` and `PROJECT-STATUS-AND-CONTINUATION.md`. Each opens with a STOP banner. Never restore from one of them.
- Before implementation, run `git fetch origin` and `git log --oneline HEAD..origin/azure-provider` as required by CLAUDE.md. Review overlapping work before editing; fetch does not authorize merging or resetting.
- Do not push `consolidated` without explicit user authorization. Do not install dependencies into the verified environment as a routine setup step.

## 2. Read the whole planning set before choosing work

Read these documents in order. Read planning documents fully, in bounded batches; do not scan the whole source tree. On subsequent turns in the same session, reread only changed plans and relevant sections. If a listed file is missing, report the gap; do not substitute a sibling project's file.

| Order | Document | Extract |
|---|---|---|
| 1 | [Plan index](docs/plan/README.md) | Inventory and checklist conventions; include any subsequently added planning documents |
| 2 | [Master backlog](docs/plan/00-MASTER-BACKLOG.md) | B01–B24, priorities, owners, checked and unchecked acceptance items |
| 3 | [Demo plan](docs/plan/01-DEMO-MONDAY.md) | D1–D8, LIVE/PROXY/FUTURE boundary, rehearsal and go/no-go gates |
| 4 | [Lifecycle model](docs/plan/02-LIFECYCLE-MODEL.md) | Operative states, allowed transitions, ownership, missing mechanisms |
| 5 | [Identifier model](docs/plan/03-IDENTIFIER-MODEL.md) | Campaign/candidate/application/run distinction; proposals versus implemented IDs |
| 6 | [Known defects](docs/plan/04-KNOWN-DEFECTS.md) | Open X-items, severity, reproduction and verification requirements |
| 7 | [Post-demo roadmap](docs/plan/05-POST-DEMO-ROADMAP.md) | Increment dependencies and proposed sequencing changes |
| 8 | [Wide pass](docs/plan/06-WIDE-PASS.md) | End-to-end coverage, real state/audit with simulated external actions; historical delivery overlay |
| 9 | [Campaign journey UX](docs/plan/07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md) | Guided setup, parallel campaign work, progressive disclosure, recovery and acceptance slices |
| 10 | [Decisions](docs/DECISIONS.md) | Accepted decisions and reasons; distinguish recommendations still awaiting review |
| 11 | [Two-person delivery](docs/plan/08-TWO-PERSON-DELIVERY.md) | Complete owner matrix, exclusive files, common-baseline gate, contract/PR order and central-document handoff |

Dates and test counts in these files describe earlier observations. An old “not built” paragraph may conflict with a newer completed checklist; neither is fresh runtime evidence. The September 2026 demo schedule is historical once its dates pass. Do not replay an expired schedule or parallel-agent assignment automatically.

## 3. Reconcile done versus left before building

Build a compact status report from existing IDs. Cover all B01–B24 at a summary level, and relevant D/W/X items. Group related items if useful, but leave none unaccounted for. Inspect only relevant code/tests to resolve contradictory or unsupported claims.

Use two separate dimensions:

- **Delivery status:** done / partial / not started / blocked / deliberately dropped.
- **Evidence:** verified this session / recorded earlier / unverified or conflicting.

A backend route without a working screen is partial for a user-facing feature. A proxy can be complete for its explicitly simulated scope while its external integration remains pending. A written plan is not implemented UX. Historical “552 passed” is not a current test result.

Report with this format:

| Plan ID | Done / working scope | Left / next acceptance item | Evidence and limitation |
|---|---|---|---|
| Existing ID | Concrete behavior, or none verified | Concrete remaining behavior/dependency | File/test/browser observation; identify historical evidence |

For any conflict, preserve the evidence, identify the affected item and correct only what is established. Current code establishes implementation facts; it does not silently approve a design or product policy. Latest explicit user decisions govern intent. Ask only when an unresolved decision materially blocks the selected work; continue independent authorized work.

## 4. Choose and complete one authorized slice

1. Map the user's request to existing B/D/W/X IDs. Name selected IDs and acceptance target. Do not invent unrelated scope or silently change agreed priorities.
2. Honor accepted dependencies and urgent defects. UX proposal recommends durable B14/X18 setup before broader navigation; proposed roadmap changes still require sequencing agreement.
3. Check approval status: user-requested planning can proceed as planning. A proposal alone does not authorize implementing unresolved policy or architecture. Do not ask again for actions already authorized.
4. Read affected modules, callers, tests and relevant domain decisions. Reuse current API/state contracts; identify unsupported assumptions before coding.
5. Implement a small complete slice. Use failing regression tests first for non-trivial fixes/features. Preserve existing valid routes and behaviors.
6. Validate targeted tests and actual user path. Run required full suite once at the appropriate completion gate; record observed outcome and failures honestly. Browser work follows the project's `/browse` requirement.
7. If blocked, name exact dependency and remaining work. Do not mark the item complete because a screen renders or a tool call returned successfully.

## 5. UX rules for every slice

- **Act → Understand → Inspect:** surface essential context, next task, status and blocker; reveal reasoning/options next; provide direct access to sources, versions and complete history.
- User's 20/80 principle is a usability hypothesis, not a quota. Validate routine work with recruiters. Never hide material evidence gaps, unsaved changes, missing approvals, failures, stale results or simulated-action labels.
- Preserve Today. Campaigns owns role setup/resume; candidate actions retain campaign/application context. Keep specialist screens accessible without making them obligatory detours.
- Setup is guided and durable. Active campaigns support candidates in different stages and multiple batches/vacancies. Four phases are navigation groups, not a replacement state machine or false completion percentage.
- One saved campaign throughout setup; no cosmetic save, duplicate creation on retry or silent auto-approval. Verify contracts before claiming guarantees.
- Operative lifecycle state stays stored. Suggested next tasks are presentation derived from authoritative records, not invented workflow transitions.
- AI recommendation remains separate from human decision. Accepted offer is not joined. Proxy outbound actions retain visible simulation labels beside the action.
- Preserve deep-link context and browser Back. Full details must remain reachable; progressive disclosure must not become nested-panel navigation.

## 6. Update the source checklists after every slice

In the same turn, before reporting completion:

During concurrent work, Subhadeep performs central-document edits below. Ankush supplies exact deltas and evidence through his PR or `docs/handoffs/ankush/` in the same turn; Subhadeep consolidates after verification/merge. Both report unmerged work as branch-complete, not integrated product completion.

- [ ] Update relevant items in [master backlog](docs/plan/00-MASTER-BACKLOG.md).
- [ ] Update affected [demo checklist](docs/plan/01-DEMO-MONDAY.md) or [wide-pass checklist](docs/plan/06-WIDE-PASS.md), where applicable. Do not rewrite historical test observations as new results.
- [ ] Update [known defects](docs/plan/04-KNOWN-DEFECTS.md) for defects found/fixed; preserve stable IDs.
- [ ] Update affected model/UX/roadmap documents when an approved contract or decision changes.
- [ ] Append decisions with plan IDs, alternatives, reason and owner to [decisions](docs/DECISIONS.md). Label proposals as proposals.
- [ ] Save [session state](docs/SESSION-STATE.md), under 2,000 tokens, with completed work, open tasks, actual verification, decisions and exact next task. Include this entry document in resume reads.
- [ ] Finish with **Done / Left / Blocked / Verification / Next**. Cite changed artifacts. State when no code or tests changed.

Checkbox meanings: `[ ]` not started; `[~]` partial/in progress; `[x]` done with supporting evidence; `[-]` intentionally dropped with reason. Never check an entire feature because only its planning document or backend half is complete.

## Handoff prompt

> Read AGENT-START-HERE.md in talent-intelligence-system. Follow its complete planning read order, reconcile B01–B24 and relevant demo/defect items against available evidence, report what is done and left, then progress the next authorized slice. Preserve progressive disclosure and update the authoritative checklists and session state after verification. Do not treat proposals or historical test counts as completed implementation.
