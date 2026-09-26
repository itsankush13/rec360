"""
Page- and section-aware index over a retained CV.

The client requires "evidence excerpts with CV page or section references".
Neither reference is available from `CandidateDocument.extracted_text` alone:
Phase C's PDF extractor joins page texts with newlines and throws the page
boundaries away, and `section_map` is populated by the spaCy-backed
`document_parser.segment_resume`, which is best-effort and returns None when
the model isn't installed.

So this module rebuilds both, deterministically:

  * Page boundaries are recovered by re-opening the retained file — which
    exists precisely because Phase C stopped deleting uploads. The
    reconstruction is verified against the stored text before being trusted;
    if the two disagree by so much as a character, page numbers are reported
    as None rather than guessed. A wrong page citation is worse than none.
  * Sections are found with a heading scan over the text itself, so a DOCX
    (which has no pages at all) still cites "EXPERIENCE" rather than nothing.

Nothing here calls a model. Two runs over the same document produce the same
citations, which is the point — evidence a client can check.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Canonical section names, mapped from the heading variants that appear in
# real CVs. Kept separate from document_intake._SECTION_HEADINGS: that set
# exists to stop name extraction running past the header block, and is
# deliberately narrow. This one has to classify.
_SECTION_ALIASES: dict[str, str] = {
    "summary": "SUMMARY", "professional summary": "SUMMARY",
    "executive summary": "SUMMARY", "profile": "SUMMARY",
    "professional profile": "SUMMARY", "about": "SUMMARY",
    "about me": "SUMMARY", "objective": "SUMMARY",
    "career objective": "SUMMARY", "career summary": "SUMMARY",
    "overview": "SUMMARY", "synopsis": "SUMMARY",

    "experience": "EXPERIENCE", "work experience": "EXPERIENCE",
    "professional experience": "EXPERIENCE", "work history": "EXPERIENCE",
    "employment": "EXPERIENCE", "employment history": "EXPERIENCE",
    "career history": "EXPERIENCE", "career": "EXPERIENCE",
    "relevant experience": "EXPERIENCE", "professional background": "EXPERIENCE",
    "work": "EXPERIENCE",

    "education": "EDUCATION", "academic": "EDUCATION",
    "academics": "EDUCATION", "academic background": "EDUCATION",
    "academic qualifications": "EDUCATION", "qualifications": "EDUCATION",
    "qualification": "EDUCATION", "educational qualifications": "EDUCATION",
    "education and training": "EDUCATION",

    "skills": "SKILLS", "technical skills": "SKILLS",
    "key skills": "SKILLS", "core skills": "SKILLS",
    "core competencies": "SKILLS", "competencies": "SKILLS",
    "technologies": "SKILLS", "technical proficiencies": "SKILLS",
    "technical expertise": "SKILLS", "areas of expertise": "SKILLS",
    "tools": "SKILLS", "tools and technologies": "SKILLS",
    "skill set": "SKILLS", "expertise": "SKILLS",

    "projects": "PROJECTS", "key projects": "PROJECTS",
    "project experience": "PROJECTS", "portfolio": "PROJECTS",
    "selected projects": "PROJECTS", "major projects": "PROJECTS",

    "certifications": "CERTIFICATIONS", "certification": "CERTIFICATIONS",
    "certificates": "CERTIFICATIONS", "licenses": "CERTIFICATIONS",
    "licenses and certifications": "CERTIFICATIONS",
    "professional certifications": "CERTIFICATIONS",
    "training": "CERTIFICATIONS", "courses": "CERTIFICATIONS",
    "training and certifications": "CERTIFICATIONS",

    "achievements": "ACHIEVEMENTS", "key achievements": "ACHIEVEMENTS",
    "accomplishments": "ACHIEVEMENTS", "awards": "ACHIEVEMENTS",
    "awards and recognition": "ACHIEVEMENTS", "honors": "ACHIEVEMENTS",
    "honours": "ACHIEVEMENTS", "recognition": "ACHIEVEMENTS",

    "publications": "PUBLICATIONS", "papers": "PUBLICATIONS",
    "research": "PUBLICATIONS", "patents": "PUBLICATIONS",

    "languages": "LANGUAGES", "languages known": "LANGUAGES",

    "interests": "OTHER", "hobbies": "OTHER",
    "hobbies and interests": "OTHER", "extracurricular": "OTHER",
    "activities": "OTHER", "volunteering": "OTHER",
    "volunteer experience": "OTHER", "references": "REFERENCES",
    "declaration": "OTHER", "personal details": "OTHER",
    "personal information": "OTHER", "additional information": "OTHER",
    "contact": "HEADER", "contact details": "HEADER",
    "contact information": "HEADER",
}

# The header block above the first recognised heading.
HEADER_SECTION = "HEADER"

_HEADING_MAX_LEN = 48
_TRIM_CHARS = " \t:-–—_*#•·>|=\u2022"

# Excerpt shaping. Long enough to be quotable evidence, short enough that the
# UI can show several without a wall of text.
EXCERPT_MAX_CHARS = 320
EXCERPT_CONTEXT = 90


@dataclass
class SectionSpan:
    name: str
    start: int
    end: int
    heading_text: str = ""


@dataclass
class Citation:
    """Where a character offset sits in the document, in human terms."""
    page_number: int | None
    section: str
    char_start: int
    char_end: int
    excerpt: str


@dataclass
class EvidenceIndex:
    text: str
    page_starts: list[int] = field(default_factory=list)  # char offset of each page
    sections: list[SectionSpan] = field(default_factory=list)
    page_count: int = 0
    pages_reliable: bool = False
    document_id: str | None = None

    # -- lookups -----------------------------------------------------------

    def page_for(self, offset: int) -> int | None:
        """1-based page number containing `offset`, or None if unknown."""
        if not self.pages_reliable or not self.page_starts:
            return None
        page = 0
        for index, start in enumerate(self.page_starts):
            if offset >= start:
                page = index
            else:
                break
        return page + 1

    def section_for(self, offset: int) -> str:
        for span in self.sections:
            if span.start <= offset < span.end:
                return span.name
        return HEADER_SECTION if self.sections else ""

    def section_text(self, name: str) -> str:
        """All text under a canonical section name, concatenated."""
        parts = [
            self.text[span.start:span.end]
            for span in self.sections
            if span.name == name.upper()
        ]
        return "\n".join(parts)

    def has_section(self, name: str) -> bool:
        return any(span.name == name.upper() for span in self.sections)

    def section_names(self) -> list[str]:
        seen: list[str] = []
        for span in self.sections:
            if span.name not in seen:
                seen.append(span.name)
        return seen

    # -- excerpting --------------------------------------------------------

    def excerpt_at(self, start: int, end: int) -> str:
        """
        Quote around [start, end), snapped outwards to line boundaries so the
        excerpt is a readable fragment rather than a term sliced mid-sentence.
        """
        if not self.text:
            return ""
        start = max(0, min(start, len(self.text)))
        end = max(start, min(end, len(self.text)))

        # Anchor on the line the match sits in — that line is the evidence.
        line_start = self.text.rfind("\n", 0, start) + 1
        line_end = self.text.find("\n", end)
        line_end = len(self.text) if line_end < 0 else line_end
        left, right = line_start, line_end

        # A bare "Postgres" on its own line is not quotable on its own, so
        # neighbouring lines are pulled in only until the excerpt reads as a
        # fragment. Forward first: the detail usually follows the term.
        while right - left < EXCERPT_CONTEXT and right < len(self.text):
            nxt = self.text.find("\n", right + 1)
            nxt = len(self.text) if nxt < 0 else nxt
            if nxt - left > EXCERPT_MAX_CHARS:
                break
            right = nxt
        while right - left < EXCERPT_CONTEXT and left > 0:
            prev = self.text.rfind("\n", 0, left - 1) + 1
            if right - prev > EXCERPT_MAX_CHARS:
                break
            left = prev

        excerpt = re.sub(r"[ \t]+", " ", self.text[left:right]).strip()
        excerpt = re.sub(r"\n{2,}", "\n", excerpt)
        if len(excerpt) > EXCERPT_MAX_CHARS:
            excerpt = excerpt[:EXCERPT_MAX_CHARS].rstrip() + "…"
        return excerpt

    def cite(self, start: int, end: int) -> Citation:
        return Citation(
            page_number=self.page_for(start),
            section=self.section_for(start),
            char_start=start,
            char_end=end,
            excerpt=self.excerpt_at(start, end),
        )


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def _canonical_heading(line: str) -> str | None:
    cleaned = line.strip().strip(_TRIM_CHARS)
    if not cleaned or len(cleaned) > _HEADING_MAX_LEN:
        return None
    lowered = re.sub(r"\s+", " ", cleaned).casefold()
    direct = _SECTION_ALIASES.get(lowered)
    if direct:
        return direct
    # "EXPERIENCE (8 YEARS)" / "Technical Skills:" style headings.
    stripped = re.sub(r"\(.*?\)", "", lowered).strip(_TRIM_CHARS)
    return _SECTION_ALIASES.get(stripped)


def find_sections(text: str) -> list[SectionSpan]:
    """
    Split `text` into canonical sections by scanning for heading lines.

    A heading is a short line that matches a known alias. Bullet lines are
    skipped so that a bullet reading "Skills: Python, AWS" inside an
    experience entry does not open a bogus SKILLS section.
    """
    if not text:
        return []

    boundaries: list[tuple[int, int, str, str]] = []  # start, heading_end, name, raw
    offset = 0
    for line in text.splitlines(keepends=True):
        bare = line.strip()
        # A real heading sits on its own line. Bullets and long prose don't.
        if bare and not bare.startswith(("-", "•", "*", "·", "◦")):
            name = _canonical_heading(line)
            if name:
                boundaries.append((offset, offset + len(line), name, bare))
        offset += len(line)

    if not boundaries:
        return [SectionSpan(name=HEADER_SECTION, start=0, end=len(text))]

    spans: list[SectionSpan] = []
    if boundaries[0][0] > 0:
        spans.append(SectionSpan(name=HEADER_SECTION, start=0, end=boundaries[0][0]))
    for index, (start, heading_end, name, raw) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        spans.append(SectionSpan(name=name, start=start, end=end, heading_text=raw))
    return spans


# ---------------------------------------------------------------------------
# Page recovery
# ---------------------------------------------------------------------------

def _pdf_page_starts(data: bytes, expected_text: str) -> tuple[list[int], int, bool]:
    """
    Recover per-page character offsets by re-extracting the PDF exactly the
    way `document_intake._extract_pdf` did, then checking the result matches
    the text on file.

    Phase C built the stored text as `"\\n".join(page_texts).strip()`. The
    leading strip shifts every offset, so it is measured rather than assumed.
    Returns (page_starts, page_count, reliable).
    """
    try:
        import pymupdf
    except Exception:
        return [], 0, False

    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                return [], 0, False
            pages = [page.get_text() for page in document]
            page_count = document.page_count
    except Exception as exc:
        logger.debug("Page recovery failed: %s", exc)
        return [], 0, False

    raw = "\n".join(pages)
    lead = len(raw) - len(raw.lstrip())
    rebuilt = raw.strip()

    starts: list[int] = []
    cursor = 0
    for page_text in pages:
        starts.append(max(0, cursor - lead))
        cursor += len(page_text) + 1  # the "\n" the join inserted

    # Only trust the mapping if the reconstruction is byte-identical to what
    # Phase C stored. Anything else means the extractor or the file changed,
    # and a page citation would be pointing at the wrong page.
    reliable = rebuilt == (expected_text or "")
    if not reliable:
        logger.debug(
            "Page offsets not trusted: rebuilt %d chars vs stored %d",
            len(rebuilt), len(expected_text or ""),
        )
    return starts, page_count, reliable


def build_index(document, *, load_file: bool = True) -> EvidenceIndex:
    """
    Build an index for a `CandidateDocument`.

    `load_file=False` skips re-reading the stored PDF, which is what the
    experience and criterion engines want when they only need sections —
    it keeps the hot path off the filesystem.
    """
    text = getattr(document, "extracted_text", "") or ""
    index = EvidenceIndex(
        text=text,
        sections=find_sections(text),
        page_count=getattr(document, "page_count", 0) or 0,
        document_id=getattr(document, "id", None),
    )

    extension = (getattr(document, "extension", "") or "").lower()
    storage_path = getattr(document, "storage_path", "") or ""
    if not load_file or extension != ".pdf" or not storage_path:
        # DOCX has no page concept in Phase C's extractor (page_count is 0),
        # so section references are the only honest citation available.
        return index

    try:
        from app.core import storage
        data = storage.read(storage_path)
    except Exception as exc:
        logger.debug("Retained document unreadable (%s); citing sections only", exc)
        return index

    starts, page_count, reliable = _pdf_page_starts(data, text)
    index.page_starts = starts
    index.pages_reliable = reliable
    if page_count:
        index.page_count = page_count
    return index
