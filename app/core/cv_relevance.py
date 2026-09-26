"""
Rank discovered CVs by how well they cover a campaign's active rubric terms,
so a recruiter pointed at a repository sees likely-relevant files first
instead of ticking through an unordered folder listing (`B03`).

Deterministic term coverage only, reusing `skill_taxonomy.find_term` — the
same matcher `criterion_scorer` uses for real evaluation, so a CV that would
score well against the rubric also ranks well here. This is not evaluation:
no per-criterion weighting, no outcome classification, no persistence — a
fast pre-import signal so the recruiter can skip the obviously irrelevant
files. Full scoring still runs on import, unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core import skill_taxonomy
from app.core.document_intake import DocumentRejected, extract_document

# A CV covering at least this share of the campaign's mined terms is flagged
# `recommended`. Coarser than criterion_scorer.BINARY_THRESHOLD (0.7) on
# purpose: that threshold is coverage of one criterion's own term set, while
# this is coverage across every criterion's terms at once — a strong CV
# rarely matches all of them.
RECOMMENDED_THRESHOLD = 0.4


@dataclass
class RelevanceScore:
    coverage: float
    matched_terms: list[str] = field(default_factory=list)


def terms_for_weights(weights) -> list[str]:
    """Union of terms mined from each active rubric weight's label."""
    terms: list[str] = []
    for weight in weights:
        for term in skill_taxonomy.extract_terms(weight.label, limit=6):
            if term not in terms:
                terms.append(term)
    return terms


def score_text(text: str, terms: list[str]) -> RelevanceScore:
    if not terms:
        return RelevanceScore(coverage=0.0)
    matched: list[str] = []
    credit_sum = 0.0
    for term in terms:
        match = skill_taxonomy.find_term(term, text)
        if match.credit > 0:
            matched.append(term)
            credit_sum += match.credit
    return RelevanceScore(coverage=credit_sum / len(terms), matched_terms=matched)


def score_file(path: Path, filename: str, terms: list[str]) -> RelevanceScore | None:
    """
    `None` means "could not be scored" (unsupported extension, corrupt file,
    no extractable text) — the caller must treat that CV as unranked, not as
    irrelevant; a folder full of scanned CVs with OCR unavailable should
    still list every file.
    """
    if not terms:
        return None
    try:
        extracted = extract_document(str(path), filename)
    except DocumentRejected:
        return None
    return score_text(extracted.text, terms)
