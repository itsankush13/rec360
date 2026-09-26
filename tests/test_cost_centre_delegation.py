"""
B13 — cost-centre controls and delegation of authority.

Before this, `POST .../cost-centre` logged whatever code and budget holder
the caller sent, with nothing checked. These tests cover the registry and
grant ledger that make both claims checkable.
"""
from tests.test_approvals_api import _requested, feedback_complete, people


# ---------------------------------------------------------------------------
# Cost-centre registry
# ---------------------------------------------------------------------------

def test_creating_a_cost_centre_requires_a_real_active_budget_holder(client, people):
    created = client.post("/api/cost-centres", json={
        "code": "cc-500", "name": "Plant Ops", "budget_holder_id": people["admin"]["id"],
    })
    assert created.status_code == 201
    body = created.json()
    # Codes are normalized upper-case so "CC-500" and "cc-500" collide.
    assert body["code"] == "CC-500"
    assert body["budget_holder_id"] == people["admin"]["id"]
    assert body["active"] is True


def test_a_cost_centre_can_carry_its_bu_budget_envelope(client, people):
    """Demo-readiness pass, 2026-09-14: business_unit/currency/fiscal_year/
    role_grade/approved_headcount/salary_band_min-max — the pre-approved BU
    envelope the approvals page shows, all in one stated currency so no
    screen has to convert between currencies to display it."""
    created = client.post("/api/cost-centres", json={
        "code": "CC-QCHEM-ICE", "name": "Instrumentation & Control", "budget_holder_id": people["admin"]["id"],
        "business_unit": "Technical Services", "currency": "QAR", "fiscal_year": "FY2026",
        "role_grade": "Engineer II", "approved_headcount": 2,
        "salary_band_min": 180000, "salary_band_max": 220000,
    })
    assert created.status_code == 201
    body = created.json()
    assert body["business_unit"] == "Technical Services"
    assert body["currency"] == "QAR"
    assert body["fiscal_year"] == "FY2026"
    assert body["approved_headcount"] == 2
    assert body["salary_band_min"] == 180000
    assert body["salary_band_max"] == 220000


def test_a_cost_centre_without_a_budget_envelope_still_defaults_to_usd(client, people):
    created = client.post("/api/cost-centres", json={
        "code": "CC-PLAIN", "name": "Plain Ops", "budget_holder_id": people["admin"]["id"],
    })
    assert created.status_code == 201
    assert created.json()["currency"] == "USD"


def test_creating_a_cost_centre_refuses_an_unknown_budget_holder(client):
    refused = client.post("/api/cost-centres", json={
        "code": "CC-600", "name": "Plant Ops", "budget_holder_id": "not-a-real-user",
    })
    assert refused.status_code == 422


def test_a_duplicate_code_is_refused(client, people):
    client.post("/api/cost-centres", json={
        "code": "CC-700", "name": "Ops", "budget_holder_id": people["admin"]["id"],
    })
    dup = client.post("/api/cost-centres", json={
        "code": "CC-700", "name": "Different name", "budget_holder_id": people["admin2"]["id"],
    })
    assert dup.status_code == 422
    assert "already on file" in dup.json()["detail"]


def test_cost_centre_step_refuses_a_code_not_on_file(client, feedback_complete, people):
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-DOES-NOT-EXIST",
            "budget_holder_id": people["admin2"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "not a cost centre on file" in refused.json()["detail"]


def test_cost_centre_step_refuses_a_claimed_budget_holder_who_does_not_hold_it(
    client, feedback_complete, people,
):
    client.post("/api/cost-centres", json={
        "code": "CC-410", "name": "Operations", "budget_holder_id": people["admin2"]["id"],
    })
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    # people["admin"] is not the registered holder of CC-410 — admin2 is.
    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-410", "budget_holder_id": people["admin"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "does not hold the budget" in refused.json()["detail"]


def test_cost_centre_step_routes_to_the_registrys_holder_even_if_correctly_claimed(
    client, feedback_complete, people,
):
    client.post("/api/cost-centres", json={
        "code": "CC-410", "name": "Operations", "budget_holder_id": people["admin2"]["id"],
    })
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
    assert moved.json()["owner_name"] == "Youssef Nasser"


def test_a_closed_cost_centre_refuses_new_approvals(client, feedback_complete, people):
    client.post("/api/cost-centres", json={
        "code": "CC-410", "name": "Operations", "budget_holder_id": people["admin2"]["id"],
    })
    client.post("/api/cost-centres/CC-410/close")
    campaign_id, candidate_id = feedback_complete
    _requested(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre",
        json={
            "cost_centre_code": "CC-410", "budget_holder_id": people["admin2"]["id"],
            "actor_id": people["manager"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "closed" in refused.json()["detail"]


# ---------------------------------------------------------------------------
# Delegation of authority
# ---------------------------------------------------------------------------

def test_delegation_grant_requires_two_different_real_people(client, people):
    refused = client.post("/api/delegations", json={
        "grantor_id": people["admin"]["id"], "delegate_id": people["admin"]["id"],
        "created_by": people["admin"]["id"],
    })
    assert refused.status_code == 422
    assert "cannot delegate authority to themselves" in refused.json()["detail"]

    ok = client.post("/api/delegations", json={
        "grantor_id": people["admin"]["id"], "delegate_id": people["manager"]["id"],
        "created_by": people["admin"]["id"],
    })
    assert ok.status_code == 201
    assert ok.json()["revoked_at"] is None


def test_approval_claiming_a_delegation_with_no_grant_is_refused(
    client, feedback_complete, people,
):
    campaign_id, candidate_id = feedback_complete
    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "justification": "Panel recommends hire.",
            "actor_id": people["recruiter"]["id"],
            # Claims to act for the admin, but nobody granted that.
            "on_behalf_of_id": people["admin"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "delegation" in refused.json()["detail"].lower()


def test_approval_with_an_active_delegation_succeeds_and_is_recorded(
    client, feedback_complete, people, db_session,
):
    campaign_id, candidate_id = feedback_complete
    client.post("/api/delegations", json={
        "grantor_id": people["admin"]["id"], "delegate_id": people["recruiter"]["id"],
        "created_by": people["admin"]["id"], "campaign_id": campaign_id,
    })

    sent = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "justification": "Panel recommends hire.",
            "actor_id": people["recruiter"]["id"],
            "on_behalf_of_id": people["admin"]["id"],
        },
    )
    assert sent.status_code == 200

    from app.db.models import LifecycleTransition
    transition = db_session.query(LifecycleTransition).filter_by(
        candidate_id=candidate_id, to_status="PENDING_APPROVAL",
    ).first()
    assert transition.on_behalf_of_id == people["admin"]["id"]


def test_a_revoked_delegation_no_longer_authorizes(client, feedback_complete, people):
    campaign_id, candidate_id = feedback_complete
    grant = client.post("/api/delegations", json={
        "grantor_id": people["admin"]["id"], "delegate_id": people["recruiter"]["id"],
        "created_by": people["admin"]["id"],
    }).json()
    client.post(f"/api/delegations/{grant['id']}/revoke")

    refused = client.post(
        f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request",
        json={
            "chain": [people["manager"]["id"], people["admin"]["id"]],
            "justification": "Panel recommends hire.",
            "actor_id": people["recruiter"]["id"],
            "on_behalf_of_id": people["admin"]["id"],
        },
    )
    assert refused.status_code == 422
