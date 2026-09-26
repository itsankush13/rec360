"""
Deterministic experience engine.

Before Phase D, `experience_years` was a single float the LLM guessed from
the CV. That is unusable for a mandatory "8+ years" rule: it cannot be
audited, it moves between runs, and it says nothing about *what kind* of
experience or *when*. The client asked for years, relevance, recency,
continuity, gaps and contradiction detection, all of which need the actual
employment timeline.

So the timeline is parsed out of the CV's EXPERIENCE section:

  * Total years is the **union** of the parsed stints, not their sum.
    Summing double-counts concurrent roles — the usual way a CV with a
    consulting engagement listed alongside a staff role reads as 14 years
    when the person has 8.
  * Relevant years counts only the stints whose text matches the campaign's
    own terms, via the skill taxonomy. "10 years of experience" in an
    unrelated field is not 10 years of relevant experience.
  * Contradictions are recorded, not resolved. If the summary claims 12
    years and the timeline shows 6, that is a finding for a recruiter, not
    something for this module to average away.

No model calls. Every number here is reproducible from the CV text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.core import skill_taxonomy

# A gap shorter than this is ordinary (notice periods, moving, a holiday) and
# is not worth a recruiter's attention.
GAP_MONTHS_THRESHOLD = 4

# How far a self-claimed total may sit from the computed total before it
# counts as a contradiction. CVs round generously; two years is not rounding.
CLAIM_TOLERANCE_YEARS = 2.0

# A role ending this long ago makes the skills in it stale.
RECENCY_STALE_MONTHS = 36

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_PRESENT = {
    "present", "current", "till date", "to date", "now", "ongoing", "date",
    "present day", "currently", "till now", "until now",
}

_DASH = r"[-–—]|\bto\b|\buntil\b|\btill\b"

_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))

# "Mar 2021", "March 2021", "Mar-2021", "Mar '21"
_MONTH_YEAR = rf"(?P<mon>{_MONTH_NAMES})[a-z]*[\s.,\-/']*(?P<yr>(?:19|20)\d{{2}}|'?\d{{2}})"
# "03/2021", "03-2021", "2021/03"
_NUM_MONTH_YEAR = r"(?P<nmon>0?[1-9]|1[0-2])[/\-.](?P<nyr>(?:19|20)\d{2})"
_YEAR_ONLY = r"(?P<yonly>(?:19|20)\d{2})"

_PRESENT_RE = "|".join(sorted((re.escape(p) for p in _PRESENT), key=len, reverse=True))

_RANGE_RE = re.compile(
    rf"(?P<start>{_MONTH_YEAR}|{_NUM_MONTH_YEAR}|{_YEAR_ONLY})"
    rf"\s*(?:{_DASH})\s*"
    rf"(?P<end>{_PRESENT_RE}|"
    rf"(?:(?P<mon2>{_MONTH_NAMES})[a-z]*[\s.,\-/']*(?P<yr2>(?:19|20)\d{{2}}|'?\d{{2}}))|"
    rf"(?:(?P<nmon2>0?[1-9]|1[0-2])[/\-.](?P<nyr2>(?:19|20)\d{{2}}))|"
    rf"(?P<yonly2>(?:19|20)\d{{2}}))",
    re.IGNORECASE,
)

# "7 years", "7+ yrs", "seven years" is deliberately not handled — spelled-out
# numbers in a claim are rare and ambiguous ("a couple of years").
_CLAIM_RE = re.compile(
    r"(?P<years>\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b"
    r"(?![\s\w]{0,20}\b(?:old|of\s+age)\b)",
    re.IGNORECASE,
)


def _year(raw: str) -> int:
    """Expand a two-digit year. '98 -> 1998, '21 -> 2021."""
    value = int(raw.strip().lstrip("'"))
    if value >= 100:
        return value
    return 2000 + value if value <= (date.today().year % 100) else 1900 + value


@dataclass
class Stint:
    """One employment period parsed from the CV."""
    start: date
    end: date
    is_current: bool = False
    text: str = ""
    start_precise: bool = True   # False when only a year was given
    end_precise: bool = True

    @property
    def months(self) -> int:
        return max(0, (self.end.year - self.start.year) * 12 + (self.end.month - self.start.month))

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "is_current": self.is_current,
            "months": self.months,
            "years": round(self.months / 12.0, 2),
            "approximate": not (self.start_precise and self.end_precise),
            "excerpt": self.text[:200],
        }


@dataclass
class Gap:
    start: date
    end: date

    @property
    def months(self) -> int:
        return max(0, (self.end.year - self.start.year) * 12 + (self.end.month - self.start.month))

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "months": self.months,
        }


@dataclass
class ExperienceProfile:
    total_years: float = 0.0
    relevant_years: float = 0.0
    stints: list[Stint] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    months_since_last_role: int | None = None
    currently_employed: bool = False
    continuity_ratio: float = 1.0        # covered months / span months
    claimed_years: float | None = None   # what the CV says about itself
    contradictions: list[dict] = field(default_factory=list)
    parse_confidence: float = 0.0
    timeline_found: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return (
            self.months_since_last_role is not None
            and self.months_since_last_role > RECENCY_STALE_MONTHS
        )

    def to_dict(self) -> dict:
        return {
            "total_years": self.total_years,
            "relevant_years": self.relevant_years,
            "claimed_years": self.claimed_years,
            "currently_employed": self.currently_employed,
            "months_since_last_role": self.months_since_last_role,
            "is_stale": self.is_stale,
            "continuity_ratio": self.continuity_ratio,
            "timeline_found": self.timeline_found,
            "parse_confidence": self.parse_confidence,
            "stint_count": len(self.stints),
            "stints": [s.to_dict() for s in self.stints],
            "gaps": [g.to_dict() for g in self.gaps],
            "contradictions": self.contradictions,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_endpoint(match: re.Match[str], group_names: tuple[str, str, str]) -> tuple[date | None, bool]:
    """Resolve one end of a range. Returns (date, precise)."""
    month_key, year_key, year_only_key = group_names
    month_raw = match.group(month_key) if month_key else None
    if month_raw and match.group(year_key):
        month = _MONTHS.get(month_raw.strip().casefold()[:4].rstrip(".")) or \
            _MONTHS.get(month_raw.strip().casefold()[:3])
        if month:
            return date(_year(match.group(year_key)), month, 1), True
    if year_only_key and match.group(year_only_key):
        return date(_year(match.group(year_only_key)), 1, 1), False
    return None, False


def _parse_start(match: re.Match[str]) -> tuple[date | None, bool]:
    if match.group("mon") and match.group("yr"):
        month = _MONTHS.get(match.group("mon").casefold())
        if month:
            return date(_year(match.group("yr")), month, 1), True
    if match.group("nmon") and match.group("nyr"):
        return date(_year(match.group("nyr")), int(match.group("nmon")), 1), True
    if match.group("yonly"):
        return date(_year(match.group("yonly")), 1, 1), False
    return None, False


def _parse_end(match: re.Match[str], today: date) -> tuple[date | None, bool, bool]:
    """Returns (date, precise, is_current)."""
    raw = (match.group("end") or "").strip().casefold()
    if raw in _PRESENT:
        return today, True, True
    if match.group("mon2") and match.group("yr2"):
        month = _MONTHS.get(match.group("mon2").casefold())
        if month:
            return date(_year(match.group("yr2")), month, 1), True, False
    if match.group("nmon2") and match.group("nyr2"):
        return date(_year(match.group("nyr2")), int(match.group("nmon2")), 1), True, False
    if match.group("yonly2"):
        # A bare end year means "through that year", so December.
        return date(_year(match.group("yonly2")), 12, 1), False, False
    return None, False, False


def parse_stints(text: str, today: date | None = None) -> tuple[list[Stint], list[dict]]:
    """
    Pull employment date ranges out of `text`.

    Returns the stints plus any structural problems found while parsing
    (reversed ranges, future dates) as contradiction dicts.
    """
    today = today or date.today()
    text = text or ""
    stints: list[Stint] = []
    problems: list[dict] = []

    matches = list(_RANGE_RE.finditer(text))
    # Each role's text runs from its own header line to the start of the next
    # role's header line. Using only the date line means the bullets
    # underneath — which is where the actual technology is named — never
    # count towards relevance, so every candidate scored 0 relevant years.
    line_starts = [text.rfind("\n", 0, m.start()) + 1 for m in matches]

    for position, match in enumerate(matches):
        start, start_precise = _parse_start(match)
        end, end_precise, is_current = _parse_end(match, today)

        line_start = line_starts[position]
        block_end = (
            line_starts[position + 1] if position + 1 < len(line_starts) else len(text)
        )
        excerpt = text[line_start:block_end].strip()

        if start is None or end is None:
            continue

        if end < start:
            problems.append({
                "type": "REVERSED_DATE_RANGE",
                "detail": f"A date range ends before it starts: {excerpt[:120]}",
                "severity": "MEDIUM",
            })
            continue
        if start > today:
            problems.append({
                "type": "FUTURE_START_DATE",
                "detail": f"A role starts in the future: {excerpt[:120]}",
                "severity": "MEDIUM",
            })
            continue
        if end > today:
            end, end_precise = today, False

        stints.append(Stint(
            start=start, end=end, is_current=is_current, text=excerpt,
            start_precise=start_precise, end_precise=end_precise,
        ))

    return stints, problems


def _union_months(stints: list[Stint]) -> int:
    """
    Total months covered by the union of the stints.

    Summing stint lengths double-counts concurrent roles. A CV listing a
    full-time role 2018-2024 and a side consultancy 2020-2022 has 6 years of
    experience, not 8.
    """
    if not stints:
        return 0
    intervals = sorted(
        ((s.start.year * 12 + s.start.month, s.end.year * 12 + s.end.month) for s in stints)
    )
    merged: list[list[int]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(max(0, end - start) for start, end in merged)


def _find_gaps(stints: list[Stint]) -> list[Gap]:
    if len(stints) < 2:
        return []
    intervals = sorted(((s.start, s.end) for s in stints))
    gaps: list[Gap] = []
    cursor = intervals[0][1]
    for start, end in intervals[1:]:
        months = (start.year - cursor.year) * 12 + (start.month - cursor.month)
        if months >= GAP_MONTHS_THRESHOLD:
            gaps.append(Gap(start=cursor, end=start))
        cursor = max(cursor, end)
    return gaps


def _claimed_years(text: str) -> float | None:
    """
    The largest 'N years' claim in the CV's own words.

    The largest is taken deliberately: a CV saying "3 years with Kafka, 9
    years overall" is claiming 9 years of experience, and that is the number
    a mandatory-years rule would be checked against.
    """
    values = [float(m.group("years")) for m in _CLAIM_RE.finditer(text or "")]
    plausible = [v for v in values if 0 < v <= 50]
    return max(plausible) if plausible else None


def analyse(
    index,
    campaign_terms: list[str] | None = None,
    today: date | None = None,
) -> ExperienceProfile:
    """
    Build an ExperienceProfile from an `EvidenceIndex`.

    `campaign_terms` are the terms mined from the rubric's criteria; a stint
    whose text hits one of them counts towards relevant years.
    """
    today = today or date.today()
    profile = ExperienceProfile()
    full_text = getattr(index, "text", "") or ""
    if not full_text:
        profile.notes.append("No CV text available; experience could not be assessed.")
        return profile

    profile.claimed_years = _claimed_years(full_text)

    # Prefer the EXPERIENCE and PROJECTS sections: date ranges in EDUCATION
    # are degrees, not employment, and counting them inflates the total.
    scoped = "\n".join(
        part for part in (
            index.section_text("EXPERIENCE"),
            index.section_text("PROJECTS"),
        ) if part
    ).strip()
    if scoped:
        stints, problems = parse_stints(scoped, today)
        source = "experience section"
    else:
        # No recognised section — fall back to the whole document and say so,
        # because education ranges may now be in the total.
        stints, problems = parse_stints(full_text, today)
        source = "whole document"
        if stints:
            profile.notes.append(
                "No EXPERIENCE section heading was found; the timeline was read "
                "from the whole CV and may include non-employment dates."
            )

    profile.contradictions.extend(problems)
    profile.stints = sorted(stints, key=lambda s: s.start)
    profile.timeline_found = bool(stints)

    if not stints:
        profile.notes.append(
            f"No employment date ranges could be parsed from the {source}."
        )
        # A claim with no timeline behind it is all there is to go on, and it
        # is explicitly low confidence.
        if profile.claimed_years is not None:
            profile.total_years = profile.claimed_years
            profile.parse_confidence = 0.25
            profile.notes.append(
                "Total years is taken from the candidate's own stated figure and "
                "is not corroborated by a parsed timeline."
            )
            profile.contradictions.append({
                "type": "UNVERIFIED_EXPERIENCE_CLAIM",
                "detail": (
                    f"The CV claims {profile.claimed_years:g} years but no dated "
                    "employment history could be read from it."
                ),
                "severity": "MEDIUM",
            })
        return profile

    total_months = _union_months(stints)
    profile.total_years = round(total_months / 12.0, 2)
    profile.gaps = _find_gaps(stints)
    profile.currently_employed = any(s.is_current for s in stints)

    latest_end = max(s.end for s in stints)
    profile.months_since_last_role = 0 if profile.currently_employed else max(
        0, (today.year - latest_end.year) * 12 + (today.month - latest_end.month)
    )

    earliest = min(s.start for s in stints)
    span_months = max(1, (latest_end.year - earliest.year) * 12 + (latest_end.month - earliest.month))
    profile.continuity_ratio = round(min(1.0, total_months / span_months), 3)

    # Relevance: months in stints that mention something the rubric cares about.
    terms = [t for t in (campaign_terms or []) if t]
    if terms:
        relevant = [
            s for s in stints
            if any(skill_taxonomy.find_term(term, s.text).found for term in terms)
        ]
        profile.relevant_years = round(_union_months(relevant) / 12.0, 2)
        if not relevant:
            profile.notes.append(
                "No parsed role mentions the campaign's criteria; relevant "
                "experience is recorded as zero rather than assumed."
            )
    else:
        # Nothing to measure relevance against — report total rather than
        # implying a relevance judgement was made.
        profile.relevant_years = profile.total_years
        profile.notes.append(
            "No rubric terms supplied; relevant years mirrors total years."
        )

    # Parse confidence: precise dates and a continuous timeline earn trust.
    precise = sum(1 for s in stints if s.start_precise and s.end_precise)
    precision_ratio = precise / len(stints)
    profile.parse_confidence = round(
        min(1.0, 0.45 + 0.35 * precision_ratio + 0.20 * profile.continuity_ratio), 2
    )

    # -- contradictions ----------------------------------------------------

    if profile.claimed_years is not None:
        drift = profile.claimed_years - profile.total_years
        if abs(drift) > CLAIM_TOLERANCE_YEARS:
            profile.contradictions.append({
                "type": "EXPERIENCE_CLAIM_MISMATCH",
                "detail": (
                    f"The CV claims {profile.claimed_years:g} years of experience but the "
                    f"dated employment history covers {profile.total_years:g} years "
                    f"({'overstated' if drift > 0 else 'understated'} by "
                    f"{abs(drift):.1f})."
                ),
                "severity": "HIGH" if abs(drift) > 2 * CLAIM_TOLERANCE_YEARS else "MEDIUM",
            })

    concurrent = _max_concurrent(stints)
    if concurrent > 2:
        profile.contradictions.append({
            "type": "OVERLAPPING_ROLES",
            "detail": (
                f"{concurrent} roles overlap in time. This can be legitimate "
                "(advisory or part-time work) but should be confirmed."
            ),
            "severity": "LOW",
        })

    for gap in profile.gaps:
        if gap.months >= 12:
            profile.contradictions.append({
                "type": "EMPLOYMENT_GAP",
                "detail": (
                    f"A {gap.months}-month gap between {gap.start.isoformat()} and "
                    f"{gap.end.isoformat()} is unexplained in the CV."
                ),
                "severity": "LOW",
            })

    if profile.is_stale:
        profile.contradictions.append({
            "type": "STALE_EXPERIENCE",
            "detail": (
                f"The most recent parsed role ended about "
                f"{profile.months_since_last_role} months ago."
            ),
            "severity": "MEDIUM",
        })

    return profile


def _max_concurrent(stints: list[Stint]) -> int:
    """Peak number of simultaneously-held roles."""
    events: list[tuple[int, int]] = []
    for stint in stints:
        events.append((stint.start.year * 12 + stint.start.month, 1))
        events.append((stint.end.year * 12 + stint.end.month, -1))
    events.sort()
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak
