"""
Phase D tests — rubric-driven scoring, evidence citation, eligibility,
confidence, the experience engine and result immutability.

The unit tests drive the engines directly with plain objects, because the
whole value of Phase D is that scoring is deterministic: the same CV and the
same rubric must produce the same numbers, and that is only testable if the
engines are exercised without a model in the loop.

The integration tests go through the real API from campaign creation to
leaderboard, using the same PDF-building helpers as the Phase C suite so the
retained-document and page-citation paths are genuinely exercised rather
than mocked.
"""
import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest

from app.core import (
    criterion_scorer, eligibility_engine, evidence_index, experience_engine,
    skill_taxonomy,
)
from app.db.models import (
    ConfidenceBand, CriterionOutcome, EligibilityStatus, EvidenceMatchType,
    Recommendation, RequirementCategory, RequirementType, RuleOperator,
    RuleSeverity, RuleType, ScoringMethod,
)

from tests.test_processing import (
    DOCX_MIME, FAKE_JD_EXTRACTION, PDF_MIME, make_docx, upload,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STRONG_CV = "\n".join([
    "Priya Raman",
    "priya.raman@example.com | +91 98765 43210 | Bengaluru, India",
    "",
    "SUMMARY",
    "Senior backend engineer with 8 years of experience building and operating",
    "high-throughput distributed systems for fintech clients across India.",
    "",
    "SKILLS",
    "Python, Postgres, Amazon Web Services, K8s, FastAPI, Terraform, Redis, Git",
    "",
    "EXPERIENCE",
    "Staff Engineer, Acme Corp (Mar 2021 - Present)",
    "- Built REST APIs with FastAPI on Postgres and AWS serving 2M requests daily",
    "- Led five engineers through an Oracle to Postgres migration",
    "- Introduced Terraform provisioning across three environments",
    "Senior Engineer, Globex (Jul 2018 - Feb 2021)",
    "- Owned Python microservices on AWS with automated CI/CD pipelines",
    "- Ran the Postgres read-replica topology and Redis caching layer",
    "",
    "EDUCATION",
    "B.Tech in Computer Science, NIT Trichy, 2018",
    "",
    "CERTIFICATIONS",
    "AWS Certified Solutions Architect",
])

WEAK_CV = "\n".join([
    "Rahul Verma",
    "rahul.verma@example.com | +91 91234 56780 | Pune, India",
    "",
    "SUMMARY",
    "Graphic designer with 3 years of experience in brand identity and print",
    "production for regional retail clients.",
    "",
    "SKILLS",
    "Adobe Illustrator, Photoshop, InDesign, typography, colour theory",
    "",
    "EXPERIENCE",
    "Designer, Studio Nine (Jan 2023 - Present)",
    "- Produced packaging artwork and in-store signage",
    "Junior Designer, PrintWorks (Feb 2021 - Dec 2022)",
    "- Prepared press-ready files and managed proofing cycles",
    "",
    "EDUCATION",
    "Bachelor of Fine Arts, Pune University, 2020",
])


def make_pdf_pages(pages, user_password=None):
    """Multi-page PDF, so page-number citation has something to cite."""
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        y = 60
        for line in lines:
            page.insert_text((50, y), line, fontsize=9)
            y += 12
    data = document.tobytes()
    document.close()
    return data


def make_cv_pdf(text):
    """One page per ~28 lines, mirroring how a real CV paginates."""
    lines = text.split("\n")
    return make_pdf_pages([lines[i:i + 28] for i in range(0, len(lines), 28)] or [[""]])


def index_for(text):
    """An EvidenceIndex over raw text — no file, so sections only."""
    return evidence_index.EvidenceIndex(
        text=text, sections=evidence_index.find_sections(text)
    )


def weight(
    key, label, *, category=RequirementCategory.SKILL,
    requirement_type=RequirementType.MANDATORY, w=25.0,
    method=ScoringMethod.WEIGHTED, order=0, requirement_id=None,
):
    return SimpleNamespace(
        id=f"w-{key}", criterion_key=key, label=label, category=category,
        requirement_type=requirement_type, weight=w, max_score=100.0,
        scoring_method=method, evidence_required=True, active=True,
        display_order=order, requirement_id=requirement_id,
    )


def rule(
    code, label, *, rule_type=RuleType.MISSING_MANDATORY_SKILL,
    operator=RuleOperator.MISSING, threshold=None, value="",
    severity=RuleSeverity.HARD_FAIL, params=None, message="", order=0,
    requirement_id=None,
):
    return SimpleNamespace(
        id=f"r-{code}", code=code, label=label, rule_type=rule_type,
        operator=operator, threshold=threshold, value=value, params=params,
        severity=severity, message=message, active=True, display_order=order,
        requirement_id=requirement_id,
    )


@pytest.fixture()
def evaluated_campaign(client):
    """A campaign with an approved rubric and two candidates uploaded."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Phase D campaign",
            "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS backend engineer.",
            "location": "Bengaluru",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"seed_from_requirements": True},
    )
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
        json={"approved_by": "Priya Nair"},
    )

    response = upload(client, campaign_id, [
        ("strong.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("weak.pdf", make_cv_pdf(WEAK_CV), PDF_MIME),
    ])
    assert response.status_code == 201, response.text
    return campaign_id


# ===========================================================================
# Skill taxonomy
# ===========================================================================

def test_taxonomy_matches_aliases_as_full_credit():
    """The bug this replaces: 'Postgres' in a CV missed a 'PostgreSQL' need."""
    match = skill_taxonomy.find_term("PostgreSQL", "Skills: Postgres, Redis")
    assert match.kind == "EQUIVALENT"
    assert match.credit == 1.0
    assert match.matched_surface == "Postgres"


@pytest.mark.parametrize("need,cv_text,expected", [
    ("AWS", "Amazon Web Services experience", "EQUIVALENT"),
    ("Kubernetes", "Ran K8s clusters", "EQUIVALENT"),
    ("JavaScript", "Strong JS background", "EQUIVALENT"),
    ("Power BI", "Dashboards in Power-BI", "EXACT"),
    ("C#", "Built services in C#", "EXACT"),
    ("MySQL", "Deep PostgreSQL experience", "ADJACENT"),
    ("Rust", "Python and Java only", "NONE"),
])
def test_taxonomy_match_tiers(need, cv_text, expected):
    assert skill_taxonomy.find_term(need, cv_text).kind == expected


def test_adjacent_matches_earn_partial_not_full_credit():
    match = skill_taxonomy.find_term("MySQL", "Expert in PostgreSQL")
    assert match.kind == "ADJACENT"
    assert 0 < match.credit < 1.0


def test_short_terms_do_not_match_inside_words():
    """'go' must not match 'category'; 'R' must not match every word."""
    assert not skill_taxonomy.find_term("go", "category management").found
    assert not skill_taxonomy.find_term("R", "Strong programmer").found


def test_punctuated_skill_names_survive_matching():
    """'c++' and '.net' contain regex metacharacters and word boundaries."""
    assert skill_taxonomy.find_term("C++", "Languages: C++, Java").kind == "EXACT"
    assert skill_taxonomy.find_term(".NET", "Built on .NET Core").found


def test_extract_terms_prefers_multiword_taxonomy_entries():
    terms = skill_taxonomy.extract_terms(
        "5+ years hands-on experience with Microsoft SQL Server and Power BI"
    )
    assert "microsoft sql server" in terms
    assert "power bi" in terms
    # Not shredded into 'microsoft', 'sql', 'server'
    assert "server" not in terms


def test_extract_terms_drops_filler_nouns():
    assert skill_taxonomy.extract_terms("Bachelor of Technology degree") == ["b.tech"]


# ===========================================================================
# Evidence index — page and section citation
# ===========================================================================

def test_sections_are_detected_from_headings():
    index = index_for(STRONG_CV)
    names = index.section_names()
    assert "SUMMARY" in names
    assert "EXPERIENCE" in names
    assert "EDUCATION" in names
    assert "CERTIFICATIONS" in names
    assert names[0] == evidence_index.HEADER_SECTION


def test_heading_aliases_map_to_canonical_sections():
    text = "Name\nPROFESSIONAL EXPERIENCE\nx\nACADEMIC QUALIFICATIONS\ny\nTECHNICAL SKILLS\nz"
    names = index_for(text).section_names()
    assert "EXPERIENCE" in names
    assert "EDUCATION" in names
    assert "SKILLS" in names


def test_bulleted_lines_do_not_open_bogus_sections():
    """A bullet reading 'Skills: Python' inside a role is not a SKILLS heading."""
    text = "Name\nEXPERIENCE\nEngineer, Acme (2020-2023)\n- Skills: Python, AWS\n- Shipped things"
    index = index_for(text)
    assert index.section_names() == [evidence_index.HEADER_SECTION, "EXPERIENCE"]


def test_section_lookup_locates_an_offset():
    index = index_for(STRONG_CV)
    position = STRONG_CV.index("B.Tech")
    assert index.section_for(position) == "EDUCATION"


def test_page_numbers_are_recovered_from_the_retained_pdf(tmp_path, monkeypatch):
    """
    Phase C joins page text and discards boundaries, so page numbers are
    rebuilt by re-reading the stored file. This is the check that they land
    on the right page.
    """
    from app.core import document_intake, storage

    data = make_pdf_pages([
        ["Priya Raman", "priya.raman@example.com", "SUMMARY"]
        + ["Senior backend engineer building Python services on AWS."] * 4,
        ["CERTIFICATIONS", "AWS Certified Solutions Architect"]
        + ["Completed the associate and professional tracks in 2024."] * 4,
    ])
    path = tmp_path / "cv.pdf"
    path.write_bytes(data)
    extracted = document_intake.extract_document(str(path), "cv.pdf")

    monkeypatch.setattr(storage, "read", lambda key: data)
    document = SimpleNamespace(
        id="doc-1", extracted_text=extracted.text, page_count=extracted.page_count,
        extension=".pdf", storage_path="key",
    )
    index = evidence_index.build_index(document)

    assert index.pages_reliable is True
    assert index.page_count == 2
    assert index.page_for(index.text.index("SUMMARY")) == 1
    assert index.page_for(index.text.index("CERTIFICATIONS")) == 2


def test_page_numbers_are_withheld_when_reconstruction_disagrees(monkeypatch):
    """A wrong page citation is worse than none, so a mismatch yields None."""
    from app.core import storage

    monkeypatch.setattr(storage, "read", lambda key: make_pdf_pages([["Totally", "different"]]))
    document = SimpleNamespace(
        id="doc-2", extracted_text="Stored text that does not match the file",
        page_count=1, extension=".pdf", storage_path="key",
    )
    index = evidence_index.build_index(document)
    assert index.pages_reliable is False
    assert index.page_for(0) is None


def test_docx_cites_sections_with_no_page_number():
    """Phase C's DOCX extractor reports page_count 0 — sections are all we have."""
    document = SimpleNamespace(
        id="doc-3", extracted_text=STRONG_CV, page_count=0,
        extension=".docx", storage_path="key",
    )
    index = evidence_index.build_index(document)
    assert index.page_for(0) is None
    assert "EXPERIENCE" in index.section_names()


def test_excerpt_is_anchored_on_the_matched_line():
    index = index_for(STRONG_CV)
    position = STRONG_CV.index("Terraform provisioning")
    citation = index.cite(position, position + 10)
    assert "Terraform provisioning" in citation.excerpt
    assert len(citation.excerpt) <= evidence_index.EXCERPT_MAX_CHARS + 1


# ===========================================================================
# Experience engine
# ===========================================================================

def test_total_years_uses_the_union_not_the_sum():
    """Concurrent roles must not double-count. Sum would say 12.5; union 5.9."""
    text = "\n".join([
        "EXPERIENCE",
        "Consultant, X (Jan 2015 - Dec 2020)",
        "- work",
        "Advisor, Y (Jan 2016 - Dec 2019)",
        "- work",
        "Partner, Z (Feb 2017 - Mar 2018)",
        "- work",
    ])
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.total_years == pytest.approx(5.92, abs=0.05)


def test_relevant_years_counts_only_matching_roles():
    profile = experience_engine.analyse(
        index_for(STRONG_CV), campaign_terms=["postgresql"], today=date(2026, 9, 1)
    )
    assert profile.relevant_years > 0
    assert profile.relevant_years <= profile.total_years


def test_relevant_years_is_zero_when_nothing_matches():
    profile = experience_engine.analyse(
        index_for(WEAK_CV), campaign_terms=["kubernetes", "terraform"],
        today=date(2026, 9, 1),
    )
    assert profile.total_years > 0
    assert profile.relevant_years == 0.0


def test_gaps_are_detected():
    text = "EXPERIENCE\nEngineer, A (Jan 2016 - Dec 2018)\n- x\nEngineer, B (Jan 2021 - Dec 2023)\n- y"
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert len(profile.gaps) == 1
    assert profile.gaps[0].months == pytest.approx(25, abs=1)


def test_short_gaps_are_ignored():
    text = "EXPERIENCE\nEngineer, A (Jan 2020 - Mar 2022)\n- x\nEngineer, B (May 2022 - Dec 2023)\n- y"
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.gaps == []


def test_overstated_experience_claim_is_flagged():
    text = "\n".join([
        "SUMMARY", "Engineer with 15 years of experience.",
        "EXPERIENCE", "Engineer, A (Jan 2020 - Present)", "- work",
    ])
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    types = [c["type"] for c in profile.contradictions]
    assert "EXPERIENCE_CLAIM_MISMATCH" in types


def test_unparseable_timeline_is_low_confidence_and_flagged():
    text = "SUMMARY\nEngineer with 8 years of experience.\nSKILLS\nPython, AWS"
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.timeline_found is False
    assert profile.total_years == 8.0          # the claim, used explicitly
    assert profile.parse_confidence <= 0.3     # and clearly not trusted
    assert "UNVERIFIED_EXPERIENCE_CLAIM" in [c["type"] for c in profile.contradictions]


def test_reversed_date_range_is_reported_not_counted():
    text = "EXPERIENCE\nEngineer, A (Dec 2022 - Jan 2019)\n- work"
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.stints == []
    assert "REVERSED_DATE_RANGE" in [c["type"] for c in profile.contradictions]


def test_stale_experience_is_flagged():
    text = "EXPERIENCE\nEngineer, A (Jan 2010 - Dec 2015)\n- work"
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.is_stale is True
    assert "STALE_EXPERIENCE" in [c["type"] for c in profile.contradictions]


def test_education_dates_are_excluded_from_the_timeline():
    """A 2013-2017 degree is not four years of employment."""
    text = "\n".join([
        "EXPERIENCE", "Engineer, A (Jan 2020 - Dec 2022)", "- work",
        "EDUCATION", "B.Tech, IIT (2013 - 2017)",
    ])
    profile = experience_engine.analyse(index_for(text), today=date(2026, 9, 1))
    assert profile.total_years == pytest.approx(2.92, abs=0.1)
    assert len(profile.stints) == 1


def test_stint_text_includes_its_bullets():
    """Relevance is judged on the role's bullets, not just its date line."""
    profile = experience_engine.analyse(index_for(STRONG_CV), today=date(2026, 9, 1))
    assert any("Terraform" in stint.text for stint in profile.stints)


@pytest.mark.parametrize("date_text", [
    "Mar 2021 - Present", "March 2021 to Present", "03/2021 - 05/2023",
    "2019 - 2022", "Jan 2020 – Dec 2021", "Feb 2018 till date",
])
def test_common_date_formats_parse(date_text):
    text = f"EXPERIENCE\nEngineer, Acme ({date_text})\n- work"
    stints, _ = experience_engine.parse_stints(text, today=date(2026, 9, 1))
    assert len(stints) == 1


# ===========================================================================
# Criterion scorer
# ===========================================================================

def test_confirmed_match_scores_full_and_cites_evidence():
    index = index_for(STRONG_CV)
    result = criterion_scorer.score_criterion(
        weight("pg", "Strong experience with PostgreSQL"), index
    )
    assert result.outcome == CriterionOutcome.CONFIRMED_MATCH
    assert result.raw_score == 100.0
    assert result.evidence
    assert result.confidence_band == ConfidenceBand.HIGH


def test_not_demonstrated_on_a_full_cv_is_a_confident_absence():
    """
    The key confidence property: a thorough CV that never mentions Kafka is
    strong evidence of absence, so the score is 0 but confidence is not.
    """
    result = criterion_scorer.score_criterion(
        weight("kafka", "Hands-on with Apache Kafka"), index_for(STRONG_CV)
    )
    assert result.outcome == CriterionOutcome.NOT_DEMONSTRATED
    assert result.raw_score == 0.0
    assert result.confidence >= criterion_scorer.CONFIDENCE_MEDIUM


def test_thin_document_is_insufficient_evidence_not_a_zero():
    """A two-line CV must not be reported as a candidate who lacks the skill."""
    result = criterion_scorer.score_criterion(
        weight("kafka", "Hands-on with Apache Kafka"), index_for("Priya Raman\nEngineer")
    )
    assert result.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE
    assert result.confidence_band == ConfidenceBand.LOW


def test_negated_mention_is_contradictory_evidence():
    text = STRONG_CV.replace("Redis, Git", "Redis, Git. No Kafka experience.")
    result = criterion_scorer.score_criterion(
        weight("kafka", "Hands-on with Apache Kafka"), index_for(text)
    )
    assert result.outcome == CriterionOutcome.CONTRADICTORY_EVIDENCE
    assert any(
        e.match_type == EvidenceMatchType.CONTRADICTION for e in result.evidence
    )


def test_adjacent_skill_yields_a_partial_match():
    text = (
        STRONG_CV
        .replace("Amazon Web Services", "Microsoft Azure")
        .replace("on Postgres and AWS", "on Postgres and Azure")
        .replace("Python microservices on AWS", "Python microservices on Azure")
        .replace("AWS Certified Solutions Architect", "Azure Administrator")
    )
    assert "AWS" not in text
    result = criterion_scorer.score_criterion(
        weight("aws", "Experience with AWS"), index_for(text)
    )
    assert result.outcome == CriterionOutcome.PARTIAL_MATCH
    assert 0 < result.raw_score < 100
    assert result.equivalent_terms


def test_equivalent_match_is_recorded_as_such():
    result = criterion_scorer.score_criterion(
        weight("pg", "PostgreSQL administration"), index_for(STRONG_CV)
    )
    assert any("postgres" in entry.lower() for entry in result.equivalent_terms)


def test_binary_criterion_is_all_or_nothing():
    met = criterion_scorer.score_criterion(
        weight("deg", "Bachelor of Technology", method=ScoringMethod.BINARY),
        index_for(STRONG_CV),
    )
    assert met.raw_score in (0.0, 100.0)
    assert met.raw_score == 100.0

    unmet = criterion_scorer.score_criterion(
        weight("deg", "Master of Business Administration", method=ScoringMethod.BINARY),
        index_for(STRONG_CV),
    )
    assert unmet.raw_score == 0.0


def test_weighted_score_scales_by_rubric_weight():
    """The rubric->scoring bridge: change the weight, change the contribution."""
    index = index_for(STRONG_CV)
    light = criterion_scorer.score_criterion(weight("pg", "PostgreSQL", w=10.0), index)
    heavy = criterion_scorer.score_criterion(weight("pg", "PostgreSQL", w=40.0), index)
    assert light.raw_score == heavy.raw_score          # same evidence
    assert heavy.weighted_score == pytest.approx(4 * light.weighted_score)


def test_experience_criterion_uses_the_timeline_not_keywords():
    index = index_for(STRONG_CV)
    profile = experience_engine.analyse(
        index, campaign_terms=["postgresql", "aws"], today=date(2026, 9, 1)
    )
    result = criterion_scorer.score_criterion(
        weight("exp", "8+ years of backend engineering experience",
               category=RequirementCategory.EXPERIENCE),
        index, profile,
    )
    assert result.outcome == CriterionOutcome.CONFIRMED_MATCH
    assert "years" in result.rationale


def test_experience_criterion_is_partial_when_short_of_the_bar():
    index = index_for(WEAK_CV)
    profile = experience_engine.analyse(index, today=date(2026, 9, 1))
    result = criterion_scorer.score_criterion(
        weight("exp", "10+ years of experience", category=RequirementCategory.EXPERIENCE),
        index, profile,
    )
    assert result.raw_score < 100.0
    assert result.outcome != CriterionOutcome.CONFIRMED_MATCH


def test_experience_criterion_penalizes_overqualification():
    """
    A Jr HSE Officer role asking for 2 years must not score a candidate with
    8+ years as an ideal fit — well past the requirement is a caution
    (flight-risk/cost-mismatch), not a stronger match.
    """
    index = index_for(STRONG_CV)
    profile = experience_engine.analyse(index, today=date(2026, 9, 1))
    junior = criterion_scorer.score_criterion(
        weight("exp", "2+ years of experience", category=RequirementCategory.EXPERIENCE),
        index, profile,
    )
    fitting = criterion_scorer.score_criterion(
        weight("exp", "8+ years of experience", category=RequirementCategory.EXPERIENCE),
        index, profile,
    )
    assert junior.raw_score < fitting.raw_score
    assert junior.raw_score >= criterion_scorer.OVERQUALIFIED_FLOOR * junior.max_score
    assert "overqualified" in junior.rationale.lower()


def test_unmineable_label_is_insufficient_evidence():
    """A vague criterion must not read as a candidate failing it."""
    result = criterion_scorer.score_criterion(
        weight("vague", "Must be a good cultural fit"), index_for(STRONG_CV)
    )
    assert result.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE
    assert "manual" in result.rationale.lower() or "specific" in result.rationale.lower()


def test_scoring_is_deterministic():
    index = index_for(STRONG_CV)
    first = criterion_scorer.score_criterion(weight("pg", "PostgreSQL"), index)
    second = criterion_scorer.score_criterion(weight("pg", "PostgreSQL"), index)
    assert (first.raw_score, first.confidence, first.outcome) == \
           (second.raw_score, second.confidence, second.outcome)


# ===========================================================================
# Eligibility engine
# ===========================================================================

def facts_for(text, **kwargs):
    index = index_for(text)
    return eligibility_engine.CandidateFacts(
        text=text, index=index,
        experience=experience_engine.analyse(
            index, campaign_terms=kwargs.pop("terms", None), today=date(2026, 9, 1)
        ),
        **kwargs,
    )


def test_missing_mandatory_skill_hard_fails():
    outcome = eligibility_engine.evaluate(
        [rule("kafka", "Must have Apache Kafka experience")], facts_for(STRONG_CV)
    )
    assert outcome.status == EligibilityStatus.DISQUALIFIED
    assert len(outcome.hard_failures) == 1


def test_present_mandatory_skill_passes():
    outcome = eligibility_engine.evaluate(
        [rule("pg", "Must have PostgreSQL experience")], facts_for(STRONG_CV)
    )
    assert outcome.status == EligibilityStatus.ELIGIBLE
    assert outcome.findings[0].triggered is False


def test_equivalent_skill_satisfies_a_mandatory_rule():
    """'Postgres' in the CV satisfies a 'PostgreSQL' rule — the Phase D fix."""
    outcome = eligibility_engine.evaluate(
        [rule("pg", "PostgreSQL required", value="PostgreSQL")], facts_for(STRONG_CV)
    )
    assert outcome.status == EligibilityStatus.ELIGIBLE


def test_adjacent_skill_does_not_satisfy_a_mandatory_rule():
    """Partial credit in scoring, but not a pass on a mandatory gate."""
    text = STRONG_CV.replace("Postgres,", "MySQL,").replace("Postgres", "MySQL")
    outcome = eligibility_engine.evaluate(
        [rule("pg", "PostgreSQL required", value="PostgreSQL")], facts_for(text)
    )
    assert outcome.status == EligibilityStatus.DISQUALIFIED


def test_negated_skill_does_not_satisfy_a_rule():
    text = STRONG_CV + "\nNo Kubernetes experience."
    outcome = eligibility_engine.evaluate(
        [rule("k8s", "Kubernetes required", value="Kubernetes")],
        facts_for(text.replace("K8s, ", "")),
    )
    assert outcome.status == EligibilityStatus.DISQUALIFIED


def test_min_years_rule_fails_a_short_candidate():
    outcome = eligibility_engine.evaluate([
        rule("years", "Minimum 10 years of experience",
             rule_type=RuleType.MIN_YEARS_EXPERIENCE,
             operator=RuleOperator.LT, threshold=10.0)
    ], facts_for(WEAK_CV))
    assert outcome.status == EligibilityStatus.DISQUALIFIED
    assert "years" in outcome.hard_failures[0].observed_value


def test_min_years_rule_passes_a_long_candidate():
    outcome = eligibility_engine.evaluate([
        rule("years", "Minimum 5 years of experience",
             rule_type=RuleType.MIN_YEARS_EXPERIENCE,
             operator=RuleOperator.LT, threshold=5.0)
    ], facts_for(STRONG_CV))
    assert outcome.status == EligibilityStatus.ELIGIBLE


def test_unverifiable_years_goes_to_review_not_disqualified():
    """
    The safety property: a CV with no dated history is not auto-rejected on a
    years rule, and is not silently passed either.
    """
    text = "SUMMARY\nEngineer with lots of experience.\nSKILLS\nPython, AWS, Postgres"
    outcome = eligibility_engine.evaluate([
        rule("years", "Minimum 8 years of experience",
             rule_type=RuleType.MIN_YEARS_EXPERIENCE,
             operator=RuleOperator.LT, threshold=8.0)
    ], facts_for(text))
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED
    assert outcome.findings[0].indeterminate is True


def test_missing_threshold_is_indeterminate_not_a_pass():
    outcome = eligibility_engine.evaluate([
        rule("years", "Several years of experience",
             rule_type=RuleType.MIN_YEARS_EXPERIENCE,
             operator=RuleOperator.LT, threshold=None)
    ], facts_for(STRONG_CV))
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED


def test_review_required_severity_does_not_disqualify():
    outcome = eligibility_engine.evaluate([
        rule("kafka", "Kafka preferred", severity=RuleSeverity.REVIEW_REQUIRED)
    ], facts_for(STRONG_CV))
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED
    assert outcome.hard_failures == []


def test_location_mismatch_never_auto_disqualifies():
    """A candidate may relocate and simply not say so — flag, never reject."""
    outcome = eligibility_engine.evaluate([
        rule("loc", "Must be based in Berlin", rule_type=RuleType.LOCATION_MISMATCH,
             value="Berlin")
    ], facts_for(STRONG_CV, candidate_location="Bengaluru, India"))
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED
    assert "relocate" in outcome.findings[0].message.lower()


def test_certification_rule_is_scoped_to_credible_sections():
    outcome = eligibility_engine.evaluate([
        rule("cert", "AWS Certified Solutions Architect required",
             rule_type=RuleType.MISSING_CERTIFICATION,
             value="AWS Certified Solutions Architect")
    ], facts_for(STRONG_CV))
    assert outcome.status == EligibilityStatus.ELIGIBLE


def test_min_criterion_score_rule_reads_the_scored_criterion():
    facts = facts_for(STRONG_CV)
    facts.criterion_scores = {"pg": 20.0}
    outcome = eligibility_engine.evaluate([
        rule("minscore", "PostgreSQL must score at least 50",
             rule_type=RuleType.MIN_CRITERION_SCORE,
             operator=RuleOperator.LT, threshold=50.0, value="pg")
    ], facts)
    assert outcome.status == EligibilityStatus.DISQUALIFIED


def test_min_criterion_score_rule_pointing_nowhere_is_indeterminate():
    outcome = eligibility_engine.evaluate([
        rule("minscore", "Nonexistent criterion must score 50",
             rule_type=RuleType.MIN_CRITERION_SCORE,
             operator=RuleOperator.LT, threshold=50.0, value="ghost")
    ], facts_for(STRONG_CV))
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED


def test_inactive_rules_are_skipped():
    inactive = rule("kafka", "Kafka required")
    inactive.active = False
    outcome = eligibility_engine.evaluate([inactive], facts_for(STRONG_CV))
    assert outcome.findings == []
    assert outcome.status == EligibilityStatus.ELIGIBLE


def test_recruiter_message_overrides_the_generated_one():
    outcome = eligibility_engine.evaluate([
        rule("kafka", "Kafka required", message="Kafka is non-negotiable for this role.")
    ], facts_for(STRONG_CV))
    assert outcome.findings[0].message == "Kafka is non-negotiable for this role."


def test_a_broken_rule_does_not_sink_the_evaluation():
    broken = rule("bad", "Broken rule")
    broken.rule_type = RuleType.MIN_YEARS_EXPERIENCE
    broken.threshold = "not a number"  # would raise inside the comparison
    outcome = eligibility_engine.evaluate([broken], facts_for(STRONG_CV))
    assert len(outcome.findings) == 1
    assert outcome.status == EligibilityStatus.REVIEW_REQUIRED


# ===========================================================================
# API — runs, scoring, leaderboard
# ===========================================================================

def test_run_requires_an_approved_rubric(client):
    campaign_id = client.post("/api/campaigns", json={
        "name": "No rubric", "job_title": "Engineer", "job_description": "x",
    }).json()["id"]

    response = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    assert response.status_code == 422
    assert "rubric" in str(response.json()["detail"]).lower()


def test_run_scores_every_criterion_in_the_rubric(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    version = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    active_keys = {w["criterion_key"] for w in version["weights"] if w["active"]}

    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "COMPLETED"
    assert body["evaluated_count"] == 2

    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    assert {c["criterion_key"] for c in detail["criteria"]} == active_keys


def test_run_pins_the_rubric_version_it_scored_against(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    active_id = client.get(f"/api/campaigns/{campaign_id}/rubric/active").json()["id"]
    body = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    assert body["rubric_version_id"] == active_id
    assert all(e["rubric_version_id"] == active_id for e in body["evaluations"])


def test_relevant_candidate_outscores_an_irrelevant_one(evaluated_campaign, client):
    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    by_name = {e["candidate_name"]: e for e in body["evaluations"]}
    strong = next(v for k, v in by_name.items() if "Priya" in k)
    weak = next(v for k, v in by_name.items() if "Rahul" in k)
    assert strong["overall_score"] > weak["overall_score"]


def test_evaluation_detail_carries_the_candidate_360_fields(evaluated_campaign, client):
    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    strong = next(e for e in body["evaluations"] if "Priya" in e["candidate_name"])
    detail = client.get(f"/api/evaluations/{strong['id']}").json()

    for field in (
        "overall_score", "overall_confidence", "confidence_band", "mandatory_score",
        "eligibility_status", "recommendation", "strengths", "gaps",
        "missing_information", "contradictions", "narrative", "criteria",
        "eligibility_findings", "experience_profile",
    ):
        assert field in detail, field
    assert detail["rubric_version_number"] == 1
    assert detail["engine_version"]


def test_narrative_confirmed_count_excludes_informational_criteria(evaluated_campaign, client):
    """X2: FAKE_JD_EXTRACTION seeds informational criteria (seniority,
    responsibilities) as zero-weight rows so they still display on the
    review screen, but they must not inflate the "confirmed on X of Y"
    denominator — that is what made a candidate who matched everything they
    were actually being scored on look like they'd matched almost nothing."""
    campaign_id = evaluated_campaign
    version = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    scored_count = sum(1 for w in version["weights"] if w["weight"] > 0)
    total_count = len(version["weights"])
    assert scored_count < total_count  # the fixture must actually seed informational rows

    body = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    strong = next(e for e in body["evaluations"] if "Priya" in e["candidate_name"])
    detail = client.get(f"/api/evaluations/{strong['id']}").json()

    assert f"of {scored_count} scored criteria" in detail["narrative"]
    assert f"of {total_count} criteria" not in detail["narrative"]


def test_evidence_excerpts_carry_page_or_section_references(evaluated_campaign, client):
    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    strong = next(e for e in body["evaluations"] if "Priya" in e["candidate_name"])
    detail = client.get(f"/api/evaluations/{strong['id']}").json()

    evidence = [e for c in detail["criteria"] for e in c["evidence"]]
    assert evidence, "expected at least one cited excerpt"
    for item in evidence:
        assert item["excerpt"].strip()
        # Page or section — a PDF gives both, a DOCX only the section.
        assert item["page_number"] is not None or item["section"]


def test_every_criterion_has_an_outcome_classification(evaluated_campaign, client):
    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    valid = {o.value for o in CriterionOutcome}
    assert all(c["outcome"] in valid for c in detail["criteria"])
    assert all(0.0 <= c["confidence"] <= 1.0 for c in detail["criteria"])


def test_overall_score_is_the_sum_of_weighted_contributions(evaluated_campaign, client):
    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    expected = sum(c["weighted_score"] for c in detail["criteria"])
    assert detail["overall_score"] == pytest.approx(expected, abs=0.05)
    assert 0.0 <= detail["overall_score"] <= 100.0


def test_deterministic_run_makes_no_llm_calls(evaluated_campaign, client):
    """A DETERMINISTIC run must be scoreable with no model available at all."""
    with patch(
        "app.core.llm_provider.get_chat_model",
        side_effect=AssertionError(
            "A model client was constructed during a deterministic run"
        ),
    ):
        client.post(
            f"/api/campaigns/{evaluated_campaign}/evaluations/runs",
            json={"scoring_mode": "DETERMINISTIC"},
        )


def test_llm_failure_falls_back_to_deterministic_scores(evaluated_campaign, client):
    """An LLM outage must not fail a screening run."""
    with patch(
        "app.agents.scoring_agent.refine_criterion_scores",
        side_effect=RuntimeError("groq is down"),
    ):
        response = client.post(
            f"/api/campaigns/{evaluated_campaign}/evaluations/runs",
            json={"scoring_mode": "LLM_ASSISTED"},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    assert all(
        c["raw_score"] == c["deterministic_score"] and not c["llm_adjusted"]
        for c in detail["criteria"]
    )


def test_llm_adjustment_is_clamped_to_the_band(evaluated_campaign, client):
    """A model returning +500 must not produce an out-of-range score."""
    from app.agents import scoring_agent

    def wild(results, index, campaign=None, version=None):
        for result in results:
            if result.evidence:
                result.raw_score = min(
                    result.max_score,
                    result.deterministic_score + scoring_agent.LLM_ADJUSTMENT_BAND,
                )
                result.llm_adjusted = True

    with patch("app.agents.scoring_agent.refine_criterion_scores", side_effect=wild):
        body = client.post(
            f"/api/campaigns/{evaluated_campaign}/evaluations/runs",
            json={"scoring_mode": "LLM_ASSISTED"},
        ).json()

    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    for criterion in detail["criteria"]:
        assert 0.0 <= criterion["raw_score"] <= criterion["max_score"]
        assert abs(criterion["raw_score"] - criterion["deterministic_score"]) <= \
            scoring_agent.LLM_ADJUSTMENT_BAND + 0.01


def test_candidate_with_no_document_is_skipped_not_dropped(evaluated_campaign, client, db_session):
    """An unscoreable candidate must still appear in the run."""
    from app.db.models import Candidate

    orphan = Candidate(campaign_id=evaluated_campaign, full_name="No Document")
    db_session.add(orphan)
    db_session.commit()

    body = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={}
    ).json()
    entry = next(e for e in body["evaluations"] if e["candidate_name"] == "No Document")
    assert entry["status"] == "SKIPPED"
    assert entry["recommendation"] == "REVIEW_REQUIRED"
    assert body["skipped_count"] == 1


# ===========================================================================
# Leaderboard
# ===========================================================================

def test_leaderboard_ranks_and_exposes_criterion_scores(evaluated_campaign, client):
    client.post(f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={})
    rows = client.get(f"/api/campaigns/{evaluated_campaign}/leaderboard").json()

    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert rows == sorted(rows, key=lambda r: -r["overall_score"])
    assert rows[0]["criterion_scores"]
    for row in rows:
        assert "overall_confidence" in row
        assert "eligibility_status" in row


def test_leaderboard_excludes_disqualified_by_default(evaluated_campaign, client, db_session):
    from app.db.models import Evaluation, EligibilityStatus as ES

    client.post(f"/api/campaigns/{evaluated_campaign}/evaluations/runs", json={})
    evaluation = db_session.query(Evaluation).first()
    evaluation.eligibility_status = ES.DISQUALIFIED
    db_session.commit()

    default = client.get(f"/api/campaigns/{evaluated_campaign}/leaderboard").json()
    included = client.get(
        f"/api/campaigns/{evaluated_campaign}/leaderboard",
        params={"include_ineligible": True},
    ).json()
    assert len(included) == len(default) + 1


def test_leaderboard_limit_selects_the_top_scorers_not_the_first_rows(evaluated_campaign, client):
    """X12: `limit` must choose the top-scoring candidates (SQL ORDER BY +
    LIMIT), not just truncate whatever order the full set happened to load
    in — the bug this replaces slices an unbounded `.all()` in Python."""
    campaign_id = evaluated_campaign
    upload(client, campaign_id, [
        ("strong2.pdf", make_cv_pdf(
            STRONG_CV.replace("priya.raman@example.com", "priya.two@example.com")
                      .replace("+91 98765 43210", "+91 98765 40002")
                      .replace("Priya Raman", "Priya Two")
        ), PDF_MIME),
        ("weak2.pdf", make_cv_pdf(
            WEAK_CV.replace("rahul.verma@example.com", "rahul.two@example.com")
                    .replace("+91 91234 56780", "+91 91234 50002")
                    .replace("Rahul Verma", "Rahul Two")
        ), PDF_MIME),
    ])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    full = client.get(f"/api/campaigns/{campaign_id}/leaderboard").json()
    assert len(full) == 4

    limited = client.get(
        f"/api/campaigns/{campaign_id}/leaderboard", params={"limit": 2}
    ).json()
    assert [e["rank"] for e in limited] == [1, 2]
    assert [e["candidate_name"] for e in limited] == [e["candidate_name"] for e in full[:2]]


# ===========================================================================
# Immutability and re-evaluation
# ===========================================================================

def test_rerunning_supersedes_instead_of_overwriting(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    first = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    first_ids = {e["id"] for e in first["evaluations"]}

    second = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    second_ids = {e["id"] for e in second["evaluations"]}
    assert not (first_ids & second_ids), "a re-run must create new rows"

    # The originals are still readable, with their scores intact.
    for evaluation_id in first_ids:
        old = client.get(f"/api/evaluations/{evaluation_id}").json()
        assert old["is_current"] is False
        assert old["superseded_by_evaluation_id"] in second_ids

    current = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    assert {e["id"] for e in current} == second_ids


def test_candidate_history_returns_every_evaluation(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]
    history = client.get(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/evaluations"
    ).json()
    assert len(history) == 2
    assert sum(1 for h in history if h["is_current"]) == 1


def test_there_is_no_endpoint_that_mutates_an_evaluation(client):
    """Results are immutable by construction, not by convention."""
    paths = client.app.openapi()["paths"]
    for path, operations in paths.items():
        if "/evaluations" not in path:
            continue
        for method in operations:
            if method.lower() in ("put", "patch", "delete"):
                pytest.fail(f"{method.upper()} {path} would allow mutating a result")


def test_reevaluation_status_reports_nothing_stale_initially(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    status = client.get(
        f"/api/campaigns/{campaign_id}/evaluations/reevaluation-status"
    ).json()
    assert status["counts"]["stale"] == 0
    assert status["counts"]["current"] == 2
    assert status["reevaluation_required"] is False


def test_approving_a_new_rubric_version_makes_results_stale(evaluated_campaign, client):
    """
    The Phase B hook. Approving v2 sets reevaluation_required and re-scores
    nothing; Phase D reports which results are now stale.
    """
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1, "change_reason": "Reweight skills"},
    )
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/2/submit", json={})
    approved = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/2/approve",
        json={"approved_by": "Priya Nair"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["reevaluation_required"] is True

    status = client.get(
        f"/api/campaigns/{campaign_id}/evaluations/reevaluation-status"
    ).json()
    assert status["active_version_number"] == 2
    assert status["reevaluation_required"] is True
    assert status["counts"]["stale"] == 2
    assert all(c["scored_under_version"] == 1 for c in status["stale_candidates"])
    assert "re-evaluation" in status["action_required"].lower()


def test_reevaluation_rescores_against_the_new_version(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1, "change_reason": "Reweight"},
    )
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/2/submit", json={})
    client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions/2/approve",
        json={"approved_by": "Priya Nair"},
    )

    version_2_id = client.get(f"/api/campaigns/{campaign_id}/rubric/active").json()["id"]
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/reevaluate").json()
    assert run["trigger"] == "REEVALUATION"
    assert run["rubric_version_id"] == version_2_id
    assert run["evaluated_count"] == 2

    status = client.get(
        f"/api/campaigns/{campaign_id}/evaluations/reevaluation-status"
    ).json()
    assert status["counts"]["stale"] == 0

    history = client.get(
        f"/api/campaigns/{campaign_id}/evaluations", params={"current_only": False}
    ).json()
    assert len(history) == 4  # two candidates x two rubric versions


def test_reevaluation_with_nothing_stale_is_rejected(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    response = client.post(f"/api/campaigns/{campaign_id}/evaluations/reevaluate")
    assert response.status_code == 422
    assert "current" in str(response.json()["detail"]).lower()


def test_only_unevaluated_skips_already_scored_candidates(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    second = client.post(
        f"/api/campaigns/{campaign_id}/evaluations/runs",
        json={"only_unevaluated": True},
    ).json()
    assert second["total_candidates"] == 0
    assert second["evaluated_count"] == 0


def test_batch_scoped_run_uses_the_batch_pinned_version(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    batch_id = client.get(f"/api/campaigns/{campaign_id}/batches").json()[0]["id"]
    pinned = client.get(
        f"/api/processing/batches/{batch_id}"
    ).json()["batch"]["rubric_version_id"]

    run = client.post(
        f"/api/campaigns/{campaign_id}/evaluations/runs", json={"batch_id": batch_id}
    ).json()
    assert run["batch_id"] == batch_id
    assert run["rubric_version_id"] == pinned


def test_run_is_rejected_for_a_draft_rubric_version(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    draft = client.post(
        f"/api/campaigns/{campaign_id}/rubric/versions",
        json={"clone_from_version": 1, "change_reason": "wip"},
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign_id}/evaluations/runs",
        json={"rubric_version_id": draft["id"]},
    )
    assert response.status_code == 422
    assert "DRAFT" in str(response.json()["detail"])


def test_run_is_rejected_for_another_campaigns_rubric_version(evaluated_campaign, client):
    """Scoring against a foreign rubric would silently produce nonsense."""
    other = client.post("/api/campaigns", json={
        "name": "Other", "job_title": "Analyst", "job_description": "y",
    }).json()["id"]
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        client.post(f"/api/campaigns/{other}/requirements/extract", json={})
    client.post(f"/api/campaigns/{other}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{other}/rubric/versions/1/submit", json={})
    foreign = client.post(
        f"/api/campaigns/{other}/rubric/versions/1/approve",
        json={"approved_by": "x"},
    ).json()

    response = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs",
        json={"rubric_version_id": foreign["id"]},
    )
    assert response.status_code == 422
    assert "does not belong" in str(response.json()["detail"])


def test_unknown_candidate_ids_are_rejected(evaluated_campaign, client):
    response = client.post(
        f"/api/campaigns/{evaluated_campaign}/evaluations/runs",
        json={"candidate_ids": ["not-a-real-candidate"]},
    )
    assert response.status_code == 422


def test_campaign_moves_to_review_once_results_exist(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    assert client.get(f"/api/campaigns/{campaign_id}").json()["status"] == "PROCESSING"
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    assert client.get(f"/api/campaigns/{campaign_id}").json()["status"] == "REVIEW"


def test_runs_are_listed_newest_first(evaluated_campaign, client):
    campaign_id = evaluated_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    runs = client.get(f"/api/campaigns/{campaign_id}/evaluations/runs").json()
    assert len(runs) == 2
    assert runs[0]["created_at"] >= runs[1]["created_at"]


def test_docx_candidate_is_scored_with_section_references(client):
    """DOCX has no pages, so citation must fall back to sections cleanly."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Docx campaign", "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "x"})
    upload(client, campaign_id, [("cv.docx", make_docx(STRONG_CV), DOCX_MIME)])

    body = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    assert body["evaluated_count"] == 1
    detail = client.get(f"/api/evaluations/{body['evaluations'][0]['id']}").json()
    evidence = [e for c in detail["criteria"] for e in c["evidence"]]
    assert evidence
    assert all(e["page_number"] is None for e in evidence)
    assert any(e["section"] for e in evidence)
