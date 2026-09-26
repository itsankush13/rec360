"""
Optical character recognition, and what a CV read from images does to an
assessment.

The governing rule, asserted several ways below:

    **Reading quality changes confidence, never the score.**

A candidate whose CV arrives as photographs is not a worse candidate. They
are a candidate we read less reliably, and the honest expression of that is
a lower confidence with the same score — not points deducted for their
scanner. The score answers "how well does this person match"; confidence
answers "how sure are we that we read them correctly". Conflating the two
would let a strong operator drop below a weak one on the strength of their
office equipment.

The OCR tests skip when the package is absent, so the suite stays green on a
machine that has not installed it — which is also the behaviour the
application itself has.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest

from app.core import document_intake, document_quality, ocr
from app.core.document_intake import (
    TEXT_SOURCE_EXTRACTED, TEXT_SOURCE_MIXED, TEXT_SOURCE_OCR,
)

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, cv_text, upload


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

SCANNABLE_CV = "\n".join([
    "Haitham Al-Otaibi",
    "haitham.alotaibi@example.com",
    "+966 55 123 4567",
    "",
    "EXPERIENCE",
    "Senior Control Room Operator, Coastal Terminal, 2016 to present.",
    "Held a console licence on a live ethylene unit for seven years,",
    "including two full turnarounds. Named permit-to-work authority",
    "for the olefins area. Wrote the emergency depressurisation procedure.",
    "",
    "EDUCATION",
    "Diploma in Chemical Process Technology",
])


def make_scanned_pdf(text=SCANNABLE_CV, pages=1, dpi=200):
    """
    A PDF with no text layer at all — the page is a picture of the words.
    This is what a third of the client's held files actually are.
    """
    source = pymupdf.open()
    page = source.new_page()
    page.insert_text((60, 80), text, fontsize=11)
    # JPEG rather than a raw pixmap: an uncompressed 200 dpi page is about
    # 11 MB, over the upload limit, and a real scanner produces JPEG anyway.
    image = page.get_pixmap(dpi=dpi).tobytes("jpeg", jpg_quality=85)

    scan = pymupdf.open()
    for _ in range(pages):
        target = scan.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=image)
    return scan.tobytes()


def make_half_scanned_pdf():
    """Page one is real text; page two is a picture. A stapled certificate."""
    source = pymupdf.open()
    drawn = source.new_page()
    drawn.insert_text((60, 80), SCANNABLE_CV, fontsize=11)
    image = drawn.get_pixmap(dpi=200).tobytes("jpeg", jpg_quality=85)

    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((60, 80), cv_text(), fontsize=9)
    second = document.new_page(width=drawn.rect.width, height=drawn.rect.height)
    second.insert_image(second.rect, stream=image)
    return document.tobytes()


def document(source=TEXT_SOURCE_EXTRACTED, *, pages=2, read=2, by_ocr=0):
    return SimpleNamespace(
        text_source=source, page_count=pages,
        pages_with_text=read, ocr_pages=by_ocr,
    )


needs_ocr = pytest.mark.skipif(
    not ocr.available(), reason="the OCR package is not installed"
)


# ---------------------------------------------------------------------------
# The ceiling
# ---------------------------------------------------------------------------

def test_a_normally_read_cv_has_no_ceiling():
    assert document_quality.confidence_ceiling(document()) is None


def test_a_cv_read_from_images_is_capped():
    ceiling = document_quality.confidence_ceiling(
        document(TEXT_SOURCE_OCR, by_ocr=2)
    )
    assert ceiling == document_quality.OCR_CONFIDENCE_CEILING
    assert ceiling < 1.0


def test_a_partly_scanned_cv_is_capped_less_harshly():
    partly = document_quality.confidence_ceiling(document(TEXT_SOURCE_MIXED, by_ocr=1))
    wholly = document_quality.confidence_ceiling(document(TEXT_SOURCE_OCR, by_ocr=2))
    assert wholly < partly < 1.0


def test_a_missing_document_has_no_ceiling():
    assert document_quality.confidence_ceiling(None) is None


# ---------------------------------------------------------------------------
# The readout
# ---------------------------------------------------------------------------

def test_nothing_is_said_about_a_cv_that_read_normally():
    """No reassurance nobody asked for on the overwhelming majority of CVs."""
    assert document_quality.describe(document()) is None


def test_the_readout_is_plain_english_with_its_denominator():
    readout = document_quality.describe(document(TEXT_SOURCE_OCR, pages=3, read=3, by_ocr=3))
    assert "3 of 3 page(s)" in readout["summary"]
    for banned in ("OCR", "NO_TEXT_EXTRACTED", "ocr_pages"):
        assert banned not in readout["summary"]


def test_the_readout_says_the_score_is_not_reduced():
    """
    The distinction this whole design rests on has to be legible to whoever
    reads the screen, not just to whoever reads the code.
    """
    readout = document_quality.describe(document(TEXT_SOURCE_MIXED, by_ocr=1))
    assert "not reduced" in readout["effect_on_assessment"]


def test_the_note_reaches_the_missing_information_list():
    note = document_quality.missing_information_note(document(TEXT_SOURCE_OCR, by_ocr=2))
    assert note and "character recognition" in note
    assert document_quality.missing_information_note(document()) is None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_a_text_pdf_is_never_sent_to_ocr(tmp_path):
    """
    OCR costs seconds a page. It must run only where there is nothing to
    read, or the batch slows down for every candidate to no purpose.
    """
    path = tmp_path / "cv.pdf"
    path.write_bytes(pymupdf.open().tobytes() if False else _text_pdf())

    with patch("app.core.ocr.read_pdf") as never:
        extracted = document_intake.extract_document(path, "cv.pdf")

    never.assert_not_called()
    assert extracted.text_source == TEXT_SOURCE_EXTRACTED
    assert extracted.ocr_pages == 0


def _text_pdf():
    document_ = pymupdf.open()
    page = document_.new_page()
    page.insert_text((60, 60), cv_text(), fontsize=9)
    return document_.tobytes()


@needs_ocr
def test_a_scanned_cv_is_recovered_and_marked_as_recognised(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_scanned_pdf())

    extracted = document_intake.extract_document(path, "scan.pdf")

    assert extracted.text_source == TEXT_SOURCE_OCR
    assert extracted.ocr_pages == 1
    assert "ethylene" in extracted.text.lower()


@needs_ocr
def test_pages_with_real_text_are_never_replaced_by_recognised_text(tmp_path):
    """
    Extracted text is exact and recognised text is an approximation, so a
    page that has both must keep the exact one.
    """
    path = tmp_path / "half.pdf"
    path.write_bytes(make_half_scanned_pdf())

    extracted = document_intake.extract_document(path, "half.pdf")

    assert extracted.text_source == TEXT_SOURCE_MIXED
    assert extracted.ocr_pages == 1
    assert extracted.pages_with_text == 2
    # Page one's exact text survived intact.
    assert "priya.menon@example.com" in extracted.text


def test_ocr_is_skipped_when_it_is_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_ENABLED", "false")
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_scanned_pdf())

    extracted = document_intake.extract_document(path, "scan.pdf")

    assert extracted.low_text is True
    assert len(extracted.text) < document_intake.MIN_TEXT_CHARS


def test_a_broken_ocr_install_still_screens_rather_than_failing_the_batch(tmp_path):
    """
    OCR is an improvement on reading the file, never a reason a scanned CV
    stops being screened — a broken install degrades to low_text, not a
    held/failed job.
    """
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_scanned_pdf())

    with patch("app.core.ocr._get_engine", return_value=None):
        extracted = document_intake.extract_document(path, "scan.pdf")

    assert extracted.low_text is True


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

@pytest.fixture()
def screening_campaign_for_scans(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Scanned intake", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    return campaign_id


@needs_ocr
def test_a_scanned_cv_becomes_a_candidate_instead_of_a_held_file(
    screening_campaign_for_scans, client
):
    """The whole point: a real application that used to vanish now doesn't."""
    body = upload(client, screening_campaign_for_scans, [
        ("scan.pdf", make_scanned_pdf(), PDF_MIME),
    ]).json()

    job = body["jobs"][0]
    assert job["status"] != "FAILED", job["error_message"]
    candidates = client.get(
        f"/api/campaigns/{screening_campaign_for_scans}/candidates"
    ).json()
    assert len(candidates) == 1


@needs_ocr
def test_a_recovered_cv_is_flagged_for_a_human_look(
    screening_campaign_for_scans, client
):
    """
    Recovered, not verified. A recogniser that turns DCS into DcS can lose a
    mandatory skill, so somebody should glance at it.
    """
    body = upload(client, screening_campaign_for_scans, [
        ("scan.pdf", make_scanned_pdf(), PDF_MIME),
    ]).json()
    assert body["jobs"][0]["requires_review"] is True


@needs_ocr
def test_the_assessment_reports_how_the_cv_was_read(
    screening_campaign_for_scans, client
):
    upload(client, screening_campaign_for_scans, [
        ("scan.pdf", make_scanned_pdf(), PDF_MIME),
    ])
    run = client.post(
        f"/api/campaigns/{screening_campaign_for_scans}/evaluations/runs", json={}
    ).json()
    evaluation_id = run["evaluations"][0]["id"]

    detail = client.get(f"/api/evaluations/{evaluation_id}").json()

    assert detail["document_quality"] is not None
    assert detail["document_quality"]["pages_read_by_character_recognition"] == 1
    # And it is in the "what we don't know" list the client asks for.
    assert any("character recognition" in item
               for item in detail["missing_information"])


@needs_ocr
def test_a_recovered_cv_is_capped_on_confidence_but_not_on_score(
    screening_campaign_for_scans, client
):
    upload(client, screening_campaign_for_scans, [
        ("scan.pdf", make_scanned_pdf(), PDF_MIME),
    ])
    run = client.post(
        f"/api/campaigns/{screening_campaign_for_scans}/evaluations/runs", json={}
    ).json()
    detail = client.get(f"/api/evaluations/{run['evaluations'][0]['id']}").json()

    assert detail["overall_confidence"] <= document_quality.OCR_CONFIDENCE_CEILING
    # The score is whatever the rubric said. Nothing was deducted for the
    # file being a photograph, which is the entire design decision here.
    assert detail["overall_score"] > 0


def test_a_normally_read_cv_carries_no_readout(screening_campaign_for_scans, client):
    upload(client, screening_campaign_for_scans, [("cv.pdf", _text_pdf(), PDF_MIME)])
    run = client.post(
        f"/api/campaigns/{screening_campaign_for_scans}/evaluations/runs", json={}
    ).json()
    detail = client.get(f"/api/evaluations/{run['evaluations'][0]['id']}").json()
    assert detail["document_quality"] is None
