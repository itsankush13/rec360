"""
B17 — what-if proposal workflow: send previewed weights to a named hiring
manager, separate the proposer from the approver, audit both the proposed
and the approved versions.

`app.core.analytics.what_if()` itself (tested in `test_analytics.py`) is
untouched — these tests are about the one write path this backlog item
requires: a proposal record and its decision.
"""
from app.db.models import AuditAction, AuditEvent

from tests.test_analytics import analysed_campaign  # noqa: F401
from tests.test_lifecycle import people  # noqa: F401


def _baseline_keys(client, campaign_id):
    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    return [c["criterion_key"] for c in baseline["criteria"]]


def _skewed_weights(keys):
    weights = {k: 0.0 for k in keys}
    weights[keys[0]] = 100.0
    return weights


def test_propose_creates_a_pending_proposal(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
            "note": "Weighting mandatory criteria higher for this role.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PROPOSED"
    assert body["proposed_by_name"] == "Fatima Al-Rashid"
    assert body["approver_name"] == "Aziz Rahman"
    assert body["approved_weights"] is None
    assert body["rubric_version_number"] == 1


def test_propose_requires_a_hiring_manager_approver(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    other_recruiter = client.post("/api/users", json={
        "full_name": "Second Recruiter", "email": "second@example.com",
        "role": "RECRUITER",
    }).json()

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": other_recruiter["id"],
        },
    )
    assert response.status_code == 422
    assert "not a hiring manager" in str(response.json()["detail"])


def test_hiring_manager_can_propose_weights_to_hr(analysed_campaign, people, client):
    """The reverse direction: the hiring manager proposes, HR decides."""
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["manager"]["id"],
            "approver_id": people["recruiter"]["id"],
            "note": "Can we weight this differently?",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PROPOSED"
    assert body["proposed_by_name"] == "Aziz Rahman"
    assert body["approver_name"] == "Fatima Al-Rashid"

    approve = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{body['id']}/approve",
        json={"decided_by": people["recruiter"]["id"]},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"


def test_propose_requires_hr_approver_when_proposer_is_the_manager(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    other_manager = client.post("/api/users", json={
        "full_name": "Second Manager", "email": "second-manager@example.com",
        "role": "HIRING_MANAGER",
    }).json()

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["manager"]["id"],
            "approver_id": other_manager["id"],
        },
    )
    assert response.status_code == 422
    assert "not HR" in str(response.json()["detail"])


def test_propose_rejects_proposer_as_approver(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["manager"]["id"],
            "approver_id": people["manager"]["id"],
        },
    )
    assert response.status_code == 422
    assert "different people" in str(response.json()["detail"])


def test_propose_validates_weight_shape(analysed_campaign, people, client):
    """Reuses analytics.validate_weights — an unbalanced set is still refused."""
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": {keys[0]: 50.0},
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    )
    assert response.status_code == 422
    assert "not 100" in str(response.json()["detail"])


def test_only_the_named_approver_can_decide(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    other_manager = client.post("/api/users", json={
        "full_name": "Other Manager", "email": "other-manager@example.com",
        "role": "HIRING_MANAGER",
    }).json()

    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": other_manager["id"]},
    )
    assert response.status_code == 422
    assert "this proposal was sent to" in str(response.json()["detail"])


def test_approve_persists_nothing_to_rubric_or_evaluations(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    rubric_before = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    evaluations_before = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()

    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()
    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": people["manager"]["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["approved_weights"] == _skewed_weights(keys)
    assert body["decided_by_name"] == "Aziz Rahman"

    rubric_after = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    evaluations_after = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    assert rubric_before == rubric_after
    assert evaluations_before == evaluations_after


def test_approve_can_amend_the_proposed_weights(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    proposed = _skewed_weights(keys)
    amended = {k: 0.0 for k in keys}
    amended[keys[1]] = 100.0

    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": proposed,
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()
    body = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": people["manager"]["id"], "weights": amended},
    ).json()

    assert body["proposed_weights"] == proposed
    assert body["approved_weights"] == amended
    assert body["proposed_weights"] != body["approved_weights"]


def test_reject_requires_a_reason(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/reject",
        json={"decided_by": people["manager"]["id"], "note": ""},
    )
    assert response.status_code == 422
    assert "needs a reason" in str(response.json()["detail"])

    rejected = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/reject",
        json={"decided_by": people["manager"]["id"], "note": "Not aligned with the JD."},
    ).json()
    assert rejected["status"] == "REJECTED"
    assert rejected["decision_note"] == "Not aligned with the JD."


def test_a_decided_proposal_cannot_be_decided_again(analysed_campaign, people, client):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()
    client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": people["manager"]["id"]},
    )

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/reject",
        json={"decided_by": people["manager"]["id"], "note": "Too late."},
    )
    assert response.status_code == 422
    assert "already approved" in str(response.json()["detail"])


def test_propose_and_approve_each_write_their_own_audit_event(
    analysed_campaign, people, client, db_session,
):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    proposed = _skewed_weights(keys)
    amended = {k: 0.0 for k in keys}
    amended[keys[1]] = 100.0

    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": proposed,
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()
    client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": people["manager"]["id"], "weights": amended},
    )

    events = db_session.query(AuditEvent).filter(
        AuditEvent.entity_type == "whatif_proposal",
        AuditEvent.entity_id == proposal["id"],
    ).order_by(AuditEvent.created_at).all()

    assert [e.action for e in events] == [
        AuditAction.APPROVAL_REQUESTED, AuditAction.APPROVAL_GRANTED,
    ]
    assert events[0].after["proposed_weights"] == proposed
    assert events[1].before["proposed_weights"] == proposed
    assert events[1].after["approved_weights"] == amended


def test_proposal_needs_an_approved_rubric(client, people):
    campaign_id = client.post("/api/campaigns", json={
        "name": "No rubric", "job_title": "Engineer", "job_description": "x",
    }).json()["id"]

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": {"anything": 100.0},
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    )
    assert response.status_code == 422
    assert "no approved rubric" in str(response.json()["detail"])


# ---------------------------------------------------------------------------
# Wiring an approved proposal into a real RubricVersion draft — the B17
# remainder: approving authorizes proceeding to a real rubric revision, it
# does not perform one on its own.
# ---------------------------------------------------------------------------

def _approved_proposal(client, campaign_id, people, keys):
    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()
    return client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/approve",
        json={"decided_by": people["manager"]["id"]},
    ).json()


def test_approving_alone_creates_no_rubric_draft(analysed_campaign, people, client):
    """Matches `whatif_service`'s own docstring: approving authorizes, it
    does not perform, a rubric revision."""
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    approved = _approved_proposal(client, campaign_id, people, keys)

    assert approved["draft_version_id"] is None
    versions = client.get(f"/api/campaigns/{campaign_id}/rubric/versions").json()
    assert len(versions) == 1  # only the already-approved version 1


def test_create_draft_turns_an_approved_proposal_into_a_real_rubric_draft(
    analysed_campaign, people, client,
):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    approved = _approved_proposal(client, campaign_id, people, keys)

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{approved['id']}/create-draft",
        json={"created_by": people["manager"]["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft_version_id"] is not None
    assert body["draft_version_number"] == 2

    draft = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/2").json()
    assert draft["status"] == "DRAFT"
    by_key = {w["criterion_key"]: w["weight"] for w in draft["weights"]}
    assert by_key[keys[0]] == 100.0


def test_create_draft_refuses_a_proposal_that_is_not_yet_approved(
    analysed_campaign, people, client,
):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    proposal = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals",
        json={
            "weights": _skewed_weights(keys),
            "proposed_by": people["recruiter"]["id"],
            "approver_id": people["manager"]["id"],
        },
    ).json()

    refused = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{proposal['id']}/create-draft",
        json={"created_by": people["manager"]["id"]},
    )
    assert refused.status_code == 422
    assert "not approved" in str(refused.json()["detail"])


def test_create_draft_refuses_a_second_draft_from_the_same_proposal(
    analysed_campaign, people, client,
):
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    approved = _approved_proposal(client, campaign_id, people, keys)
    client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{approved['id']}/create-draft",
        json={"created_by": people["manager"]["id"]},
    )

    refused = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{approved['id']}/create-draft",
        json={"created_by": people["manager"]["id"]},
    )
    assert refused.status_code == 422
    assert "already been created" in str(refused.json()["detail"])


def test_create_draft_surfaces_an_unrelated_draft_already_in_flight(
    analysed_campaign, people, client,
):
    """`rubric_service.create_version` allows only one DRAFT/SUBMITTED
    version per rubric at a time. If someone started an unrelated draft
    first, this must be a clear 422, not a silent overwrite or a 500."""
    campaign_id, _, _ = analysed_campaign
    keys = _baseline_keys(client, campaign_id)
    approved = _approved_proposal(client, campaign_id, people, keys)

    other_draft = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions", json={"clone_from_version": 1},
    )
    assert other_draft.status_code == 201

    refused = client.post(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{approved['id']}/create-draft",
        json={"created_by": people["manager"]["id"]},
    )
    assert refused.status_code == 422
    assert "already" in str(refused.json()["detail"])
    # The proposal itself stays approved and retryable — it is not consumed
    # by the failed attempt.
    proposal_after = client.get(
        f"/api/campaigns/{campaign_id}/what-if/proposals/{approved['id']}"
    ).json()
    assert proposal_after["status"] == "APPROVED"
    assert proposal_after["draft_version_id"] is None
