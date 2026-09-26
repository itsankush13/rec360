"""
Password hashing and session tokens for the login gate (B22, phase 1).

Real password check, no new infrastructure: bcrypt (already a dependency,
see requirements.txt) for the hash, and a stateless HMAC-signed bearer token
for the session — no sessions table, so nothing to clean up, and it survives
a server restart since it isn't held in memory. A token cannot be revoked
before it expires; fine for a two-person prototype, not for production.

    ponytail: stateless token, no revoke-before-expiry. Add a sessions
    table (or a denylist) if a real "log out everywhere" is ever needed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import bcrypt

from app.core.config import settings

TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12 hours


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False  # malformed hash, e.g. an empty/legacy row


def _secret() -> bytes:
    return settings.session_secret.encode("utf-8")


def issue_token(user_id: str) -> str:
    payload = json.dumps({"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
                         separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii")
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_token(token: str) -> str | None:
    """Returns the user id the token was issued for, or None if invalid/expired."""
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload.get("sub")
