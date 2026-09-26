> # STOP — THIS FILE IS NOT THE CURRENT SESSION STATE
>
> **Subhadeep is the current session state that needs to be checked right now.**
>
> Read `talent-intelligence-system/docs/SESSION-STATE.md` on the current branch.
> That branch is spelled **`Subodhip`** in git; "Subhadeep" is the owner whose lane
> it is. Check it with `git -C talent-intelligence-system branch --show-current`.
>
> Everything below this line is a dead prototype kept for reference. It names the
> wrong tree, the wrong branch and stale test counts. Do not restore from it, do
> not act on it, and do not report its contents as the current position.

# Talent Intelligence System — Status and Continuation Report

**Paste this whole file as your first message in a new Claude session.**

Repo: https://github.com/ankushsaxena130/talent-intelligence-system
Branch: `phase-d` · Alembic head: `4f28eb855061` · **345 tests passing**

---

# PART 0 — How to work with me on this

- I'm on **Windows** (PowerShell, VS Code, venv, SQLite for local dev). Docker
  is not set up.
- Give me **exact PowerShell commands, one line at a time**.
- Deliver code as a **`git apply`-able patch plus the individual files**.
- **My files have CRLF line endings; your patches will have LF. I must always
  use `git apply --ignore-whitespace`.** Put that in every instruction.
  Patches that only add files work either way; patches that modify existing
  files fail without it.
- **Verify the patch applies to a clean clone before giving it to me.**
  Several have failed on my machine.
- When writing files with Python, **read and write bytes** or restore CRLF
  afterwards. `write_text()` normalises line endings and turns a 10-line
  change into a 900-line diff.
- PowerShell mangles nested quotes in `python -c`. Write a `.py` file with a
  here-string instead.
- **Stop uvicorn before any git operation** — Windows locks `*.db`.

## Running it locally

Terminal 1 (the `$env:` line is required, see Gotcha 1):

```powershell
$env:QUEUE_BACKEND = "inline"; python -m uvicorn app.main:app --port 8000
```

Terminal 2:

```powershell
cd web ; python -m http.server 8124
```

Open `http://localhost:8124`. API docs at `http://localhost:8000/docs`.

---

# PART 1 — WHAT IS DONE

## Architecture decisions already made (do not relitigate)

1. **Two codebases were reconciled.** The client's `Recruitment-360-Delivery`
   bundle contained a second backend with no Phases A–C (memory-only runs,
   Azure OpenAI). **This repo's backend is canonical**; the bundle's static
   `frontend/` is canonical for UI and lives at `web/`. The bundle's Azure
   cost/telemetry subsystem was dropped.
2. **The frontend was not rewritten.** `app/api/compat.py` serves the
   contract the delivered UI already expects. No HTML/CSS file was replaced.
3. **Deterministic-first scoring.** Every score comes from rubric weights,
   taxonomy matches and the parsed experience timeline. The LLM may only
   adjust a criterion within ±15 points where evidence already exists, and
   never sees the eligibility rules. **Scoring runs with no model at all.**
4. **Unverifiable is not failed.** When a fact cannot be established from the
   CV, the eligibility finding is `indeterminate` and the candidate goes to
   REVIEW_REQUIRED — never auto-disqualified, never silently passed.
5. **Confidence is not the score.** A thorough CV lacking a skill scores 0
   with HIGH confidence; a two-line CV scores low with LOW confidence.
6. **An override never mutates an evaluation.** It is a separate
   `CandidateAction` row. Both views stay on the record.
7. **LLM provider is Groq** (`langchain-groq`). Azure was considered and
   dropped.

## Backend — Phases A to H, complete

| Phase | What | Migration | Tests |
|---|---|---|---|
| A | Campaigns, job requirements (mandatory/preferred/informational), 11 requirement categories | `92eec49b510e` | 11 |
| B | Rubric versioning, weights summing to exactly 100, disqualification rules, approval workflow, controlled re-evaluation | `63d33e3e05be` | 34 |
| C | Bulk PDF/DOCX intake, retained documents, queue abstraction, duplicate detection, 10 error codes | `4b653d768425` | 38 |
| D | Rubric-driven per-criterion scoring, skill equivalence taxonomy, experience timeline engine, deterministic eligibility engine, evidence with CV page/section, confidence, immutable results | `42eb3fd3b075` | 96 |
| E | Challenge Agent — six deterministic checks | `1e9e5fabd527` | 38 |
| F | Candidate 360 completion, disposition/override/comments, audit trail, benchmarks | `4f28eb855061` | 41 |
| G | Comparison, what-if analysis, KPI aggregates | none (derived) | 32 |
| H | Candidate 360 PDF, CSV/XLSX export, SuccessFactors field mapping | none | 25 |
| — | Frontend integration + wiring | none | 30 |

### Key modules

```
app/core/skill_taxonomy.py     three-tier matching: EXACT / EQUIVALENT / ADJACENT (0.55)
app/core/evidence_index.py     recovers PDF page numbers, verified byte-for-byte
app/core/experience_engine.py  union-of-stints years, gaps, staleness, contradictions
app/core/eligibility_engine.py disqualification rules, arithmetic, outside the LLM
app/core/criterion_scorer.py   five outcome classifications, per-criterion confidence
app/core/challenge_engine.py   six checks, never alters a score
app/core/candidate_360.py      category rollups, next action, validation questions
app/core/analytics.py          comparison, what-if, KPI aggregates
app/core/report_builder.py     Candidate 360 PDF in the client palette
app/core/ats_export.py         SuccessFactors field mapping, CSV + XLSX
app/api/compat.py              serves the delivered UI's contract
```

### Client requirement coverage

**Fully met:** campaign and job setup; bulk CV screening; candidate
evaluation and ranking (all five classifications); Challenge Agent (all six
checks); **all 16 Candidate 360 sections including export**.

**Not met:** RBAC; validated throughput; live ATS integration.

## Frontend — 10 of 12 screens live

| Screen | State |
|---|---|
| `index.html` HR KPI Dashboard | ✅ wired |
| `campaigns.html` Control Tower | ✅ wired |
| `rubric.html` Rubric Review | ✅ wired |
| `leaderboard.html` Leaderboard | ✅ wired |
| `candidate.html` Candidate 360 | ⚠️ wired but see Known Issue 1 |
| `compare.html` Comparison | ✅ wired |
| `whatif.html` What-if | ✅ wired (adaptive bands) |
| `decisions.html` Decision | ✅ wired; export buttons not connected |
| `performance.html` Performance | ✅ wired (trend deliberately not) |
| `new-campaign.html` | ✅ runs the full modern pipeline |
| `audit.html` Audit | ❌ static — see Known Issue 2 |
| `developer.html` | ❌ dead — calls a removed endpoint |

**The theme must not change.** All colour lives in `web/assets/app.css` as
CSS custom properties (`--maroon:#971A3E`, `--sand`, `--gold`, and the
four-step verdict scale `--v-strong`/`--v-potential`/`--v-review`/`--v-no`).
Wiring adds only `id` attributes plus one appended `<script>` before
`assets/app.js`. Tests fail if a hex colour appears in a wired page's body.
`web/rubric.html` is the reference implementation — read it first.

**Follow `web/DATA.md` language rules** in anything visible: plain English,
never an enum or error code, never a percentage without its denominator,
never a saving without its baseline, never the words demo/sample/mock/
placeholder, and always state that AI recommends while a person decides.

---

# PART 2 — KNOWN ISSUES

## 1. `candidate.html` shows the design example unless given a parameter

Opening it bare, or from the top nav, shows the shipped example (Haitham
Al-Otaibi, CAM-2611). It accepts `?evaluation=`, `?candidate=` or
`?campaign=`, and works with any of them.

A patch was written to make leaderboard rows link through with
`?evaluation=<id>`, but **it failed to apply** against the local
`leaderboard.html`, which has diverged from the remote. Unresolved.

**To fix:** diff `web/leaderboard.html` against the committed version, then
in the `results.forEach` loop change `makeElement('div', 'lb-row')` to an
anchor with `href='candidate.html?evaluation=' + score.evaluation_id`, and
drop the `aria-disabled` attribute. `evaluation_id` is already on every score
from `compat.py`. Also update the note text that still says *"Candidate
detail and decisions are not connected yet"* — that is no longer true.

## 2. The audit trail is thin

`audit_events` only records dispositions, overrides and comments. Nothing
writes events for campaign creation, rubric approval, uploads or assessment
runs, so `audit.html` would be nearly empty. `AuditAction` already has the
enum values.

**To fix:** call `disposition_service.record_audit()` from
`campaign_service`, `rubric_service`, `processing_service` and
`evaluation_service` at each state change. Then wire `audit.html` — it has no
inline script, so it is a clean append following the `rubric.html` pattern.

## 3. Two mislabelled commits in history

`ee33868` is labelled "Phase E" but contains an abandoned parallel Phase F
(`app/api/decision.py`, `decision_service.py`, migration `7d2a4f5c91b8`).
Those files are absent from the working tree and there are no duplicate
routes, but **`app/db/models.py` carries ~45 unused lines from it**. There is
also an empty migration `707237c86d96` (all `pass`), already stamped, which
`42eb3fd3b075` chains after — leave that one alone.

**To fix:** identify the unused model classes from `git show ee33868 -- app/db/models.py` and remove them in their own commit.

---

# PART 3 — WHAT IS LEFT, AND HOW TO DO IT

Ordered by value. Items 1–3 are small; 4–6 are substantial.

## 1. Wire the export buttons on `decisions.html` (small)

The endpoints exist. `decisions.html` currently disables them with
"Export is not available yet".

- Point the CSV control at `GET /api/campaigns/{id}/export.csv`
- Add an XLSX control → `GET /api/campaigns/{id}/export.xlsx`
- Add a "Download assessment" control per candidate row →
  `GET /api/evaluations/{id}/report.pdf`
- Render the mapping table from `GET /api/exports/ats/field-mapping` rather
  than the hardcoded copy, so the screen and the export cannot drift
- **Leave "Send to SuccessFactors" disabled.** There is no such endpoint and
  a live integration is not agreed.

Note export defaults to `decided_only=true`. If nothing is decided it
returns 422 with a plain message — surface that rather than a silent failure.

## 2. Fix the two known issues above (small)

## 3. Three outstanding requirement gaps (small)

- **Folder upload.** `new-campaign.html`'s dropzone lacks `webkitdirectory`.
  The requirement explicitly says "drag-and-drop **folder** upload". Add
  `webkitdirectory multiple` and filter to `.pdf`/`.docx` in JS.
- **Retry button.** `POST /api/processing/jobs/{id}/retry` exists and nothing
  calls it. Add it to the held-files panel on `campaigns.html`. Jobs with
  `max_attempts = 0` cannot be retried — don't offer it for those.
- **Missing campaign fields.** The form doesn't collect `business_unit`,
  `recruiter`, `hiring_manager` or `target_completion_date`.
  `POST /api/campaigns` accepts all four and the requirement asks for them.

## 4. RBAC (substantial)

Four roles: recruiter, hiring manager, admin, reviewer. Today **all users see
everything.**

`app/core/auth.py` and `scripts/manage_tenants.py` duplicate the same
tenant-plan schema against a *separate* SQLite database (`tenants.db`) that
Alembic does not manage. **De-duplicate those first**, then add roles as a
proper Alembic-managed table. Do not extend `tenants.db`.

Enforcement points that matter: rubric approval (recruiter only), override
(recruiter or hiring manager), export (audited per actor), audit view (admin
and reviewer).

## 5. Postgres verification (substantial, do before any volume work)

**Postgres has never been run.** Every one of the 345 tests is SQLite-only.
`docker-compose.yml` defines it but it has never been started.

Where I would expect dialect problems: the `JSON` columns (`category_scores`,
`experience_profile`, `observed`, `before`/`after`), the `Enum(native_enum=False)`
columns, the `autoflush=False` aggregate queries, and the timezone-naive
datetime handling in `_aware()` — SQLite returns naive datetimes and Postgres
does not, so that helper may behave differently.

Run the full suite against Postgres before trusting any of it.

## 6. Benchmarking (substantial — and a commercial risk)

**The 10,000 CVs/month design target is completely unvalidated.** No
benchmarking script exists, and no timing has ever been measured.

Needed: a generator for realistic volume, per-stage timing (intake, parse,
score, challenge), and a written `BENCHMARKING.md` stating what hardware
produced the numbers. Until that exists, **no batch-size or processing-time
commitment should be made to the client.** The requirement wording already
says these are "to be confirmed through benchmarking on the client's
intended hardware" — keep it that way in writing.

Note Phase C has no thread-pool backend deliberately: concurrent SQLite
writers hit write locking. Real concurrency needs Postgres plus the `rq`
backend, which is Linux-only.

## 7. Skill taxonomy tuning (substantial — highest quality impact)

`app/core/skill_taxonomy.py` has ~200 alias groups and ~30 adjacency groups,
all hand-curated and **slanted toward technology, security and consulting.
It has never seen a petrochemical JD.** For "console hours on a live
continuous-process unit" or "permit-to-work authority" it falls back to
generic term matching.

Four real client JDs sit in `sample-inputs/job-descriptions/`. Extending the
taxonomy is a data edit, not a code change. **This is the single change most
likely to improve real-world scoring quality, and the most likely to
embarrass a demo if skipped.**

Related: "industry and functional experience" and "role seniority and
responsibility alignment" are requirement categories that score through
generic term matching with no taxonomy behind them.

## 8. Smaller items

- **OCR** for image-only PDFs, currently held as "Photographs of a CV, with
  no text to read". Roughly a third of held files in the client's own data
  are this category.
- **`developer.html`** — dead. Remove its nav link from all pages, or rebuild
  it on `GET /api/analytics/kpis`. Don't leave a broken page.
- **Live SuccessFactors integration** — needs a sandbox tenant, OData
  credentials, and an OAuth client approved by the client's IT. That is
  calendar weeks, not code. The field mapping in `ats_export.py` is the
  payload either way.
- **`PROJECT_GAP_ANALYSIS.md`** in the repo root still describes pre-Phase-A
  state and actively misleads. Delete or rewrite it.

---

# PART 4 — GOTCHAS (do not rediscover these)

1. **`QUEUE_BACKEND` must be a shell variable, not just in `.env`.**
   `queue.backend()` reads `os.environ` directly, and pydantic-settings only
   loads `.env` for its own fields. Without `$env:QUEUE_BACKEND = "inline"`
   in the window running uvicorn, uploaded CVs sit `QUEUED` forever and every
   screen looks empty. **This cost hours.** Drain stuck jobs with
   `python scripts\run_worker.py` (no arguments).
2. `SessionLocal` is `autoflush=False`. Aggregate queries depending on a
   pending ORM change need an explicit `db.flush()`.
3. SQLite `DateTime` is timezone-naive. Reuse `_aware()` from
   `processing_service` / `evaluation_service`.
4. FastAPI stores routers lazily; use `app.openapi()["paths"]` to introspect.
5. `app/utils/document_parser.py` loads spaCy at import time. Import lazily.
6. `app/agents/scoring_agent.py` constructs `ChatGroq` at module import, so
   importing it requires `GROQ_API_KEY`. Phase D imports it lazily — keep
   doing that.
7. **A model referencing an enum declared later in `models.py`** cannot use
   `Mapped[TheEnum]`; the forward ref won't resolve. Use `Mapped[str]` with an
   `Enum(...)` column type, as `evaluations.next_action` does.
8. **List endpoints are summaries.** `GET /rubric/versions` carries no
   `weights` or `disqualification_rules` — reading them off the list renders
   a silently empty rubric. Use `/rubric/active` or `/rubric/versions/{n}`.
9. **Two score scales.** `leaderboard.html` prefers `hiring_match_pct`
   (0–100) and falls back to `weighted_total * 10` (legacy 0–10).
   `dimensions[].score` is 0–10; `criteria[].raw_score` is 0–100.
10. **`null` is not zero.** Category scores, `score_distribution`,
    `benchmarks` and `position` are `null` when there isn't enough data.
    Render "Not assessed" or hide the section. Distribution statistics are
    withheld below four candidates by design.
11. **`page_number` is null for DOCX** — no page concept in the extractor.
    Cite the section alone.
12. **`indeterminate` is not `triggered`.** Indeterminate means not
    verifiable, not failed.
13. **Two error shapes.** `/api/documents/extract-text` and `/api/runs/*`
    return `{error:{code,message,request_id}}`. Everything else returns
    FastAPI's `{"detail": ...}`, where detail may be a string or
    `{message, errors}`.
14. **A malformed `.env` cost hours once.** One line had a model name and an
    API key concatenated with no newline, producing a 404 that read like a
    model problem. Check `.env` has one setting per line, no quotes, and a
    trailing newline.
15. **`.env` must be gitignored** — it has contained live API keys.
16. Browser **service workers cache aggressively**. After changing a page,
    unregister the worker (DevTools → Application → Service Workers) or the
    old version keeps loading. `127.0.0.1:8124` is a clean origin if needed.

---

# PART 5 — UNUSED MODULES: REUSE, DON'T REBUILD

`interview_generator.py` (LLM-only, no fallback — wrap it),
`candidate_comparator.py`, `summary_generator.py`, `heatmap.py`,
`skill_gap_forecaster.py`, `knowledge_graph.py`, `multi_jd_matcher.py`,
`bias_audit_agent.py` (**exists but is NOT wired — do not claim bias
testing**).

`report_generator.py` was deliberately **not** reused for Phase H: it renders
in dark navy/teal against the client's maroon-on-sand design, and consumes
the legacy five-dimension shape where twelve of the sixteen Candidate 360
sections don't exist. `report_builder.py` replaces it for the modern path;
the old module stays for the legacy pipeline.

---

# PART 6 — RISK REGISTER

| Risk | Severity | Note |
|---|---|---|
| 10,000 CVs/month unvalidated | **High** | A commitment may already have been implied |
| Taxonomy never tuned to the client's domain | **High** | Most likely cause of poor demo scoring |
| Postgres never exercised | Medium | All 345 tests are SQLite-only |
| No RBAC | Medium | All users see everything |
| Audit trail thin | Medium | Only decisions are recorded |
| No live ATS integration | Medium | File export works; API needs client IT |
| No OCR | Low | Degrades gracefully — files held, not lost |

---

# PART 7 — CLIENT REQUIREMENTS (verbatim, for reference)

AI recommendations must never be presented as autonomous hiring decisions.
Rankings show overall score, criterion-level scores, confidence, and
supporting evidence. Candidate 360 must contain: executive recommendation
(Strong Fit / Potential Fit / Review Required / Not Recommended), overall
score and confidence, eligibility result, mandatory-requirement score,
skills/experience/education/certification scores, strengths, material gaps
and risks, evidence excerpts with CV page or section references, missing or
ambiguous information, suggested recruiter validation questions, suggested
interview focus areas, Challenge Agent findings, comparison with campaign
benchmarks, recommended next action, and recruiter comments/override/final
disposition.

The nine required screens: HR KPI Dashboard, Campaign Control Tower,
Requirement and Rubric Review, Candidate Leaderboard, Candidate 360,
Candidate Comparison, What-if Analysis, Decision and Export, Audit and
Administration.

The design target is 10,000 CVs per month. Actual batch-size and
processing-time commitments will be confirmed through benchmarking on the
client's intended hardware.
