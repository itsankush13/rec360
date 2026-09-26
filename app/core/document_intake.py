"""
File validation and identity extraction.

Everything here is deterministic and LLM-free on purpose. Phase C's job is to
decide whether a file is processable, get its text out, and work out who it
belongs to well enough to spot duplicates. Semantic understanding — skills,
experience, scoring — stays in the existing agents and runs in Phase D.

That separation matters for two reasons: the exception statuses the upload
screen shows (corrupt, password-protected, unsupported) must not depend on an
LLM being reachable, and these functions need to run 10,000 times a month
without a token bill.

PyMuPDF and python-docx are imported lazily inside the functions. Importing
app.utils.document_parser at module scope would pull in spaCy and its model,
which costs seconds of startup and is not needed to validate a file.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.db.models import JobErrorCode

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx"}

# Defaults; the service reads overrides from the environment.
DEFAULT_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
MIN_TEXT_CHARS = 120                   # below this it's almost certainly a scan


class DocumentRejected(Exception):
    """A file cannot be processed. Carries the code the UI groups exceptions by."""

    def __init__(self, code: JobErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# Where a document's text came from. Recorded because text recovered from an
# image is not as trustworthy as text read from a real text layer, and the
# assessment has to know the difference — see app/core/document_quality.py.
TEXT_SOURCE_EXTRACTED = "extracted"
TEXT_SOURCE_OCR = "ocr"
TEXT_SOURCE_MIXED = "mixed"


@dataclass
class ExtractedDocument:
    text: str = ""
    page_count: int = 0
    section_map: dict | None = None
    text_source: str = TEXT_SOURCE_EXTRACTED
    # Pages that yielded any text at all, by whatever means.
    pages_with_text: int = 0
    # Of those, how many were read as images.
    ocr_pages: int = 0
    # Per-page text, kept in memory only. Not persisted: the page map exists
    # so the OCR fallback can fill in the pages that came back blank, and so
    # evidence citation keeps its page numbers.
    pages: list[str] = field(default_factory=list)
    # Zero-based numbers of pages that hold an image and no text. A page that
    # is simply empty is not in here: there is nothing on it to recognise,
    # and OCR costs seconds a page, so a trailing blank page must not slow
    # down every CV in the batch.
    pages_needing_ocr: list[int] = field(default_factory=list)
    # Below MIN_TEXT_CHARS even after OCR was tried. This no longer blocks
    # the file — the caller still screens it on whatever text exists and
    # flags it for a person to also read the original — but the pipeline
    # still needs to know the text is too thin to trust on its own.
    low_text: bool = False


@dataclass
class Identity:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def has_strong_identity(self) -> bool:
        """Email or phone — something that can actually key a duplicate check."""
        return bool(self.email or self.phone)

    @property
    def is_empty(self) -> bool:
        return not (self.email or self.phone or self.full_name)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_upload(filename: str, data: bytes, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Cheap checks that need no parsing. Raises DocumentRejected."""
    extension = normalize_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentRejected(
            JobErrorCode.UNSUPPORTED_FORMAT,
            f"'{extension or filename}' is not a supported CV format. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    if not data:
        raise DocumentRejected(JobErrorCode.EMPTY_FILE, "File is empty (0 bytes).")
    if len(data) > max_bytes:
        raise DocumentRejected(
            JobErrorCode.FILE_TOO_LARGE,
            f"File is {len(data) / 1_048_576:.1f} MB, above the "
            f"{max_bytes / 1_048_576:.0f} MB limit.",
        )


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_pdf(path) -> ExtractedDocument:
    import pymupdf

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.CORRUPT_FILE, f"PDF could not be opened: {exc}"
        ) from exc

    try:
        # needs_pass is the reliable signal. An encrypted PDF opens fine and
        # then yields empty pages, which would otherwise look like a scan.
        if document.needs_pass:
            raise DocumentRejected(
                JobErrorCode.PASSWORD_PROTECTED,
                "PDF is password-protected and cannot be read.",
            )
        pages = []
        needs_ocr = []
        for number, page in enumerate(document):
            text = page.get_text()
            pages.append(text)
            if not text.strip():
                try:
                    has_image = bool(page.get_images())
                except Exception:
                    has_image = False
                if has_image:
                    needs_ocr.append(number)
        return ExtractedDocument(
            text="\n".join(pages).strip(),
            page_count=document.page_count,
            pages_with_text=sum(1 for page in pages if page.strip()),
            pages=pages,
            pages_needing_ocr=needs_ocr,
        )
    except DocumentRejected:
        raise
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.EXTRACTION_FAILED, f"PDF text extraction failed: {exc}"
        ) from exc
    finally:
        document.close()


def _extract_docx(path) -> ExtractedDocument:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(str(path))
    except PackageNotFoundError as exc:
        # python-docx raises the same error for a corrupt zip and for an
        # encrypted OOXML file, so the two are not distinguishable here.
        raise DocumentRejected(
            JobErrorCode.CORRUPT_FILE,
            "DOCX could not be opened — the file is corrupt, password-protected, "
            "or not a valid Word document.",
        ) from exc
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.CORRUPT_FILE, f"DOCX could not be opened: {exc}"
        ) from exc

    try:
        paragraphs = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                paragraphs.extend(cell.text for cell in row.cells)
        text = "\n".join(paragraphs).strip()
        return ExtractedDocument(
            text=text, page_count=0, pages_with_text=1 if text else 0,
        )
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.EXTRACTION_FAILED, f"DOCX text extraction failed: {exc}"
        ) from exc


def _extract_pptx(path) -> ExtractedDocument:
    """
    Mirrors _extract_docx: same return shape, same error handling. A slide
    deck has no notion of a page, so slide N is mapped to page N, one-based,
    so evidence citation keeps working exactly as it does for PDF and DOCX.
    """
    import pptx
    from pptx.exc import PackageNotFoundError

    try:
        presentation = pptx.Presentation(str(path))
    except PackageNotFoundError as exc:
        raise DocumentRejected(
            JobErrorCode.CORRUPT_FILE,
            "PPTX could not be opened — the file is corrupt, password-protected, "
            "or not a valid PowerPoint document.",
        ) from exc
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.CORRUPT_FILE, f"PPTX could not be opened: {exc}"
        ) from exc

    try:
        pages = []
        for slide in presentation.slides:
            lines = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    lines.append(shape.text_frame.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        lines.extend(cell.text for cell in row.cells)
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text
                if notes_text:
                    lines.append(notes_text)
            pages.append("\n".join(lines).strip())
        text = "\n".join(pages).strip()
        return ExtractedDocument(
            text=text,
            page_count=len(pages),
            pages_with_text=sum(1 for page in pages if page.strip()),
            pages=pages,
        )
    except DocumentRejected:
        raise
    except Exception as exc:
        raise DocumentRejected(
            JobErrorCode.EXTRACTION_FAILED, f"PPTX text extraction failed: {exc}"
        ) from exc


def _recover_with_ocr(path, extracted: ExtractedDocument) -> ExtractedDocument:
    """
    Read the pages that came back blank as images.

    Only the blank pages: a page with a real text layer is always read from
    it, because that text is exact and OCR text is an approximation. A CV
    with a scanned certificate stapled to the back therefore keeps a perfect
    reading of its first pages and gains an approximate reading of the last.
    """
    from app.core import ocr

    if not ocr.enabled():
        return extracted

    recovered = ocr.read_pdf(
        path,
        only_pages=set(extracted.pages_needing_ocr) or None,
    )
    if not recovered.pages_with_text:
        return extracted

    native = extracted.pages or []
    merged: list[str] = []
    for number in range(max(len(native), len(recovered.pages))):
        from_text = native[number] if number < len(native) else ""
        if from_text.strip():
            merged.append(from_text)
            continue
        merged.append(recovered.pages[number] if number < len(recovered.pages) else "")

    ocr_pages = sum(
        1 for number, page in enumerate(merged)
        if page.strip() and not (number < len(native) and native[number].strip())
    )
    if not ocr_pages:
        return extracted

    pages_with_text = sum(1 for page in merged if page.strip())
    return ExtractedDocument(
        text="\n".join(page for page in merged if page).strip(),
        page_count=extracted.page_count,
        section_map=extracted.section_map,
        text_source=(
            TEXT_SOURCE_MIXED if ocr_pages < pages_with_text else TEXT_SOURCE_OCR
        ),
        pages_with_text=pages_with_text,
        ocr_pages=ocr_pages,
        pages=merged,
    )


def extract_document(path, filename: str) -> ExtractedDocument:
    extension = normalize_extension(filename)
    if extension == ".pdf":
        extracted = _extract_pdf(path)
        # Two cases reach OCR: a PDF that is images throughout, and one whose
        # text pages are fine but which has a scanned page stapled to it —
        # a certificate, or a signed reference. This is the one place OCR
        # belongs: the document is already stored, so a failure here is still
        # retryable, and everything downstream is unchanged.
        if len(extracted.text) < MIN_TEXT_CHARS or extracted.pages_needing_ocr:
            extracted = _recover_with_ocr(path, extracted)
    elif extension in (".docx", ".doc"):
        extracted = _extract_docx(path)
    elif extension == ".pptx":
        extracted = _extract_pptx(path)
    elif extension == ".ppt":
        # The old binary PowerPoint format. python-pptx cannot read it, so it
        # must keep failing — but the message must point at the format that
        # does work, not just say no.
        raise DocumentRejected(
            JobErrorCode.UNSUPPORTED_FORMAT,
            "'.ppt' is not supported. Save the file as '.pptx' and upload that instead.",
        )
    else:
        raise DocumentRejected(
            JobErrorCode.UNSUPPORTED_FORMAT, f"Unsupported extension '{extension}'."
        )

    if len(extracted.text) < MIN_TEXT_CHARS:
        # A photographed or scanned CV that OCR couldn't (fully) recover.
        # This used to hold the file out of the batch entirely; now it is
        # screened on whatever text is available, flagged for a person to
        # also read the original — see process_job's low_text handling.
        extracted.low_text = True
    return extracted


def segment(text: str) -> dict | None:
    """
    Reuse the existing section segmenter. Best-effort: if spaCy or the model
    isn't installed, processing must still succeed without a section map.
    """
    try:
        from app.utils.document_parser import segment_resume
    except Exception:
        return None
    try:
        return segment_resume(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Identity extraction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Deliberately conservative: 10-15 digits with common separators and an
# optional country code. A loose pattern matches years, PIN codes and postal
# codes, which would then key false duplicates.
_PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.\-]?)?(?:\(?\d{2,5}\)?[\s.\-]?){2,4}\d{2,4}")

_NAME_STOPWORDS = {
    "curriculum", "vitae", "resume", "cv", "profile", "summary", "objective",
    "contact", "details", "personal", "information", "confidential",
}

# A name only ever appears in the header block, above the first section
# heading. Scanning past one is how "Python, AWS, PostgreSQL, Docker" got
# picked up as a candidate name from a SKILLS line.
_SECTION_HEADINGS = {
    "summary", "objective", "profile", "about",
    "experience", "work history", "employment", "career",
    "education", "academic", "qualifications", "qualification",
    "skills", "technical skills", "competencies", "technologies",
    "projects", "portfolio", "certifications", "certificates",
    "achievements", "awards", "languages", "interests", "references",
    "declaration", "publications", "training", "courses",
}


def _is_section_heading(line: str) -> bool:
    cleaned = line.strip().strip(":-–—_* ").lower()
    return len(cleaned) <= 40 and cleaned in _SECTION_HEADINGS


# A CV header commonly packs name, location, email and phone onto one line,
# joined by one of these. Split on them before testing for a name so the
# email/phone/location neighbours don't sink the whole line.
_NAME_FIELD_SEPARATOR_RE = re.compile(r"[—–|•]")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """
    Digits only, last 10 kept. Country-code and formatting variants of the
    same Indian mobile number ("+91 98765 43210", "098765-43210") must collide
    or duplicate detection is useless in practice.
    """
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else ""


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _looks_like_name(line: str) -> bool:
    stripped = line.strip()
    if not (3 <= len(stripped) <= 60):
        return False
    if any(char.isdigit() for char in stripped) or "@" in stripped:
        return False
    # A comma-separated list is not a name. One comma is allowed for the
    # "Menon, Priya" surname-first convention; two or more means a list.
    if stripped.count(",") >= 2:
        return False
    if any(char in stripped for char in "|/\\•\t"):
        return False
    words = stripped.split()
    if not (2 <= len(words) <= 4):
        return False
    if any(word.lower().strip(":,.") in _NAME_STOPWORDS for word in words):
        return False
    # Accept Title Case or ALL CAPS, both common in CV headers.
    return all(word[0].isalpha() and (word[0].isupper() or word.isupper()) for word in words)


def extract_identity(text: str) -> Identity:
    identity = Identity()

    email_match = _EMAIL_RE.search(text)
    if email_match:
        identity.email = email_match.group(0).strip()
    else:
        identity.warnings.append("No email address found in the document.")

    for candidate in _PHONE_RE.finditer(text):
        normalized = normalize_phone(candidate.group(0))
        if normalized:
            identity.phone = candidate.group(0).strip()
            break
    if not identity.phone:
        identity.warnings.append("No phone number found in the document.")

    # Names live in the header block: the first few lines, and always above
    # the first section heading. Scanning further picks up employer names,
    # university names, and comma-separated skill lists.
    for line in [ln for ln in text.splitlines() if ln.strip()][:12]:
        if _is_section_heading(line):
            break
        for fragment in _NAME_FIELD_SEPARATOR_RE.split(line):
            if _looks_like_name(fragment):
                identity.full_name = " ".join(fragment.strip().split())
                break
        if identity.full_name:
            break
    if not identity.full_name:
        identity.warnings.append("Candidate name could not be determined from the document.")

    return identity
