"""
`GET/POST /api/jd-library` — a small, standalone JD repository. Four demo JDs
are seeded here by `scripts/seed_demo.py`; a recruiter reads one to prefill
`new-campaign.html` without a campaign ever having to exist first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import jd_library_service
from app.services.jd_library_service import JDLibraryError

router = APIRouter(prefix="/api/jd-library", tags=["jd-library"])


class JDTemplateIn(BaseModel):
    role_title: str
    body: str
    summary: str = ""
    tags: str = ""
    source_file: str | None = None
    created_by: str = ""


class JDTemplateOut(BaseModel):
    id: str
    role_title: str
    summary: str
    body: str
    tags: str
    source_file: str | None = None


def _out(template) -> JDTemplateOut:
    return JDTemplateOut(
        id=template.id, role_title=template.role_title, summary=template.summary,
        body=template.body, tags=template.tags, source_file=template.source_file,
    )


@router.get("", response_model=list[JDTemplateOut])
def list_jd_templates(db: Session = Depends(get_db)):
    return [_out(t) for t in jd_library_service.list_templates(db)]


@router.get("/{template_id}", response_model=JDTemplateOut)
def get_jd_template(template_id: str, db: Session = Depends(get_db)):
    template = jd_library_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="JD template not found")
    return _out(template)


@router.post("", response_model=JDTemplateOut, status_code=201)
def create_jd_template(payload: JDTemplateIn, db: Session = Depends(get_db)):
    try:
        template = jd_library_service.create_template(
            db, role_title=payload.role_title, body=payload.body,
            summary=payload.summary, tags=payload.tags,
            source_file=payload.source_file, created_by=payload.created_by,
        )
    except JDLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(template)
    return _out(template)
