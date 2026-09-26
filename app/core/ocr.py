"""
Optical character recognition for CVs that are images rather than text.

Roughly a third of the held files in the client's own data are photographs
or scans of a CV. Without this they are never assessed, which means a real
application is silently absent from the shortlist.

Design constraints this module exists to satisfy:

  * **No system binary.** Tesseract needs an installer and administrator
    rights, which are not available on the delivery machine. RapidOCR ships
    its detection, recognition and angle-classification models inside the
    Python wheel, so `pip install` is the whole installation and nothing is
    downloaded at first use.
  * **Never constructed at import.** Building the engine loads three ONNX
    models. Doing that at module scope would make importing this module cost
    a second and would break test collection on a machine without the
    package — the same rule the LLM providers follow.
  * **Optional.** If the package is absent, or `OCR_ENABLED` is false,
    everything behaves exactly as it did before: the file is held with
    `NO_TEXT_EXTRACTED` and the recruiter is told it could not be read.
    OCR degrades to the previous behaviour, it does not fail.
  * **Page by page.** Evidence citation depends on `page_number`, so OCR
    text must stay attributed to the page it came from rather than being
    concatenated into one blob.

What this module deliberately does NOT do: decide anything about the
candidate. It returns text. Text recovered this way is less reliable than
text extracted from a real text layer — a single misread character turns
`DCS` into `DcS` and a mandatory skill into a miss — so the caller records
where the text came from and the assessment lowers its confidence
accordingly. See `app.core.document_quality`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Below 200 dpi the recogniser starts merging adjacent lines, which destroys
# the section structure the segmenter depends on. Measured, not guessed.
DEFAULT_DPI = 200

# A CV longer than this is either not a CV or is a portfolio. Capping the
# page count bounds the worst case: OCR costs seconds per page, and one
# pathological 400-page scan should not stall a batch.
DEFAULT_MAX_PAGES = 12

_engine = None
_engine_failed = False


@dataclass
class OcrResult:
    """Per-page text, plus what it cost, so throughput can be reported."""
    pages: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def text(self) -> str:
        return "\n".join(page for page in self.pages if page).strip()

    @property
    def pages_with_text(self) -> int:
        return sum(1 for page in self.pages if page.strip())


def enabled() -> bool:
    """
    OCR is on unless explicitly disabled, and is silently off when the
    package is not installed.
    """
    setting = os.getenv("OCR_ENABLED", "").strip().lower()
    if setting in ("0", "false", "no", "off"):
        return False
    return available()


def available() -> bool:
    """True when the OCR package can be imported. Never raises."""
    try:
        import rapidocr  # noqa: F401
    except Exception:
        return False
    return True


def dpi() -> int:
    try:
        return max(120, int(os.getenv("OCR_DPI", str(DEFAULT_DPI))))
    except ValueError:
        return DEFAULT_DPI


def max_pages() -> int:
    try:
        return max(1, int(os.getenv("OCR_MAX_PAGES", str(DEFAULT_MAX_PAGES))))
    except ValueError:
        return DEFAULT_MAX_PAGES


def _get_engine():
    """
    Build the engine once, on first use. A failure is remembered so a broken
    install costs one attempt per process rather than one per CV.
    """
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    try:
        from rapidocr import RapidOCR

        _engine = RapidOCR()
    except Exception:
        logger.exception("OCR engine could not be built; continuing without it")
        _engine_failed = True
        _engine = None
    return _engine


def reset_engine() -> None:
    """Drop the cached engine. Tests use this; nothing else should need it."""
    global _engine, _engine_failed
    _engine = None
    _engine_failed = False


def read_pdf(path, *, page_limit: int | None = None,
             only_pages: set[int] | None = None) -> OcrResult:
    """
    Read a PDF's pages as images and return their text, page by page.

    `only_pages` restricts the work to the pages that actually need it,
    keyed by zero-based page number. Pages outside it come back empty, so
    the caller's page numbering is preserved either way — evidence citation
    depends on it.

    Returns an empty result rather than raising, for any reason at all. A CV
    that cannot be read is already handled — it is held and the recruiter is
    told why — and an OCR fault must not turn that into a failed batch.
    """
    import time

    result = OcrResult()
    if not enabled():
        return result

    engine = _get_engine()
    if engine is None:
        return result

    started = time.time()
    try:
        import pymupdf

        document = pymupdf.open(path)
    except Exception:
        logger.exception("OCR could not open the document")
        return result

    limit = page_limit or max_pages()
    resolution = dpi()
    try:
        for number, page in enumerate(document):
            if number >= limit:
                logger.info(
                    "OCR stopped at the %s-page limit for this document", limit
                )
                break
            if only_pages is not None and number not in only_pages:
                result.pages.append("")
                continue
            try:
                image = page.get_pixmap(dpi=resolution).tobytes("png")
                ocr_output = engine(image)
            except Exception:
                logger.exception("OCR failed on page %s", number + 1)
                result.pages.append("")
                continue
            result.pages.append(
                "\n".join(t for t in (getattr(ocr_output, "txts", None) or []) if t).strip()
            )
    finally:
        try:
            document.close()
        except Exception:
            pass

    result.duration_ms = int((time.time() - started) * 1000)
    return result
