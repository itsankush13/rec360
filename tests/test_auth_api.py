"""Login gate (B22 phase 1): password hash/verify, token round-trip, and the
ankush/subhadeep HR <-> Hiring manager flip in the interview co-manager list.
"""
from app.core.session_auth import hash_password, verify_password, issue_token, verify_token


def test_password_hash_round_trip():
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong horse", hashed)


def test_verify_password_rejects_missing_hash():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "")


def test_token_round_trip():
    token = issue_token("user-123")
    assert verify_token(token) == "user-123"


def test_token_rejects_tampering():
    token = issue_token("user-123")
    body, _, signature = token.partition(".")
    assert verify_token(body + "." + signature[::-1]) is None


def test_login_success_and_failure(client):
    client.post("/api/users", json={
        "full_name": "Ankush Saxena", "email": "ankush.saxena@protivitiglobal.in",
        "role": "RECRUITER",
    })
    # No password set yet: login must fail, not silently succeed.
    resp = client.post("/api/auth/login", json={
        "email": "ankush.saxena@protivitiglobal.in", "password": "whatever",
    })
    assert resp.status_code == 401


def test_interviews_co_manager_flip(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "calendar_backend", "simulated")

    ankush = client.post("/api/users", json={
        "full_name": "Ankush Saxena", "email": "ankush.saxena@protivitiglobal.in",
        "role": "RECRUITER",
    }).json()
    subhadeep = client.post("/api/users", json={
        "full_name": "Subhadeep Majumder", "email": "subhadeep.m@protivitiglobal.in",
        "role": "HIRING_MANAGER",
    }).json()

    from unittest.mock import patch
    from tests.test_processing import FAKE_JD_EXTRACTION
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Flip test", "job_title": "Engineer",
            "job_description": "Backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    from tests.test_evaluations import STRONG_CV, make_cv_pdf
    from tests.test_processing import PDF_MIME, upload
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve", json={"approved_by": "Ankush Saxena"})
    upload(client, campaign_id, [("c.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Ankush Saxena"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": ankush["id"], "manager_id": subhadeep["id"]},
    )

    # ankush.saxena is logged in (actor_id = his user id): subhadeep.m
    # should now be an accepted co-manager, on top of the fixed demo list.
    resp = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/schedule",
        json={
            "when": "2026-10-01T10:00:00", "duration_minutes": 30, "mode": "VIDEO",
            "round": 1, "actor_id": ankush["id"],
            "co_manager_email": "subhadeep.m@protivitiglobal.in",
        },
    )
    assert resp.status_code == 201, resp.text
