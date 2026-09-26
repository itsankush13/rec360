from unittest.mock import patch


def _create_campaign(client):
    response = client.post("/api/campaigns", json={
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": "We need a senior backend engineer with Python and AWS experience.",
    })
    return response.json()["id"]


FAKE_JD_EXTRACTION = {
    "role_title": "Senior Software Engineer",
    "required_skills": ["Python", "AWS", "PostgreSQL"],
    "preferred_skills": ["Kubernetes"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science or related field",
    "key_responsibilities": ["Own backend services", "Mentor junior engineers"],
    "seniority_level": "Senior",
}


@patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION)
def test_extract_requirements_creates_structured_rows(mock_parse_jd, client):
    campaign_id = _create_campaign(client)
    response = client.post(
        f"/api/campaigns/{campaign_id}/requirements/extract",
        json={},
    )
    assert response.status_code == 200
    rows = response.json()

    # 3 required skills + 1 preferred skill + experience + education + seniority + 2 responsibilities = 9
    assert len(rows) == 9
    mandatory_skills = [r for r in rows if r["category"] == "SKILL" and r["requirement_type"] == "MANDATORY"]
    assert {r["description"] for r in mandatory_skills} == {"Python", "AWS", "PostgreSQL"}
    # mandatory skills should split a 40-point weight budget evenly
    assert abs(sum(r["weight"] for r in mandatory_skills) - 40.0) < 0.1

    experience_rows = [r for r in rows if r["category"] == "EXPERIENCE"]
    assert experience_rows[0]["disqualifying"] is True
    mock_parse_jd.assert_called_once()


@patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION)
def test_re_extraction_does_not_duplicate_ai_rows(mock_parse_jd, client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    second = client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    assert len(second.json()) == 9

    listed = client.get(f"/api/campaigns/{campaign_id}/requirements")
    assert len(listed.json()) == 9


@patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION)
def test_manual_requirement_survives_re_extraction(mock_parse_jd, client):
    campaign_id = _create_campaign(client)
    client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    manual = client.post(f"/api/campaigns/{campaign_id}/requirements", json={
        "description": "Must be willing to work Bengaluru shift hours",
        "category": "ELIGIBILITY",
        "requirement_type": "MANDATORY",
        "priority": 1,
        "weight": 0,
        "disqualifying": True,
        "evidence_required": False,
    })
    assert manual.status_code == 201

    client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    listed = client.get(f"/api/campaigns/{campaign_id}/requirements").json()
    assert any(r["source"] == "MANUAL" for r in listed)
    assert len(listed) == 10  # 9 AI rows + the 1 manual row that survived


def test_extract_without_jd_text_returns_422(client):
    response = client.post("/api/campaigns", json={
        "name": "Empty JD campaign",
        "job_title": "Role",
        "job_description": "",
    })
    campaign_id = response.json()["id"]
    extract_response = client.post(
        f"/api/campaigns/{campaign_id}/requirements/extract", json={}
    )
    assert extract_response.status_code == 422
