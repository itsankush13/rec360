"""
Database engine + session factory.

Reads DATABASE_URL from the environment. Defaults to a local SQLite file so
the project still runs with zero setup, but production / real bulk-volume
work must set DATABASE_URL to a Postgres connection string, e.g.:

    DATABASE_URL=postgresql+psycopg2://tis_user:tis_password@localhost:5432/tis

SQLite is fine for Phase A development and unit tests, but background
workers (Phase C onward) and concurrent bulk uploads need Postgres —
SQLite's file-level locking will bottleneck under real concurrent writes.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tis_app.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db():
    """FastAPI dependency — yields a DB session and always closes it."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
