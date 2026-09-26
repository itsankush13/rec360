"""
B13 — the cost-centre registry `app/api/approvals.py`'s cost-centre step
validates against. See `app/services/cost_centre_service.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import cost_centre_service
from app.services.cost_centre_service import CostCentreError
from app.services.lifecycle_service import LifecycleError

router = APIRouter(prefix="/api/cost-centres", tags=["cost-centres"])


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


class CostCentreIn(BaseModel):
    code: str
    name: str = ""
    budget_holder_id: str
    annual_budget_usd: float | None = None
    business_unit: str | None = None
    currency: str = "USD"
    fiscal_year: str | None = None
    role_grade: str | None = None
    approved_headcount: int | None = None
    salary_band_min: float | None = None
    salary_band_max: float | None = None


class CostCentreOut(BaseModel):
    id: str
    code: str
    name: str
    budget_holder_id: str
    annual_budget_usd: float | None = None
    business_unit: str | None = None
    currency: str = "USD"
    fiscal_year: str | None = None
    role_grade: str | None = None
    approved_headcount: int | None = None
    salary_band_min: float | None = None
    salary_band_max: float | None = None
    active: bool


def _out(centre) -> CostCentreOut:
    return CostCentreOut(
        id=centre.id, code=centre.code, name=centre.name,
        budget_holder_id=centre.budget_holder_id,
        annual_budget_usd=centre.annual_budget_usd,
        business_unit=centre.business_unit, currency=centre.currency,
        fiscal_year=centre.fiscal_year, role_grade=centre.role_grade,
        approved_headcount=centre.approved_headcount,
        salary_band_min=centre.salary_band_min,
        salary_band_max=centre.salary_band_max,
        active=centre.active,
    )


@router.get("", response_model=list[CostCentreOut])
def list_cost_centres(active_only: bool = True, db: Session = Depends(get_db)):
    return [_out(c) for c in cost_centre_service.list_cost_centres(db, active_only=active_only)]


@router.post("", response_model=CostCentreOut, status_code=201)
def create_cost_centre(payload: CostCentreIn, db: Session = Depends(get_db)):
    try:
        centre = cost_centre_service.create_cost_centre(
            db, code=payload.code, name=payload.name,
            budget_holder_id=payload.budget_holder_id,
            annual_budget_usd=payload.annual_budget_usd,
            business_unit=payload.business_unit, currency=payload.currency,
            fiscal_year=payload.fiscal_year, role_grade=payload.role_grade,
            approved_headcount=payload.approved_headcount,
            salary_band_min=payload.salary_band_min,
            salary_band_max=payload.salary_band_max,
        )
    except (CostCentreError, LifecycleError) as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(centre)
    return _out(centre)


@router.post("/{code}/close", response_model=CostCentreOut)
def close_cost_centre(code: str, db: Session = Depends(get_db)):
    centre = cost_centre_service.get_by_code(db, code)
    if centre is None:
        raise HTTPException(status_code=404, detail="Cost centre not found")
    cost_centre_service.close_cost_centre(db, centre)
    db.commit()
    db.refresh(centre)
    return _out(centre)
