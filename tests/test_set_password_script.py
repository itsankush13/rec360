"""scripts/set_password.py core logic (B22 phase 1 login gate).

Exercises set_password() directly against the pytest in-memory-sqlite
db_session fixture (see tests/conftest.py) rather than shelling out to the
CLI -- getpass and argv parsing aren't the interesting part here.
"""
import pytest
from sqlalchemy import select

from app.core.session_auth import verify_password
from app.db.models import User
from scripts.set_password import set_password


def test_creates_new_user_with_working_password(db_session):
    user, created = set_password(
        db_session, email="new.hire@protivitiglobal.in", password="correct horse",
        role="RECRUITER", full_name="New Hire",
    )
    db_session.commit()

    assert created is True
    assert user.email == "new.hire@protivitiglobal.in"
    assert user.full_name == "New Hire"
    assert user.role.value == "RECRUITER"
    assert verify_password("correct horse", user.password_hash)
    assert not verify_password("wrong horse", user.password_hash)

    # Actually landed in the db, not just on the in-memory object.
    fetched = db_session.scalars(
        select(User).where(User.email == "new.hire@protivitiglobal.in")
    ).one()
    assert verify_password("correct horse", fetched.password_hash)


def test_updates_existing_user_without_touching_role_or_name(db_session):
    existing = User(
        full_name="Ankush Saxena", email="ankush.saxena@protivitiglobal.in",
        role="RECRUITER",
    )
    db_session.add(existing)
    db_session.commit()

    user, created = set_password(
        db_session, email="ankush.saxena@protivitiglobal.in", password="new-secret",
    )
    db_session.commit()

    assert created is False
    assert user.id == existing.id
    assert user.full_name == "Ankush Saxena"
    assert user.role.value == "RECRUITER"
    assert verify_password("new-secret", user.password_hash)


def test_refuses_to_create_without_role(db_session):
    with pytest.raises(ValueError, match="--role"):
        set_password(
            db_session, email="brand.new@protivitiglobal.in", password="whatever",
            full_name="Brand New",
        )
    assert db_session.scalars(
        select(User).where(User.email == "brand.new@protivitiglobal.in")
    ).first() is None


def test_refuses_to_create_without_full_name(db_session):
    with pytest.raises(ValueError, match="--full-name"):
        set_password(
            db_session, email="brand.new@protivitiglobal.in", password="whatever",
            role="RECRUITER",
        )
    assert db_session.scalars(
        select(User).where(User.email == "brand.new@protivitiglobal.in")
    ).first() is None


def test_refuses_invalid_role(db_session):
    with pytest.raises(ValueError, match="--role must be one of"):
        set_password(
            db_session, email="brand.new@protivitiglobal.in", password="whatever",
            role="NOT_A_REAL_ROLE", full_name="Brand New",
        )
