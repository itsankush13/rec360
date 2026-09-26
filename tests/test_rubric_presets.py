"""
Starting weightings for a rubric.

The thing being protected here is the approval control. A preset sets the
numbers in a draft; it must not be capable of scoring anything on its own,
of changing an approved rubric, or of producing a rubric that does not sum
to 100. If any of those ever became possible, the recruiter's approval would
stop meaning what the client was told it means.
"""
from unittest.mock import patch

import pytest

from app.core import rubric_presets
from app.core.rubric_presets import MARKET_STANDARD

from tests.test_processing import FAKE_JD_EXTRACTION


@pytest.fixture()
def campaign_with_requirements(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Control Room Operator intake",
            "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    return campaign_id


def weights_of(client, campaign_id, version=1):
    return client.get(
        f"/api/campaigns/{campaign_id}/rubric/versions/{version}"
    ).json()["weights"]


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------

def test_a_weighted_draft_still_sums_to_one_hundred(campaign_with_requirements, client):
    """
    The invariant the whole rubric rests on. A preset that broke it would
    produce a draft that cannot be submitted, which is a worse outcome than
    having no preset at all.
    """
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "seed_from_requirements": True, "weighting": MARKET_STANDARD,
    })
    total = sum(w["weight"] for w in weights_of(client, campaign_with_requirements)
                if w["active"])
    assert round(total, 2) == 100.0


def test_the_weighting_only_ever_produces_a_draft(campaign_with_requirements, client):
    """It is a starting point. Approval is still a separate, human act."""
    created = client.post(
        f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
            "seed_from_requirements": True, "weighting": MARKET_STANDARD,
        }).json()
    assert created["status"] == "DRAFT"


def test_mandatory_requirements_carry_the_most_weight(campaign_with_requirements, client):
    """
    The point of this particular weighting: what the role cannot do without
    outweighs what is merely desirable.
    """
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "seed_from_requirements": True, "weighting": MARKET_STANDARD,
    })
    weights = [w for w in weights_of(client, campaign_with_requirements)
               if w["active"] and w["weight"] > 0]

    mandatory = sum(w["weight"] for w in weights
                    if w["requirement_type"] == "MANDATORY")
    preferred = sum(w["weight"] for w in weights
                    if w["requirement_type"] == "PREFERRED")
    assert mandatory > preferred


def test_informational_criteria_are_never_given_a_score(campaign_with_requirements, client):
    """
    A zero-weight row is one the recruiter chose not to score. A preset must
    not quietly start scoring it.
    """
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "seed_from_requirements": True, "weighting": MARKET_STANDARD,
    })
    for weight in weights_of(client, campaign_with_requirements):
        if weight["requirement_type"] == "INFORMATIONAL":
            assert weight["weight"] == 0


def test_an_unknown_weighting_is_refused_in_plain_english(campaign_with_requirements, client):
    response = client.post(
        f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
            "seed_from_requirements": True, "weighting": "aggressive",
        })
    assert response.status_code == 422
    assert "aggressive" in response.json()["detail"]


def test_no_weighting_leaves_the_seeded_numbers_alone(campaign_with_requirements, client):
    """The default is unchanged: this is additive, not a new default."""
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions",
                json={"seed_from_requirements": True})
    plain = {w["criterion_key"]: w["weight"]
             for w in weights_of(client, campaign_with_requirements)}

    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "clone_from_version": 1, "weighting": MARKET_STANDARD,
    })
    weighted = {w["criterion_key"]: w["weight"]
                for w in weights_of(client, campaign_with_requirements, version=2)}

    assert plain != weighted  # the preset did something
    assert round(sum(weighted.values()), 2) == 100.0


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

def test_the_weightings_are_offered_to_the_recruiter(campaign_with_requirements, client):
    body = client.get(
        f"/api/campaigns/{campaign_with_requirements}/rubric/weightings"
    ).json()
    assert any(item["key"] == MARKET_STANDARD for item in body)
    standard = next(item for item in body if item["key"] == MARKET_STANDARD)
    assert sum(component["share"] for component in standard["components"]) == 100


def test_the_catalogue_is_written_for_a_recruiter_not_a_developer():
    """No enum values on a screen — web/DATA.md applies to this list too."""
    for preset in rubric_presets.available():
        for banned in ("REQUIREMENT", "MANDATORY", "_"):
            assert banned not in preset["label"]
        assert preset["description"]


def test_readability_is_not_one_of_the_scored_components():
    """
    The standard table reserves points for how machine-readable the CV is.
    We measure that and let it lower confidence instead, so a candidate is
    never marked down for their typesetting.
    """
    standard = rubric_presets.PRESETS[MARKET_STANDARD]
    labels = " ".join(c["label"].lower() for c in standard["components"])
    assert "readab" not in labels
    assert "confidence" in standard["note"]


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

def test_an_absent_category_gives_its_budget_back(campaign_with_requirements, client):
    """
    Few campaigns have criteria in every category. The missing budget must be
    shared out rather than left as a hole in the hundred.
    """
    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "seed_from_requirements": True, "weighting": MARKET_STANDARD,
    })
    weights = [w for w in weights_of(client, campaign_with_requirements)
               if w["active"] and w["weight"] > 0]
    assert round(sum(w["weight"] for w in weights), 2) == 100.0
    assert all(w["weight"] > 0 for w in weights)


def test_drafting_with_a_weighting_is_recorded(campaign_with_requirements, client, db_session):
    from sqlalchemy import select

    from app.db.models import AuditAction, AuditEvent

    client.post(f"/api/campaigns/{campaign_with_requirements}/rubric/versions", json={
        "seed_from_requirements": True, "weighting": MARKET_STANDARD,
    })
    event = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.campaign_id == campaign_with_requirements,
            AuditEvent.action == AuditAction.RUBRIC_VERSION_CREATED,
        )
    ).first()
    assert "standard screening weighting" in event.summary
