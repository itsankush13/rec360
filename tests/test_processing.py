"""
Phase C tests — bulk intake, per-file exception classification, duplicate
detection, retry, cancellation and progress reporting.

Fixtures build real PDF and DOCX bytes (including encrypted and corrupt ones)
rather than mocking the parsers, because the whole point of the validation
layer is what actually happens when PyMuPDF or python-docx meets a bad file.
"""
import io
from unittest.mock import patch

import docx
import pymupdf
import pytest

FAKE_JD_EXTRACTION = {
    "role_title": "Senior Software Engineer",
    "required_skills": ["Python", "AWS", "PostgreSQL"],
    "preferred_skills": ["Kubernetes"],
    "min_experience_years": 5,
    "education_requirement": "Bachelor's in Computer Science",
    "key_responsibilities": ["Own backend services"],
    "seniority_level": "Senior",
}


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------

def cv_text(name="Priya Menon", email="priya.menon@example.com", phone="+91 98765 43210"):
    return "\n".join([
        name,
        email,
        phone,
        "Bengaluru, India",
        "",
        "SUMMARY",
        "Senior backend engineer with eight years building Python services on AWS.",
        "",
        "EXPERIENCE",
        "Staff Engineer, Acme Corp (2020-present). Led the payments platform team.",
        "Senior Engineer, Globex (2017-2020). Built PostgreSQL-backed microservices.",
        "",
        "SKILLS",
        "Python, AWS, PostgreSQL, Docker, Kubernetes, FastAPI",
        "",
        "EDUCATION",
        "B.Tech Computer Science, NIT Trichy",
    ])


def make_pdf(text=None, user_password=None, blank=False):
    document = pymupdf.open()
    page = document.new_page()
    if not blank:
        page.insert_text((60, 60), text or cv_text(), fontsize=9)
    if user_password:
        data = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw=user_password
        )
    else:
        data = document.tobytes()
    document.close()
    return data


def make_docx(text=None):
    document = docx.Document()
    for line in (text or cv_text()).split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client, campaign_id, files, **params):
    """files: list of (filename, bytes, content_type)."""
    payload = [
        ("files", (filename, io.BytesIO(data), content_type))
        for filename, data, content_type in files
    ]
    return client.post(f"/api/campaigns/{campaign_id}/batches", files=payload, params=params)


PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------------------------------------------------------------------------
# Campaign with an approved rubric — the precondition for uploading
# ---------------------------------------------------------------------------

@pytest.fixture()
def screening_campaign(client):
    """A campaign with requirements extracted and an APPROVED rubric."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Bulk screening campaign",
            "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"seed_from_requirements": True},
    )
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/approve", json={"approved_by": "Priya Nair"}
    )
    assert approved.status_code == 200, approved.text
    return campaign_id


# ---------------------------------------------------------------------------
# Rubric gate — Phase B <-> Phase C linkage
# ---------------------------------------------------------------------------

def test_upload_requires_an_approved_rubric(client):
    campaign_id = client.post("/api/campaigns", json={
        "name": "No rubric yet", "job_title": "Engineer", "job_description": "x",
    }).json()["id"]

    response = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)])
    assert response.status_code == 409
    assert "approved rubric" in response.json()["detail"]


def test_batch_pins_the_rubric_version_and_locks_it(screening_campaign, client):
    campaign_id = screening_campaign
    active = client.get(f"/api/campaigns/{campaign_id}/rubric/active").json()
    assert active["status"] == "APPROVED"

    body = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
    assert body["batch"]["rubric_version_id"] == active["id"]

    # Screening against it freezes it — changing an in-use rubric in place is
    # exactly what the versioning rules forbid.
    after = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert after["status"] == "LOCKED"
    # And the campaign advances to PROCESSING.
    assert client.get(f"/api/campaigns/{campaign_id}").json()["status"] == "PROCESSING"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_pdf_and_docx_both_process_into_candidates(screening_campaign, client):
    campaign_id = screening_campaign
    body = upload(client, campaign_id, [
        ("priya.pdf", make_pdf(), PDF_MIME),
        ("arun.docx", make_docx(cv_text("Arun Verma", "arun.verma@example.com", "+91 91234 56780")), DOCX_MIME),
    ]).json()

    assert body["accepted_files"] == 2
    assert body["rejected_on_intake"] == 0
    assert body["queue_backend"] == "inline"

    progress = client.get(f"/api/processing/batches/{body['batch']['id']}").json()["progress"]
    assert progress["completed"] == 2
    assert progress["failed"] == 0
    assert progress["percent_complete"] == 100.0

    candidates = client.get(f"/api/campaigns/{campaign_id}/candidates").json()
    assert {c["full_name"] for c in candidates} == {"Priya Menon", "Arun Verma"}
    assert {c["email"] for c in candidates} == {"priya.menon@example.com", "arun.verma@example.com"}


def test_extracted_text_is_retained_for_evidence_citation(screening_campaign, client):
    """Phase D cannot cite evidence if the document isn't kept."""
    campaign_id = screening_campaign
    body = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
    document_id = body["jobs"][0]["document_id"]

    stored = client.get(f"/api/processing/documents/{document_id}/text").json()
    assert stored["text_char_count"] > 200
    assert "PostgreSQL" in stored["extracted_text"]
    assert stored["page_count"] == 1


def test_candidate_detail_lists_its_documents(screening_campaign, client):
    campaign_id = screening_campaign
    upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)])
    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]

    detail = client.get(f"/api/processing/candidates/{candidate_id}").json()
    assert len(detail["documents"]) == 1
    assert detail["documents"][0]["original_filename"] == "cv.pdf"


def test_job_records_elapsed_time(screening_campaign, client):
    campaign_id = screening_campaign
    body = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
    job = body["jobs"][0]
    assert job["duration_ms"] is not None
    assert job["started_at"] and job["finished_at"]
    assert job["attempts"] == 1


# ---------------------------------------------------------------------------
# Exception classification — every bad file gets a reason
# ---------------------------------------------------------------------------

def test_unsupported_format_is_rejected_on_intake(screening_campaign, client):
    body = upload(client, screening_campaign, [
        ("notes.txt", b"just some text, not a CV", "text/plain"),
    ]).json()
    job = body["jobs"][0]
    assert job["status"] == "FAILED"
    assert job["error_code"] == "UNSUPPORTED_FORMAT"
    assert body["rejected_on_intake"] == 1
    # Nothing was stored, so there is nothing to retry.
    assert job["document_id"] is None
    assert job["is_retryable"] is False


def test_empty_file_is_rejected(screening_campaign, client):
    body = upload(client, screening_campaign, [("empty.pdf", b"", PDF_MIME)]).json()
    assert body["jobs"][0]["error_code"] == "EMPTY_FILE"


def test_oversized_file_is_rejected(screening_campaign, client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    body = upload(screening_campaign and client, screening_campaign, [
        ("big.pdf", make_pdf(), PDF_MIME),
    ]).json()
    assert body["jobs"][0]["error_code"] == "FILE_TOO_LARGE"


def test_password_protected_pdf_is_reported_as_such(screening_campaign, client):
    """Must not be misreported as a scan — the recruiter needs to ask for an
    unlocked copy, not run OCR."""
    body = upload(client, screening_campaign, [
        ("locked.pdf", make_pdf(user_password="secret"), PDF_MIME),
    ]).json()
    job = body["jobs"][0]
    assert job["status"] == "FAILED"
    assert job["error_code"] == "PASSWORD_PROTECTED"


def test_corrupt_pdf_is_reported_as_corrupt(screening_campaign, client):
    body = upload(client, screening_campaign, [
        ("broken.pdf", b"%PDF-1.4 this is not really a pdf at all", PDF_MIME),
    ]).json()
    assert body["jobs"][0]["error_code"] == "CORRUPT_FILE"


def test_corrupt_docx_is_reported_as_corrupt(screening_campaign, client):
    body = upload(client, screening_campaign, [
        ("broken.docx", b"definitely not a zip archive", DOCX_MIME),
    ]).json()
    assert body["jobs"][0]["error_code"] == "CORRUPT_FILE"


def test_scanned_pdf_with_no_text_is_still_screened_and_flagged(screening_campaign, client):
    """
    A page with nothing on it is screened along with every other CV, whether
    or not character recognition is installed — there is nothing to
    recognise either way — but it is flagged so a person knows to also read
    the original file. The message is written for a recruiter, so it says
    what happened rather than naming the technique that failed.
    """
    body = upload(client, screening_campaign, [
        ("scan.pdf", make_pdf(blank=True), PDF_MIME),
    ]).json()
    job = body["jobs"][0]
    assert job["status"] == "COMPLETED"
    assert job["requires_review"] is True
    assert job["error_code"] == "NO_TEXT_EXTRACTED"
    message = job["error_message"].lower()
    assert "scanned image" in message or "character recognition" in message


def test_document_with_no_identity_completes_but_is_flagged(screening_campaign, client):
    """No name/email/phone no longer holds a file out of screening — it is
    screened on its text alone and flagged for a person to confirm who it
    belongs to."""
    filler = "Responsibilities included building and maintaining backend services. " * 8
    body = upload(client, screening_campaign, [
        ("anon.pdf", make_pdf(text=filler), PDF_MIME),
    ]).json()
    job = body["jobs"][0]
    assert job["status"] == "COMPLETED"
    assert job["requires_review"] is True
    assert job["error_code"] == "INCOMPLETE_CONTENT"

    flagged = client.get(f"/api/campaigns/{screening_campaign}/candidates?requires_review=true").json()
    assert len(flagged) == 1


def test_partial_identity_completes_but_requires_review(screening_campaign, client):
    """A name with no email or phone is usable but needs a human look."""
    text = "Ravi Kulkarni\nBengaluru\n\n" + ("Backend engineer working with Python services. " * 8)
    body = upload(client, screening_campaign, [("partial.pdf", make_pdf(text=text), PDF_MIME)]).json()
    job = body["jobs"][0]
    assert job["status"] == "COMPLETED"
    assert job["requires_review"] is True
    assert job["error_code"] == "INCOMPLETE_CONTENT"

    flagged = client.get(f"/api/campaigns/{screening_campaign}/candidates?requires_review=true").json()
    assert len(flagged) == 1
    assert flagged[0]["full_name"] == "Ravi Kulkarni"


def test_mixed_batch_accounts_for_every_file(screening_campaign, client):
    """N files in, N jobs out — nothing silently disappears."""
    campaign_id = screening_campaign
    body = upload(client, campaign_id, [
        ("good.pdf", make_pdf(), PDF_MIME),
        ("locked.pdf", make_pdf(user_password="x"), PDF_MIME),
        ("broken.pdf", b"garbage", PDF_MIME),
        ("notes.txt", b"nope", "text/plain"),
        ("scan.pdf", make_pdf(blank=True), PDF_MIME),
    ]).json()

    assert body["batch"]["total_files"] == 5
    assert len(body["jobs"]) == 5

    progress = client.get(f"/api/processing/batches/{body['batch']['id']}").json()["progress"]
    # scan.pdf is screened and flagged now, not held, so it counts as completed.
    assert progress["completed"] == 2
    assert progress["failed"] == 3
    assert progress["percent_complete"] == 100.0
    assert progress["status"] == "COMPLETED_WITH_ERRORS"

    codes = {job["error_code"] for job in body["jobs"] if job["error_code"]}
    assert codes == {
        "PASSWORD_PROTECTED", "CORRUPT_FILE", "UNSUPPORTED_FORMAT", "NO_TEXT_EXTRACTED"
    }


def test_exceptions_panel_can_filter_by_status(screening_campaign, client):
    body = upload(client, screening_campaign, [
        ("good.pdf", make_pdf(), PDF_MIME),
        ("broken.pdf", b"garbage", PDF_MIME),
    ]).json()
    batch_id = body["batch"]["id"]

    failed = client.get(f"/api/processing/batches/{batch_id}/jobs?status=FAILED").json()
    assert len(failed) == 1
    assert failed[0]["original_filename"] == "broken.pdf"

    completed = client.get(f"/api/processing/batches/{batch_id}/jobs?status=COMPLETED").json()
    assert len(completed) == 1


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def test_byte_identical_file_is_an_exact_duplicate(screening_campaign, client):
    campaign_id = screening_campaign
    data = make_pdf()
    body = upload(client, campaign_id, [
        ("cv.pdf", data, PDF_MIME),
        ("cv-copy.pdf", data, PDF_MIME),
    ]).json()

    statuses = {job["original_filename"]: job for job in body["jobs"]}
    assert statuses["cv.pdf"]["status"] == "COMPLETED"
    duplicate = statuses["cv-copy.pdf"]
    assert duplicate["status"] == "DUPLICATE"
    assert duplicate["duplicate_type"] == "EXACT_FILE"
    assert duplicate["duplicate_of_document_id"]

    # One candidate, not two.
    assert len(client.get(f"/api/campaigns/{campaign_id}/candidates").json()) == 1


def test_same_email_different_file_is_a_candidate_duplicate(screening_campaign, client):
    """A reformatted CV for the same person is one candidate, two documents."""
    campaign_id = screening_campaign
    upload(client, campaign_id, [("v1.pdf", make_pdf(), PDF_MIME)])
    body = upload(client, campaign_id, [
        ("v2.docx", make_docx(cv_text() + "\nAdditional certification: AWS Solutions Architect"), DOCX_MIME),
    ]).json()

    job = body["jobs"][0]
    assert job["status"] == "DUPLICATE"
    assert job["duplicate_type"] == "SAME_CANDIDATE_EMAIL"

    candidates = client.get(f"/api/campaigns/{campaign_id}/candidates").json()
    assert len(candidates) == 1
    # The newer document is kept and attached to the existing candidate.
    detail = client.get(f"/api/processing/candidates/{candidates[0]['id']}").json()
    assert len(detail["documents"]) == 2


def test_same_phone_in_a_different_format_is_detected(screening_campaign, client):
    """'+91 98765 43210' and '098765-43210' are the same number."""
    campaign_id = screening_campaign
    upload(client, campaign_id, [("a.pdf", make_pdf(), PDF_MIME)])
    body = upload(client, campaign_id, [(
        "b.pdf",
        make_pdf(text=cv_text("Priya M Menon", "different.address@example.com", "098765-43210")),
        PDF_MIME,
    )]).json()

    job = body["jobs"][0]
    assert job["status"] == "DUPLICATE"
    assert job["duplicate_type"] == "SAME_CANDIDATE_PHONE"


def test_name_only_match_is_flagged_for_review_not_trusted(screening_campaign, client):
    campaign_id = screening_campaign
    text_a = "Vikram Rao\nBengaluru\n\n" + ("Backend engineer building Python services. " * 8)
    text_b = "Vikram Rao\nPune\n\n" + ("Data engineer building Spark pipelines. " * 8)
    upload(client, campaign_id, [("a.pdf", make_pdf(text=text_a), PDF_MIME)])
    body = upload(client, campaign_id, [("b.pdf", make_pdf(text=text_b), PDF_MIME)]).json()

    job = body["jobs"][0]
    assert job["status"] == "DUPLICATE"
    assert job["duplicate_type"] == "SAME_CANDIDATE_NAME"
    assert job["requires_review"] is True
    assert "confirm" in job["error_message"].lower()


def test_duplicates_are_scoped_to_a_campaign(client):
    """The same person applying to two roles is not a duplicate."""
    def build_campaign(name):
        with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
            cid = client.post("/api/campaigns", json={
                "name": name, "job_title": "Engineer", "job_description": "Python AWS",
            }).json()["id"]
            client.post(f"/api/campaigns/{cid}/requirements/extract", json={})
        client.post(f"/api/campaigns/{cid}/rubric/versions", json={"seed_from_requirements": True})
        client.post(f"/api/campaigns/{cid}/rubric/versions/1/submit", json={})
        client.post(f"/api/campaigns/{cid}/rubric/versions/1/approve", json={})
        return cid

    first, second = build_campaign("Role A"), build_campaign("Role B")
    data = make_pdf()
    assert upload(client, first, [("cv.pdf", data, PDF_MIME)]).json()["jobs"][0]["status"] == "COMPLETED"
    assert upload(client, second, [("cv.pdf", data, PDF_MIME)]).json()["jobs"][0]["status"] == "COMPLETED"

    assert len(client.get(f"/api/campaigns/{first}/candidates").json()) == 1
    assert len(client.get(f"/api/campaigns/{second}/candidates").json()) == 1


def test_enrichment_fills_blanks_without_overwriting(screening_campaign, client):
    """A later CV can add a missing phone but must not change a known email."""
    campaign_id = screening_campaign
    no_phone = "Neha Gupta\nneha.gupta@example.com\n\n" + ("Engineer working on Python services. " * 8)
    upload(client, campaign_id, [("a.pdf", make_pdf(text=no_phone), PDF_MIME)])

    with_phone = cv_text("Neha Gupta", "neha.gupta@example.com", "+91 90000 11111")
    upload(client, campaign_id, [("b.pdf", make_pdf(text=with_phone), PDF_MIME)])

    candidate = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]
    assert candidate["email"] == "neha.gupta@example.com"
    assert "90000" in candidate["phone"]


# ---------------------------------------------------------------------------
# Retry and cancel
# ---------------------------------------------------------------------------

def test_retry_reprocesses_a_stored_file(screening_campaign, client):
    """
    Retry works because the document was retained. Simulate a transient
    extraction failure, then retry once the fault clears.
    """
    campaign_id = screening_campaign
    from app.core.document_intake import DocumentRejected
    from app.db.models import JobErrorCode

    with patch(
        "app.services.processing_service.document_intake.extract_document",
        side_effect=DocumentRejected(JobErrorCode.EXTRACTION_FAILED, "transient glitch"),
    ):
        body = upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)]).json()

    job = body["jobs"][0]
    assert job["status"] == "FAILED"
    assert job["error_code"] == "EXTRACTION_FAILED"
    assert job["is_retryable"] is True
    assert job["document_id"] is not None

    retried = client.post(f"/api/processing/jobs/{job['id']}/retry").json()
    assert retried["status"] == "COMPLETED"
    assert retried["attempts"] == 2
    assert len(client.get(f"/api/campaigns/{campaign_id}/candidates").json()) == 1


def test_retry_is_refused_for_a_file_that_was_never_stored(screening_campaign, client):
    body = upload(client, screening_campaign, [("notes.txt", b"nope", "text/plain")]).json()
    response = client.post(f"/api/processing/jobs/{body['jobs'][0]['id']}/retry")
    assert response.status_code == 409
    assert "nothing to retry" in response.json()["detail"]


def test_retry_is_refused_for_a_completed_job(screening_campaign, client):
    body = upload(client, screening_campaign, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
    response = client.post(f"/api/processing/jobs/{body['jobs'][0]['id']}/retry")
    assert response.status_code == 409


def test_retry_stops_at_max_attempts(screening_campaign, client, monkeypatch):
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "1")
    from app.core.document_intake import DocumentRejected
    from app.db.models import JobErrorCode

    with patch(
        "app.services.processing_service.document_intake.extract_document",
        side_effect=DocumentRejected(JobErrorCode.EXTRACTION_FAILED, "still broken"),
    ):
        body = upload(client, screening_campaign, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
        job_id = body["jobs"][0]["id"]
        response = client.post(f"/api/processing/jobs/{job_id}/retry")

    assert response.status_code == 409
    assert "attempts" in response.json()["detail"]


def test_cancel_stops_queued_work_and_keeps_finished_results(screening_campaign, client, monkeypatch):
    campaign_id = screening_campaign
    monkeypatch.setenv("QUEUE_BACKEND", "deferred")

    body = upload(client, campaign_id, [
        ("a.pdf", make_pdf(), PDF_MIME),
        ("b.pdf", make_pdf(text=cv_text("Arun Verma", "arun@example.com", "+91 91234 56780")), PDF_MIME),
    ]).json()
    batch_id = body["batch"]["id"]
    assert body["queue_backend"] == "deferred"
    assert all(job["status"] == "QUEUED" for job in body["jobs"])

    # Process only the first file, then cancel the rest.
    client.post(f"/api/processing/batches/{batch_id}/run?limit=1")
    cancelled = client.post(f"/api/processing/batches/{batch_id}/cancel").json()

    assert cancelled["batch"]["status"] == "CANCELLED"
    assert cancelled["progress"]["completed"] == 1
    assert cancelled["progress"]["cancelled"] == 1
    assert len(client.get(f"/api/campaigns/{campaign_id}/candidates").json()) == 1


def test_cancel_is_refused_once_a_batch_has_finished(screening_campaign, client):
    body = upload(client, screening_campaign, [("cv.pdf", make_pdf(), PDF_MIME)]).json()
    response = client.post(f"/api/processing/batches/{body['batch']['id']}/cancel")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Deferred queue backend and progress
# ---------------------------------------------------------------------------

def test_deferred_backend_returns_immediately_then_drains(screening_campaign, client, monkeypatch):
    """The Windows dev path: upload is fast, a drainer does the work."""
    campaign_id = screening_campaign
    monkeypatch.setenv("QUEUE_BACKEND", "deferred")

    body = upload(client, campaign_id, [
        ("a.pdf", make_pdf(), PDF_MIME),
        ("b.pdf", make_pdf(text=cv_text("Arun Verma", "arun@example.com", "+91 91234 56780")), PDF_MIME),
    ]).json()
    batch_id = body["batch"]["id"]

    progress = client.get(f"/api/processing/batches/{batch_id}").json()["progress"]
    assert progress["queued"] == 2
    assert progress["percent_complete"] == 0.0
    assert progress["status"] == "PENDING"

    drained = client.post(f"/api/processing/batches/{batch_id}/run").json()
    assert drained["processed"] == 2
    assert drained["remaining"] == 0
    assert drained["progress"]["completed"] == 2
    assert drained["progress"]["status"] == "COMPLETED"


def test_progress_reports_throughput_and_eta(screening_campaign, client, monkeypatch):
    campaign_id = screening_campaign
    monkeypatch.setenv("QUEUE_BACKEND", "deferred")
    files = [
        (f"cv{i}.pdf", make_pdf(text=cv_text(f"Person {'ABCDE'[i]}", f"p{i}@example.com", f"+91 9000 0{i}0000")), PDF_MIME)
        for i in range(4)
    ]
    batch_id = upload(client, campaign_id, files).json()["batch"]["id"]

    client.post(f"/api/processing/batches/{batch_id}/run?limit=2")
    progress = client.get(f"/api/processing/batches/{batch_id}").json()["progress"]

    assert progress["total_files"] == 4
    assert progress["queued"] == 2
    assert progress["percent_complete"] == 50.0
    assert progress["average_seconds_per_file"] is not None
    assert progress["estimated_seconds_remaining"] is not None
    assert progress["elapsed_seconds"] is not None


def test_batch_list_and_lookup(screening_campaign, client):
    campaign_id = screening_campaign
    upload(client, campaign_id, [("cv.pdf", make_pdf(), PDF_MIME)], name="Morning intake")

    batches = client.get(f"/api/campaigns/{campaign_id}/batches").json()
    assert len(batches) == 1
    assert batches[0]["name"] == "Morning intake"

    assert client.get("/api/processing/batches/nope").status_code == 404
    assert client.get("/api/processing/jobs/nope").status_code == 404
    assert client.get("/api/processing/candidates/nope").status_code == 404


def test_empty_upload_is_rejected(screening_campaign, client):
    response = client.post(f"/api/campaigns/{screening_campaign}/batches", files=[])
    assert response.status_code == 422


def test_per_batch_file_limit_is_enforced(screening_campaign, client, monkeypatch):
    monkeypatch.setenv("MAX_FILES_PER_BATCH", "2")
    response = upload(client, screening_campaign, [
        ("a.pdf", make_pdf(), PDF_MIME),
        ("b.pdf", make_pdf(), PDF_MIME),
        ("c.pdf", make_pdf(), PDF_MIME),
    ])
    assert response.status_code == 422
    assert "per-batch limit" in response.json()["detail"]


def test_upload_to_unknown_campaign_returns_404(client):
    assert upload(client, "does-not-exist", [("cv.pdf", make_pdf(), PDF_MIME)]).status_code == 404


def test_a_skills_line_is_not_mistaken_for_a_candidate_name(screening_campaign, client):
    """
    Regression: a CV with no contact details produced a candidate called
    "Python, AWS, PostgreSQL, Docker" because the name heuristic scanned past
    the SKILLS heading and matched the comma-separated list beneath it.
    """
    anonymous = "\n".join([
        "CURRICULUM VITAE", "",
        "EXPERIENCE",
        "Backend engineer responsible for building and running Python services.",
        "Migrated a monolith to containerised microservices on AWS.", "",
        "SKILLS", "Python, AWS, PostgreSQL, Docker",
    ])
    body = upload(client, screening_campaign, [("anon.pdf", make_pdf(text=anonymous), PDF_MIME)]).json()

    job = body["jobs"][0]
    assert job["status"] == "COMPLETED"
    assert job["error_code"] == "INCOMPLETE_CONTENT"
    candidates = client.get(f"/api/campaigns/{screening_campaign}/candidates").json()
    assert len(candidates) == 1
    assert candidates[0]["full_name"] == ""


def test_name_above_the_first_heading_is_still_found(screening_campaign, client):
    """The tightened heuristic must not lose real names in the header block."""
    text = "Vikram Rao\nKolkata\n\nEXPERIENCE\n" + ("Senior engineer building Python services. " * 8)
    body = upload(client, screening_campaign, [("v.pdf", make_pdf(text=text), PDF_MIME)]).json()

    assert body["jobs"][0]["status"] == "COMPLETED"
    assert body["jobs"][0]["requires_review"] is True
    assert client.get(f"/api/campaigns/{screening_campaign}/candidates").json()[0]["full_name"] == "Vikram Rao"


def test_surname_first_name_format_is_accepted(screening_campaign, client):
    """One comma is the 'Menon, Priya' convention; two or more is a list."""
    from app.core.document_intake import extract_identity
    assert extract_identity("Menon, Priya\npriya@example.com\n").full_name == "Menon, Priya"
    assert extract_identity("SKILLS\nPython, AWS, Docker, Redis\n").full_name == ""


def test_em_dash_packed_header_still_yields_a_name(screening_campaign, client):
    """X1: `Resume_ProcessEngineer_DanielCruz_Unstructured.docx`'s header packs
    name, location, email and phone onto one line with em dashes. The name is
    there; only the first fragment that looks like a name should be taken."""
    from app.core.document_intake import extract_identity
    text = "Daniel Cruz — Doha, Qatar — daniel.cruz1988@example.com — +974 5567 1122\n"
    identity = extract_identity(text)
    assert identity.full_name == "Daniel Cruz"
    assert identity.email == "daniel.cruz1988@example.com"


def test_throughput_survives_a_fast_machine(screening_campaign, client, monkeypatch):
    """
    A job quick enough to finish inside a millisecond still counts as work.

    Duration 0 is reserved for files rejected at intake, which are excluded
    from throughput deliberately. Before the floor, a fast machine recorded
    real jobs as 0 too, so the Control Tower showed no throughput and no ETA
    — and the faster the hardware, the more often it happened.
    """
    from app.db.models import ProcessingJob

    monkeypatch.setenv("QUEUE_BACKEND", "deferred")
    batch_id = upload(client, screening_campaign, [
        ("cv0.pdf", make_pdf(text=cv_text()), PDF_MIME),
        ("cv1.pdf", make_pdf(text=cv_text("Reem", "reem@example.com", "+966 55 111 2222")), PDF_MIME),
    ]).json()["batch"]["id"]

    client.post(f"/api/processing/batches/{batch_id}/run?limit=1")
    progress = client.get(f"/api/processing/batches/{batch_id}").json()["progress"]

    assert progress["average_seconds_per_file"] is not None
    assert progress["estimated_seconds_remaining"] is not None
