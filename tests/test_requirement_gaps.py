"""
The three gaps between the client's written requirements and the build.

Each is small on its own. They are grouped because they share a failure
mode: the capability exists in the backend and nothing on screen reaches it,
so a demo looks like the feature is missing when it is only unwired.
"""
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, make_pdf, upload


def _web(page):
    return (Path(__file__).resolve().parent.parent / "web" / page).read_text(
        encoding="utf-8", errors="ignore"
    )


# ---------------------------------------------------------------------------
# Folder upload
# ---------------------------------------------------------------------------

def test_a_whole_folder_of_applications_can_be_chosen():
    """
    The requirement says folder. A recruiter holds a month of applications as
    a folder, not as a multi-select.
    """
    html = _web("new-campaign.html")
    assert "webkitdirectory" in html


def test_choosing_a_file_is_still_possible():
    """
    webkitdirectory turns a picker into folders only, so it must not replace
    the file picker — choosing three CVs is still the commoner action.
    """
    html = _web("new-campaign.html")
    assert 'id="resume-input"' in html
    assert 'id="resume-folder"' in html


def test_non_cv_files_in_a_folder_are_filtered_out():
    """A folder sweep collects spreadsheets and stray system files too."""
    html = _web("new-campaign.html")
    assert "pdf|docx|doc" in html


# ---------------------------------------------------------------------------
# The campaign record
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", [
    "business_unit", "recruiter", "hiring_manager", "target_completion_date",
])
def test_the_campaign_form_collects_what_the_requirement_asks_for(field):
    assert field in _web("new-campaign.html")


def test_the_api_stores_them(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        created = client.post("/api/campaigns", json={
            "name": "HSE Officer intake", "job_title": "HSE Officer",
            "job_description": "Python and AWS backend engineer.",
            "business_unit": "Refining and Petrochemicals",
            "recruiter": "Fatima Al-Rashid",
            "hiring_manager": "Aziz Rahman",
        }).json()

    assert created["business_unit"] == "Refining and Petrochemicals"
    assert created["recruiter"] == "Fatima Al-Rashid"
    assert created["hiring_manager"] == "Aziz Rahman"


# ---------------------------------------------------------------------------
# Retrying a held file
# ---------------------------------------------------------------------------

def _held_files(client, campaign_id):
    """The held-file block the Campaigns board actually reads."""
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    runs = client.get("/api/runs", params={"campaign_id": campaign_id}).json()["runs"]
    assert runs, "a run should exist"
    return runs[0]["held_files"]


@pytest.fixture()
def campaign_with_a_held_file(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Held", "job_title": "Process Engineer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    return campaign_id


def test_a_readable_failure_is_offered_a_retry(campaign_with_a_held_file, client):
    from app.core.document_intake import DocumentRejected
    from app.db.models import JobErrorCode

    with patch(
        "app.services.processing_service.document_intake.extract_document",
        side_effect=DocumentRejected(JobErrorCode.EXTRACTION_FAILED, "transient glitch"),
    ):
        upload(client, campaign_with_a_held_file, [("cv.pdf", make_pdf(), PDF_MIME)])

    held = _held_files(client, campaign_with_a_held_file)
    assert held, "the file should be held"
    assert held[0]["can_retry"] is True
    assert held[0]["id"]


def test_a_file_rejected_at_the_door_is_not_offered_a_retry(
    campaign_with_a_held_file, client
):
    """
    A wrong-format file has no attempts allowed. Offering to try again would
    promise something that cannot work.
    """
    upload(client, campaign_with_a_held_file, [("notes.txt", b"not a CV", "text/plain")])

    held = _held_files(client, campaign_with_a_held_file)
    assert held
    assert held[0]["can_retry"] is False


def test_the_held_panel_calls_the_retry_endpoint():
    """The endpoint existed and nothing called it. That is the gap."""
    html = _web("campaigns.html")
    assert "/retry" in html
    assert "can_retry" in html


def test_the_changed_screens_introduce_no_colour():
    for page in ("new-campaign.html", "campaigns.html"):
        body = _web(page).split("</head>", 1)[1]
        hexes = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", body))
        assert not hexes, f"{page}: {hexes}"
