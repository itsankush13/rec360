"""
'AI should start the campaign' — POST /api/campaigns/ai-start.

Follows the mocking pattern established by tests/test_jd_generation.py and
tests/test_requirements.py: the LLM-backed agent functions are patched at
the module that actually calls them (lazy imports patched where they're
imported, `app.agents.jd_agent.generate_jd`; module-level imports patched
where they're bound, `app.services.requirement_service.parse_jd`), never a
real LLM call.
"""
from unittest.mock import patch

from app.agents.campaign_request_agent import HiringRequestParseError

FAKE_UNDERSTANDING = {
    "role_title": "Senior Data Engineer",
    "seniority_level": "Senior",
    "min_experience_years": 5,
    "required_skills": ["Python", "SQL", "AWS"],
    "preferred_skills": ["Airflow"],
    "education_requirement": "Bachelor's in Computer Science",
    "key_responsibilities": ["Build data pipelines"],
    "location": "Remote",
    "work_arrangement": "remote",
    "vacancies": 2,
    "business_unit": "Data Platform",
    "remuneration": None,
}

FAKE_JD_GENERATION = {
    "jd_text": "We are hiring a Senior Data Engineer to build data pipelines.",
    "role_title": "Senior Data Engineer",
    "required_skills": ["Python", "SQL", "AWS"],
    "preferred_skills": ["Airflow"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science",
    "key_responsibilities": ["Build data pipelines"],
    "seniority_level": "Senior",
}

FAKE_JD_EXTRACTION = {
    "role_title": "Senior Data Engineer",
    "required_skills": ["Python", "SQL", "AWS"],
    "preferred_skills": ["Airflow"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science",
    "key_responsibilities": ["Build data pipelines"],
    "seniority_level": "Senior",
}

def _patched(understanding=FAKE_UNDERSTANDING, jd=FAKE_JD_GENERATION, extraction=FAKE_JD_EXTRACTION):
    return (
        patch("app.services.campaign_from_request_service.extract_hiring_intent", return_value=understanding),
        patch("app.agents.jd_agent.generate_jd", return_value=jd),
        patch("app.services.requirement_service.parse_jd", return_value=extraction),
        # LLM weight tailoring is a best-effort layer on top of the
        # market-standard preset create_version already applies — failing
        # it (unmocked, it would try a real network call) must not fail the
        # request, but every test here mocks it anyway for determinism.
        patch("app.agents.weight_suggestion_agent.suggest_weights", side_effect=RuntimeError("not under test")),
    )


def test_valid_request_creates_draft_campaign_with_jd_requirements_and_rubric(client):
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        response = client.post("/api/campaigns/ai-start", json={
            "request": "Hire a Senior Data Engineer with 5+ years of experience, strong "
                       "Python and SQL skills, AWS experience, and data pipeline experience.",
        })

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["campaign"]["status"] == "DRAFT"
    assert body["campaign"]["job_title"] == "Senior Data Engineer"
    assert body["campaign"]["vacancies"] == 2
    assert body["campaign"]["location"] == "Remote"

    assert body["understood"]["role_title"] == "Senior Data Engineer"
    assert "Python" in body["understood"]["required_skills"]

    assert body["jd_text"] == FAKE_JD_GENERATION["jd_text"]
    assert body["jd_source"] == "llm"

    assert len(body["requirements"]) > 0
    assert any(r["description"] == "Python" for r in body["requirements"])

    assert body["rubric_version"] == 1
    assert len(body["rubric_criteria"]) > 0
    total_weight = sum(c["weight"] for c in body["rubric_criteria"])
    assert round(total_weight) == 100

    # Fetching the campaign through the ordinary endpoint shows the same
    # DRAFT campaign — this is not a parallel/shadow record.
    fetched = client.get(f"/api/campaigns/{body['campaign']['id']}").json()
    assert fetched["job_description"] == FAKE_JD_GENERATION["jd_text"]


def test_valid_request_records_ai_campaign_drafted_audit_event(client):
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        response = client.post("/api/campaigns/ai-start", json={
            "request": "Hire a Senior Data Engineer with Python, SQL and AWS.",
        })
    campaign_id = response.json()["campaign"]["id"]

    events = client.get(f"/api/audit?campaign_id={campaign_id}")
    assert events.status_code == 200, events.text
    actions = [e["action"] for e in events.json()]
    assert "CAMPAIGN_CREATED" in actions
    assert "AI_CAMPAIGN_DRAFTED" in actions


def test_empty_request_is_rejected_with_a_useful_message(client):
    response = client.post("/api/campaigns/ai-start", json={"request": "   "})
    assert response.status_code in (400, 422)
    assert "traceback" not in response.text.lower()


def test_missing_request_field_is_a_validation_error(client):
    response = client.post("/api/campaigns/ai-start", json={})
    assert response.status_code == 422


def test_ai_understanding_failure_creates_nothing(client):
    with patch(
        "app.services.campaign_from_request_service.extract_hiring_intent",
        side_effect=RuntimeError("model unreachable"),
    ):
        response = client.post("/api/campaigns/ai-start", json={
            "request": "Hire someone great.",
        })

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()
    assert "unreachable" not in response.text.lower()  # no raw internal error leaked

    assert client.get("/api/campaigns").json() == []


def test_malformed_ai_output_with_no_role_is_rejected(client):
    with patch(
        "app.services.campaign_from_request_service.extract_hiring_intent",
        side_effect=HiringRequestParseError("AI could not identify a role"),
    ):
        response = client.post("/api/campaigns/ai-start", json={"request": "asdf qwer"})

    assert response.status_code == 422
    assert client.get("/api/campaigns").json() == []


def test_jd_generation_failure_still_produces_a_draft_campaign(client):
    p1, _, p3, p4 = _patched()
    with p1, p3, p4, patch("app.agents.jd_agent.generate_jd", side_effect=RuntimeError("LLM down")):
        response = client.post("/api/campaigns/ai-start", json={
            "request": "Hire a Senior Data Engineer with Python, SQL and AWS.",
        })

    assert response.status_code == 201, response.text
    body = response.json()
    # No built-in template for "Senior Data Engineer" and the LLM failed —
    # jd_generation_service's own floor is exhausted, so the orchestrator's
    # minimal fallback JD is used instead of failing the whole request.
    assert body["jd_source"] == "minimal"
    assert body["campaign"]["status"] == "DRAFT"
    assert any("job description" in w.lower() for w in body["warnings"])


def test_requirement_extraction_failure_still_produces_a_draft_campaign(client):
    p1, p2, _, p4 = _patched()
    with p1, p2, p4, patch(
        "app.services.requirement_service.parse_jd", side_effect=RuntimeError("LLM down")
    ):
        response = client.post("/api/campaigns/ai-start", json={
            "request": "Hire a Senior Data Engineer with Python, SQL and AWS.",
        })

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requirements"] == []
    assert body["rubric_version"] is None
    assert any("requirement" in w.lower() for w in body["warnings"])


def test_repeat_request_with_same_idempotency_key_does_not_duplicate(client):
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        first = client.post(
            "/api/campaigns/ai-start",
            json={"request": "Hire a Senior Data Engineer with Python, SQL and AWS."},
            headers={"Idempotency-Key": "same-key-123"},
        )
        second = client.post(
            "/api/campaigns/ai-start",
            json={"request": "Hire a Senior Data Engineer with Python, SQL and AWS."},
            headers={"Idempotency-Key": "same-key-123"},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["campaign"]["id"] == second.json()["campaign"]["id"]
    assert len(client.get("/api/campaigns").json()) == 1
