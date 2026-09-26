"""
B25 — one fixed, known login per operational role, so the three-role demo
walkthrough (HR sends to HM, HM records a verdict, HR schedules, HM scores,
HR proceeds, the budget approver grants, HR sends the offer) can be driven
by signing in and out of three different accounts.

DEMO/DEV CONVENIENCE ONLY, same convention as scripts/seed_demo_login.py:
these credentials are fixed and public (committed to the repo), never to be
reused anywhere a real password would matter.

Idempotent: safe to re-run. If an account already exists, only its password
is reset to the fixed value below; role and name are left alone.

Usage (from the repo root, venv active, after `alembic upgrade head`):

    python scripts/seed_role_logins.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.set_password import set_password  # noqa: E402

DEMO_PASSWORD = "Demo12345!"  # fixed and public on purpose -- see module docstring

ROLE_LOGINS = [
    {"email": "hr@demo.local", "role": "RECRUITER", "full_name": "Demo HR"},
    {"email": "hm@demo.local", "role": "HIRING_MANAGER", "full_name": "Demo Hiring Manager"},
    {"email": "budget@demo.local", "role": "REVIEWER", "full_name": "Demo Budget Approver"},
]


def main() -> int:
    db = SessionLocal()
    try:
        for spec in ROLE_LOGINS:
            user, created = set_password(
                db, email=spec["email"], password=DEMO_PASSWORD,
                role=spec["role"], full_name=spec["full_name"],
            )
            verb = "Created" if created else "Reset"
            print(f"{verb} demo login: {spec['email']} / {DEMO_PASSWORD} ({user.role.value}).")
        db.commit()
    finally:
        db.close()

    print("Demo credentials only -- do not reuse these passwords for a real account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
