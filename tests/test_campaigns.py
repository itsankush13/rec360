def _create_campaign(client, **overrides):
    payload = {
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": "We need a senior backend engineer with Python and AWS experience.",
        "vacancies": 3,
        "location": "Bengaluru",
        "business_unit": "Engineering",
        "recruiter": "Aarav Sharma",
        "hiring_manager": "Priya Nair",
    }
    payload.update(overrides)
    return client.post("/api/campaigns", json=payload)


def test_create_campaign_defaults_to_draft(client):
    response = _create_campaign(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["job_title"] == "Senior Software Engineer"
    assert body["id"]


def test_list_campaigns_returns_created_campaign(client):
    _create_campaign(client)
    response = client.get("/api/campaigns")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_missing_campaign_returns_404(client):
    response = client.get("/api/campaigns/does-not-exist")
    assert response.status_code == 404


def test_update_campaign_fields(client):
    campaign_id = _create_campaign(client).json()["id"]
    response = client.patch(f"/api/campaigns/{campaign_id}", json={"vacancies": 5})
    assert response.status_code == 200
    assert response.json()["vacancies"] == 5


def test_valid_status_transition_succeeds(client):
    campaign_id = _create_campaign(client).json()["id"]
    response = client.post(
        f"/api/campaigns/{campaign_id}/status",
        json={"status": "AWAITING_RUBRIC_APPROVAL"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_RUBRIC_APPROVAL"


def test_invalid_status_transition_is_rejected(client):
    """A DRAFT campaign cannot jump straight to PROCESSING — must go through
    AWAITING_RUBRIC_APPROVAL -> APPROVED first."""
    campaign_id = _create_campaign(client).json()["id"]
    response = client.post(
        f"/api/campaigns/{campaign_id}/status",
        json={"status": "PROCESSING"},
    )
    assert response.status_code == 409


def test_delete_campaign(client):
    campaign_id = _create_campaign(client).json()["id"]
    delete_response = client.delete(f"/api/campaigns/{campaign_id}")
    assert delete_response.status_code == 204
    get_response = client.get(f"/api/campaigns/{campaign_id}")
    assert get_response.status_code == 404


# ---------- B14: retry protection (idempotency key) ----------

def test_create_campaign_defaults_to_version_one(client):
    body = _create_campaign(client).json()
    assert body["version"] == 1


def test_retried_create_with_same_idempotency_key_returns_same_campaign(client):
    headers = {"Idempotency-Key": "retry-key-1"}
    first = client.post("/api/campaigns", json={
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": "We need a senior backend engineer.",
        "vacancies": 3,
        "location": "Bengaluru",
        "business_unit": "Engineering",
        "recruiter": "Aarav Sharma",
        "hiring_manager": "Priya Nair",
    }, headers=headers)
    assert first.status_code == 201
    first_id = first.json()["id"]

    retry = client.post("/api/campaigns", json={
        "name": "Senior Backend Hiring - Q3",
        "job_title": "Senior Software Engineer",
        "job_description": "We need a senior backend engineer.",
        "vacancies": 3,
        "location": "Bengaluru",
        "business_unit": "Engineering",
        "recruiter": "Aarav Sharma",
        "hiring_manager": "Priya Nair",
    }, headers=headers)
    assert retry.status_code == 200
    assert retry.json()["id"] == first_id

    listing = client.get("/api/campaigns")
    assert len(listing.json()) == 1


def test_create_without_idempotency_key_makes_separate_campaigns(client):
    first = _create_campaign(client)
    second = _create_campaign(client)
    assert first.json()["id"] != second.json()["id"]
    assert len(client.get("/api/campaigns").json()) == 2


# ---------- B14: version/conflict checks on PATCH ----------

def test_update_campaign_increments_version(client):
    campaign_id = _create_campaign(client).json()["id"]
    response = client.patch(f"/api/campaigns/{campaign_id}", json={"vacancies": 5})
    assert response.json()["version"] == 2


def test_patch_with_correct_expected_version_succeeds(client):
    campaign_id = _create_campaign(client).json()["id"]
    response = client.patch(
        f"/api/campaigns/{campaign_id}",
        json={"vacancies": 5, "expected_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["vacancies"] == 5
    assert response.json()["version"] == 2


def test_patch_with_stale_expected_version_is_rejected(client):
    campaign_id = _create_campaign(client).json()["id"]
    # Someone else's edit lands first, advancing the version to 2.
    client.patch(f"/api/campaigns/{campaign_id}", json={"vacancies": 5})

    stale = client.patch(
        f"/api/campaigns/{campaign_id}",
        json={"vacancies": 9, "expected_version": 1},
    )
    assert stale.status_code == 409

    unchanged = client.get(f"/api/campaigns/{campaign_id}")
    assert unchanged.json()["vacancies"] == 5


def test_status_transition_also_advances_version(client):
    campaign_id = _create_campaign(client).json()["id"]
    client.post(
        f"/api/campaigns/{campaign_id}/status",
        json={"status": "AWAITING_RUBRIC_APPROVAL"},
    )
    response = client.get(f"/api/campaigns/{campaign_id}")
    assert response.json()["version"] == 2
