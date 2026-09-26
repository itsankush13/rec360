"""
Login gate (B22 phase 1) — see app/services/auth_service.py for the identity
rules and app/core/session_auth.py for the password/token mechanics.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.session_auth import issue_token, verify_token
from app.db.models import User
from app.db.session import get_db
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def _current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    user_id = verify_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in again.")
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Sign in again.")
    return user


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return {"token": issue_token(user.id), "user": auth_service.display_identity(db, user)}


@router.get("/me")
def me(user=Depends(_current_user), db: Session = Depends(get_db)):
    return {"user": auth_service.display_identity(db, user)}
