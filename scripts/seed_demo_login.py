"""
Create one fixed, known login so a fresh clone can sign in immediately.

DEMO/DEV CONVENIENCE ONLY. The credential below is fixed and public (it is
committed to the repo), so it must never be used anywhere a real password
would matter. It exists purely so that a second developer -- or anyone
cloning this repo to a new laptop -- can reach a signed-in screen without
first choosing and typing their own password through `set_password.py`'s
interactive getpass prompt (which remains the right tool for a real login).

Idempotent: safe to re-run. If the account already exists, only its
password is reset to the fixed value below; role and name are left alone.

Usage (from the repo root, venv active, after `alembic upgrade head`):

    python scripts/seed_demo_login.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.db.models import UserRole  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from scripts.set_password import set_password  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo12345!"  # fixed and public on purpose -- see module docstring
DEMO_ROLE = UserRole.ADMIN.value
DEMO_FULL_NAME = "Demo Admin"


def main() -> int:
    db = SessionLocal()
    try:
        user, created = set_password(
            db, email=DEMO_EMAIL, password=DEMO_PASSWORD,
            role=DEMO_ROLE, full_name=DEMO_FULL_NAME,
        )
        role_value = user.role.value
        db.commit()
    finally:
        db.close()

    verb = "Created" if created else "Reset"
    print(f"{verb} demo login: {DEMO_EMAIL} / {DEMO_PASSWORD} ({role_value}).")
    print("Demo credential only -- do not reuse this password for a real account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
