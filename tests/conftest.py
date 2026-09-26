import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used-in-tests")
# Phase C: run jobs synchronously so upload assertions are deterministic, and
# keep retained documents out of the repo's ./storage directory.
os.environ["QUEUE_BACKEND"] = "inline"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import get_db
from app.main import app
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Point document retention at a per-test temp directory."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("QUEUE_BACKEND", "inline")
    yield


@pytest.fixture(autouse=True)
def simulated_backends_by_default(monkeypatch):
    """Force email/calendar backends to "simulated" for every test.

    `Settings` reads the machine's real `.env`, so a developer with
    `EMAIL_BACKEND=outlook` set (for real Outlook sends outside tests) would
    silently change test behaviour: the allowlist guard in
    `app.core.mail_guard` would start firing against fixture addresses.
    Test outcomes must not depend on local `.env` state. A test that wants
    to exercise the real-send path sets `email_backend`/`calendar_backend`
    to "outlook" itself, after this fixture runs.
    """
    monkeypatch.setattr(settings, "email_backend", "simulated")
    monkeypatch.setattr(settings, "calendar_backend", "simulated")
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    from fastapi.testclient import TestClient
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
