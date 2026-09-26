"""
Phase F tests — Candidate 360 completion, recruiter disposition, override,
audit trail, benchmarks.

The central assertion, made several ways: a recruiter decision never mutates
an evaluation. If a human overrules the machine and the machine's record is
edited to match, there is no longer any evidence the disagreement happened —
which is the one thing an audit needs.
"""
from unittest.mock import patch

import pytest

from app.core import candidate_360
from app.db.models import (
    ConfidenceBand, CriterionOutcome, Disposition, EligibilityStatus,
    NextAction, Recommendation, RequirementCategory,
)

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, WEAK_CV, make_cv_pdf
from tests.test_challenge import criterion as make_criterion


@pytest.fixture()
def decided_campaign(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Phase F", "job_title": "Senior Software Engineer",
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
    candidates = client.get(f"/api/campaigns/{campaign_id}/candidates").json()
    return campaign_id, run["id"], candidates[0]["id"]


# ===========================================================================
# Category rollups
# ===========================================================================

def result(key, category, *, weight, raw, confidence=0.8,
           outcome=CriterionOutcome.CONFIRMED_MATCH):
    obj = make_criterion(key, weight=weight, raw=raw, confidence=confidence,
                         outcome=outcome)
    obj.category = category
    obj.weighted_score = raw / 100.0 * weight
    return obj


def test_rollup_uses_the_categorys_own_weight_as_denominator():
    """
    Not `sum(weighted_score)` — that would express skills as a share of the
    whole rubric, so a perfect score on 20 points of skills criteria would
    read as 20/100 on skills.
    """
    rollups = candidate_360.category_rollups([
        result("a", RequirementCategory.SKILL, weight=20.0, raw=100.0),
        result("b", RequirementCategory.EXPERIENCE, weight=80.0, raw=50.0),
    ])
    assert rollups["SKILL"]["score"] == pytest.approx(100.0)
    assert rollups["EXPERIENCE"]["score"] == pytest.approx(50.0)


def test_rollup_is_weight_weighted_within_a_category():
    rollups = candidate_360.category_rollups([
        result("a", RequirementCategory.SKILL, weight=30.0, raw=100.0),
        result("b", RequirementCategory.SKILL, weight=10.0, raw=0.0),
    ])
    assert rollups["SKILL"]["score"] == pytest.approx(75.0)


def test_absent_category_is_none_not_zero():
    """
    "Not assessed" and "assessed and scored zero" are different claims about
    a candidate.
    """
    rollups = candidate_360.category_rollups([
        result("a", RequirementCategory.SKILL, weight=100.0, raw=80.0),
    ])
    named = candidate_360.named_rollups(rollups)
    assert named["skills_score"] == pytest.approx(80.0)
    assert named["certification_score"] is None
    assert named["education_score"] is None


def test_unweighted_criteria_are_excluded_from_rollups():
    rollups = candidate_360.category_rollups([
        result("a", RequirementCategory.SKILL, weight=0.0, raw=0.0),
    ])
    assert "SKILL" not in rollups


# ===========================================================================
# Recommended next action
# ===========================================================================

def _action(**kwargs):
    defaults = dict(
        eligibility_status=EligibilityStatus.ELIGIBLE,
        recommendation=Recommendation.POTENTIAL_FIT,
        confidence_band=ConfidenceBand.HIGH,
        has_indeterminate=False,
        high_severity_findings=0,
        insufficient_criteria=0,
    )
    defaults.update(kwargs)
    return candidate_360.next_action(**defaults)


def test_disqualified_candidate_is_rejected():
    action, reason = _action(eligibility_status=EligibilityStatus.DISQUALIFIED)
    assert action == NextAction.REJECT
    assert "cannot overturn" in reason


def test_indeterminate_eligibility_outranks_everything_else():
    """An unproven mandatory condition must be settled before anything else."""
    action, reason = _action(
        has_indeterminate=True, recommendation=Recommendation.STRONG_FIT,
        high_severity_findings=3,
    )
    assert action == NextAction.CONFIRM_ELIGIBILITY
    assert "not been failed" in reason


def test_high_severity_findings_force_manual_review():
    action, _ = _action(
        recommendation=Recommendation.STRONG_FIT, high_severity_findings=2
    )
    assert action == NextAction.MANUAL_REVIEW


def test_low_confidence_forces_manual_review():
    action, reason = _action(confidence_band=ConfidenceBand.LOW)
    assert action == NextAction.MANUAL_REVIEW
    assert "document more than the candidate" in reason


def test_several_unassessable_criteria_request_evidence():
    action, _ = _action(insufficient_criteria=3)
    assert action == NextAction.REQUEST_EVIDENCE


def test_clean_strong_candidate_goes_to_interview():
    action, _ = _action(recommendation=Recommendation.STRONG_FIT)
    assert action == NextAction.INTERVIEW


def test_every_next_action_carries_a_reason():
    for kwargs in (
        {"eligibility_status": EligibilityStatus.DISQUALIFIED},
        {"has_indeterminate": True},
        {"high_severity_findings": 1},
        {"confidence_band": ConfidenceBand.LOW},
        {"insufficient_criteria": 5},
        {"recommendation": Recommendation.STRONG_FIT},
        {"recommendation": Recommendation.NOT_RECOMMENDED},
        {"recommendation": Recommendation.REVIEW_REQUIRED},
    ):
        _, reason = _action(**kwargs)
        assert reason.strip(), kwargs


# ===========================================================================
# Validation questions and interview focus
# ===========================================================================

def test_questions_come_from_findings_not_a_model():
    results = [
        result("kafka", RequirementCategory.SKILL, weight=20.0, raw=0.0,
               outcome=CriterionOutcome.INSUFFICIENT_EVIDENCE),
    ]
    questions = candidate_360.validation_questions(results, [], None)
    assert questions
    assert questions[0]["source"] == "criterion"
    assert questions[0]["reference"] == "kafka"


def test_indeterminate_eligibility_produces_a_high_priority_question():
    from types import SimpleNamespace
    finding = SimpleNamespace(
        indeterminate=True, code="MIN_YEARS",
        label="Minimum 8 years of experience",
    )
    questions = candidate_360.validation_questions([], [finding], None)
    assert questions[0]["priority"] == "HIGH"
    assert questions[0]["source"] == "eligibility"


def test_experience_contradictions_produce_questions():
    from types import SimpleNamespace
    profile = SimpleNamespace(contradictions=[
        {"type": "EMPLOYMENT_GAP", "detail": "A 25-month gap."},
        {"type": "EXPERIENCE_CLAIM_MISMATCH", "detail": "Claims 15, timeline shows 6."},
    ])
    questions = candidate_360.validation_questions([], [], profile)
    sources = {q["reference"] for q in questions}
    assert "EMPLOYMENT_GAP" in sources
    assert "EXPERIENCE_CLAIM_MISMATCH" in sources


def test_clean_candidate_generates_no_questions():
    """The system must not invent questions to look thorough."""
    results = [
        result("a", RequirementCategory.SKILL, weight=100.0, raw=100.0),
    ]
    assert candidate_360.validation_questions(results, [], None) == []


def test_questions_are_capped():
    results = [
        result(f"c{i}", RequirementCategory.SKILL, weight=5.0, raw=0.0,
               outcome=CriterionOutcome.INSUFFICIENT_EVIDENCE)
        for i in range(20)
    ]
    assert len(candidate_360.validation_questions(results, [], None)) \
        <= candidate_360.MAX_QUESTIONS


def test_partial_matches_drive_interview_focus():
    results = [
        result("pg", RequirementCategory.SKILL, weight=30.0, raw=55.0,
               outcome=CriterionOutcome.PARTIAL_MATCH),
    ]
    focus = candidate_360.interview_focus(results, {})
    assert focus
    assert focus[0]["criterion_key"] == "pg"


# ===========================================================================
# Benchmarks
# ===========================================================================

def test_benchmarks_need_at_least_four_candidates():
    """A median across two people is meaningless; claiming one is worse."""
    assert candidate_360.benchmarks([50.0, 70.0]) is None
    assert candidate_360.benchmarks([50.0, 60.0, 70.0, 80.0]) is not None


def test_benchmarks_report_the_distribution():
    stats = candidate_360.benchmarks([40.0, 50.0, 60.0, 70.0, 80.0])
    assert stats["median"] == pytest.approx(60.0)
    assert stats["lowest"] == 40.0
    assert stats["highest"] == 80.0
    assert stats["candidates_assessed"] == 5


def test_percentile_always_reports_its_denominator():
    """web/DATA.md forbids a percentage without one."""
    position = candidate_360.percentile_of(80.0, [40.0, 50.0, 60.0, 70.0, 80.0])
    assert position["out_of"] == 5
    assert position["rank"] == 1
    assert "of 5" in position["statement"]


def test_percentile_is_none_on_a_tiny_campaign():
    assert candidate_360.percentile_of(80.0, [70.0, 80.0]) is None


# ===========================================================================
# API — Candidate 360 fields
# ===========================================================================

def test_candidate_360_carries_the_phase_f_sections(decided_campaign, client):
    campaign_id, _, _ = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    detail = client.get(f"/api/evaluations/{evaluations[0]['id']}").json()

    for field in (
        "skills_score", "experience_score", "education_score",
        "certification_score", "category_scores", "next_action",
        "next_action_reason", "validation_questions", "interview_focus",
    ):
        assert field in detail, field
    assert detail["next_action"] in {a.value for a in NextAction}
    assert detail["next_action_reason"]


def test_category_scores_are_consistent_with_the_overall_score(decided_campaign, client):
    """Guards against the double-scaling bug class."""
    campaign_id, _, _ = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    detail = client.get(f"/api/evaluations/{evaluations[0]['id']}").json()

    for value in detail["category_scores"].values():
        assert 0.0 <= value["score"] <= 100.0
    for field in ("skills_score", "experience_score", "education_score",
                  "certification_score"):
        if detail[field] is not None:
            assert 0.0 <= detail[field] <= 100.0


# ===========================================================================
# API — disposition and override
# ===========================================================================

def test_disposition_is_recorded(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    response = client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["disposition"] == "SHORTLIST"
    assert body["action_type"] == "DISPOSITION"
    assert body["ai_recommendation"]


def test_disposition_does_not_change_the_evaluation(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    before = {e["id"]: (e["overall_score"], e["recommendation"]) for e in evaluations}

    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "REJECT", "actor": "x"},
    )
    after = {
        e["id"]: (e["overall_score"], e["recommendation"])
        for e in client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    }
    assert before == after


def test_override_requires_a_reason(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    response = client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/override",
        json={"overridden_to": "STRONG_FIT", "reason": ""},
    )
    assert response.status_code == 422


def test_override_leaves_the_ai_recommendation_intact(decided_campaign, client):
    """
    The central guarantee: both views survive, so the disagreement is on the
    record.
    """
    campaign_id, _, candidate_id = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    mine = next(e for e in evaluations if e["candidate_id"] == candidate_id)
    original = mine["recommendation"]
    target = "STRONG_FIT" if original != "STRONG_FIT" else "NOT_RECOMMENDED"

    response = client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/override",
        json={"overridden_to": target, "reason": "Spoke to them; depth is there.",
              "actor": "Fatima Al-Rashid"},
    )
    assert response.status_code == 201

    detail = client.get(f"/api/evaluations/{mine['id']}").json()
    assert detail["recommendation"] == original

    effective = client.get(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/recommendation"
    ).json()
    assert effective["ai_recommendation"] == original
    assert effective["effective_recommendation"] == target
    assert effective["is_overridden"] is True
    assert effective["override_reason"]


def test_effective_recommendation_suggests_a_rationale_draft(decided_campaign, client):
    """
    B05: a starting draft for the comment box, built from the evaluation's
    own evidence — never a silent decision. The recruiter still saves their
    own comment; this only saves them typing the same summary from scratch.

    The brief itself is now genuinely LLM-generated, so the LLM call is
    stubbed here rather than hitting a real provider — this repo's test suite
    never calls a real LLM (see test_evaluations.test_deterministic_run_makes_
    no_llm_calls), and the score line is guaranteed to survive verbatim
    regardless of what the (stubbed) LLM returns.
    """
    from app.services import disposition_service

    campaign_id, _, candidate_id = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    mine = next(e for e in evaluations if e["candidate_id"] == candidate_id)

    with patch.object(
        disposition_service, "_llm_brief_rationale",
        return_value="He has strong, directly relevant experience. One open question is worth checking before a final call.",
    ):
        effective = client.get(
            f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/recommendation"
        ).json()
    rationale = effective["suggested_rationale"]
    assert rationale
    assert "AI assessment" not in rationale
    assert str(round(mine["overall_score"])) in rationale


def test_suggested_rationale_is_cached_after_first_generation(decided_campaign, client):
    """
    An Evaluation is write-once, so its rationale is generated once and
    reused — not re-billed to the LLM on every Candidate 360 page view.
    """
    from app.services import disposition_service

    campaign_id, _, candidate_id = decided_campaign
    url = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/recommendation"

    with patch.object(
        disposition_service, "_llm_brief_rationale",
        return_value=(
            "- **Overall: brief, plain-language summary of the evidence.**\n"
            "- Nothing further to add for this stub."
        ),
    ) as mock_llm:
        first = client.get(url).json()["suggested_rationale"]
        second = client.get(url).json()["suggested_rationale"]

    assert first == second
    assert mock_llm.call_count == 1


def test_suggested_rationale_falls_back_to_template_when_llm_unavailable(decided_campaign, client):
    """
    A missing/misbehaving provider must never break the comment-box draft —
    it degrades to the same deterministic bulleted text this function always
    produced, not a 500.
    """
    from app.services import disposition_service

    campaign_id, _, candidate_id = decided_campaign
    with patch.object(disposition_service, "_llm_brief_rationale", return_value=None):
        effective = client.get(
            f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/recommendation"
        ).json()
    rationale = effective["suggested_rationale"]
    assert rationale
    assert "AI assessment" not in rationale
    assert "Score:" in rationale


def test_suggested_rationale_is_empty_with_no_evaluation(db_session):
    """No evaluation exists yet, so there is nothing honest to draft from."""
    from app.db.models import Campaign, Candidate
    from app.services import disposition_service

    campaign = Campaign(name="No evaluation yet", job_title="Engineer")
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    candidate = Candidate(campaign_id=campaign.id, full_name="Unassessed")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    effective = disposition_service.effective_recommendation(db_session, candidate.id)
    assert effective["suggested_rationale"] == ""


def test_override_to_the_same_recommendation_is_rejected(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    mine = next(e for e in evaluations if e["candidate_id"] == candidate_id)
    response = client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/override",
        json={"overridden_to": mine["recommendation"], "reason": "same"},
    )
    assert response.status_code == 422
    assert "nothing to override" in str(response.json()["detail"])


def test_changing_a_decision_supersedes_rather_than_edits(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    base = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}"
    first = client.post(f"{base}/disposition", json={"disposition": "HOLD"}).json()
    second = client.post(f"{base}/disposition", json={"disposition": "SHORTLIST"}).json()

    history = client.get(f"{base}/actions").json()
    assert len(history) == 2
    superseded = next(a for a in history if a["id"] == first["id"])
    assert superseded["is_current"] is False
    assert superseded["superseded_by_action_id"] == second["id"]
    assert superseded["disposition"] == "HOLD"  # original value preserved


def test_comments_accumulate_without_superseding(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    base = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}"
    client.post(f"{base}/comments", json={"comment": "Chased for references."})
    client.post(f"{base}/comments", json={"comment": "Available from March."})
    history = client.get(f"{base}/actions").json()
    comments = [a for a in history if a["action_type"] == "COMMENT"]
    assert len(comments) == 2
    assert all(c["is_current"] for c in comments)


def test_empty_comment_is_rejected(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    response = client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/comments",
        json={"comment": "   "},
    )
    assert response.status_code == 422


def test_candidate_from_another_campaign_is_rejected(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    other = client.post("/api/campaigns", json={
        "name": "Other", "job_title": "Analyst", "job_description": "y",
    }).json()["id"]
    response = client.post(
        f"/api/campaigns/{other}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST"},
    )
    assert response.status_code == 422


def test_no_endpoint_edits_or_deletes_a_decision(client):
    """Decisions are append-only, like the assessments they concern."""
    paths = client.app.openapi()["paths"]
    for path, operations in paths.items():
        if not any(k in path for k in ("actions", "disposition", "override", "comments")):
            continue
        for method in operations:
            assert method.lower() in ("get", "post"), f"{method.upper()} {path}"


# ===========================================================================
# API — audit trail
# ===========================================================================

def test_decisions_are_audited(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    base = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}"
    client.post(f"{base}/disposition", json={"disposition": "SHORTLIST", "actor": "Fatima"})

    events = client.get(f"/api/campaigns/{campaign_id}/audit").json()
    entry = next(e for e in events if e["action"] == "DISPOSITION_SET")
    assert entry["actor"] == "Fatima"
    assert entry["entity_id"] == candidate_id
    assert entry["after"]["disposition"] == "SHORTLIST"


def test_override_audit_records_both_sides(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    mine = next(e for e in evaluations if e["candidate_id"] == candidate_id)
    target = "STRONG_FIT" if mine["recommendation"] != "STRONG_FIT" else "NOT_RECOMMENDED"

    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/override",
        json={"overridden_to": target, "reason": "Verified by phone.", "actor": "Fatima"},
    )
    events = client.get(f"/api/campaigns/{campaign_id}/audit").json()
    entry = next(e for e in events if e["action"] == "RECOMMENDATION_OVERRIDDEN")
    assert entry["before"]["recommendation"] == mine["recommendation"]
    assert entry["after"]["recommendation"] == target
    assert "Verified by phone" in entry["summary"]


def test_audit_can_be_filtered(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    base = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}"
    client.post(f"{base}/comments", json={"comment": "note"})
    client.post(f"{base}/disposition", json={"disposition": "HOLD"})

    filtered = client.get(
        f"/api/campaigns/{campaign_id}/audit", params={"action": "COMMENT_ADDED"}
    ).json()
    assert filtered
    assert all(e["action"] == "COMMENT_ADDED" for e in filtered)


def test_audit_is_newest_first(decided_campaign, client):
    campaign_id, _, candidate_id = decided_campaign
    base = f"/api/campaigns/{campaign_id}/candidates/{candidate_id}"
    client.post(f"{base}/comments", json={"comment": "first"})
    client.post(f"{base}/comments", json={"comment": "second"})
    events = client.get(f"/api/campaigns/{campaign_id}/audit").json()
    assert events[0]["created_at"] >= events[-1]["created_at"]


def test_audit_has_no_write_endpoint(client):
    """An audit trail a user can post to is not an audit trail."""
    paths = client.app.openapi()["paths"]
    for path, operations in paths.items():
        if path.endswith("/audit"):
            assert set(m.lower() for m in operations) == {"get"}


# ===========================================================================
# API — benchmarks
# ===========================================================================

def test_campaign_benchmarks_include_the_override_rate(decided_campaign, client):
    campaign_id, _, _ = decided_campaign
    body = client.get(f"/api/campaigns/{campaign_id}/benchmarks").json()
    assert "benchmarks" in body
    assert "of" in body["override_rate"]["statement"]
    assert body["override_rate"]["assessed"] == 2


def test_benchmarks_are_null_on_a_small_campaign(decided_campaign, client):
    """Two candidates is not a distribution, and it says so rather than guessing."""
    campaign_id, _, _ = decided_campaign
    assert client.get(f"/api/campaigns/{campaign_id}/benchmarks").json()["benchmarks"] is None


def test_candidate_benchmark_needs_an_assessment(decided_campaign, client, db_session):
    from app.db.models import Candidate

    campaign_id, _, _ = decided_campaign
    orphan = Candidate(campaign_id=campaign_id, full_name="Unassessed")
    db_session.add(orphan)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign_id}/candidates/{orphan.id}/benchmark"
    )
    assert response.status_code == 404
