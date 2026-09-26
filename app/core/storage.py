"""
Document retention.

The old /api/campaigns/screen flow wrote uploads to NamedTemporaryFile and
deleted them in a finally block. That is why nothing in the system can cite
evidence back to a CV today. Phase C retains every accepted file so Phase D
can quote from it with a page reference.

Storage is a local directory by default (STORAGE_ROOT, default ./storage).
The interface is deliberately narrow — save / read / exists / delete on an
opaque relative key — so swapping in S3 or Azure Blob later touches only this
module. Nothing else in the codebase builds a path.

Writes are append-only: a key is derived from the document's UUID, so a save
never overwrites an existing file.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_STORAGE_ROOT = "./storage"


class StorageError(RuntimeError):
    pass


def storage_root() -> Path:
    """Resolved at call time, not import time, so tests can point it elsewhere."""
    return Path(os.getenv("STORAGE_ROOT", DEFAULT_STORAGE_ROOT)).resolve()


def build_key(campaign_id: str, document_id: str, extension: str) -> str:
    """
    Relative storage key. Sharded by campaign so a campaign's documents can be
    exported or purged as a unit (retention policy, GDPR erasure).
    """
    suffix = extension if extension.startswith(".") else f".{extension}" if extension else ""
    return f"campaigns/{campaign_id}/{document_id}{suffix}"


def _resolve(key: str) -> Path:
    root = storage_root()
    path = (root / key).resolve()
    # Refuse anything that escapes the root — the key is derived internally,
    # but a filename-derived key must never be able to traverse out.
    if not str(path).startswith(str(root)):
        raise StorageError(f"Refusing to resolve key outside storage root: {key}")
    return path


def save(key: str, data: bytes) -> str:
    path = _resolve(key)
    if path.exists():
        raise StorageError(f"Refusing to overwrite existing document at {key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(data)
    except OSError as exc:
        raise StorageError(f"Could not write document to {key}: {exc}") from exc
    return key


def read(key: str) -> bytes:
    path = _resolve(key)
    if not path.exists():
        raise StorageError(f"No stored document at {key}")
    return path.read_bytes()


def local_path(key: str) -> Path:
    """
    Filesystem path for libraries that need a real file (PyMuPDF, python-docx).
    Only valid for the local backend; a remote backend would download to a
    temp file here instead.
    """
    return _resolve(key)


def exists(key: str) -> bool:
    try:
        return _resolve(key).exists()
    except StorageError:
        return False


def delete(key: str) -> None:
    """Only for campaign purge / retention enforcement — never during processing."""
    path = _resolve(key)
    if path.exists():
        path.unlink()


def purge_campaign(campaign_id: str) -> None:
    path = _resolve(f"campaigns/{campaign_id}")
    if path.exists():
        shutil.rmtree(path)
