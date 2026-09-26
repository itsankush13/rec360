"""
Send-mode disclosure (truthfulness fix, 2026-09-14 demo).

Several web/ pages hardcoded a "SIMULATED" badge next to a send button. Once
`EMAIL_BACKEND`/`CALENDAR_BACKEND` are set to "outlook" the badge lied — the
button now sends for real. The frontend had no way to know which backend is
active, so it guessed. This endpoint tells it.

Exposes only the two backend mode strings. Never the Azure credentials, the
sender address, or any other `.env` setting — see `app/core/config.py` for
what those two settings mean.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/send-modes")
def send_modes() -> dict:
    return {
        "email_backend": settings.email_backend,
        "calendar_backend": settings.calendar_backend,
    }
