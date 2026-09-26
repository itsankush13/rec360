"""
How much of a CV could actually be read, and what that means for confidence.

This is deliberately **not** a scoring component. It never contributes a
point to the candidate's match score, for two reasons:

  * The rubric weights are approved by a named person and sum to exactly
    100. Adding a fixed readability slice would change what was signed off
    without anyone approving the change.
  * The client's requirement is that every scored criterion carries evidence
    from the CV. "This PDF is a photograph" is evidence about the file, not
    about the candidate's career. Scoring it would mean a strong operator
    losing points for their scanner.

What it does instead is lower the ceiling on **confidence**, which the
engine already treats as separate from the score and already uses to
withhold an automatic recommendation. A candidate read from images can still
score 91; they will simply not be presented as a confident 91.

The ceilings are conservative and flat rather than tuned. Text recovered
from an image is right most of the time and wrong in ways that matter: a
single misread character turns DCS into DcS, and a mandatory criterion into
a miss. Until that error rate has been measured against real client CVs,
a coarse ceiling is the honest instrument.
"""
from __future__ import annotations

from app.core.document_intake import (
    TEXT_SOURCE_EXTRACTED, TEXT_SOURCE_MIXED, TEXT_SOURCE_OCR,
)

# Wholly read from images: the whole assessment rests on approximate text.
OCR_CONFIDENCE_CEILING = 0.60

# Partly: the pages with a real text layer are exact, so the penalty is
# lighter, but a mandatory requirement may still sit on a misread page.
MIXED_CONFIDENCE_CEILING = 0.75


def confidence_ceiling(document) -> float | None:
    """
    The highest confidence an assessment of this document may claim.

    None means no ceiling — the text came from a real text layer and nothing
    about the file itself casts doubt on the reading.
    """
    if document is None:
        return None
    source = getattr(document, "text_source", TEXT_SOURCE_EXTRACTED)
    if source == TEXT_SOURCE_OCR:
        return OCR_CONFIDENCE_CEILING
    if source == TEXT_SOURCE_MIXED:
        return MIXED_CONFIDENCE_CEILING
    return None


def describe(document) -> dict | None:
    """
    A readout for Candidate 360, in the words of web/DATA.md: plain English,
    never an enum, never a count without its denominator.

    Returns None for a document read normally, so the screen shows nothing
    at all in the ordinary case rather than a reassuring line nobody needs.
    """
    if document is None:
        return None
    source = getattr(document, "text_source", TEXT_SOURCE_EXTRACTED)
    if source == TEXT_SOURCE_EXTRACTED:
        return None

    pages = getattr(document, "page_count", 0) or 0
    read = getattr(document, "pages_with_text", 0) or 0
    by_ocr = getattr(document, "ocr_pages", 0) or 0

    if source == TEXT_SOURCE_OCR:
        summary = (
            f"This CV is photographs rather than text. "
            f"{by_ocr} of {pages} page(s) were read by character recognition."
            if pages else
            "This CV is photographs rather than text, and was read by "
            "character recognition."
        )
    else:
        summary = (
            f"Part of this CV is photographs rather than text. "
            f"{by_ocr} of {pages} page(s) were read by character recognition; "
            f"the rest were read directly."
            if pages else
            "Part of this CV is photographs rather than text."
        )

    return {
        "pages": pages or None,
        "pages_read": read or None,
        "pages_read_by_character_recognition": by_ocr,
        "read_directly": max(0, read - by_ocr),
        "summary": summary,
        # The consequence, stated rather than left for the reader to infer.
        "effect_on_assessment": (
            "Recognised text can contain mistakes, so this assessment is held "
            "to a lower confidence than one read from a text file. The score "
            "itself is not reduced. Check the quoted evidence before deciding."
        ),
    }


def missing_information_note(document) -> str | None:
    """The same fact, phrased for the Candidate 360 "what we don't know" list."""
    if confidence_ceiling(document) is None:
        return None
    by_ocr = getattr(document, "ocr_pages", 0) or 0
    pages = getattr(document, "page_count", 0) or 0
    where = f"{by_ocr} of {pages} page(s)" if pages else "Part of this CV"
    return (
        f"{where} of this CV had no readable text and were read by character "
        "recognition, so quoted evidence from them may not be word-perfect."
    )
