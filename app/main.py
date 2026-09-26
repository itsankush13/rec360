"""
Main FastAPI application.

Run locally with:
    uvicorn app.main:app --reload --port 8000

`api/index.py` re-exports `app` from this module so any existing deploy
target that imports from `api.index` keeps working unchanged.
"""
import os
import pathlib
import sys
import tempfile

from contextlib import asynccontextmanager

from app.core.console import configure_utf8_output

# A cp1252 console must not be able to fail a request through a log line.
for _stream in (sys.stdout, sys.stderr):
    configure_utf8_output(_stream)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.config import router as config_router
from app.api.campaigns import router as campaigns_router
from app.api.campaign_ai import router as campaign_ai_router
from app.api.jd import router as jd_router
from app.api.jd_library import router as jd_library_router
from app.api.requirements import router as requirements_router
from app.api.rubrics import router as rubrics_router
from app.api.processing import campaign_router as processing_campaign_router
from app.api.processing import processing_router
from app.api.evaluations import campaign_router as evaluations_campaign_router
from app.api.evaluations import evaluation_router
from app.api.compat import router as compat_router
from app.api.exports import router as exports_router
from app.api.decisions import audit_router
from app.api.lifecycle import router as lifecycle_router
from app.api.lifecycle import users_router
from app.api.lifecycle import sla_router
from app.api.decisions import router as decisions_router
from app.api.analytics import router as analytics_router
from app.api.analytics import global_router as analytics_global_router
from app.api.discovery import router as discovery_router
from app.api.handoff import router as handoff_router
from app.api.interviews import router as interviews_router
from app.api.approvals import router as approvals_router
from app.api.offers import router as offers_router
from app.api.messages import router as messages_router
from app.api.reports import router as reports_router
from app.api.metrics import router as metrics_router
from app.api.cost_centres import router as cost_centres_router
from app.api.delegations import router as delegations_router
from app.api.developer import router as developer_router
from app.api.replies import router as replies_router
from app.api.replies import campaign_router as replies_campaign_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned exclusively by Alembic. The create_all() that used to
    # live here raced the migrations: starting the app created new tables
    # itself, so the next `alembic upgrade head` failed on "table already
    # exists". Run migrations before starting the app:
    #     python -m alembic upgrade head
    yield


app = FastAPI(title="Talent Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "http://127.0.0.1:5173",
        # The static Recruitment 360 UI under web/ is served on 8124.
        "http://localhost:8124",
        "http://127.0.0.1:8124",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Content-Disposition isn't on the CORS response-header safelist, so a
    # cross-origin fetch() (the static UI on 8124 calling the API on 8000)
    # gets `null` back from response.headers.get(...) without this — the CV
    # viewer needs the real filename/extension out of that header to know
    # whether to render a PDF, convert a DOCX, or fall back to a download.
    expose_headers=["Content-Disposition"],
)

app.include_router(auth_router)
app.include_router(config_router)
app.include_router(campaigns_router)
app.include_router(campaign_ai_router)
app.include_router(jd_router)
app.include_router(jd_library_router)
app.include_router(requirements_router)
app.include_router(rubrics_router)
app.include_router(processing_campaign_router)
app.include_router(processing_router)
app.include_router(evaluations_campaign_router)
app.include_router(evaluation_router)
app.include_router(decisions_router)
app.include_router(audit_router)
app.include_router(users_router)
app.include_router(lifecycle_router)
app.include_router(sla_router)
app.include_router(analytics_router)
app.include_router(analytics_global_router)
app.include_router(exports_router)
app.include_router(compat_router)
app.include_router(discovery_router)
app.include_router(handoff_router)
app.include_router(interviews_router)
app.include_router(approvals_router)
app.include_router(offers_router)
app.include_router(messages_router)
app.include_router(reports_router)
app.include_router(metrics_router)
app.include_router(cost_centres_router)
app.include_router(delegations_router)
app.include_router(developer_router)
app.include_router(replies_router)
app.include_router(replies_campaign_router)


# ---------------------------------------------------------------------------
# Demo-only: serve the static web/ UI from this same process under /ui, so a
# single tunnel (e.g. ngrok on a free plan, which allows only one public
# endpoint) can expose both the API and the frontend. Normal local dev still
# serves web/ separately via `python -m http.server 8124`; this mount is
# additive and does not replace that.
# ---------------------------------------------------------------------------

_WEB_DIR = pathlib.Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="web-ui")


# ---------------------------------------------------------------------------
# Error envelope for the static Recruitment 360 frontend.
#
# Its JavaScript reads `body.error.message` and shows `body.error.request_id`
# as a reference. FastAPI would wrap a raised detail as {"detail": {...}},
# which the UI cannot see, so a detail that is already an envelope is passed
# through unwrapped. Everything else keeps FastAPI's default shape, so the
# Phase A-D routes and their tests are unaffected.
# ---------------------------------------------------------------------------

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def _envelope_aware_http_handler(request, exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


# ---------------------------------------------------------------------------
# Legacy endpoints, carried over unchanged from the original api/index.py so
# the existing React screening flow keeps working while campaign
# persistence (above) is adopted incrementally.
# ---------------------------------------------------------------------------

def _serialize_result(result: dict) -> dict:
    return {
        "score": result["score"].model_dump(),
        "profile": result["profile"].model_dump(),
        "jd": result.get("jd", {}),
        "bias_audit": result.get("bias_audit", {}),
        "challenge_audit": result.get("challenge_audit", {}),
        "jd_matches": result.get("jd_matches", []),
    }


@app.get("/")
def home():
    return {"message": "Talent Intelligence API"}


@app.post("/api/campaigns/screen")
async def screen_campaign(
    jd_text: str = Form(...),
    files: list[UploadFile] = File(...),
    campaign_id: str = Form("1"),
):
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text is required")
    if not files:
        raise HTTPException(status_code=422, detail="At least one resume is required")

    temp_paths = []
    try:
        for upload in files:
            suffix = os.path.splitext(upload.filename or "resume.pdf")[1].lower() or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(await upload.read())
                temp_paths.append(temp_file.name)
        from app.core.pipeline import run_pipeline  # lazy: pulls in faiss/spacy/sentence-transformers
        results = run_pipeline(jd_text, temp_paths)
        return {
            "campaign_id": campaign_id,
            "count": len(results),
            "results": [_serialize_result(result) for result in results],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
