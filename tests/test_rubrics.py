"""
Phase B tests — rubric versioning, weight-sum-to-100 validation,
disqualification rules, immutability of approved versions, and the legacy
flat-JSON endpoints the existing screens still call.
"""
from unittest.mock import patch

import pytest

FAKE_JD_EXTRACTION = {
    "role_title": "Senior Software Engineer",
    "required_skills": ["Python", "AWS", "PostgreSQL"],
    "preferred_skills": ["Kubernetes"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science or related field",
    "key_responsibilities": ["Own backend services", "Mentor junior engineers"],
    "seniority_level": "Senior",
}


def _create_campaign(client):
    response = client.post("/api/campaigns", json={
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": "We need a senior backend engineer with Python and AWS experience.",
    })
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture()
def campaign_with_requirements(client):
    """A campaign whose Phase A requirements have been extracted."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = _create_campaign(client)
        extract = client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
        assert extract.status_code == 200
    return campaign_id


def _seeded_draft(client, campaign_id):
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"seed_from_requirements": True, "created_by": "Aarav Sharma"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, campaign_id, version_number, lock=False):
    submitted = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/{version_number}/submit",
        json={"submitted_by": "Aarav Sharma"},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/{version_number}/approve",
        json={"approved_by": "Priya Nair", "lock_immediately": lock},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


# ---------------------------------------------------------------------------
# Seeding from Phase A requirements
# ---------------------------------------------------------------------------

def test_seed_from_requirements_builds_balanced_weights(campaign_with_requirements, client):
    """Phase A hands over a partial 80-point budget; seeding must rescale to 100."""
    version = _seeded_draft(client, campaign_with_requirements)

    assert version["version_number"] == 1
    assert version["status"] == "DRAFT"
    assert version["weights"], "expected criteria seeded from requirements"
    assert version["is_balanced"] is True
    assert abs(version["weight_total"] - 100.0) < 0.01

    # Informational requirements are carried but must not affect the score.
    informational = [w for w in version["weights"] if w["requirement_type"] == "INFORMATIONAL"]
    assert informational
    assert all(w["weight"] == 0.0 for w in informational)

    # Every seeded criterion traces back to a real JobRequirement row.
    assert all(w["requirement_id"] for w in version["weights"])


def test_seed_creates_disqualification_rules_from_requirements(campaign_with_requirements, client):
    version = _seeded_draft(client, campaign_with_requirements)
    rules = version["disqualification_rules"]

    # Phase A marks the minimum-experience requirement as disqualifying.
    assert len(rules) == 1
    rule = rules[0]
    assert rule["rule_type"] == "MIN_YEARS_EXPERIENCE"
    assert rule["operator"] == "LT"
    assert rule["threshold"] == 5.0  # parsed out of "Minimum 5 years..."
    assert rule["severity"] == "HARD_FAIL"


def test_seeding_without_requirements_returns_422(client):
    campaign_id = _create_campaign(client)
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"seed_from_requirements": True},
    )
    assert response.status_code == 422


def test_empty_draft_can_be_created_and_filled_by_hand(client):
    campaign_id = _create_campaign(client)
    version = client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={}).json()
    assert version["weights"] == []
    assert version["weight_total"] == 0.0

    added = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
        json={"label": "Skills & Technical Expertise", "weight": 100},
    )
    assert added.status_code == 201
    assert added.json()["criterion_key"] == "skills_technical_expertise"


# ---------------------------------------------------------------------------
# Weight-sum-to-100 validation
# ---------------------------------------------------------------------------

def test_submit_rejected_when_weights_do_not_sum_to_100(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    version = _seeded_draft(client, campaign_id)
    weight_id = version["weights"][0]["id"]

    # Knock the total off 100.
    patched = client.patch(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/{weight_id}",
        json={"weight": 0},
    )
    assert patched.status_code == 200

    validation = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1/validate").json()
    assert validation["valid"] is False
    assert validation["is_balanced"] is False

    submitted = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={}
    )
    assert submitted.status_code == 422
    assert "100" in str(submitted.json()["detail"])


def test_normalize_weights_rebalances_to_exactly_100(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    for label, weight in [("Skills", 25), ("Experience", 20), ("Education", 10)]:
        client.post(
            f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
            json={"label": label, "weight": weight},
        )

    before = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert abs(before["weight_total"] - 55.0) < 0.01

    normalized = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/normalize"
    )
    assert normalized.status_code == 200
    body = normalized.json()
    assert body["is_balanced"] is True
    assert abs(body["weight_total"] - 100.0) < 0.01
    # Relative emphasis is preserved: Skills stays the heaviest.
    heaviest = max(body["weights"], key=lambda w: w["weight"])
    assert heaviest["label"] == "Skills"


def test_bulk_set_weights_saves_whole_table(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    for label in ["Skills", "Experience"]:
        client.post(
            f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
            json={"label": label, "weight": 10},
        )

    response = client.put(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
        json={"weights": [
            {"criterion_key": "skills", "weight": 60},
            {"criterion_key": "experience", "weight": 40},
        ]},
    )
    assert response.status_code == 200
    assert response.json()["is_balanced"] is True


def test_bulk_set_rejects_unknown_criterion_key(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    response = client.put(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
        json={"weights": [{"criterion_key": "does_not_exist", "weight": 100}]},
    )
    assert response.status_code == 422


def test_duplicate_criterion_key_is_rejected(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    payload = {"criterion_key": "skills", "label": "Skills", "weight": 50}
    assert client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights", json=payload
    ).status_code == 201
    assert client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights", json=payload
    ).status_code == 422


# ---------------------------------------------------------------------------
# Draft -> Submitted -> Approved -> Locked workflow
# ---------------------------------------------------------------------------

def test_full_approval_workflow_and_campaign_status_sync(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)

    submitted = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/submit",
        json={"submitted_by": "Aarav Sharma"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "SUBMITTED"
    # Submitting for approval moves the campaign along its own state graph.
    assert client.get(f"/api/campaigns/{campaign_id}").json()["status"] == "AWAITING_RUBRIC_APPROVAL"

    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
        json={"approved_by": "Priya Nair"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "APPROVED"
    assert body["approved_by"] == "Priya Nair"
    assert body["approved_at"] is not None
    # First approved rubric — nothing existed before it, so no re-evaluation.
    assert body["reevaluation_required"] is False
    assert client.get(f"/api/campaigns/{campaign_id}").json()["status"] == "APPROVED"

    locked = client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/lock")
    assert locked.status_code == 200
    assert locked.json()["status"] == "LOCKED"


def test_cannot_approve_without_submitting_first(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/approve", json={}
    )
    assert response.status_code == 409


def test_rejected_version_can_be_replaced_by_a_new_draft(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})

    rejected = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/reject",
        json={"rejected_by": "Priya Nair", "rejection_reason": "Skills over-weighted"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["rejection_reason"] == "Skills over-weighted"

    # A rejected version is terminal; the recruiter clones it into a new draft.
    clone = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1, "change_reason": "Rebalanced after rejection"},
    )
    assert clone.status_code == 201
    assert clone.json()["version_number"] == 2
    assert clone.json()["status"] == "DRAFT"


def test_only_one_draft_in_flight_at_a_time(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    second = client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Immutability — historical rubrics are never overwritten
# ---------------------------------------------------------------------------

def test_approved_version_cannot_be_edited(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    version = _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)
    weight_id = version["weights"][0]["id"]

    patched = client.patch(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/{weight_id}",
        json={"weight": 99},
    )
    assert patched.status_code == 409

    deleted = client.delete(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/{weight_id}"
    )
    assert deleted.status_code == 409

    added_rule = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules",
        json={"label": "Must hold work authorization"},
    )
    assert added_rule.status_code == 409


def test_approved_version_cannot_be_deleted(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)
    assert client.delete(f"/api/campaigns/{campaign_id}/rubric/versions/1").status_code == 409


def test_draft_version_can_be_deleted(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    assert client.delete(f"/api/campaigns/{campaign_id}/rubric/versions/1").status_code == 204


def test_approving_new_version_supersedes_old_without_mutating_its_weights(
    campaign_with_requirements, client
):
    campaign_id = campaign_with_requirements
    v1 = _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)
    v1_weights = {w["criterion_key"]: w["weight"] for w in v1["weights"]}

    # Clone v1, rebalance it hard, and approve as v2.
    clone = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1, "change_reason": "Hiring manager wants skills-first"},
    ).json()
    assert clone["version_number"] == 2
    keys = [w["criterion_key"] for w in clone["weights"]]
    client.put(
        f"/api/campaigns/{campaign_id}/rubric/versions/2/weights",
        json={"weights": [
            {"criterion_key": keys[0], "weight": 100},
            *[{"criterion_key": k, "weight": 0} for k in keys[1:]],
        ]},
    )
    v2 = _approve(client, campaign_id, 2)

    assert v2["status"] == "APPROVED"
    assert v2["supersedes_version_id"] == v1["id"]
    # Results already on file were scored under v1 — flag, don't auto-rescore.
    assert v2["reevaluation_required"] is True

    # v1 is now SUPERSEDED but its weights are byte-for-byte unchanged.
    v1_after = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert v1_after["status"] == "SUPERSEDED"
    assert v1_after["superseded_at"] is not None
    assert {w["criterion_key"]: w["weight"] for w in v1_after["weights"]} == v1_weights

    # /active always points at the newest approved version.
    active = client.get(f"/api/campaigns/{campaign_id}/rubric/active").json()
    assert active["version_number"] == 2


def test_clone_copies_weights_and_rules_independently(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    v1 = _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)

    clone = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1},
    ).json()

    assert clone["cloned_from_version_id"] == v1["id"]
    assert len(clone["weights"]) == len(v1["weights"])
    assert len(clone["disqualification_rules"]) == len(v1["disqualification_rules"])
    # Copies, not shared rows.
    original_ids = {w["id"] for w in v1["weights"]}
    assert not (original_ids & {w["id"] for w in clone["weights"]})


def test_acknowledge_reevaluation_clears_the_flag(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={"clone_from_version": 1})
    v2 = _approve(client, campaign_id, 2)
    assert v2["reevaluation_required"] is True

    acked = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/2/acknowledge-reevaluation",
        json={"acknowledged_by": "Priya Nair"},
    )
    assert acked.status_code == 200
    assert acked.json()["reevaluation_required"] is False
    assert acked.json()["reevaluation_acknowledged_by"] == "Priya Nair"

    # Idempotency guard: acknowledging twice is a conflict, not a silent no-op.
    assert client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/2/acknowledge-reevaluation", json={}
    ).status_code == 409


# ---------------------------------------------------------------------------
# Disqualification rules
# ---------------------------------------------------------------------------

def test_add_and_update_disqualification_rule(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})

    created = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules",
        json={
            "label": "Minimum 5 years experience",
            "rule_type": "MIN_YEARS_EXPERIENCE",
            "operator": "LT",
            "threshold": 5,
            "severity": "HARD_FAIL",
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert created.json()["code"] == "minimum_5_years_experience"

    updated = client.patch(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules/{rule_id}",
        json={"severity": "REVIEW_REQUIRED", "threshold": 3},
    )
    assert updated.status_code == 200
    assert updated.json()["severity"] == "REVIEW_REQUIRED"
    assert updated.json()["threshold"] == 3.0

    assert client.delete(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules/{rule_id}"
    ).status_code == 204


def test_numeric_rule_without_threshold_is_rejected(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules",
        json={"label": "Too little experience", "operator": "LT"},
    )
    assert response.status_code == 422


def test_rule_cannot_reference_another_campaigns_requirement(campaign_with_requirements, client):
    other_campaign = campaign_with_requirements
    foreign_requirement = client.get(
        f"/api/campaigns/{other_campaign}/requirements"
    ).json()[0]["id"]

    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/rules",
        json={"label": "Borrowed requirement", "requirement_id": foreign_requirement},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Version history / lookups
# ---------------------------------------------------------------------------

def test_rubric_history_lists_every_version(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    _approve(client, campaign_id, 1)
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={"clone_from_version": 1})
    _approve(client, campaign_id, 2)

    rubric = client.get(f"/api/campaigns/{campaign_id}/rubric").json()
    assert [v["version_number"] for v in rubric["versions"]] == [1, 2]
    assert [v["status"] for v in rubric["versions"]] == ["SUPERSEDED", "APPROVED"]
    assert rubric["active_version_number"] == 2

    history = client.get(f"/api/campaigns/{campaign_id}/rubric/versions").json()
    assert len(history) == 2


def test_active_returns_404_before_any_approval(campaign_with_requirements, client):
    campaign_id = campaign_with_requirements
    _seeded_draft(client, campaign_id)
    assert client.get(f"/api/campaigns/{campaign_id}/rubric/active").status_code == 404


def test_rubric_endpoints_404_for_unknown_campaign(client):
    assert client.get("/api/campaigns/nope/rubric").status_code == 404
    assert client.get("/api/campaigns/nope/rubric/versions").status_code == 404
    assert client.post(
        "/api/campaigns/nope/rubric/versions", json={}
    ).status_code == 404


def test_unknown_version_number_returns_404(client):
    campaign_id = _create_campaign(client)
    assert client.get(f"/api/campaigns/{campaign_id}/rubric/versions/7").status_code == 404


# ---------------------------------------------------------------------------
# Legacy flat-JSON compatibility — the existing screens must keep working
# ---------------------------------------------------------------------------

LEGACY_RUBRIC = [
    {"criterion": "Skills & Technical Expertise", "weight": 25, "type": "Mandatory"},
    {"criterion": "Experience & Relevance", "weight": 20, "type": "Mandatory"},
    {"criterion": "Education & Certifications", "weight": 10, "type": "Mandatory"},
    {"criterion": "Industry Experience", "weight": 10, "type": "Preferred"},
    {"criterion": "Role Seniority", "weight": 10, "type": "Preferred"},
    {"criterion": "Cultural Fit", "weight": 5, "type": "Informational"},
]


def test_legacy_save_rubric_keeps_its_response_contract(client):
    campaign_id = _create_campaign(client)
    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version_id"] == 1
    assert body["campaign_id"] == campaign_id
    assert body["approved"] is False
    assert len(body["rubric"]) == 6
    assert body["rubric"][0]["criterion"] == "Skills & Technical Expertise"
    assert body["rubric"][0]["type"] == "Mandatory"


def test_legacy_save_works_for_a_campaign_id_that_does_not_exist_yet(client):
    """The old React client posts opaque ids like "1"; it must not 404."""
    response = client.post("/api/campaigns/1/rubric", json={"rubric": LEGACY_RUBRIC})
    assert response.status_code == 200
    assert response.json()["campaign_id"] == "1"


def test_legacy_approve_normalizes_an_unbalanced_rubric(client):
    """The shipped default sums to 80 — approve must succeed and still land 100."""
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})

    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/approve", json={"version_id": None}
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert approved.json()["approved_at"] is not None

    stored = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert stored["status"] == "APPROVED"
    assert stored["is_balanced"] is True


def test_legacy_approve_with_explicit_version_id(client):
    campaign_id = _create_campaign(client)
    saved = client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})
    version_id = saved.json()["version_id"]

    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/approve", json={"version_id": version_id}
    )
    assert approved.status_code == 200
    assert approved.json()["version_id"] == version_id


def test_legacy_approve_without_any_draft_returns_404(client):
    campaign_id = _create_campaign(client)
    response = client.post(f"/api/campaigns/{campaign_id}/rubric/approve", json={})
    assert response.status_code == 404


def test_legacy_save_replaces_pending_draft_instead_of_stacking(client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})
    second = client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})
    assert second.status_code == 200
    history = client.get(f"/api/campaigns/{campaign_id}/rubric/versions").json()
    assert len(history) == 1


def test_legacy_save_after_approval_creates_a_new_version(client):
    """Approved rubrics are never overwritten, even via the legacy path."""
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})
    client.post(f"/api/campaigns/{campaign_id}/rubric/approve", json={})

    resaved = client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": LEGACY_RUBRIC})
    assert resaved.status_code == 200
    assert resaved.json()["version_id"] == 2

    v1 = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert v1["status"] == "APPROVED"


def test_legacy_empty_rubric_is_rejected(client):
    campaign_id = _create_campaign(client)
    response = client.post(f"/api/campaigns/{campaign_id}/rubric", json={"rubric": []})
    assert response.status_code == 422
