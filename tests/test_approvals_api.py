"""
HR discussion and approval routing (journey step 7, plan W-C).

The chain: FEEDBACK_COMPLETE -> PENDING_APPROVAL -> PENDING_COST_CENTRE ->
APPROVED, with a legitimate return one step back at either waiting state.
Real state lives in `CandidateLifecycle` via `lifecycle_service.transition`;
the approver chain, the grade, the salary band and the justification are
structured detail on the audit row, per the no-new-tables rule.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import AuditAction, AuditEvent

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def people(client):
    def make(name, email, role):
        return client.post("/api/users", json={
            "full_name": name, "email": email, "role": role,
        }).json()

    return {
        "recruiter": make("Fatima Al-Rashid", "fatima@example.com", "RECRUITER"),
        "manager": make("Aziz Rahman", "aziz@example.com", "HIRING_MANAGER"),
        "admin": make("Sara Khan", "sara@example.com", "ADMIN"),
        "admin2": make("Youssef Nasser", "youssef@example.com", "ADMIN"),
    }


@pytest.fixture()
def feedback_complete(client, people):
    """A campaign with one candidate at FEEDBACK_COMPLETE, ready for approval."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Approvals", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"], "manager_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "FEEDBACK_COMPLETE", "actor_id": people["manager"]["id"]},
    )
    return campaign_id, candidate_id


# ---------------------------------------------------------------------------
# Requesting approval
# ---------------------------------------------------------------------------

def test_requesting_approval_moves_the_candidate_and_names_the_chain(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    sent = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "grade": "G7", "salary_band": "40-48k",
            "justification": "Strongest candidate on console hours.",
            "actor_id": people["recruiter"]["id"],
        },
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "PENDING_APPROVAL"
    assert body["owner_name"] == "Aziz Rahman"


def test_requesting_approval_refuses_an_empty_chain(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [], "grade": "G7", "salary_band": "40-48k",
            "justification": "Strongest candidate.",
            "actor_id": people["recruiter"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "no named approver" in refused.json()["detail"]


def test_requesting_approval_writes_an_audit_row_naming_the_chain(
    client, feedback_complete, people, db_session
):
    campaign_id, candidate_id = feedback_complete
    client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "grade": "G7", "salary_band": "40-48k",
            "justification": "Strongest candidate on console hours.",
            "actor_id": people["recruiter"]["id"],
        },
    )
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.APPROVAL_REQUESTED)
    ).first()
    assert event is not None
    assert event.after["chain"][0]["name"] == "Aziz Rahman"
    assert event.after["chain"][0]["role_label"] == "Hiring manager"
    assert event.after["justification"] == "Strongest candidate on console hours."


# ---------------------------------------------------------------------------
# Cost centre and grant
# ---------------------------------------------------------------------------

def _requested(client, campaign_id, candidate_id, people):
    return client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "grade": "G7", "salary_band": "40-48k",
            "justification": "Strongest candidate on console hours.",
            "actor_id": people["recruiter"]["id"],
        },
    )


@pytest.fixture()
def cost_centre(client, people):
    """
    B13: the cost-centre step now validates against the `CostCentre`
    registry instead of accepting whatever code and budget holder the
    caller sends — this seeds the one the approval tests below claim.
    """
    return client.post("/api/cost-centres", json={
        "code": "CC-410", "name": "Operations", "budget_holder_id": people["admin2"]["id"],
    }).json()


def test_cost_centre_step_moves_the_candidate_to_the_budget_holder(
    client, feedback_complete, people, cost_centre
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    moved = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-410", "budget_holder_id": people["admin2"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )
    assert moved.status_code == 200
    body = moved.json()
    assert body["status"] == "PENDING_COST_CENTRE"
    assert body["owner_name"] == "Youssef Nasser"


def test_grant_moves_the_candidate_to_approved(client, feedback_complete, people, cost_centre):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-410", "budget_holder_id": people["admin2"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )

    granted = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/grant",
        json={"actor_id": people["admin2"]["id"], "note": "Budget confirmed for Q4."},
    )
    assert granted.status_code == 200
    assert granted.json()["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

def test_return_needs_a_reason_even_though_the_state_machine_does_not_force_one(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/return",
        json={"actor_id": people["manager"]["id"], "reason": ""},
    )
    assert refused.status_code == 422
    assert "reason" in refused.json()["detail"]


def test_return_from_pending_approval_goes_back_to_feedback_complete(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    returned = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/return",
        json={"actor_id": people["manager"]["id"], "reason": "Grade needs revising."},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "FEEDBACK_COMPLETE"


def test_return_from_pending_cost_centre_goes_back_to_pending_approval(
    client, feedback_complete, people, cost_centre
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-410", "budget_holder_id": people["admin2"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )

    returned = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/return",
        json={"actor_id": people["admin2"]["id"], "reason": "No budget this quarter."},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "PENDING_APPROVAL"


# ---------------------------------------------------------------------------
# Queue and history
# ---------------------------------------------------------------------------

def test_the_queue_shows_who_owes_the_decision_and_the_justification(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    queue = client.get(f"/api/campaigns/{campaign_id}/approvals/queue").json()
    assert len(queue) == 1
    row = queue[0]
    assert row["candidate_id"] == candidate_id
    assert row["owner_name"] == "Aziz Rahman"
    assert row["justification"] == "Strongest candidate on console hours."
    assert row["days_waiting"] >= 0


def test_the_history_reads_oldest_first_and_includes_a_return(
    client, feedback_complete, people
):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/return",
        json={"actor_id": people["manager"]["id"], "reason": "Grade needs revising."},
    )

    history = client.get(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}"
    ).json()
    actions = [h["action"] for h in history]
    assert actions == ["APPROVAL_REQUESTED", "APPROVAL_RETURNED"]
