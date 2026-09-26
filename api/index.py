"""
Re-exports the FastAPI app for any deploy target that imports `api.index`.
All real application code lives in app/main.py — keep this file thin.
"""
from app.main import app  # noqa: F401
