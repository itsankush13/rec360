"""
Extends B07 ("Allow HR override and custom criteria") with a per-JD,
LLM-tailored weight suggestion for every active criterion — as opposed to
the static MARKET_STANDARD preset in `app.core.rubric_presets`.
"""
from unittest.mock import patch

import pytest


def _create_campaign(client, job_description="We need a senior backend engineer."):
    response = client.post("/api/campaigns", json={
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": job_description,
    })
    assert response.status_code == 201
    return response.json()["id"]


def _draft_with_weights(client, campaign_id):
    """An empty draft with three hand-picked, predictably-keyed criteria."""
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={})
    for key, label, weight in [
        ("skills", "Skills", 10),
        ("experience", "Experience", 20),
        ("education", "Education", 30),
    ]:
        response = client.post(
            f"/api/campaigns/{campaign_id}/rubric/versions/1/weights",
            json={"criterion_key": key, "label": label, "weight": weight},
        )
        assert response.status_code == 201, response.text
    return campaign_id


@patch(
    "app.agents.weight_suggestion_agent.suggest_weights",
    return_value={"skills": 40, "experience": 40, "education": 40},
)
def test_suggest_weights_returns_normalized_weights_and_persists(mock_suggest, client):
    campaign_id = _draft_with_weights(client, _create_campaign(client))

    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/suggest"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_balanced"] is True
    assert abs(body["weight_total"] - 100.0) < 0.01
    by_key = {w["criterion_key"]: w["weight"] for w in body["weights"]}
    # All three came back equal from the model, so they stay equal (within
    # 2dp rounding) after rescale to 100.
    assert abs(by_key["skills"] - by_key["experience"]) < 0.02
    assert abs(by_key["experience"] - by_key["education"]) < 0.02

    # Persisted, not just returned.
    persisted = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert abs(persisted["weight_total"] - 100.0) < 0.01


@patch(
    "app.agents.weight_suggestion_agent.suggest_weights",
    side_effect=RuntimeError("model unreachable"),
)
def test_suggest_weights_surfaces_clean_4xx_when_llm_fails(mock_suggest, client):
    campaign_id = _draft_with_weights(client, _create_campaign(client))

    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/suggest"
    )

    assert response.status_code == 422
    assert "manually" in str(response.json()["detail"]).lower()


@patch(
    "app.agents.weight_suggestion_agent.suggest_weights",
    return_value={"skills": 50, "experience": 50},
)
def test_suggest_weights_keeps_prior_weight_for_omitted_criterion(mock_suggest, client):
    """The model omitted 'education' — its prior weight (30) is kept, not zeroed,
    and it still gets its proportional share after the sum-to-100 rescale."""
    campaign_id = _draft_with_weights(client, _create_campaign(client))

    response = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/weights/suggest"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert abs(body["weight_total"] - 100.0) < 0.01
    by_key = {w["criterion_key"]: w["weight"] for w in body["weights"]}
    assert by_key["education"] > 0
