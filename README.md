# 🧠 Talent Intelligence System
### Explainable Multi-Agent AI Hiring Platform

> AI Enablement Internship — Task 1: HR Resume & LinkedIn Shortlisting Agent

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Groq](https://img.shields.io/badge/LLM-Llama--3.3--70b-orange)](https://groq.com)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)](https://streamlit.io)

---

## 🎯 Project Overview

Most candidates build: **Resume → GPT → Score**

We built: **Explainable Multi-Agent Talent Intelligence System**

A production-grade AI hiring platform with hybrid RAG retrieval, multi-agent orchestration, bias mitigation, explainable scoring, and HR automation tools.

---

## 🏗️ Agent Architecture
┌─────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                  │
│     Streamlit Dashboard · Sidebar Navigation         │
│     HR Override · Email Sender · PDF Reports         │
└─────────────────────┬───────────────────────────────┘
│
┌─────────────────────▼───────────────────────────────┐
│                   AGENT LAYER                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ JD Agent │ │ Resume   │ │ Scoring  │ │  Bias  │ │
│  │          │ │  Parser  │ │  Agent   │ │ Audit  │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘ │
└─────────────────────┬───────────────────────────────┘
│
┌─────────────────────▼───────────────────────────────┐
│                INTELLIGENCE LAYER                    │
│   FAISS Semantic  +  BM25 Lexical  +  Ensemble       │
│   Skill Gap Forecast  +  Confidence Calibration      │
└─────────────────────┬───────────────────────────────┘
│
┌─────────────────────▼───────────────────────────────┐
│                   DATA LAYER                         │
│   In-Memory FAISS · Candidate Profiles · PDF Reports │
└─────────────────────────────────────────────────────┘
**Pipeline Flow:**
1. HR uploads JD + resumes/LinkedIn profiles
2. JD Agent extracts structured hiring requirements
3. Resume Parser Agent segments and extracts candidate profiles
4. Hybrid Retrieval (FAISS + BM25) finds top candidates
5. Scoring Agent computes ensemble score (LLM + Semantic + BM25)
6. Bias Audit Agent checks for demographic bias and PII
7. Multi-JD Matcher ranks each candidate against all open roles
8. Dashboard displays ranked shortlist with full explainability

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **Multi-Agent Pipeline** | JD, Resume, Scoring, Bias agents with single responsibilities |
| **Hybrid Retrieval** | FAISS semantic + BM25 lexical combined for best-of-both |
| **Ensemble Scoring** | 50% LLM + 30% Semantic + 20% BM25 with confidence score |
| **Hiring Match %** | Human-readable JD alignment percentage per candidate |
| **Multi-JD Matching** | Each candidate matched against all open roles simultaneously |
| **Skill Gap Forecast** | Learning adaptability + ramp-up time estimate |
| **Competency Heatmap** | Visual strength/weakness matrix across all candidates |
| **Knowledge Graph** | Candidate × role fit visualization |
| **Bias Audit Agent** | PII masking + demographic removal + fairness score |
| **HR Override** | Score override with audit log + automatic re-ranking |
| **Email Automation** | Pre-written rejection + personalized selection emails |
| **PDF Report** | Full shortlist with alternative role recommendations |
| **LinkedIn Ingestion** | JSON export + text paste supported |

---

## 🛠️ Tech Stack & LLM Decision Log

| Component | Choice | Rationale |
|---|---|---|
| **LLM** | Llama-3.3-70b via Groq | 3–5x faster than GPT-4o, free tier available, same quality for structured extraction tasks. Context window: 128K tokens. Full tool-calling support. |
| **Agent Framework** | LangGraph-style Multi-Agent | Production orchestration pattern. Single-responsibility agents are debuggable and testable. ReAct-style loop per agent. |
| **Embeddings** | all-MiniLM-L6-v2 | Strong open-source embedding model. No API cost. 384-dim vectors, fast local inference via sentence-transformers. |
| **Vector DB** | FAISS (in-memory) | Millisecond semantic search. No external service required. IndexFlatIP with normalized vectors for cosine similarity. |
| **Lexical Search** | BM25 (rank-bm25) | Catches exact keyword matches embeddings miss — e.g. "RAG", "LangChain", "FastAPI". Complements semantic retrieval. |
| **Resume Parsing** | PyMuPDF + spaCy + LLM | Three-layer extraction: PDF text → NLP NER → LLM structured output. Maximum accuracy. |
| **Dashboard** | Streamlit + Custom CSS | Multi-page app with sidebar navigation, dark enterprise theme, interactive charts. |
| **Monitoring** | Langfuse (optional) | Prompt tracing, token usage, latency tracking for production observability. |

### Agent Architecture Style
**Plan-and-Execute Multi-Agent** — each agent has a single responsibility:
- `JD Agent` → extracts structured requirements from job description
- `Resume Parser Agent` → segments and profiles each candidate
- `Scoring Agent` → computes ensemble score with LLM evaluation
- `Bias Audit Agent` → checks scoring rationale and resume for bias indicators

### Key Prompt Design
All agents use:
- **System prompt** with strict JSON-only output instructions
- **Structured output schemas** via Pydantic models
- **Few-shot structure** in scoring rubric to ground LLM evaluation
- **Guardrails**: output parsers strip markdown fences, validate JSON before use

---

## 🔐 Security Risk Mitigation

| Risk | Description | Our Mitigation |
|---|---|---|
| **Prompt Injection** | Malicious input manipulating agent behaviour | Regex pattern matching on all inputs + deny-list (`ignore previous instructions`, `system prompt`, `act as`) before any LLM call |
| **Data Privacy / PII** | Resume data contains personal info | Phone, email, Aadhaar masked with regex before sending to Groq API. Demographic info (age, gender) removed pre-scoring |
| **API Key Exposure** | Groq/email API keys leaked in code | `.env` + `python-dotenv`. Never hardcoded. `.env` in `.gitignore`. Use secrets manager in production |
| **Hallucination Risk** | LLM generating false scores | Structured JSON output + Pydantic validation + confidence thresholds + human-in-the-loop HR override |
| **Demographic Bias** | Names/gender/age influencing scores | Bias Audit Agent scans both resume text and scoring rationale. Flags age disclosure, gender mentions, name-origin bias |
| **Unauthorised Access** | Anyone triggering the agent endpoint | Local deployment only in prototype. Production: API key / OAuth on exposed endpoints + rate limiting |

---

## 📊 Scoring Rubric

| Dimension | Weight | 0 — Poor | 5 — Average | 10 — Excellent |
|---|---|---|---|---|
| Skills Match | **30%** | < 30% skills match | 50–70% match | > 85% match |
| Experience Relevance | **25%** | Unrelated domain | Adjacent domain | Exact domain + seniority |
| Education & Certs | **15%** | Below minimum | Meets minimum | Exceeds + extra certs |
| Project Portfolio | **20%** | No evidence | 1–2 generic | Strong relevant portfolio |
| Communication Quality | **10%** | Poor structure | Adequate | Crisp, structured, impactful |

**Ensemble Formula:**
Final Score = 0.50 × LLM Score + 0.30 × Semantic Similarity + 0.20 × BM25 Score
Hiring Match % = 0.50 × Semantic Sim + 0.30 × Skill Coverage + 0.20 × (Score/10)

---

## 🚀 Getting started (set up a fresh clone)

The commands below are PowerShell, for the team's Windows setup. A step that
differs on Mac/Linux Bash says so.

The repository target is **Python 3.13.15**, pinned in `runtime.txt`,
`.python-version`, and CI. Use that version, not a newer or older Python 3.

```powershell
# 1. Clone the repository and enter it
git clone https://github.com/itsankush13/talent-intelligence-system
cd talent-intelligence-system

# 2. Create a virtual environment with Python 3.13.15 and activate it
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
# source venv/bin/activate      # Mac/Linux

# 3. Install dependencies (OCR deps install in this same pass, see requirements.txt)
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Copy the env template and set your Azure OpenAI key
copy .env.example .env
# cp .env.example .env          # Mac/Linux
# Edit .env: set AZURE_OPENAI_API_KEY to your own key. Leave
# EMAIL_SENDER_ADDRESS and CALENDAR_SENDER_EMAIL blank - see the comments
# in .env.example.

# 5. Build the database (creates ./tis_app.db in the repo root)
.\venv\Scripts\python.exe -m alembic upgrade head

# 6. Seed demo data (idempotent - safe to re-run)
# The JD and CV source documents are NOT in the repo. They are shared
# separately. Point these two variables at wherever you unpacked them.
# Skip them only if the two folders already sit one level above the clone.
$env:JD_REPOSITORY_DIR = "C:\path\to\JD-Repository"
$env:CV_REPOSITORY_DIR = "C:\path\to\CV-Repository"
# CALENDAR_BACKEND=simulated is required here: the interview-schedule guard
# rejects seeded fictional actors when the calendar backend is "outlook".
$env:CALENDAR_BACKEND = "simulated"
.\venv\Scripts\python.exe scripts\seed_demo.py --dry-run   # preview, no writes
.\venv\Scripts\python.exe scripts\seed_demo.py             # seeds for real

# 7. Create a login. A fresh database has NO password on any user, so the
# sign-in page rejects everyone until this runs.
#
# Option A - your own account (recommended once you're doing real work).
# Prompts for the password and never echoes it:
.\venv\Scripts\python.exe scripts\set_password.py you@example.com --role ADMIN --full-name "Your Name"
#
# Option B - a fixed, known demo login, no prompt, same on every clone:
#   demo@example.com / Demo12345!
# This credential is committed to the repo and public, so it is for local
# demo use only - never reuse it for a real account.
.\venv\Scripts\python.exe scripts\seed_demo_login.py

# 8. Run the app - two terminals

# Terminal 1 (backend). QUEUE_BACKEND MUST be a shell variable, not a line
# in .env - without it uploads sit QUEUED forever and every screen looks empty.
$env:QUEUE_BACKEND = "inline"
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Terminal 2 (static frontend). Then open http://localhost:8124/login.html
cd web
python -m http.server 8124

# 9. Run tests
.\venv\Scripts\python.exe -m pytest -q
```

Run `alembic upgrade head` and `uvicorn` from the repository root. `DATABASE_URL`
defaults to `sqlite:///./tis_app.db`, a path relative to the process working
directory - starting `uvicorn` from any other folder silently builds a second,
empty database.

### What is NOT in the repo

| Path | Why it is gitignored |
|---|---|
| `.env` | Holds secrets (the Azure key). Copy `.env.example` instead. |
| `venv/` | Rebuilt locally from `requirements.txt`. |
| `storage/` | Uploaded CV documents. Auto-creates on first upload. |
| `*.db` | Built by `alembic upgrade head` and `scripts/seed_demo.py`. |
| `JD-Repository/`, `CV-Repository/` | The source JD and CV documents. Shared out of band - see step 6. |

The database is not committed because two developers sharing one binary
SQLite file diverge immediately and cannot merge.

---

## 📁 Project Structure
talent-intelligence-system/
├── app/
│   ├── agents/
│   │   ├── jd_agent.py              # JD parsing agent
│   │   ├── resume_parser_agent.py   # Resume + LinkedIn parser
│   │   ├── scoring_agent.py         # Ensemble scoring agent
│   │   └── bias_audit_agent.py      # Bias detection agent
│   ├── core/
│   │   ├── pipeline.py              # Main orchestration pipeline
│   │   ├── embeddings.py            # FAISS embedding engine
│   │   ├── bm25_retriever.py        # BM25 lexical retrieval
│   │   ├── multi_jd_matcher.py      # Multi-role matching
│   │   ├── skill_gap_forecaster.py  # Skill transferability
│   │   ├── knowledge_graph.py       # Plotly knowledge graph
│   │   ├── heatmap.py               # Competency heatmap
│   │   ├── email_sender.py          # SMTP email automation
│   │   ├── report_generator.py      # PDF report generator
│   │   ├── security.py              # PII masking + injection defense
│   │   └── config.py                # Pydantic settings
│   ├── models/
│   │   └── candidate.py             # Pydantic data models
│   ├── utils/
│   │   ├── document_parser.py       # PDF/DOCX extraction
│   │   └── linkedin_parser.py       # LinkedIn JSON/text parser
│   └── dashboard.py                 # Streamlit multi-page UI
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md

---

## 🎬 Demo

Upload a Job Description + candidate resumes → the system automatically:
- Extracts JD requirements with the JD Agent
- Parses resumes with PyMuPDF + spaCy + LLM
- Retrieves top candidates via FAISS + BM25
- Scores each candidate with ensemble model
- Audits for bias and PII exposure
- Ranks candidates with explainable scores
- Generates PDF shortlist report
- Sends personalized emails to selected/rejected candidates

---

## 🔗 Links

- **GitHub:** https://github.com/itsankush13/talent-intelligence-system
- **LLM Provider:** https://console.groq.com
- **Embeddings:** https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
