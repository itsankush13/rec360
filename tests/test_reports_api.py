"""
B10 (outbound half) — emailing the shortlist report to the hiring manager.

Reuses the `exportable` fixture from tests/test_exports.py: a campaign with
four assessed candidates and one decision recorded, exactly the state the
CSV/XLSX export tests already build. The point of reusing it rather than a
smaller hand-rolled fixture is that this endpoint reuses the export's own
record-building (`app.api.exports._export_records` and
`app.core.ats_export.build_rows`), so the same fixture is the honest test of
that reuse.
"""
from unittest.mock import patch

from app.api import reports as reports_api
from app.core.mail_ref import ref_tag
from app.core.outlook_adapter import SendResult
from app.db.models import AuditAction, AuditEvent, LifecycleStatus

from tests.test_exports import exportable  # noqa: F401 (fixture import)
from tests.test_processing import FAKE_JD_EXTRACTION


def test_the_report_is_sent_and_audited(exportable, client, db_session):
    campaign_id, _evaluations = exportable

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com", "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["recipient"] == "manager@example.com"
    assert body["candidates"] == 1  # decided_only defaults to True
    assert body["simulated"] is True  # default backend is "simulated"
    assert ref_tag(campaign_id) in body["subject"]

    events = list(db_session.query(AuditEvent).filter_by(
        action=AuditAction.SENT_TO_HIRING_MANAGER,
    ).all())
    assert len(events) == 1
    event = events[0]
    assert event.campaign_id == campaign_id
    assert event.entity_type == "campaign"
    assert event.after["recipient"] == "manager@example.com"
    assert event.after["candidates"] == 1
    assert event.after["simulated"] is True


def test_the_subject_carries_the_campaign_only_reference_tag(exportable, client):
    """A campaign-wide report is about the whole campaign, not one candidate —
    the tag must have no `:candidate_id` half."""
    campaign_id, _ = exportable
    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    subject = response.json()["subject"]
    assert subject.endswith(f"[REF-{campaign_id}]")
    assert ":" not in subject.split("[REF-")[-1]


def test_cc_is_threaded_to_the_mail_adapter(exportable, client, monkeypatch):
    campaign_id, _ = exportable
    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None, attachments=None, html_body=None):
            captured["to_address"] = to_address
            captured["cc_address"] = cc_address
            captured["subject"] = subject
            captured["body"] = body
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(reports_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com", "cc": "recruiter@example.com"},
    )
    assert response.status_code == 201
    assert captured["to_address"] == "manager@example.com"
    assert captured["cc_address"] == "recruiter@example.com"
    assert response.json()["simulated"] is False
    assert "Sent." in response.json()["send_detail"]


def test_the_html_body_carries_a_formal_bulleted_summary_table(exportable, client, monkeypatch):
    campaign_id, _evaluations = exportable
    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None, attachments=None, html_body=None):
            captured["body"] = body
            captured["html_body"] = html_body
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(reports_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    assert response.status_code == 201

    plain_body = captured["body"]
    assert plain_body.startswith("Dear Hiring Manager,")
    assert "Best regards," in plain_body

    html_body = captured["html_body"]
    assert "Dear Hiring Manager," in html_body
    assert "<table" in html_body
    for header in ("Candidate", "Overall Score", "Why This Score",
                   "Strength", "Weakness", "Overall Feedback"):
        assert header in html_body
    assert "<ul" in html_body or "&mdash;" in html_body


def test_the_body_names_every_candidate_in_the_report(exportable, client):
    campaign_id, evaluations = exportable
    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com", "decided_only": False},
    )
    assert response.status_code == 201
    assert response.json()["candidates"] == len(evaluations)


def test_an_empty_recipient_is_refused(exportable, client):
    campaign_id, _ = exportable
    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "  "},
    )
    assert response.status_code == 422


def test_refused_when_nothing_is_decided_and_decided_only(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Undecided", "job_title": "Engineer", "job_description": "x",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    assert response.status_code == 422
    assert "nothing to report" in str(response.json()["detail"]).lower()


def test_404s_for_an_unknown_campaign(client):
    response = client.post(
        "/api/campaigns/nope/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    assert response.status_code == 404


def test_the_email_carries_one_zip_attachment_with_shortlisted_pdfs(exportable, client, monkeypatch):
    import zipfile as zipfile_module
    import io as io_module

    campaign_id, _evaluations = exportable
    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None, attachments=None, html_body=None):
            captured["attachments"] = attachments
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(reports_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["attached_reports"] == 1
    assert body["attachment_filename"].endswith(".zip")

    attachments = captured["attachments"]
    assert len(attachments) == 1
    filename, content = attachments[0]
    assert filename.endswith(".zip")
    with zipfile_module.ZipFile(io_module.BytesIO(content)) as archive:
        assert len(archive.namelist()) == 1
        assert archive.namelist()[0].endswith(".pdf")


def test_decided_but_none_shortlisted_still_sends_with_no_attachment(client, monkeypatch):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Decided not shortlisted", "job_title": "Engineer", "job_description": "x",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    from tests.test_evaluations import STRONG_CV, make_cv_pdf
    from tests.test_processing import PDF_MIME, upload
    upload(client, campaign_id, [("priya.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    # A decision, but REJECT, not SHORTLIST — decided_only finds it; the zip
    # helper must find nothing to attach.
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{evaluations[0]['candidate_id']}/disposition",
        json={"disposition": "REJECT", "actor": "Fatima Al-Rashid"},
    )

    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None, attachments=None, html_body=None):
            captured["attachments"] = attachments
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(reports_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    assert response.status_code == 201
    assert captured["attachments"] is None
    body = response.json()
    assert body["attached_reports"] == 0
    assert body["attachment_filename"] is None


def test_does_not_alter_the_assessment(exportable, client):
    campaign_id, _evaluations = exportable
    before = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "manager@example.com"},
    )
    after = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    assert before == after


# ---------------------------------------------------------------------------
# Sending the report is now the handoff to the hiring manager: the
# shortlisted candidates it reports on move to WITH_HIRING_MANAGER, owned by
# whoever the recipient address belongs to.
# ---------------------------------------------------------------------------

def _make_manager(client, email="manager@example.com"):
    return client.post("/api/users", json={
        "full_name": "Aziz Rahman", "email": email, "role": "HIRING_MANAGER",
    }).json()


def _make_recruiter(client, email="fatima@example.com"):
    return client.post("/api/users", json={
        "full_name": "Fatima Al-Rashid", "email": email, "role": "RECRUITER",
    }).json()


def test_sending_to_a_known_manager_moves_the_shortlisted_candidate(exportable, client):
    campaign_id, evaluations = exportable
    manager = _make_manager(client)
    recruiter = _make_recruiter(client)
    candidate_id = evaluations[0]["candidate_id"]

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": manager["email"], "actor_id": recruiter["id"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["moved_to_manager"] == 1
    assert body["manager_name"] == "Aziz Rahman"

    lifecycle = client.get(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}"
    ).json()
    assert lifecycle["status"] == LifecycleStatus.WITH_HIRING_MANAGER.value
    assert lifecycle["owner_name"] == "Aziz Rahman"


def test_sending_to_an_unrecognised_address_still_sends_but_moves_no_one(exportable, client):
    campaign_id, evaluations = exportable
    candidate_id = evaluations[0]["candidate_id"]

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": "not-in-the-system@example.com"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["moved_to_manager"] == 0
    assert body["manager_name"] is None

    lifecycle = client.get(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}"
    )
    assert lifecycle.status_code == 404


def test_sending_again_to_the_same_manager_is_not_an_error(exportable, client):
    """Re-sending the report (e.g. with an updated attachment) must not fail
    just because the candidate is already with that manager."""
    campaign_id, evaluations = exportable
    manager = _make_manager(client)
    _make_recruiter(client)

    first = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": manager["email"]},
    )
    assert first.json()["moved_to_manager"] == 1

    second = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": manager["email"]},
    )
    assert second.status_code == 201
    assert second.json()["moved_to_manager"] == 0


def test_a_rejected_candidate_in_a_full_report_is_not_handed_to_the_manager(client, monkeypatch):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Decided not shortlisted", "job_title": "Engineer", "job_description": "x",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    from tests.test_evaluations import STRONG_CV, make_cv_pdf
    from tests.test_processing import PDF_MIME, upload
    upload(client, campaign_id, [("priya.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    candidate_id = evaluations[0]["candidate_id"]
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "REJECT", "actor": "Fatima Al-Rashid"},
    )
    manager = _make_manager(client)

    response = client.post(
        f"/api/campaigns/{campaign_id}/reports/email-to-hiring-manager",
        json={"recipient": manager["email"], "decided_only": False},
    )
    assert response.status_code == 201
    assert response.json()["moved_to_manager"] == 0

    lifecycle = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}")
    assert lifecycle.status_code == 404
