"""
Per-criterion scoring against a rubric version.

This is the rubric->scoring bridge. The old `scoring_agent` scored five
hardcoded dimensions and read nothing from `rubric_weights`; here every
scored thing is a `RubricWeight` row, keyed by `criterion_key`, weighted by
`RubricWeight.weight`, and capped by `RubricWeight.max_score`. Change the
rubric and the score changes. That is the whole point of Phase B, and until
this module existed it did not hold.

The deterministic pass is the floor, and it is always computed:

    coverage  = how much of the criterion's term set the CV evidences,
                weighted by match strength (exact/equivalent = 1.0,
                adjacent = ADJACENT_CREDIT)
    outcome   = one of the client's five classifications
    confidence= how much the judgement itself can be trusted
    evidence  = quoted excerpts with page/section references

Confidence is deliberately *not* a restatement of the score. A CV that
plainly has nothing to do with the role scores 0 with HIGH confidence — the
absence is well evidenced. A two-line CV that failed extraction also scores
low, but with LOW confidence, because the score reflects a bad document
rather than a bad candidate. Collapsing those two into one number is what
makes AI screening indefensible, so they are kept apart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import skill_taxonomy
from app.core.eligibility_engine import _NEGATION_WINDOW, _NEGATION_RE
from app.db.models import (
    ConfidenceBand, CriterionOutcome, EvidenceMatchType, RequirementCategory,
    ScoringMethod,
)

# Coverage at or above this counts as a confirmed match.
CONFIRMED_THRESHOLD = 0.85
# Below this, nothing meaningful was demonstrated.
DEMONSTRATED_THRESHOLD = 0.15
# A BINARY criterion is met at or above this coverage.
BINARY_THRESHOLD = 0.7
# GRADED bands: (minimum coverage, score as a fraction of max_score).
GRADED_BANDS = ((CONFIRMED_THRESHOLD, 1.0), (0.45, 0.6), (DEMONSTRATED_THRESHOLD, 0.3))

# Overqualification (B07): coverage for a years-of-experience criterion stays
# at 1.0 up to this multiple of the requirement, then eases down to
# OVERQUALIFIED_FLOOR by OVERQUALIFIED_MAX_MULTIPLE. A Jr HSE Officer role
# asking for 2 years does not get a better candidate at 10 years than at 4 —
# past a point, a large surplus reads as flight-risk/cost-mismatch (bored,
# underpaid, likely to leave once something senior opens up), not a
# stronger fit. The floor keeps this a caution rather than a rejection: the
# candidate can still do the job, so the criterion never scores as low as a
# candidate who doesn't meet the requirement at all.
OVERQUALIFIED_START_MULTIPLE = 2.0
OVERQUALIFIED_MAX_MULTIPLE = 5.0
OVERQUALIFIED_FLOOR = 0.5

# How much an extracted token the taxonomy doesn't recognise counts towards
# coverage, relative to a known skill. Criterion labels are JD sentences, so
# term extraction always yields some grammar alongside the real requirement.
INCIDENTAL_TERM_WEIGHT = 0.35

# A CV shorter than this cannot support a confident judgement about anything.
THIN_DOCUMENT_CHARS = 600
# Text length at which the document is considered fully informative.
RICH_DOCUMENT_CHARS = 2500

CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.5

# Evidence excerpts kept per criterion. More than this is noise in the UI and
# bloats the evaluations table across 10,000 CVs.
MAX_EVIDENCE_PER_CRITERION = 3

# Which CV sections each requirement category is credible in. Matching is
# still done across the whole document — a skill demonstrated in an
# experience bullet counts — but a hit in the expected section raises
# confidence, and this is also what makes the "section reference" in the
# client's requirement meaningful.
_EXPECTED_SECTIONS: dict[RequirementCategory, tuple[str, ...]] = {
    RequirementCategory.SKILL: ("SKILLS", "EXPERIENCE", "PROJECTS"),
    RequirementCategory.EXPERIENCE: ("EXPERIENCE", "PROJECTS", "SUMMARY"),
    RequirementCategory.QUALIFICATION: ("EDUCATION",),
    RequirementCategory.CERTIFICATION: ("CERTIFICATIONS", "EDUCATION", "ACHIEVEMENTS"),
    RequirementCategory.RESPONSIBILITY: ("EXPERIENCE", "PROJECTS", "ACHIEVEMENTS"),
    RequirementCategory.INDUSTRY: ("EXPERIENCE", "SUMMARY", "PROJECTS"),
    RequirementCategory.FUNCTIONAL: ("EXPERIENCE", "SKILLS", "SUMMARY"),
    RequirementCategory.SENIORITY: ("EXPERIENCE", "SUMMARY", "HEADER"),
    RequirementCategory.LOCATION: ("HEADER", "SUMMARY", "OTHER"),
    RequirementCategory.ELIGIBILITY: ("HEADER", "OTHER", "SUMMARY"),
    RequirementCategory.DIFFERENTIATING: ("ACHIEVEMENTS", "PROJECTS", "EXPERIENCE"),
}


@dataclass
class EvidenceItem:
    excerpt: str
    page_number: int | None
    section: str
    char_start: int | None
    char_end: int | None
    match_type: EvidenceMatchType
    matched_term: str
    relevance: float


@dataclass
class CriterionResult:
    criterion_key: str
    label: str
    category: RequirementCategory
    weight: float
    max_score: float
    scoring_method: ScoringMethod
    rubric_weight_id: str | None

    coverage: float = 0.0
    deterministic_score: float = 0.0
    raw_score: float = 0.0
    weighted_score: float = 0.0
    outcome: CriterionOutcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
    confidence: float = 0.0
    confidence_band: ConfidenceBand = ConfidenceBand.LOW

    matched_terms: list[str] = field(default_factory=list)
    equivalent_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    rationale: str = ""
    display_order: int = 0
    llm_adjusted: bool = False


def band_for(confidence: float) -> ConfidenceBand:
    if confidence >= CONFIDENCE_HIGH:
        return ConfidenceBand.HIGH
    if confidence >= CONFIDENCE_MEDIUM:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def _richness(text: str) -> float:
    """0..1 measure of how much the document gives us to work with."""
    length = len(text or "")
    if length >= RICH_DOCUMENT_CHARS:
        return 1.0
    return round(max(0.0, length / RICH_DOCUMENT_CHARS), 3)


def _negated_at(text: str, position: int) -> bool:
    window = text[max(0, position - _NEGATION_WINDOW):position]
    return bool(_NEGATION_RE.search(window.split(",")[-1].split(".")[-1]))


def _required_years(label: str) -> float | None:
    match = re.search(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", label or "", re.IGNORECASE)
    return float(match.group(1)) if match else None


def _coverage_for_years(effective: float, required: float) -> tuple[float, bool]:
    """
    Coverage for a years-of-experience requirement, discounted once the
    candidate is far past it. Returns (coverage, overqualified).
    """
    if required <= 0:
        return 1.0, False
    ratio = effective / required
    if ratio <= OVERQUALIFIED_START_MULTIPLE:
        return min(1.0, ratio), False
    span = OVERQUALIFIED_MAX_MULTIPLE - OVERQUALIFIED_START_MULTIPLE
    progress = min(1.0, (ratio - OVERQUALIFIED_START_MULTIPLE) / span)
    coverage = 1.0 - progress * (1.0 - OVERQUALIFIED_FLOOR)
    return coverage, True


# ---------------------------------------------------------------------------
# Experience criteria get their own path
# ---------------------------------------------------------------------------

def _score_experience_criterion(weight, index, profile) -> tuple[float, str, list[str]]:
    """
    Score an EXPERIENCE criterion from the parsed timeline rather than by
    term matching. "8+ years in data engineering" is a quantity question, and
    counting keyword hits answers a different one.

    Returns (coverage, rationale, notes).
    """
    required = _required_years(weight.label)
    if required is None or required <= 0:
        return -1.0, "", []  # -1 signals "fall through to term matching"

    if profile is None or not getattr(profile, "timeline_found", False):
        claimed = getattr(profile, "claimed_years", None) if profile else None
        if claimed is None:
            return 0.0, (
                f"Requires {required:g} years; no dated employment history could be "
                "read from the CV, so the duration is unverified."
            ), ["experience_unverified"]
        coverage, overqualified = _coverage_for_years(claimed, required)
        rationale = (
            f"The CV states {claimed:g} years against a requirement of {required:g}. "
            "No dated timeline was parseable, so this rests on the candidate's own "
            "claim."
        )
        notes = ["experience_unverified"]
        if overqualified:
            notes.append("experience_overqualified")
            rationale += (
                f" At {claimed:g} years against a {required:g}-year requirement, this "
                "reads as overqualified; coverage is discounted rather than scored as "
                "an ideal fit."
            )
        return coverage, rationale, notes

    relevant = getattr(profile, "relevant_years", 0.0) or 0.0
    total = getattr(profile, "total_years", 0.0) or 0.0
    # Relevant years is the honest measure, but a candidate whose CV simply
    # doesn't name technologies per role should not be zeroed out, so total
    # years contributes at a discount.
    effective = max(relevant, 0.6 * total)
    coverage, overqualified = _coverage_for_years(effective, required)

    rationale = (
        f"Requires {required:g} years. The parsed timeline shows {total:g} years "
        f"total and {relevant:g} years relevant to this campaign's criteria"
    )
    notes: list[str] = []
    if overqualified:
        notes.append("experience_overqualified")
        rationale += (
            f"; at {effective:g} effective years against a {required:g}-year "
            "requirement, this reads as overqualified — well beyond what the role "
            "needs, scored as a caution (flight-risk/cost-mismatch) rather than a "
            "stronger match"
        )
    if getattr(profile, "is_stale", False):
        # Meeting the years bar with stale experience is not the same as
        # meeting it currently, so the score is discounted rather than the
        # fact being buried in a note.
        coverage *= 0.8
        months = getattr(profile, "months_since_last_role", None)
        rationale += f"; the most recent role ended about {months} months ago"
        notes.append("experience_stale")
    if getattr(profile, "continuity_ratio", 1.0) < 0.7:
        rationale += (
            f"; the timeline is discontinuous "
            f"(continuity {getattr(profile, 'continuity_ratio', 0):.2f})"
        )
        notes.append("experience_discontinuous")
    return coverage, rationale + ".", notes


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_criterion(weight, index, profile=None, order: int = 0) -> CriterionResult:
    """
    Score one `RubricWeight` against one candidate's `EvidenceIndex`.

    `weight` is a RubricWeight row (or anything with the same attributes);
    `profile` is the ExperienceProfile, needed only for EXPERIENCE criteria.
    """
    result = CriterionResult(
        criterion_key=weight.criterion_key,
        label=weight.label,
        category=weight.category,
        weight=float(weight.weight or 0.0),
        max_score=float(weight.max_score or 100.0),
        scoring_method=weight.scoring_method,
        rubric_weight_id=getattr(weight, "id", None),
        display_order=getattr(weight, "display_order", order) or order,
    )

    text = getattr(index, "text", "") or ""
    richness = _richness(text)
    thin_document = len(text) < THIN_DOCUMENT_CHARS

    if not text:
        result.outcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
        result.confidence = 0.1
        result.confidence_band = band_for(result.confidence)
        result.rationale = "No text could be extracted from the CV, so this criterion could not be assessed."
        return result

    expected_sections = _EXPECTED_SECTIONS.get(weight.category, ())
    notes: list[str] = []
    experience_rationale = ""

    # -- experience criteria -----------------------------------------------
    coverage = -1.0
    if weight.category == RequirementCategory.EXPERIENCE:
        coverage, experience_rationale, notes = _score_experience_criterion(
            weight, index, profile
        )

    # -- term matching -----------------------------------------------------
    terms = skill_taxonomy.extract_terms(weight.label, limit=8)
    matches: list[tuple[str, skill_taxonomy.TermMatch]] = []
    contradicted: list[str] = []

    for term in terms:
        match = skill_taxonomy.find_term(term, text)
        if match.found and match.char_start is not None and _negated_at(text, match.char_start):
            contradicted.append(term)
            # A negated mention is evidence *against*, not partial credit.
            matches.append((term, skill_taxonomy.TermMatch(term=term, kind="NONE", credit=0.0)))
            continue
        matches.append((term, match))

    # Terms are not equal. "PostgreSQL" is the criterion; "degree" and
    # "platform" are grammar that survived term extraction. Scoring them
    # 1:1 let filler words halve the coverage of a criterion the candidate
    # plainly met, so a term the taxonomy recognises carries full weight and
    # an incidental token carries less.
    if terms:
        term_weights = [
            1.0 if skill_taxonomy.is_known(term) else INCIDENTAL_TERM_WEIGHT
            for term, _ in matches
        ]
        weight_total = sum(term_weights) or 1.0
        term_coverage = sum(
            m.credit * tw for (_, m), tw in zip(matches, term_weights)
        ) / weight_total
    else:
        term_coverage = -1.0

    if coverage < 0:
        coverage = term_coverage

    if coverage < 0:
        # No years requirement and no minable terms — the criterion label is
        # too vague to check mechanically. Say so rather than scoring zero,
        # which would read as "the candidate lacks this".
        result.outcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
        result.confidence = 0.2
        result.confidence_band = band_for(result.confidence)
        result.rationale = (
            f"No checkable terms could be derived from '{weight.label}'. This "
            "criterion needs a more specific label or a manual assessment."
        )
        return result

    coverage = max(0.0, min(1.0, coverage))
    result.coverage = round(coverage, 3)

    # -- term bookkeeping and evidence -------------------------------------
    for term, match in matches:
        if match.kind == "EXACT":
            result.matched_terms.append(term)
        elif match.kind == "EQUIVALENT":
            result.matched_terms.append(term)
            result.equivalent_terms.append(f"{term} ~ {match.matched_surface}")
        elif match.kind == "ADJACENT":
            result.equivalent_terms.append(f"{term} ~ {match.matched_surface} (related)")
        else:
            result.missing_terms.append(term)

    section_hits = 0
    for term, match in sorted(matches, key=lambda pair: -pair[1].credit):
        if not match.found or match.char_start is None:
            continue
        if len(result.evidence) >= MAX_EVIDENCE_PER_CRITERION:
            break
        citation = index.cite(match.char_start, match.char_end)
        if expected_sections and citation.section in expected_sections:
            section_hits += 1
        result.evidence.append(EvidenceItem(
            excerpt=citation.excerpt,
            page_number=citation.page_number,
            section=citation.section,
            char_start=citation.char_start,
            char_end=citation.char_end,
            match_type=(
                EvidenceMatchType.EXACT if match.kind == "EXACT"
                else EvidenceMatchType.EQUIVALENT
            ),
            matched_term=match.matched_surface or term,
            relevance=round(match.credit, 3),
        ))

    # Contradictions are cited too — a recruiter needs to see the line that
    # says "no Kubernetes experience", not just a low score.
    for term in contradicted[:MAX_EVIDENCE_PER_CRITERION]:
        match = skill_taxonomy.find_term(term, text)
        if match.char_start is None:
            continue
        citation = index.cite(match.char_start, match.char_end)
        result.evidence.append(EvidenceItem(
            excerpt=citation.excerpt,
            page_number=citation.page_number,
            section=citation.section,
            char_start=citation.char_start,
            char_end=citation.char_end,
            match_type=EvidenceMatchType.CONTRADICTION,
            matched_term=term,
            relevance=1.0,
        ))

    # For an EXPERIENCE criterion scored off the timeline, cite the timeline.
    if weight.category == RequirementCategory.EXPERIENCE and profile is not None:
        for stint in getattr(profile, "stints", [])[-2:]:
            if len(result.evidence) >= MAX_EVIDENCE_PER_CRITERION + 1:
                break
            position = text.find(stint.text[:60]) if stint.text else -1
            if position < 0:
                continue
            citation = index.cite(position, position + min(len(stint.text), 60))
            result.evidence.append(EvidenceItem(
                excerpt=citation.excerpt,
                page_number=citation.page_number,
                section=citation.section,
                char_start=citation.char_start,
                char_end=citation.char_end,
                match_type=EvidenceMatchType.CONTEXT,
                matched_term=f"{stint.start.isoformat()}..{stint.end.isoformat()}",
                relevance=0.5,
            ))

    # -- outcome -----------------------------------------------------------
    # A criterion whose terms the taxonomy doesn't recognise at all ("must be
    # a good cultural fit") is not measurable by term matching. Scoring it
    # NOT_DEMONSTRATED would assert an absence we cannot actually establish,
    # which is precisely the "unsupported conclusion" the client wants
    # flagged — so it is reported as unmeasurable instead.
    unmeasurable = (
        weight.category != RequirementCategory.EXPERIENCE
        and bool(terms)
        and not any(skill_taxonomy.is_known(term) for term, _ in matches)
    )

    if contradicted and coverage < CONFIRMED_THRESHOLD:
        result.outcome = CriterionOutcome.CONTRADICTORY_EVIDENCE
    elif unmeasurable and coverage < CONFIRMED_THRESHOLD:
        result.outcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
    elif thin_document and coverage < CONFIRMED_THRESHOLD:
        # A near-empty CV cannot support "not demonstrated" — there was
        # nothing to demonstrate it in.
        result.outcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
    elif "experience_unverified" in notes and coverage < CONFIRMED_THRESHOLD:
        result.outcome = CriterionOutcome.INSUFFICIENT_EVIDENCE
    elif coverage >= CONFIRMED_THRESHOLD:
        result.outcome = CriterionOutcome.CONFIRMED_MATCH
    elif coverage >= DEMONSTRATED_THRESHOLD:
        result.outcome = CriterionOutcome.PARTIAL_MATCH
    else:
        result.outcome = CriterionOutcome.NOT_DEMONSTRATED

    # -- score -------------------------------------------------------------
    if weight.scoring_method == ScoringMethod.BINARY:
        fraction = 1.0 if coverage >= BINARY_THRESHOLD else 0.0
    elif weight.scoring_method == ScoringMethod.GRADED:
        fraction = 0.0
        for minimum, value in GRADED_BANDS:
            if coverage >= minimum:
                fraction = value
                break
    else:
        fraction = coverage

    result.deterministic_score = round(fraction * result.max_score, 2)
    result.raw_score = result.deterministic_score
    result.weighted_score = round(
        (result.raw_score / result.max_score if result.max_score else 0.0) * result.weight, 3
    )

    # -- confidence --------------------------------------------------------
    found_matches = [m for _, m in matches if m.found]
    strong = [m for m in found_matches if m.kind in ("EXACT", "EQUIVALENT")]

    if result.outcome in (CriterionOutcome.CONFIRMED_MATCH, CriterionOutcome.PARTIAL_MATCH):
        # Confidence in a positive finding rests on the quality of the hits.
        precision = len(strong) / len(found_matches) if found_matches else 0.0
        section_ratio = (section_hits / len(result.evidence)) if result.evidence else 0.0
        confidence = (
            0.35
            + 0.25 * precision
            + 0.20 * min(1.0, len(result.evidence) / 2.0)
            + 0.10 * richness
            + 0.10 * section_ratio
        )
    elif result.outcome == CriterionOutcome.NOT_DEMONSTRATED:
        # Confidence in an absence rests on how complete the document is —
        # a thorough CV that never mentions Kafka probably means it.
        has_section = any(index.has_section(s) for s in expected_sections) if expected_sections else False
        confidence = 0.40 + 0.40 * richness + (0.15 if has_section else 0.0)
    elif result.outcome == CriterionOutcome.CONTRADICTORY_EVIDENCE:
        confidence = 0.45 + 0.30 * richness
    else:  # INSUFFICIENT_EVIDENCE
        confidence = 0.15 + 0.25 * richness

    if "experience_unverified" in notes:
        confidence = min(confidence, 0.45)

    result.confidence = round(max(0.05, min(0.99, confidence)), 3)
    result.confidence_band = band_for(result.confidence)

    # -- rationale ---------------------------------------------------------
    parts: list[str] = []
    if experience_rationale:
        parts.append(experience_rationale)
    if result.matched_terms:
        parts.append(f"Evidenced: {', '.join(result.matched_terms[:6])}.")
    if result.equivalent_terms:
        parts.append(f"Matched by equivalence or adjacency: {', '.join(result.equivalent_terms[:4])}.")
    if result.missing_terms:
        parts.append(f"Not found in the CV: {', '.join(result.missing_terms[:6])}.")
    if contradicted:
        parts.append(
            f"The CV appears to contradict this criterion for: {', '.join(contradicted[:4])}."
        )
    if unmeasurable:
        parts.append(
            f"None of the terms in '{weight.label}' can be checked against a CV "
            "mechanically, so this criterion needs a manual assessment rather than "
            "a score."
        )
    if thin_document:
        parts.append(
            f"The extracted CV text is only {len(text)} characters, which limits how "
            "much can be concluded either way."
        )
    result.rationale = " ".join(parts).strip()
    return result
