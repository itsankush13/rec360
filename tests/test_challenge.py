"""
Phase E tests — Challenge Agent.

The engine is driven directly with plain objects for the unit tests. That is
deliberate: every one of the client's six checks is structural, so each can
be provoked exactly rather than hoped for, and the assertions say what the
check is actually for instead of what a particular CV happened to trigger.

The overriding property, asserted several ways below: a finding never
changes a score, an outcome or an eligibility verdict.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core import challenge_engine
from app.db.models import (
    ChallengeCheck, ChallengeScope, ChallengeSeverity, ConfidenceBand,
    CriterionOutcome, EvaluationStatus, Recommendation, RequirementType,
)

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, WEAK_CV, make_cv_pdf


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def criterion(
    key="pg", label="PostgreSQL experience", *, weight=25.0, raw=100.0,
    deterministic=None, llm_adjusted=False, outcome=CriterionOutcome.CONFIRMED_MATCH,
    evidence_count=2, confidence=0.85, band=ConfidenceBand.HIGH,
    requirement_type=RequirementType.MANDATORY, matched=None, equivalents=None,
):
    return SimpleNamespace(
        id=f"c-{key}", criterion_key=key, label=label, weight=weight,
        max_score=100.0, raw_score=raw,
        deterministic_score=raw if deterministic is None else deterministic,
        llm_adjusted=llm_adjusted, outcome=outcome, evidence_count=evidence_count,
        confidence=confidence, confidence_band=band,
        requirement_type=requirement_type,
        matched_terms=matched if matched is not None else [key],
        equivalent_terms=equivalents or [],
    )


def evaluation(
    eid="e1", *, criteria=None, score=70.0, mandatory=70.0, confidence=0.8,
    band=ConfidenceBand.HIGH, recommendation=Recommendation.POTENTIAL_FIT,
    contradictions=None, status=EvaluationStatus.COMPLETED, run_id="run-1",
):
    return SimpleNamespace(
        id=eid, run_id=run_id, status=status, overall_score=score,
        mandatory_score=mandatory, overall_confidence=confidence,
        confidence_band=band, recommendation=recommendation,
        contradictions=contradictions or [],
        criteria=criteria if criteria is not None else [criterion()],
    )


def checks(report):
    return {f.check for f in report.findings}


# ===========================================================================
# 1. Unsupported conclusions
# ===========================================================================

def test_large_model_adjustment_is_flagged():
    """
    Phase D persists deterministic_score precisely so this is detectable.
    The model saw the same excerpts, so a big delta adds no evidence.
    """
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=95.0, deterministic=80.0, llm_adjusted=True)
    ])])
    assert ChallengeCheck.UNSUPPORTED_CONCLUSION in checks(report)
    finding = next(
        f for f in report.findings
        if f.check == ChallengeCheck.UNSUPPORTED_CONCLUSION
    )
    assert finding.severity == ChallengeSeverity.HIGH
    assert finding.observed["adjustment"] == 15.0


def test_small_model_adjustment_is_not_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=82.0, deterministic=80.0, llm_adjusted=True)
    ])])
    assert ChallengeCheck.UNSUPPORTED_CONCLUSION not in checks(report)


def test_deterministic_run_produces_no_unsupported_findings():
    """Nothing was adjusted, so nothing can be unsupported on that basis."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=100.0, llm_adjusted=False)
    ])])
    assert ChallengeCheck.UNSUPPORTED_CONCLUSION not in checks(report)


def test_confirmed_match_with_no_evidence_is_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(outcome=CriterionOutcome.CONFIRMED_MATCH, evidence_count=0)
    ])])
    assert ChallengeCheck.UNSUPPORTED_CONCLUSION in checks(report)


def test_score_carried_by_preferred_criteria_is_flagged():
    """A candidate can rank highly while meeting the essentials poorly."""
    report = challenge_engine.review([
        evaluation(score=85.0, mandatory=50.0)
    ])
    finding = next(
        f for f in report.findings
        if f.check == ChallengeCheck.UNSUPPORTED_CONCLUSION
        and f.scope == ChallengeScope.EVALUATION
    )
    assert finding.severity == ChallengeSeverity.HIGH
    assert "mandatory" in finding.detail.lower()


# ===========================================================================
# 2. Missing and weak evidence
# ===========================================================================

def test_score_with_no_cited_excerpt_is_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=70.0, outcome=CriterionOutcome.PARTIAL_MATCH, evidence_count=0)
    ])])
    assert ChallengeCheck.MISSING_EVIDENCE in checks(report)


def test_zero_score_with_no_evidence_is_not_a_missing_evidence_finding():
    """Nothing was claimed, so nothing needs citing."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=0.0, outcome=CriterionOutcome.NOT_DEMONSTRATED, evidence_count=0)
    ])])
    assert ChallengeCheck.MISSING_EVIDENCE not in checks(report)


def test_unweighted_criterion_is_not_flagged_for_evidence():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(weight=0.0, raw=80.0, evidence_count=0)
    ])])
    assert ChallengeCheck.MISSING_EVIDENCE not in checks(report)


def test_material_criterion_on_low_confidence_is_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(weight=30.0, raw=80.0, outcome=CriterionOutcome.PARTIAL_MATCH,
                  confidence=0.3, band=ConfidenceBand.LOW)
    ])])
    assert ChallengeCheck.WEAK_EVIDENCE in checks(report)


def test_credit_from_adjacency_only_is_flagged():
    """Partial credit for a related skill is fine; passing silently is not."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=55.0, outcome=CriterionOutcome.PARTIAL_MATCH,
                  matched=[], equivalents=["mysql ~ PostgreSQL (related)"])
    ])])
    finding = next(
        f for f in report.findings if f.check == ChallengeCheck.WEAK_EVIDENCE
    )
    assert "related skill" in finding.title.lower()


# ===========================================================================
# 3. Contradictions
# ===========================================================================

def test_contradictory_criterion_is_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion(raw=0.0, outcome=CriterionOutcome.CONTRADICTORY_EVIDENCE)
    ])])
    assert ChallengeCheck.CONTRADICTION in checks(report)


def test_contradiction_on_a_mandatory_criterion_is_high_severity():
    mandatory = challenge_engine.review([evaluation(criteria=[
        criterion(outcome=CriterionOutcome.CONTRADICTORY_EVIDENCE,
                  requirement_type=RequirementType.MANDATORY)
    ])])
    preferred = challenge_engine.review([evaluation(criteria=[
        criterion(outcome=CriterionOutcome.CONTRADICTORY_EVIDENCE,
                  requirement_type=RequirementType.PREFERRED)
    ])])
    assert mandatory.findings[0].severity == ChallengeSeverity.HIGH
    assert preferred.findings[0].severity == ChallengeSeverity.MEDIUM


def test_experience_contradictions_are_surfaced_not_rederived():
    """
    Phase D's experience engine already found these. Surfacing them keeps
    the two layers from ever disagreeing.
    """
    report = challenge_engine.review([evaluation(contradictions=[
        {"type": "EXPERIENCE_CLAIM_MISMATCH",
         "detail": "The CV claims 15 years but the timeline covers 6.",
         "severity": "HIGH"},
    ])])
    finding = next(
        f for f in report.findings
        if f.observed and f.observed.get("type") == "EXPERIENCE_CLAIM_MISMATCH"
    )
    assert finding.severity == ChallengeSeverity.HIGH
    assert "15 years" in finding.detail


# ===========================================================================
# 4. Weighting anomalies
# ===========================================================================

def test_dominant_criterion_is_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=70.0), criterion("b", weight=20.0),
        criterion("c", weight=10.0),
    ])])
    finding = next(
        f for f in report.findings if f.check == ChallengeCheck.WEIGHTING_ANOMALY
    )
    assert finding.scope == ChallengeScope.RUN
    assert finding.observed["share"] == pytest.approx(0.7, abs=0.01)


def test_balanced_weights_are_not_flagged():
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=30.0), criterion("b", weight=25.0),
        criterion("c", weight=25.0), criterion("d", weight=20.0),
    ])])
    assert ChallengeCheck.WEIGHTING_ANOMALY not in checks(report)


def test_preferred_outweighing_mandatory_is_high_severity():
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=20.0, requirement_type=RequirementType.MANDATORY),
        criterion("b", weight=40.0, requirement_type=RequirementType.PREFERRED),
        criterion("c", weight=40.0, requirement_type=RequirementType.PREFERRED),
    ])])
    finding = next(
        f for f in report.findings
        if f.check == ChallengeCheck.WEIGHTING_ANOMALY
        and "outweigh" in f.title.lower()
    )
    assert finding.severity == ChallengeSeverity.HIGH


def test_zero_weight_mandatory_criterion_is_flagged():
    """A mandatory criterion with no weight does not affect the score at all."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=100.0, requirement_type=RequirementType.PREFERRED),
        criterion("b", weight=0.0, label="Right to work",
                  requirement_type=RequirementType.MANDATORY),
    ])])
    assert any(
        "no weight" in f.title.lower() for f in report.findings
    )


def test_weighting_findings_attach_to_the_run_not_a_candidate():
    """A rubric anomaly concerns everyone, so it must not read as personal."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=80.0), criterion("b", weight=20.0),
    ])])
    for finding in report.findings:
        if finding.check == ChallengeCheck.WEIGHTING_ANOMALY:
            assert finding.scope == ChallengeScope.RUN
            assert finding.evaluation_id is None


# ===========================================================================
# 5. Unusually high or low recommendations
# ===========================================================================

def test_strong_fit_on_low_confidence_is_flagged():
    report = challenge_engine.review([evaluation(
        score=88.0, mandatory=85.0, confidence=0.55,
        band=ConfidenceBand.MEDIUM, recommendation=Recommendation.STRONG_FIT,
    )])
    assert ChallengeCheck.OUTLIER_RECOMMENDATION in checks(report)


def test_score_far_from_the_run_mean_is_flagged():
    evaluations = [
        evaluation(f"e{i}", score=score, mandatory=score)
        for i, score in enumerate([50.0, 52.0, 48.0, 51.0, 49.0, 98.0])
    ]
    report = challenge_engine.review(evaluations)
    outliers = [
        f for f in report.findings
        if f.check == ChallengeCheck.OUTLIER_RECOMMENDATION
        and f.observed and "run_mean" in f.observed
    ]
    assert outliers
    assert outliers[0].observed["overall_score"] == 98.0
    # Never a figure without its denominator — web/DATA.md's rule.
    assert "candidates_assessed" in outliers[0].observed


def test_no_outlier_claim_on_a_tiny_run():
    """Three candidates have no meaningful distribution; claiming one lies."""
    evaluations = [
        evaluation(f"e{i}", score=score, mandatory=score)
        for i, score in enumerate([10.0, 50.0, 95.0])
    ]
    report = challenge_engine.review(evaluations)
    assert not [
        f for f in report.findings
        if f.observed and "run_mean" in (f.observed or {})
    ]


def test_identical_scores_produce_no_outliers():
    evaluations = [
        evaluation(f"e{i}", score=60.0, mandatory=60.0) for i in range(5)
    ]
    report = challenge_engine.review(evaluations)
    assert not [
        f for f in report.findings
        if f.observed and "run_mean" in (f.observed or {})
    ]


# ===========================================================================
# 6. Inconsistent scoring
# ===========================================================================

def test_comparable_evidence_scored_differently_is_flagged():
    """Same criterion, same matched-term count, 60 points apart."""
    report = challenge_engine.review([
        evaluation("e1", criteria=[criterion("pg", raw=90.0, matched=["postgresql"])]),
        evaluation("e2", criteria=[criterion("pg", raw=25.0, matched=["postgresql"])]),
    ])
    finding = next(
        f for f in report.findings if f.check == ChallengeCheck.INCONSISTENT_SCORING
    )
    assert finding.observed["score_gap"] == pytest.approx(65.0)
    assert finding.criterion_key == "pg"


def test_similar_scores_are_not_flagged_as_inconsistent():
    report = challenge_engine.review([
        evaluation("e1", criteria=[criterion("pg", raw=90.0, matched=["postgresql"])]),
        evaluation("e2", criteria=[criterion("pg", raw=80.0, matched=["postgresql"])]),
    ])
    assert ChallengeCheck.INCONSISTENT_SCORING not in checks(report)


def test_different_evidence_counts_are_not_compared():
    """Two matched terms versus none is not comparable evidence."""
    report = challenge_engine.review([
        evaluation("e1", criteria=[criterion("pg", raw=95.0, matched=["a", "b"])]),
        evaluation("e2", criteria=[criterion("pg", raw=10.0, matched=[])]),
    ])
    assert ChallengeCheck.INCONSISTENT_SCORING not in checks(report)


# ===========================================================================
# Engine behaviour
# ===========================================================================

def test_findings_are_ordered_worst_first():
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=70.0),
        criterion("b", weight=15.0, outcome=CriterionOutcome.CONFIRMED_MATCH,
                  evidence_count=0),
        criterion("c", weight=15.0, raw=60.0,
                  outcome=CriterionOutcome.PARTIAL_MATCH, confidence=0.2,
                  band=ConfidenceBand.LOW),
    ])])
    rank = {
        ChallengeSeverity.HIGH: 0, ChallengeSeverity.MEDIUM: 1,
        ChallengeSeverity.LOW: 2, ChallengeSeverity.INFO: 3,
    }
    severities = [rank[f.severity] for f in report.findings]
    assert severities == sorted(severities)
    assert [f.display_order for f in report.findings] == list(range(len(report.findings)))


def test_clean_evaluation_produces_no_findings():
    """The reviewer must not manufacture concerns to look useful."""
    report = challenge_engine.review([evaluation(criteria=[
        criterion("a", weight=34.0), criterion("b", weight=33.0),
        criterion("c", weight=33.0),
    ])])
    assert report.findings == []
    assert report.risk_level == ChallengeSeverity.INFO


def test_failed_evaluations_are_not_reviewed():
    report = challenge_engine.review([
        evaluation("e1", status=EvaluationStatus.FAILED),
        evaluation("e2", status=EvaluationStatus.SKIPPED),
    ])
    assert report.findings == []


def test_review_is_deterministic():
    def build():
        return [evaluation(criteria=[
            criterion("a", weight=70.0),
            criterion("b", weight=30.0, evidence_count=0,
                      outcome=CriterionOutcome.CONFIRMED_MATCH),
        ])]

    first = challenge_engine.review(build())
    second = challenge_engine.review(build())
    assert [(f.check, f.severity, f.title) for f in first.findings] == \
           [(f.check, f.severity, f.title) for f in second.findings]


def test_review_does_not_mutate_the_evaluations_it_reads():
    """The hard rule: a reviewer, not a second scorer."""
    subject = evaluation(criteria=[
        criterion(raw=95.0, deterministic=80.0, llm_adjusted=True)
    ])
    before = (
        subject.overall_score, subject.mandatory_score, subject.recommendation,
        subject.criteria[0].raw_score, subject.criteria[0].outcome,
    )
    challenge_engine.review([subject])
    after = (
        subject.overall_score, subject.mandatory_score, subject.recommendation,
        subject.criteria[0].raw_score, subject.criteria[0].outcome,
    )
    assert before == after


def test_engine_needs_no_model():
    """All six checks are structural, so no LLM is involved at any point."""
    with patch(
        "app.core.llm_provider.get_chat_model",
        side_effect=AssertionError(
            "A model client was constructed during a deterministic run"
        ),
    ):
        challenge_engine.review([evaluation(criteria=[
            criterion(raw=95.0, deterministic=70.0, llm_adjusted=True)
        ])])


# ===========================================================================
# API and persistence
# ===========================================================================

@pytest.fixture()
def reviewed_campaign(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Challenge review", "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [
        ("strong.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("weak.pdf", make_cv_pdf(WEAK_CV), PDF_MIME),
    ])
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    return campaign_id, run["id"]


def test_findings_are_persisted_by_a_run(reviewed_campaign, client):
    _, run_id = reviewed_campaign
    response = client.get(f"/api/evaluations/runs/{run_id}/challenge")
    assert response.status_code == 200
    for finding in response.json():
        assert finding["check"] in {c.value for c in ChallengeCheck}
        assert finding["severity"] in {s.value for s in ChallengeSeverity}
        assert finding["title"]
        assert finding["engine_version"]


def test_findings_can_be_filtered_by_severity(reviewed_campaign, client):
    _, run_id = reviewed_campaign
    high = client.get(
        f"/api/evaluations/runs/{run_id}/challenge", params={"severity": "HIGH"}
    ).json()
    assert all(f["severity"] == "HIGH" for f in high)


def test_candidate_360_carries_challenge_findings(reviewed_campaign, client):
    """One of the sixteen required Candidate 360 sections."""
    campaign_id, run_id = reviewed_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    detail = client.get(f"/api/evaluations/{evaluations[0]['id']}").json()
    assert "challenge_findings" in detail
    for finding in detail["challenge_findings"]:
        # Either this candidate's own finding, or a run-scoped one.
        assert finding["evaluation_id"] in (evaluations[0]["id"], None)


def test_challenge_findings_have_no_mutation_endpoint(client):
    """Findings are immutable, like the evaluations they comment on."""
    paths = client.app.openapi()["paths"]
    for path, operations in paths.items():
        if "challenge" not in path:
            continue
        for method in operations:
            assert method.lower() == "get", f"{method.upper()} {path}"


def test_review_failure_does_not_lose_the_scoring_run(reviewed_campaign, client):
    """
    Scores are the deliverable; findings are commentary. A bug in the
    reviewer must not sink a completed run.
    """
    campaign_id, _ = reviewed_campaign
    with patch(
        "app.core.challenge_engine.review", side_effect=RuntimeError("reviewer bug")
    ):
        response = client.post(
            f"/api/campaigns/{campaign_id}/evaluations/runs", json={}
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["evaluated_count"] == 2


def test_findings_do_not_change_scores(reviewed_campaign, client):
    """End-to-end version of the same guarantee."""
    campaign_id, run_id = reviewed_campaign
    before = {
        e["id"]: e["overall_score"]
        for e in client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    }
    findings = client.get(f"/api/evaluations/runs/{run_id}/challenge").json()
    assert isinstance(findings, list)
    after = {
        e["id"]: e["overall_score"]
        for e in client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    }
    assert before == after


def test_unknown_run_is_404(client):
    assert client.get("/api/evaluations/runs/nope/challenge").status_code == 404
