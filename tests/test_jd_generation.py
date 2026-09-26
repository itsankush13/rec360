from unittest.mock import patch


def _create_campaign(client, job_title, job_description=""):
    response = client.post("/api/campaigns", json={
        "name": f"{job_title} hiring",
        "job_title": job_title,
        "job_description": job_description,
    })
    return response.json()["id"]


FAKE_GENERATION = {
    "jd_text": "We are hiring a Senior Software Engineer to build backend services.",
    "role_title": "Senior Software Engineer",
    "required_skills": ["Python", "AWS", "PostgreSQL"],
    "preferred_skills": ["Kubernetes"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science",
    "key_responsibilities": ["Own backend services"],
    "seniority_level": "Senior",
}


@patch("app.agents.jd_agent.generate_jd", return_value=FAKE_GENERATION)
def test_generate_returns_llm_output_and_does_not_persist(mock_generate, client):
    campaign_id = _create_campaign(client, "Software Engineer")

    response = client.post(f"/api/campaigns/{campaign_id}/jd/generate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jd_text"] == FAKE_GENERATION["jd_text"]
    assert body["required_skills"] == FAKE_GENERATION["required_skills"]
    assert body["source"] == "llm"
    assert body["matched_template"] == "software engineer"
    assert body["uncertain"] is False

    # A preview only — the campaign's own job_description is untouched.
    campaign = client.get(f"/api/campaigns/{campaign_id}").json()
    assert campaign["job_description"] == ""


@patch("app.agents.jd_agent.generate_jd", return_value=FAKE_GENERATION)
def test_generate_flags_uncertain_for_a_niche_role_even_when_llm_succeeds(mock_generate, client):
    campaign_id = _create_campaign(client, "Underwater Basket Weaving Instructor")

    response = client.post(f"/api/campaigns/{campaign_id}/jd/generate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["uncertain"] is True
    assert body["matched_template"] is None
    assert body["uncertainty_reason"]


@patch("app.agents.jd_agent.generate_jd", side_effect=RuntimeError("model unreachable"))
def test_generate_falls_back_to_template_when_llm_fails(mock_generate, client):
    campaign_id = _create_campaign(client, "Data Analyst")

    response = client.post(f"/api/campaigns/{campaign_id}/jd/generate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "template_only"
    assert body["matched_template"] == "data analyst"
    assert "SQL" in body["required_skills"]
    assert body["uncertain"] is True
    assert "unavailable" in body["uncertainty_reason"] or "failed" in body["uncertainty_reason"]


@patch("app.agents.jd_agent.generate_jd", side_effect=RuntimeError("model unreachable"))
def test_generate_fails_honestly_with_no_template_and_no_llm(mock_generate, client):
    campaign_id = _create_campaign(client, "Underwater Basket Weaving Instructor")

    response = client.post(f"/api/campaigns/{campaign_id}/jd/generate", json={})

    assert response.status_code == 422
    assert "template" in response.json()["detail"].lower()


@patch("app.agents.jd_agent.generate_jd")
def test_generate_passes_similar_prior_campaign_as_context(mock_generate, client):
    mock_generate.return_value = FAKE_GENERATION
    prior_id = _create_campaign(
        client, "Product Marketing Manager", job_description="A real prior JD for this role."
    )
    new_id = _create_campaign(client, "Product Marketing Manager")

    response = client.post(f"/api/campaigns/{new_id}/jd/generate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["based_on_campaign_ids"] == [prior_id]
    _, kwargs = mock_generate.call_args
    assert kwargs["similar_examples"] == ["A real prior JD for this role."]
    # A prior campaign of the same title exists, so this is not the
    # no-history niche-role case even though there's no built-in template.
    assert body["uncertain"] is False
