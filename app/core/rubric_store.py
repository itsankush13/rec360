"""
DEPRECATED as of Phase B. Superseded by app.services.rubric_service and the
Rubric / RubricVersion / RubricWeight / DisqualificationRule tables.

Kept on disk for two reasons only:
  1. Historical reads — rubric versions approved before Phase B still live in
     the flat `rubric_versions` table inside tenants.db and must remain
     readable. Nothing here is overwritten or migrated destructively.
  2. `scripts/backfill_legacy_rubrics.py` reads through this module to copy
     those old blobs into the new tables as APPROVED versions.

Do NOT call save_rubric() / approve_rubric() from new code. The public
endpoints that used to land here now route through app/api/rubrics.py.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "tenants.db"


def _connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_rubric_store():
    with _connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rubric_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                rubric_json TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                approved_at TEXT
            )
        """)


def save_rubric(campaign_id: str, rubric: list[dict]) -> dict:
    init_rubric_store()
    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            "INSERT INTO rubric_versions (campaign_id, rubric_json, created_at) VALUES (?, ?, ?)",
            (str(campaign_id), json.dumps(rubric), created_at),
        )
        return {"version_id": cursor.lastrowid, "campaign_id": str(campaign_id), "rubric": rubric, "approved": False}


def approve_rubric(campaign_id: str, version_id: int | None = None) -> dict:
    init_rubric_store()
    with _connection() as connection:
        if version_id is None:
            row = connection.execute(
                "SELECT id FROM rubric_versions WHERE campaign_id = ? ORDER BY id DESC LIMIT 1",
                (str(campaign_id),),
            ).fetchone()
            if row is None:
                raise ValueError("No rubric draft exists for this campaign")
            version_id = row["id"]
        approved_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            "UPDATE rubric_versions SET approved = 1, approved_at = ? WHERE id = ? AND campaign_id = ?",
            (approved_at, version_id, str(campaign_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError("Rubric version was not found for this campaign")
        row = connection.execute("SELECT * FROM rubric_versions WHERE id = ?", (version_id,)).fetchone()
        return {
            "version_id": row["id"],
            "campaign_id": row["campaign_id"],
            "rubric": json.loads(row["rubric_json"]),
            "approved": bool(row["approved"]),
            "approved_at": row["approved_at"],
        }