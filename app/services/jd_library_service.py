"""
The smallest honest JD library. A `JDTemplate` is a saved, reusable job
description, independent of any campaign — visible and retrievable without
creating a campaign merely to store it. This is deliberately not a bigger
"JD management" feature: no versioning, no approval workflow, no ownership
model. A recruiter starting a new campaign reads one to prefill the JD text;
nothing here is scored, and nothing here is a substitute for the per-campaign
rubric that still governs screening.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JDTemplate


class JDLibraryError(ValueError):
    pass


def create_template(
    db: Session, *, role_title: str, body: str, summary: str = "",
    tags: str = "", source_file: str | None = None, created_by: str = "",
) -> JDTemplate:
    role_title = role_title.strip()
    body = body.strip()
    if not role_title:
        raise JDLibraryError("A JD template needs a role title.")
    if not body:
        raise JDLibraryError("A JD template needs body text.")
    template = JDTemplate(
        role_title=role_title, body=body, summary=summary.strip(),
        tags=tags.strip(), source_file=source_file, created_by=created_by,
    )
    db.add(template)
    db.flush()
    return template


def list_templates(db: Session) -> list[JDTemplate]:
    return list(db.scalars(select(JDTemplate).order_by(JDTemplate.role_title)).all())


def get_template(db: Session, template_id: str) -> JDTemplate | None:
    return db.get(JDTemplate, template_id)
