"""
Deterministic eligibility engine.

Phase B can build, validate, approve and lock disqualification rules, and
until now nothing evaluated them — a `HARD_FAIL` rule failed nobody. This
module is the engine.

Two properties matter more than anything else here:

1. **It runs outside the LLM path.** It takes structured facts (the parsed
   experience timeline, taxonomy term matches, criterion scores) and applies
   the rules arithmetically. The model is not consulted, is not passed the
   rules, and its criterion adjustments are applied *before* this runs so
   that `MIN_CRITERION_SCORE` sees the final number — but it cannot reach
   the verdict itself. A `DISQUALIFIED` result cannot be argued out of by a
   high AI score.

2. **It never guesses.** When a fact cannot be established from the CV — a
   years-of-experience rule against a CV with no parseable dates, a location
   rule against a CV with no location — the finding is marked
   `indeterminate` and the candidate goes to REVIEW_REQUIRED, not
   DISQUALIFIED. Silently passing an unverifiable mandatory requirement
   would let candidates through on missing data; silently failing them would
   reject people for a bad PDF. Neither is acceptable, so a human decides.

A rule states the **failure** condition, matching how Phase B seeds them:
`MIN_YEARS_EXPERIENCE` with `operator=LT, threshold=8` means "fails if the
candidate has fewer than 8 years". `triggered=True` therefore means the
candidate failed that rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import skill_taxonomy
from app.db.models import EligibilityStatus, RuleOperator, RuleSeverity, RuleType

# Sections a certification claim is credible in. A certification named in a
# SUMMARY line ("working towards CISSP") is not evidence of holding it.
_CERT_SECTIONS = ("CERTIFICATIONS", "EDUCATION", "ACHIEVEMENTS", "SKILLS")
_QUAL_SECTIONS = ("EDUCATION", "CERTIFICATIONS", "HEADER")

# Phrases that negate a nearby term. "Familiar with Kubernetes" is not the
# same claim as "no Kubernetes experience", and a bare term match cannot
# tell them apart.
_NEGATION_RE = re.compile(
    r"\b(no|not|never|without|lack(?:ing|s)?|nil|none|zero|minimal|"
    r"limited|basic|beginner|learning|studying|pursuing|towards|"
    r"in\s+progress|expected|aspiring|willing\s+to\s+learn)\b",
    re.IGNORECASE,
)
_NEGATION_WINDOW = 60


@dataclass
class CandidateFacts:
    """
    Everything the engine is allowed to reason from. Assembled by the
    evaluation service; deliberately a plain data bundle so the engine has no
    database or model dependency and is trivially unit-testable.
    """
    text: str = ""
    index: object | None = None                       # EvidenceIndex
    experience: object | None = None                  # ExperienceProfile
    criterion_scores: dict[str, float] = field(default_factory=dict)
    criterion_keys_by_requirement: dict[str, str] = field(default_factory=dict)
    candidate_location: str = ""
    campaign_location: str = ""


@dataclass
class Finding:
    code: str
    label: str
    rule_id: str | None
    rule_type: RuleType
    operator: RuleOperator
    threshold: float | None
    severity: RuleSeverity
    triggered: bool
    indeterminate: bool
    observed_value: str
    message: str
    display_order: int = 0


@dataclass
class EligibilityOutcome:
    status: EligibilityStatus
    findings: list[Finding] = field(default_factory=list)

    @property
    def hard_failures(self) -> list[Finding]:
        return [
            f for f in self.findings
            if f.triggered and not f.indeterminate and f.severity == RuleSeverity.HARD_FAIL
        ]

    @property
    def review_items(self) -> list[Finding]:
        return [
            f for f in self.findings
            if f.indeterminate or (f.triggered and f.severity == RuleSeverity.REVIEW_REQUIRED)
        ]

    @property
    def reasons(self) -> list[str]:
        return [f.message for f in self.findings if f.triggered or f.indeterminate]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compare(observed: float, operator: RuleOperator, threshold: float | None) -> bool:
    """Evaluate the failure condition. True means the rule fired."""
    if threshold is None:
        return False
    if operator == RuleOperator.LT:
        return observed < threshold
    if operator == RuleOperator.LTE:
        return observed <= threshold
    if operator == RuleOperator.GT:
        return observed > threshold
    if operator == RuleOperator.GTE:
        return observed >= threshold
    if operator == RuleOperator.EQ:
        return abs(observed - threshold) < 1e-9
    if operator == RuleOperator.NEQ:
        return abs(observed - threshold) >= 1e-9
    return False


def _rule_terms(rule) -> list[str]:
    """
    What this rule is looking for.

    `value` is authoritative when set. Phase B's seeding leaves it empty and
    puts the requirement sentence in `label`, so the terms are mined from the
    label in that case.
    """
    explicit = (getattr(rule, "value", "") or "").strip()
    if explicit:
        parts = [p.strip() for p in re.split(r"[,;/|]| or ", explicit) if p.strip()]
        return parts or [explicit]

    params = getattr(rule, "params", None) or {}
    for key in ("terms", "skills", "values", "any_of"):
        candidate = params.get(key)
        if isinstance(candidate, list) and candidate:
            return [str(c) for c in candidate if str(c).strip()]
        if isinstance(candidate, str) and candidate.strip():
            return [candidate.strip()]

    return skill_taxonomy.extract_terms(getattr(rule, "label", "") or "", limit=6)


def _is_negated(text: str, position: int) -> bool:
    """True when a negation sits close before the match."""
    window = text[max(0, position - _NEGATION_WINDOW):position]
    # Only the tail matters — a negation two clauses back is unrelated.
    return bool(_NEGATION_RE.search(window.split(",")[-1].split(".")[-1]))


def _find_any(terms: list[str], haystack: str) -> tuple[bool, str, str]:
    """
    Look for any of `terms` in `haystack`.
    Returns (found, matched_term, kind).
    """
    adjacent_hit: tuple[str, str] | None = None
    for term in terms:
        match = skill_taxonomy.find_term(term, haystack)
        if not match.found:
            continue
        if match.char_start is not None and _is_negated(haystack, match.char_start):
            continue
        if match.kind == "ADJACENT":
            # Remember it, but keep looking for something stronger. An
            # adjacent skill does not satisfy a mandatory requirement.
            adjacent_hit = adjacent_hit or (term, match.kind)
            continue
        return True, term, match.kind
    if adjacent_hit:
        return False, adjacent_hit[0], adjacent_hit[1]
    return False, "", "NONE"


def _scoped_text(facts: CandidateFacts, sections: tuple[str, ...]) -> str:
    """
    Text from the named sections, falling back to the whole document when
    none of them were detected — a CV with no headings should still be
    checkable.
    """
    index = facts.index
    if index is None:
        return facts.text
    parts = [index.section_text(name) for name in sections]
    scoped = "\n".join(p for p in parts if p).strip()
    return scoped or facts.text


def _years_for(facts: CandidateFacts, rule) -> tuple[float | None, str]:
    """
    The years figure a MIN_YEARS_EXPERIENCE rule should be checked against.

    Relevant years is used when the rule names a domain and the timeline
    supports it; otherwise total years. Returns (value, description) with
    value None when nothing can be established.
    """
    profile = facts.experience
    if profile is None:
        return None, "no experience profile"

    params = getattr(rule, "params", None) or {}
    basis = str(params.get("basis", "")).lower()
    if basis == "relevant":
        return getattr(profile, "relevant_years", 0.0), "relevant years"
    if basis == "total":
        return getattr(profile, "total_years", 0.0), "total years"

    if not getattr(profile, "timeline_found", False):
        claimed = getattr(profile, "claimed_years", None)
        if claimed is None:
            return None, "no dated employment history and no stated total"
        # A self-reported figure is usable but must not read as verified.
        return float(claimed), "candidate's own stated total (unverified)"

    return getattr(profile, "total_years", 0.0), "total years from parsed timeline"


# ---------------------------------------------------------------------------
# Per-rule-type evaluation
# ---------------------------------------------------------------------------

def _eval_min_years(facts: CandidateFacts, rule) -> tuple[bool, bool, str, str]:
    """Returns (triggered, indeterminate, observed, message)."""
    threshold = getattr(rule, "threshold", None)
    if threshold is None:
        return False, True, "", (
            f"'{rule.label}' requires a minimum number of years but the rule has "
            "no threshold set, so it could not be checked."
        )

    years, basis = _years_for(facts, rule)
    if years is None:
        return False, True, "", (
            f"Years of experience could not be established from the CV "
            f"({basis}), so the {threshold:g}-year requirement could not be verified."
        )

    triggered = _compare(years, rule.operator, threshold)
    observed = f"{years:g} years ({basis})"
    if triggered:
        message = (
            f"Has {years:g} years of experience against a required minimum of "
            f"{threshold:g}."
        )
    else:
        message = f"Meets the {threshold:g}-year minimum with {years:g} years."
    # An unverified self-report should not hard-fail or hard-pass silently.
    if "unverified" in basis:
        return triggered, True, observed, message + (
            " This is based on the candidate's own stated figure; no dated "
            "employment history could be read from the CV."
        )
    return triggered, False, observed, message


def _eval_term_presence(
    facts: CandidateFacts, rule, sections: tuple[str, ...], noun: str
) -> tuple[bool, bool, str, str]:
    terms = _rule_terms(rule)
    if not terms:
        return False, True, "", (
            f"'{rule.label}' could not be checked: no {noun} term could be "
            "derived from the rule. Set the rule's 'value' field explicitly."
        )

    haystack = _scoped_text(facts, sections)
    found, matched, kind = _find_any(terms, haystack)

    # MISSING means "fails when absent"; PRESENT means "fails when present"
    # (an exclusion rule, e.g. a competitor non-compete).
    if rule.operator == RuleOperator.PRESENT:
        triggered = found
    else:
        triggered = not found

    if found and kind == "EQUIVALENT":
        observed = f"found '{matched}' (matched via an equivalent term)"
    elif found:
        observed = f"found '{matched}'"
    elif kind == "ADJACENT":
        observed = f"only a related {noun} was found ('{matched}'), not the one required"
    else:
        observed = f"no mention of {', '.join(terms[:4])}"

    if triggered:
        message = f"Required {noun} not evidenced in the CV: {rule.label} — {observed}."
    else:
        message = f"{noun.capitalize()} requirement satisfied: {observed}."
    return triggered, False, observed, message


def _eval_location(facts: CandidateFacts, rule) -> tuple[bool, bool, str, str]:
    target = (getattr(rule, "value", "") or facts.campaign_location or "").strip()
    if not target:
        target_terms = skill_taxonomy.extract_terms(rule.label, limit=4)
    else:
        target_terms = [target]

    if not target_terms:
        return False, True, "", (
            f"'{rule.label}' could not be checked: no target location is set on "
            "the rule or the campaign."
        )

    candidate_location = (facts.candidate_location or "").strip()
    haystack = "\n".join(p for p in (candidate_location, facts.text) if p)
    if not haystack.strip():
        return False, True, "", (
            "No location information could be read from the CV, so the location "
            "requirement could not be verified."
        )

    found, matched, _ = _find_any(target_terms, haystack)
    if not found:
        # Location is genuinely hard to establish from a CV: a candidate may
        # be willing to relocate and simply not say so. Flag, never auto-fail.
        return False, True, candidate_location or "not stated", (
            f"Could not confirm the location requirement ({', '.join(target_terms[:3])}). "
            f"CV location reads as '{candidate_location or 'not stated'}'. "
            "Confirm with the candidate, including willingness to relocate."
        )
    return False, False, matched, f"Location requirement satisfied: '{matched}' found."


def _eval_min_criterion_score(facts: CandidateFacts, rule) -> tuple[bool, bool, str, str]:
    threshold = getattr(rule, "threshold", None)
    if threshold is None:
        return False, True, "", (
            f"'{rule.label}' has no threshold set, so the minimum criterion "
            "score could not be checked."
        )

    key = (getattr(rule, "value", "") or "").strip()
    if not key:
        params = getattr(rule, "params", None) or {}
        key = str(params.get("criterion_key", "") or "").strip()
    if not key:
        requirement_id = getattr(rule, "requirement_id", None)
        if requirement_id:
            key = facts.criterion_keys_by_requirement.get(requirement_id, "")

    if not key or key not in facts.criterion_scores:
        return False, True, "", (
            f"'{rule.label}' points at criterion '{key or 'unknown'}', which is "
            "not scored in this rubric version, so it could not be checked."
        )

    score = facts.criterion_scores[key]
    triggered = _compare(score, rule.operator, threshold)
    observed = f"{key} scored {score:.1f}"
    message = (
        f"Criterion '{key}' scored {score:.1f} against a required minimum of "
        f"{threshold:g}." if triggered
        else f"Criterion '{key}' meets its minimum ({score:.1f} vs {threshold:g})."
    )
    return triggered, False, observed, message


def _eval_custom(facts: CandidateFacts, rule) -> tuple[bool, bool, str, str]:
    """
    CUSTOM and ELIGIBILITY_FAILURE rules. Only presence/absence operators can
    be evaluated deterministically; anything else is flagged for review
    rather than assumed to pass, so a rule a recruiter wrote is never quietly
    ignored.
    """
    if rule.operator in (RuleOperator.MISSING, RuleOperator.PRESENT):
        return _eval_term_presence(facts, rule, ("HEADER", "SUMMARY", "EXPERIENCE",
                                                 "EDUCATION", "SKILLS",
                                                 "CERTIFICATIONS", "OTHER"), "condition")
    if rule.operator in (RuleOperator.IN, RuleOperator.NOT_IN):
        terms = _rule_terms(rule)
        found, matched, _ = _find_any(terms, facts.text)
        triggered = (not found) if rule.operator == RuleOperator.IN else found
        observed = f"found '{matched}'" if found else "no match"
        return triggered, False, observed, (
            f"{'Failed' if triggered else 'Satisfied'} eligibility rule: {rule.label} ({observed})."
        )
    return False, True, "", (
        f"Eligibility rule '{rule.label}' uses operator {rule.operator.value}, which "
        "has no deterministic check. A recruiter must confirm it manually."
    )


_DISPATCH = {
    RuleType.MIN_YEARS_EXPERIENCE: lambda f, r: _eval_min_years(f, r),
    RuleType.MISSING_MANDATORY_SKILL: lambda f, r: _eval_term_presence(
        f, r, ("SKILLS", "EXPERIENCE", "PROJECTS", "SUMMARY"), "skill"),
    RuleType.MISSING_QUALIFICATION: lambda f, r: _eval_term_presence(
        f, r, _QUAL_SECTIONS, "qualification"),
    RuleType.MISSING_CERTIFICATION: lambda f, r: _eval_term_presence(
        f, r, _CERT_SECTIONS, "certification"),
    RuleType.LOCATION_MISMATCH: lambda f, r: _eval_location(f, r),
    RuleType.MIN_CRITERION_SCORE: lambda f, r: _eval_min_criterion_score(f, r),
    RuleType.ELIGIBILITY_FAILURE: lambda f, r: _eval_custom(f, r),
    RuleType.CUSTOM: lambda f, r: _eval_custom(f, r),
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def evaluate(rules, facts: CandidateFacts) -> EligibilityOutcome:
    """
    Apply every active rule to `facts` and return the verdict.

    Precedence, in order:
      DISQUALIFIED     — at least one HARD_FAIL rule fired on established facts
      REVIEW_REQUIRED  — a REVIEW_REQUIRED rule fired, or any rule was
                         indeterminate
      ELIGIBLE         — everything checkable passed
    """
    findings: list[Finding] = []

    for order, rule in enumerate(rules or []):
        if not getattr(rule, "active", True):
            continue

        handler = _DISPATCH.get(rule.rule_type, _eval_custom)
        try:
            triggered, indeterminate, observed, message = handler(facts, rule)
        except Exception as exc:  # a bad rule must not sink the evaluation
            triggered, indeterminate = False, True
            observed = ""
            message = (
                f"Rule '{getattr(rule, 'label', '')}' could not be evaluated "
                f"({exc.__class__.__name__}); flagged for manual review."
            )

        # A rule's own message overrides the generated one when it fired and
        # the recruiter wrote one — their wording is what the client sees.
        custom_message = (getattr(rule, "message", "") or "").strip()
        if triggered and custom_message:
            message = custom_message

        findings.append(Finding(
            code=rule.code,
            label=getattr(rule, "label", ""),
            rule_id=getattr(rule, "id", None),
            rule_type=rule.rule_type,
            operator=rule.operator,
            threshold=getattr(rule, "threshold", None),
            severity=rule.severity,
            triggered=triggered,
            indeterminate=indeterminate,
            observed_value=observed,
            message=message,
            display_order=getattr(rule, "display_order", order) or order,
        ))

    outcome = EligibilityOutcome(status=EligibilityStatus.ELIGIBLE, findings=findings)
    if outcome.hard_failures:
        outcome.status = EligibilityStatus.DISQUALIFIED
    elif outcome.review_items:
        outcome.status = EligibilityStatus.REVIEW_REQUIRED
    return outcome
