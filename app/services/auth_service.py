"""
Login identity for the two-person demo (B22 phase 1).

Real password check (app/core/session_auth.py), but the "HR" / "Hiring
manager" pairing below is a display convention, not a UserRole. The two
named people swap who is driving today; their actual UserRole (RECRUITER /
HIRING_MANAGER, checked in lifecycle_service.py and app/core/lifecycle.py)
stays exactly what it is seeded as and is untouched by who is logged in.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.session_auth import verify_password
from app.db.models import User

# The two people who take turns being "HR" for a session. Whoever is NOT
# logged in is shown elsewhere as the counterpart, "Hiring manager" — see
# app/api/interviews.py's co-manager allowlist, which reads this same map.
FLIP_COUNTERPART: dict[str, str] = {
    "ankush.saxena@protivitiglobal.in": "subhadeep.m@protivitiglobal.in",
    "subhadeep.m@protivitiglobal.in": "ankush.saxena@protivitiglobal.in",
}


def authenticate(db: Session, email: str, password: str) -> User | None:
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def display_identity(db: Session, user: User) -> dict:
    """What the frontend shows for the signed-in user and their counterpart."""
    counterpart_email = FLIP_COUNTERPART.get(user.email)
    counterpart = None
    if counterpart_email:
        counterpart = db.scalars(select(User).where(User.email == counterpart_email)).first()
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.value,
        # "HR" alone didn't say which HR job the signed-in person actually
        # does. "HR-<their role word>" (e.g. "HR-Recruiter") keeps the HR
        # framing for this two-person demo while naming their real UserRole.
        "display_label": "HR-" + _role_word(user.role) if counterpart_email else _role_word(user.role),
        "counterpart": {
            "id": counterpart.id if counterpart else None,
            "full_name": counterpart.full_name if counterpart else counterpart_email,
            "email": counterpart_email,
            "display_label": "Hiring manager",
        } if counterpart_email else None,
    }


def _role_word(role) -> str:
    from app.api.lifecycle import ROLE_WORDS  # local: avoids a circular import at module load
    return ROLE_WORDS.get(role, "Team member")
