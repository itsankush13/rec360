"""
Opening the original CV from Candidate 360.

Candidate 360 quotes lines from the CV with a page or section reference, and
the client's requirement is that a recruiter checks the evidence before
deciding. A quote is only checkable if the page can be seen — more so now
that a scanned CV is read by character recognition, where the quoted words
are an approximation of what is actually on the page.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf


@pytest.fixture()
def assessed(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "CV viewer", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    return campaign_id, run["evaluations"][0]["id"]


def test_the_original_cv_can_be_opened(assessed, client):
    _campaign_id, evaluation_id = assessed
    response = client.get(f"/api/evaluations/{evaluation_id}/cv")

    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_it_opens_in_place_rather_than_downloading(assessed, client):
    """
    The point is to read it beside the assessment, not to collect another
    copy of a file the recruiter already has.
    """
    _campaign_id, evaluation_id = assessed
    response = client.get(f"/api/evaluations/{evaluation_id}/cv")
    assert response.headers["content-disposition"].startswith("inline")
    assert "application/pdf" in response.headers["content-type"]


def test_the_screen_is_told_whether_the_cv_is_there(assessed, client):
    _campaign_id, evaluation_id = assessed
    assert client.get(f"/api/evaluations/{evaluation_id}").json()["cv_available"] is True


def test_a_missing_file_is_a_plain_not_found_not_a_crash(assessed, client, db_session):
    """
    The row can outlive the file — retention, a purge, a restored database.
    That must read as "no longer on file", not as a broken screen.
    """
    from app.db.models import CandidateDocument, Evaluation

    _campaign_id, evaluation_id = assessed
    evaluation = db_session.get(Evaluation, evaluation_id)
    document = db_session.get(CandidateDocument, evaluation.document_id)
    document.storage_path = "campaigns/gone/missing.pdf"
    db_session.commit()

    response = client.get(f"/api/evaluations/{evaluation_id}/cv")
    assert response.status_code == 404
    assert "no longer on file" in response.json()["detail"]
    assert client.get(f"/api/evaluations/{evaluation_id}").json()["cv_available"] is True


def test_an_unknown_assessment_has_no_cv(client):
    assert client.get("/api/evaluations/nope/cv").status_code == 404


def test_the_screen_offers_the_link():
    html = (Path(__file__).resolve().parent.parent / "web" / "candidate.html").read_text(
        encoding="utf-8", errors="ignore"
    )
    assert 'id="c-cv"' in html
    assert "/cv" in html
    assert "cv_available" in html


def test_the_challenge_panel_does_not_print_enum_values():
    """
    The findings list showed "HIGH review". web/DATA.md: never an enum on a
    screen. The panel already renders every finding, not just the first.
    """
    html = (Path(__file__).resolve().parent.parent / "web" / "candidate.html").read_text(
        encoding="utf-8", errors="ignore"
    )
    assert "esc(finding.severity)" not in html
    assert "severityText" in html
    assert "group.items.map(" in html


# ---------------------------------------------------------------------------
# The Challenge Agent panel
# ---------------------------------------------------------------------------

def _candidate_html():
    return (Path(__file__).resolve().parent.parent / "web" / "candidate.html").read_text(
        encoding="utf-8", errors="ignore"
    )


def test_the_panel_renders_every_finding_not_the_first():
    """
    The engine caps nothing — six checks run over every criterion of every
    assessment. A single row on screen means a single finding exists, so the
    panel has to make its own count visible or it reads like a cap.
    """
    html = _candidate_html()
    assert "findings.length" in html
    assert "point' +" in html          # "N points raised"
    assert "groups.length" in html     # grouped by kind of check


def test_findings_are_grouped_by_kind_of_check():
    html = _candidate_html()
    assert "checkText" in html
    for check in ("CONTRADICTION", "MISSING_EVIDENCE", "WEAK_EVIDENCE",
                  "UNSUPPORTED_CONCLUSION", "INCONSISTENT_SCORING",
                  "WEIGHTING_ANOMALY", "OUTLIER_RECOMMENDATION"):
        assert check in html, check


def test_a_finding_names_the_criterion_it_concerns():
    """
    A list of concerns is only actionable if each one says what it is about.
    The finding carries a criterion key; the reader knows it by its label.
    """
    assert "criterionLabel" in _candidate_html()


def test_no_findings_reads_as_a_result_not_a_gap():
    html = _candidate_html()
    assert "That is a " in html and "not a gap" in html


def test_the_panel_prints_no_enum_values():
    html = _candidate_html()
    assert "esc(finding.severity)" not in html
    assert "esc(finding.check)" not in html
