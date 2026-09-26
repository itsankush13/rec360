"""
B13 — cost-centre controls.

A cost centre used to be whatever string a caller typed into
`CostCentreIn.cost_centre_code`, logged onto the audit row and never checked
against anything (`app/api/approvals.py`, before this). This is the registry
that makes it checkable: a real code, a real budget holder, both on file
before an approval can claim them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CostCentre
from app.services.lifecycle_service import require_user


class CostCentreError(ValueError):
    pass


def create_cost_centre(
    db: Session, *, code: str, name: str, budget_holder_id: str,
    annual_budget_usd: float | None = None,
    business_unit: str | None = None, currency: str = "USD",
    fiscal_year: str | None = None, role_grade: str | None = None,
    approved_headcount: int | None = None,
    salary_band_min: float | None = None, salary_band_max: float | None = None,
) -> CostCentre:
    code = code.strip().upper()
    if not code:
        raise CostCentreError("A cost centre needs a code.")
    existing = get_by_code(db, code)
    if existing is not None:
        raise CostCentreError(f"Cost centre {code} is already on file.")
    holder = require_user(db, budget_holder_id, what="hold a cost centre's budget")

    centre = CostCentre(
        code=code, name=name.strip(), budget_holder_id=holder.id,
        annual_budget_usd=annual_budget_usd,
        business_unit=(business_unit.strip() if business_unit else None),
        currency=(currency or "USD").strip().upper() or "USD",
        fiscal_year=fiscal_year, role_grade=role_grade,
        approved_headcount=approved_headcount,
        salary_band_min=salary_band_min, salary_band_max=salary_band_max,
    )
    db.add(centre)
    db.flush()
    return centre


def list_cost_centres(db: Session, *, active_only: bool = True) -> list[CostCentre]:
    statement = select(CostCentre).order_by(CostCentre.code)
    if active_only:
        statement = statement.where(CostCentre.active.is_(True))
    return list(db.scalars(statement).all())


def get_by_code(db: Session, code: str) -> CostCentre | None:
    return db.scalar(select(CostCentre).where(CostCentre.code == code.strip().upper()))


def close_cost_centre(db: Session, centre: CostCentre) -> CostCentre:
    """Closed rather than deleted — an already-approved hire's row must keep
    pointing at something real."""
    centre.active = False
    db.flush()
    return centre


def validate(db: Session, *, code: str, claimed_budget_holder_id: str) -> CostCentre:
    """
    Reject an approval before it starts a clock against a cost centre that
    does not exist, is closed, or whose budget holder is not who the caller
    claimed. The registry's `budget_holder_id` is what wins — that is the
    field this whole table exists to stop a caller from simply asserting.
    """
    centre = get_by_code(db, code)
    if centre is None:
        raise CostCentreError(f"'{code}' is not a cost centre on file.")
    if not centre.active:
        raise CostCentreError(
            f"Cost centre {centre.code} is closed and cannot accept new approvals."
        )
    if claimed_budget_holder_id and claimed_budget_holder_id != centre.budget_holder_id:
        raise CostCentreError(
            f"{claimed_budget_holder_id} does not hold the budget for {centre.code}."
        )
    return centre
