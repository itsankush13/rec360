"""One candidate crosses the real internal stages of the wide-pass portal."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.db.models import AuditAction, AuditEvent
from tests.test_handoff_api import people, shortlisted  # shared real-CV setup fixtures


def test_shortlist_to_hire_stays_traceable(client, db_session, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    root = f"/api/campaigns/{campaign_id}"
    rec = people["recruiter"]["id"]
    manager = people["manager"]["id"]
    admin = people["admin"]["id"]

    def write(path, body, expected=200):
        response = client.post(root + path, json=body)
        assert response.status_code == expected, response.text
        return response.json()

    write(f"/lifecycle/{candidate_id}/send-to-manager",
          {"actor_id": rec, "manager_id": manager})
    write(f"/lifecycle/{candidate_id}/review",
          {"reviewer_id": manager, "outcome": "PROCEED"}, 201)
    write(f"/interviews/{candidate_id}/schedule", {
        "actor_id": manager, "when": (datetime.now() + timedelta(days=10)).isoformat(),
        "duration_minutes": 45, "mode": "VIDEO", "round": 1,
        "panel": [manager],
    }, 201)
    write(f"/interviews/{candidate_id}/feedback", {
        "actor_id": manager, "recommendation": "PROCEED",
        "strengths": "Relevant plant experience.",
    })
    write(f"/approvals/{candidate_id}/request", {
        "actor_id": rec, "chain": [manager, admin], "grade": "G7",
        "salary_band": "QAR 12-15k", "justification": "Interview panel recommends hire.",
    })
    # B13: the cost-centre step now validates against the CostCentre
    # registry rather than accepting any caller-supplied code.
    response = client.post("/api/cost-centres", json={
        "code": "CC-410", "name": "Operations", "budget_holder_id": admin,
    })
    assert response.status_code == 201, response.text
    write(f"/approvals/{candidate_id}/cost-centre", {
        "actor_id": manager, "budget_holder_id": admin,
        "cost_centre_code": "CC-410",
    })
    write(f"/approvals/{candidate_id}/grant", {"actor_id": admin})
    write(f"/offers/{candidate_id}/draft", {
        "actor_id": rec, "base_salary": 12000, "currency": "QAR",
        "start_date": (date.today() + timedelta(days=30)).isoformat(),
        "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
    }, 201)
    write(f"/offers/{candidate_id}/send", {"actor_id": rec})
    write(f"/offers/{candidate_id}/response",
          {"actor_id": rec, "response": "ACCEPTED"})
    write(f"/lifecycle/{candidate_id}/transition",
          {"actor_id": admin, "to_status": "HIRED"})

    position = client.get(root + f"/lifecycle/{candidate_id}").json()
    assert position["status"] == "HIRED"
    assert client.get(root + "/metrics/outcomes").json()["hired"] == {
        "count": 1, "of": 1,
        "basis": "Current candidate position in this campaign.",
    }
    actions = set(db_session.scalars(select(AuditEvent.action).where(
        AuditEvent.campaign_id == campaign_id,
        AuditEvent.candidate_id == candidate_id,
    )).all())
    assert {
        AuditAction.INTERVIEW_SCHEDULED, AuditAction.INTERVIEW_FEEDBACK_RECORDED,
        AuditAction.APPROVAL_REQUESTED, AuditAction.APPROVAL_GRANTED,
        AuditAction.OFFER_DRAFTED, AuditAction.OFFER_SENT,
        AuditAction.OFFER_RESPONSE_RECORDED,
    } <= actions
