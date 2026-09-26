# Project Gap Analysis — Talent Intelligence System

_Generated during Phase 0 audit. This reflects the actual state of the repo at
`ankushsaxena130/talent-intelligence-system` as of this session, not the README._

## 1. What already exists (real, working)

### 1.1 AI pipeline (`app/agents/`, `app/core/`)
- **`jd_agent.py`** — Groq LLM call that extracts a flat JD dict (`role_title`,
  `required_skills`, `preferred_skills`, `min_experience_years`,
  `education_requirement`, `key_responsibilities`, `seniority_level`).
- **`resume_parser_agent.py`** — parses PDF/DOCX via `document_parser.py`,
  masks PII/demographic info before sending to the LLM, merges LLM-extracted
  skills with spaCy regex-extracted skills, returns a `CandidateProfile`.
- **`scoring_agent.py`** — real 5-dimension LLM scoring (skills 30%, experience
  25%, education/certs 15%, portfolio 20%, communication 10%), blended with
  FAISS semantic similarity + BM25 into an ensemble score, with a deterministic
  fallback if the LLM returns bad JSON. This is the most mature piece of the
  system.
- **`bias_audit_agent.py`** — LLM-based bias/PII-leak audit on the scoring
  rationale and resume text.
- **`challenge_agent.py`** — LLM-based second opinion with a deterministic
  fallback; currently one risk_level + issues list, not per-criterion.
- **`embeddings.py` / `bm25_retriever.py`** — real FAISS + BM25 hybrid
  retrieval across the candidate pool for a campaign.
- **`multi_jd_matcher.py`** — matches one candidate against several JDs at
  once (multi-role fit).
- **`document_parser.py`** — PyMuPDF/`python-docx` text extraction, naive
  keyword-based section segmentation, spaCy+regex skill extraction.

### 1.2 Backend surface (`api/index.py`)
- A minimal FastAPI app with **3 endpoints**: `POST /api/campaigns/screen`
  (runs the whole pipeline synchronously per request, no persistence),
  `POST /api/campaigns/{id}/rubric` (draft save), `POST
  /api/campaigns/{id}/rubric/approve`. No auth on these routes.

### 1.3 Rubric versioning (`app/core/rubric_store.py`)
- Real SQLite table `rubric_versions` (campaign_id, rubric_json, approved,
  timestamps). This is a genuine seed of Phase 4/5 — but it's a flat JSON blob
  per version, no weight validation, no disqualification rules, no linkage to
  an evaluation run.

### 1.4 Multi-tenant SaaS auth (`app/core/auth.py`, `manage_tenants.py`)
- Real, working OTP-based tenant signup/login against SQLite (`tenants.db`):
  `tenants`, `otp_store`, `sessions`, `tenant_credentials`, `audit_log`
  tables. Plan-based limits (`trial`, `six_months`, `twelve_months`, `admin`)
  enforced via `feature_gate.py`. **Note:** `auth.py` and `manage_tenants.py`
  duplicate the same schema — needs de-duplication, not two sources of truth.
- This is **tenant-level** access control, not user-role RBAC
  (recruiter/hiring manager/admin/reviewer) — different concept, both needed.

### 1.5 Streamlit app (`app/dashboard.py`, `app/pages_ui/*`) — the actual product today
- This, not the React app, is where the pipeline is really wired up.
  `candidates_page.py` calls `run_pipeline()` directly and stores results in
  `st.session_state` — real screening happens here, but **nothing is
  persisted**: refresh the page and it's gone.
- `campaigns_page.py` calls `jd_agent.parse_jd`, has an editable rubric UI, but
  no backing store beyond the flat JSON in `rubric_store.py`.
- Dashboard, Reports, Integrations pages here are still mock data (per
  in-file TODOs).

### 1.6 React frontend (`frontend/`)
- Vite + React 19 + Tailwind + Recharts shell, 6 pages. Only two things are
  wired to the backend at all: `api.js#screenCandidates` (calls
  `/api/campaigns/screen`) and rubric save/approve. Dashboard, Reports,
  Integrations, Settings, Candidate 360, Comparison, and What-if are 100%
  `mock.js` data. `CampaignContext.jsx` exists but is an empty stub — no
  provider, nothing uses it yet.

### 1.7 Supporting utilities that exist but aren't wired into the main flow
`candidate_comparator.py`, `heatmap.py`, `hr_chatbot.py`,
`interview_generator.py`, `knowledge_graph.py`, `skill_gap_forecaster.py`,
`summary_generator.py`, `report_generator.py` (PDF via `reportlab`),
`email_sender.py`. These are real modules worth reusing in later phases
(Candidate 360, interview focus, PDF export) rather than rebuilding.

## 2. What's missing, mapped to the 39-phase spec

| Area | Status |
|---|---|
| Persistent database for campaigns/jobs/candidates/evaluations | ❌ Missing — everything lives in a single HTTP request or Streamlit session |
| PostgreSQL | ❌ Missing — only SQLite (`tenants.db`, rubric versions) |
| Background queue/workers (Redis) | ❌ Missing — pipeline runs synchronously in the request thread |
| Bulk upload with per-file status (queued/processing/failed/duplicate/corrupt/password-protected/retry) | ❌ Missing — file uploader exists, status tracking doesn't |
| Duplicate detection | ❌ Missing |
| Structured requirement engine (requirement_id, category, type, priority, weight, mandatory/preferred/informational, disqualification flag, evidence requirement) | ❌ Missing — JD agent returns a flat unstructured dict, not persisted, not editable |
| Skill taxonomy / equivalence matching | ❌ Missing — matching is exact-string only (`skill.casefold() in candidate_skills`) |
| Rubric weight validation (=100%), disqualification rules, "locked" state | ❌ Missing |
| Rubric → evaluation run linkage, immutable historical results | ❌ Missing |
| Per-criterion evidence (page, section, text span, confidence) | ❌ Missing — only a free-text justification string per dimension |
| Experience engine (gaps, continuity, recency, contradiction detection) | ❌ Missing — `experience_years` is one LLM-guessed float |
| Deterministic eligibility/disqualification engine (mandatory can't be overridden by AI score) | ❌ Missing |
| Rich Challenge Agent (10 checks, per-criterion severity) | ⚠️ Partial — basic version exists, needs expansion |
| Candidate 360 (strengths/gaps/risks/missing info/questions/interview focus/benchmark/override/disposition) | ⚠️ Partial — score bars only, in React; richer data exists in unused modules (`interview_generator.py` etc.) |
| Campaign benchmarking (percentile, averages) | ❌ Missing |
| HR KPI Dashboard / Control Tower with real numbers | ❌ Missing — both frontends show static mock data |
| RBAC (Admin/Recruiter/Hiring Manager/Reviewer) | ❌ Missing — only tenant-level plan gating exists |
| ATS integration abstraction | ❌ Missing — just static badges in the UI |
| Evaluation/campaign-specific audit trail | ⚠️ Partial — a generic tenant `audit_log` exists (login/otp events), not campaign/rubric/evaluation events |
| Document/object storage | ❌ Missing — uploaded files are temp files deleted after each request; nothing is retained |
| Tests | ❌ Missing — no test suite, only manual `test_email.py`/`test_send.py` scripts |
| Benchmarking scripts / BENCHMARKING.md | ❌ Missing |

## 3. Files to modify (not rebuild)

- `api/index.py` → becomes a thin re-export of a new `app/main.py` (keep any existing deploy target working)
- `app/core/rubric_store.py` → extend into the new SQLAlchemy `Rubric`/`RubricVersion` model instead of the flat SQLite table
- `app/agents/jd_agent.py` → keep the LLM call, change its output shape to populate structured `JobRequirement` rows
- `app/core/pipeline.py` → keep as the in-process orchestrator, but it gets called **by a worker task**, not directly inside the request
- `app/core/auth.py` / `manage_tenants.py` → de-duplicate into one module; extend with user-level roles for RBAC (Phase K)
- `frontend/src/lib/api.js`, `frontend/src/context/CampaignContext.jsx`, `frontend/src/pages/Campaigns.jsx` → point at real campaign CRUD instead of the one-shot screen call
- `requirements.txt` → add `sqlalchemy`, `alembic`, `psycopg2-binary`, `redis`, `rq`

## 4. New files/modules required (high level, added phase by phase)

- `app/db/` — `session.py`, `base.py`, `models.py` (SQLAlchemy ORM)
- `alembic/` — migrations
- `app/schemas/` — Pydantic request/response models (separate from the existing `app/models/candidate.py` domain models)
- `app/services/` — business logic per domain (campaigns, requirements, rubrics, evaluations, challenge, benchmarking)
- `app/api/` — FastAPI routers, one per domain, mounted into `app/main.py`
- `app/workers/` — RQ task definitions + worker entrypoint
- `docker-compose.yml` — Postgres + Redis for local dev
- `tests/` — pytest suite

## 5. Architectural decision before writing code

Per the target architecture (React → FastAPI → PostgreSQL → Redis → Workers),
I'm using:
- **PostgreSQL** via SQLAlchemy 2.0 + Alembic (not replacing SQLite in
  `tenants.db` yet — that's a separate concern, touched in Phase K/RBAC, not
  Phase A)
- **RQ** (not Celery) for background jobs — simpler ops for this scale, easy
  to swap later if needed
- The Streamlit app keeps working untouched through Phase A–C; it will start
  reading from the same Postgres tables once persistence exists, instead of
  `st.session_state`, in a later phase — not breaking it now

## 6. Recommended implementation order

Matches the spec's PHASE A → M order. Starting now with **Phase A: Campaign +
Job + Requirement Engine**.
