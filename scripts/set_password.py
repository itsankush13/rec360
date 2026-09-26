"""
Upsert a password for a user by email (B22 phase 1 login gate).

If a `User` row for the email already exists, only `password_hash` is
touched -- role and full_name are left alone. If it doesn't exist, a new
row is created, and since there's no sensible default for either, --role
and --full-name are then required.

The password is read with getpass: never pass it as a command-line
argument (it would land in shell history / process listings), and it is
never echoed back or printed, including on success.

Usage (from the repo root, venv active):

    python scripts/set_password.py jane@example.com --role RECRUITER --full-name "Jane Doe"
    python scripts/set_password.py jane@example.com
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.session_auth import hash_password  # noqa: E402
from app.db.models import User, UserRole  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

ROLE_CHOICES = [role.value for role in UserRole]


def set_password(db, *, email: str, password: str, role: str | None = None,
                  full_name: str | None = None) -> tuple[User, bool]:
    """Upsert a password for `email`. Returns (user, created).

    Raises ValueError if the user doesn't exist yet and --role/--full-name
    weren't supplied, or if `role` isn't a valid UserRole.
    """
    normalized_email = email.strip().lower()
    user = db.scalars(select(User).where(User.email == normalized_email)).first()
    created = False
    if user is None:
        if not role:
            raise ValueError(
                f"No user exists for {normalized_email} yet -- --role is required "
                f"to create one. Choices: {ROLE_CHOICES}"
            )
        if role not in ROLE_CHOICES:
            raise ValueError(f"--role must be one of {ROLE_CHOICES}, got {role!r}.")
        if not full_name or not full_name.strip():
            raise ValueError(
                f"No user exists for {normalized_email} yet -- --full-name is "
                f"required to create one."
            )
        user = User(
            full_name=full_name.strip(),
            email=normalized_email,
            role=UserRole(role),
        )
        db.add(user)
        created = True
    user.password_hash = hash_password(password)
    db.flush()
    return user, created


def _read_password() -> str:
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise ValueError("Passwords do not match.")
    if not password:
        raise ValueError("Password must not be empty.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("email", help="the user's email address")
    parser.add_argument(
        "--role", choices=ROLE_CHOICES, default=None,
        help="required when creating a new user; ignored when updating one",
    )
    parser.add_argument(
        "--full-name", default=None,
        help="required when creating a new user; ignored when updating one",
    )
    args = parser.parse_args()

    try:
        password = _read_password()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        try:
            user, created = set_password(
                db, email=args.email, password=password,
                role=args.role, full_name=args.full_name,
            )
        except ValueError as exc:
            db.rollback()
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        db.commit()
    finally:
        db.close()

    verb = "Created" if created else "Updated"
    print(f"{verb} user {user.email} ({user.role.value}). Password set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
