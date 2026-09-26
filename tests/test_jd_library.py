"""
Demo-readiness pass, 2026-09-14 — the smallest honest JD library:
`JDTemplate` rows, visible/retrievable without a campaign ever existing.
"""


def test_a_jd_template_can_be_created_and_listed_without_any_campaign(client):
    created = client.post("/api/jd-library", json={
        "role_title": "Process Operator",
        "summary": "Runs and monitors polyethylene production unit operations.",
        "body": "Full JD text goes here.",
        "tags": "QChem,demo",
    })
    assert created.status_code == 201
    body = created.json()
    assert body["role_title"] == "Process Operator"
    assert body["id"]

    listed = client.get("/api/jd-library")
    assert listed.status_code == 200
    ids = [t["id"] for t in listed.json()]
    assert body["id"] in ids


def test_a_jd_template_can_be_fetched_by_id(client):
    created = client.post("/api/jd-library", json={
        "role_title": "HSE Officer", "body": "Some JD text.",
    })
    template_id = created.json()["id"]

    fetched = client.get(f"/api/jd-library/{template_id}")
    assert fetched.status_code == 200
    assert fetched.json()["role_title"] == "HSE Officer"


def test_fetching_an_unknown_template_is_404(client):
    missing = client.get("/api/jd-library/does-not-exist")
    assert missing.status_code == 404


def test_a_template_needs_a_role_title_and_body(client):
    no_title = client.post("/api/jd-library", json={"role_title": "  ", "body": "text"})
    assert no_title.status_code == 422

    no_body = client.post("/api/jd-library", json={"role_title": "Role", "body": "  "})
    assert no_body.status_code == 422
