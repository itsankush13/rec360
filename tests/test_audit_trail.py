"""
Part 3 tests — the audit trail.

`audit_events` already carried dispositions, overrides, comments and exports.
These assert the rest of the record: campaign creation and change, rubric
version and approval, uploads, held files, retries, and assessment runs.

Two things are asserted about every event beyond its existence:
  * it is attached to a campaign, or screen 9 cannot show it;
  * its summary is written for a person, not for a log file. An auditor
    reads this screen more literally than any other, and `RUBRIC_APPROVED`
    on a page is not a record anyone can sign.
"""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import AuditAction, AuditEvent

from tests.test_processing import (
    FAKE_JD_EXTRACTION, PDF_MIME, make_pdf, upload,
)
from tests.test_evaluations import STRONG_CV, make_cv_pdf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def events(db, campaign_id, action=None):
    statement = select(AuditEvent).where(AuditEvent.campaign_id == campaign_id)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    return list(db.scalars(statement.order_by(AuditEvent.created_at)).all())


def actions(db, campaign_id):
    return [event.action for event in events(db, campaign_id)]


def _web(page):
    return (Path(__file__).resolve().parent.parent / "web" / page).read_text(
        encoding="utf-8", errors="ignore"
    )


@pytest.fixture()
def audited_campaign(client):
    """A campaign taken through every state change that should be recorded."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Control Room Operator intake",
            "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
            "location": "Coastal Terminal",
            "vacancies": 8,
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    client.patch(f"/api/campaigns/{campaign_id}", json={"vacancies": 6})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    return campaign_id


# ---------------------------------------------------------------------------
# Acceptance: creating, approving, uploading and running are all visible
# ---------------------------------------------------------------------------

def test_every_state_change_is_recorded(audited_campaign, db_session):
    recorded = set(actions(db_session, audited_campaign))
    for expected in (
        AuditAction.CAMPAIGN_CREATED,
        AuditAction.CAMPAIGN_UPDATED,
        AuditAction.RUBRIC_VERSION_CREATED,
        AuditAction.RUBRIC_SUBMITTED,
        AuditAction.RUBRIC_APPROVED,
        AuditAction.BATCH_UPLOADED,
        AuditAction.EVALUATION_RUN_STARTED,
        AuditAction.EVALUATION_RUN_COMPLETED,
    ):
        assert expected in recorded, expected.value


def test_the_trail_is_readable_through_the_screen_9_endpoint(audited_campaign, client):
    body = client.get(f"/api/campaigns/{audited_campaign}/audit").json()
    assert len(body) >= 8
    # Newest first, and every row carries the three things an auditor needs.
    for row in body:
        assert row["summary"]
        assert row["created_at"]
        assert row["action"]


def test_campaign_creation_names_the_role_and_the_vacancies(audited_campaign, db_session):
    event = events(db_session, audited_campaign, AuditAction.CAMPAIGN_CREATED)[0]
    assert "Control Room Operator" in event.summary
    assert "8 vacancies" in event.summary
    assert event.entity_type == "campaign"


def test_a_campaign_change_records_what_changed_and_what_it_was(audited_campaign, db_session):
    event = events(db_session, audited_campaign, AuditAction.CAMPAIGN_UPDATED)[0]
    assert event.before["vacancies"] == 8
    assert event.after["vacancies"] == 6
    assert "number of vacancies" in event.summary


def test_a_patch_that_changes_nothing_is_not_an_event(audited_campaign, client, db_session):
    before = len(events(db_session, audited_campaign, AuditAction.CAMPAIGN_UPDATED))
    client.patch(f"/api/campaigns/{audited_campaign}", json={"vacancies": 6})
    assert len(events(db_session, audited_campaign, AuditAction.CAMPAIGN_UPDATED)) == before


def test_rubric_approval_records_the_approver(audited_campaign, db_session):
    event = events(db_session, audited_campaign, AuditAction.RUBRIC_APPROVED)[0]
    assert event.actor == "Fatima Al-Rashid"
    assert event.entity_type == "rubric_version"
    assert "approved" in event.summary


def test_upload_records_the_file_count_and_the_rubric_version(audited_campaign, db_session):
    event = events(db_session, audited_campaign, AuditAction.BATCH_UPLOADED)[0]
    assert event.after["files"] == 1
    assert event.after["rubric_version"] == 1


def test_an_assessment_run_records_both_its_start_and_its_finish(audited_campaign, db_session):
    started = events(db_session, audited_campaign, AuditAction.EVALUATION_RUN_STARTED)[0]
    finished = events(db_session, audited_campaign, AuditAction.EVALUATION_RUN_COMPLETED)[0]
    assert started.entity_id == finished.entity_id
    assert "recommends" in started.summary  # never presented as a decision
    assert finished.after["selected"] == started.after["candidates"]


# ---------------------------------------------------------------------------
# Held files and retries
# ---------------------------------------------------------------------------

def test_a_file_that_cannot_be_read_is_recorded_as_held(client, db_session):
    """
    An unreadable file is the one thing a recruiter is most likely to be
    asked about later: it means a real person's application was never scored.
    """
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Held files", "job_title": "Process Engineer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})

    upload(client, campaign_id, [("notes.txt", b"not a CV", "text/plain")])

    held = events(db_session, campaign_id, AuditAction.FILE_HELD)
    assert len(held) == 1
    assert "notes.txt" in held[0].summary
    # The batch event says so too, with its denominator.
    uploaded = events(db_session, campaign_id, AuditAction.BATCH_UPLOADED)[0]
    assert uploaded.after["held"] == 1
    assert "1 of 1" in uploaded.summary


def test_retrying_a_held_file_is_recorded(client, db_session):
    from app.core.document_intake import DocumentRejected
    from app.db.models import JobErrorCode

    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Retries", "job_title": "Process Engineer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})

    with patch(
        "app.services.processing_service.document_intake.extract_document",
        side_effect=DocumentRejected(JobErrorCode.EXTRACTION_FAILED, "transient glitch"),
    ):
        body = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)]).json()

    job_id = body["jobs"][0]["id"]
    assert events(db_session, campaign_id, AuditAction.FILE_HELD)

    client.post(f"/api/processing/jobs/{job_id}/retry")
    retried = events(db_session, campaign_id, AuditAction.JOB_RETRIED)
    assert len(retried) == 1
    assert "cv.pdf" in retried[0].summary
    assert "of 3" in retried[0].summary  # attempts always carry their limit


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

def test_no_summary_contains_an_enum_value(audited_campaign, db_session):
    """web/DATA.md: never an enum or an error code in anything visible."""
    for event in events(db_session, audited_campaign):
        assert not re.search(r"\b[A-Z][A-Z0-9]+_[A-Z0-9_]+\b", event.summary), event.summary


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------

def test_audit_page_introduces_no_colour():
    """Wiring adds id attributes and one script. The theme is untouched."""
    body = _web("audit.html").split("</head>", 1)[1]
    hexes = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", body))
    assert not hexes, f"hard-coded colours introduced: {hexes}"


def test_audit_page_reads_the_trail_and_keeps_the_shared_script():
    html = _web("audit.html")
    assert "/audit" in html
    # The src carries a cache-busting version (X50): pages used to load
    # app.js unversioned and browsers served it stale, hiding fixes.
    assert re.search(r'<script src="assets/app\.js(\?v=\d+)?"></script>', html)
    assert html.index("renderTrail") < html.index('src="assets/app.js')


def test_audit_page_maps_every_action_to_plain_english():
    """
    No enum member may reach the screen as its own name, and every member the
    backend can write must have words of its own — an unmapped action would
    render as a blank line on the one page an auditor reads literally.
    """
    html = _web("audit.html")
    for action in AuditAction:
        assert f"'{action.value}'" in html or f'"{action.value}"' in html, action.value
    for banned in ("demo", "sample data", "placeholder", "Lorem", "mock"):
        assert banned.lower() not in html.lower(), banned


def test_audit_page_says_who_decides():
    """A screen that shows overrides must say the system does not decide."""
    html = _web("audit.html")
    assert "a person decides" in html


# ---------------------------------------------------------------------------
# Traceability — every event findable by campaign and by candidate
# ---------------------------------------------------------------------------

def test_a_decision_is_findable_by_the_applicant_it_concerns(audited_campaign, client, db_session):
    """
    "Everything that ever happened to this person" is the question an auditor
    actually asks. Until candidate_id existed it was not a query anyone could
    write: entity_id names whatever the event is about, which may be a batch
    or a rubric version.
    """
    candidates = client.get(f"/api/campaigns/{audited_campaign}/candidates").json()
    candidate_id = candidates[0]["id"]
    client.post(
        f"/api/campaigns/{audited_campaign}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )

    found = client.get(
        f"/api/campaigns/{audited_campaign}/audit",
        params={"candidate_id": candidate_id},
    ).json()

    assert found
    assert all(row["candidate_id"] == candidate_id for row in found)


def test_every_row_carries_both_the_id_and_the_name(audited_campaign, client):
    """Ids identify; names are what a person reads. An auditor needs both."""
    rows = client.get(f"/api/campaigns/{audited_campaign}/audit").json()
    row = rows[0]
    assert row["campaign_id"]
    assert row["campaign_name"]
    assert row["action_label"]


def test_the_record_reads_across_campaigns(client, audited_campaign):
    """An auditor's questions do not arrive campaign-shaped."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        other = client.post("/api/campaigns", json={
            "name": "Second", "job_title": "HSE Officer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]

    everything = client.get("/api/audit", params={"limit": 500}).json()
    campaigns = {row["campaign_id"] for row in everything}
    assert audited_campaign in campaigns
    assert other in campaigns


def test_the_record_can_be_filtered_by_person(audited_campaign, client):
    rows = client.get("/api/audit", params={"actor": "Fatima"}).json()
    assert rows
    assert all("fatima" in row["actor"].lower() for row in rows)


def test_the_filter_list_covers_every_action(client):
    """
    The screen builds its filter from this. An action missing here would be
    an action nobody could filter to, and the omission would be invisible.
    """
    listed = {item["action"] for item in client.get("/api/audit/actions").json()}
    assert listed == {action.value for action in AuditAction}
    for item in client.get("/api/audit/actions").json():
        assert item["label"]
        assert item["label"] != item["action"]


def test_the_record_downloads_as_a_spreadsheet(audited_campaign, client):
    """An auditor works in their own tools."""
    response = client.get("/api/audit/export.csv",
                          params={"campaign_id": audited_campaign})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    body = response.text
    assert "Candidate id" in body and "Campaign id" in body
    assert "Rubric version 1 approved" in body


def test_the_export_honours_the_filter(audited_campaign, client):
    response = client.get("/api/audit/export.csv", params={
        "campaign_id": audited_campaign, "action": "RUBRIC_APPROVED",
    })
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 2  # header plus the one approval


# ---------------------------------------------------------------------------
# Readability
# ---------------------------------------------------------------------------

def test_a_decision_reads_in_words_not_enum_values(audited_campaign, client, db_session):
    candidates = client.get(f"/api/campaigns/{audited_campaign}/candidates").json()
    client.post(
        f"/api/campaigns/{audited_campaign}/candidates/{candidates[0]['id']}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    rows = client.get(f"/api/campaigns/{audited_campaign}/audit",
                      params={"action": "DISPOSITION_SET"}).json()

    assert "shortlisted" in rows[0]["summary"]
    assert "SHORTLIST" not in rows[0]["summary"]


def test_the_screen_groups_by_day_and_offers_filters():
    html = _web("audit.html")
    assert "dayOf" in html            # grouped by day, not a flat list of 200
    assert "a-filter-action" in html
    assert "a-filter-actor" in html
    assert "/api/audit/export.csv" in html
    assert "/api/audit/actions" in html


def test_the_screen_names_who_a_row_concerns():
    html = _web("audit.html")
    assert "candidate_name" in html
    assert "no longer on file" in html   # deleted candidate keeps the row
