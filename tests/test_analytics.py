"""
Phase G tests — comparison, what-if analysis, KPI aggregates.

Two properties get the most attention, because they are the ones that would
mislead a client if wrong:

  * What-if writes nothing. Asserted by snapshotting every evaluation before
    and after a preview, and by checking no new run or evaluation appears.
  * No percentage is ever reported without its denominator, per the language
    rules in web/DATA.md. Asserted structurally over the whole KPI payload.
"""
from unittest.mock import patch

import pytest

from app.core import analytics
from app.core.analytics import AnalyticsError, EfficiencyAssumptions
from app.db.models import JobStatus

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, make_pdf, upload
from tests.test_evaluations import STRONG_CV, WEAK_CV, make_cv_pdf


THIRD_CV = "\n".join([
    "Anjali Menon",
    "anjali.menon@example.com | +91 90000 11122 | Chennai, India",
    "",
    "SUMMARY",
    "Platform engineer with 6 years of experience running container platforms",
    "and data pipelines for logistics and retail clients.",
    "",
    "SKILLS",
    "Python, MySQL, Kubernetes, Terraform, Jenkins, Kafka, Git",
    "",
    "EXPERIENCE",
    "Platform Engineer, Nimbus Logistics (Jun 2021 - Present)",
    "- Ran Kubernetes clusters and Terraform modules across two regions",
    "- Built Kafka pipelines feeding the reporting warehouse",
    "Engineer, Cargo Systems (Aug 2019 - May 2021)",
    "- Maintained Python services against MySQL",
    "",
    "EDUCATION",
    "B.E. in Information Technology, Anna University, 2019",
])

FOURTH_CV = "\n".join([
    "Vikram Shah",
    "vikram.shah@example.com | +91 90000 33344 | Ahmedabad, India",
    "",
    "SUMMARY",
    "Backend developer with 4 years of experience in payments integration",
    "for regional banking clients.",
    "",
    "SKILLS",
    "Java, Spring Boot, Oracle, REST APIs, Jenkins, Git",
    "",
    "EXPERIENCE",
    "Developer, PayBridge (Mar 2022 - Present)",
    "- Built Spring Boot services against Oracle for card settlement",
    "Junior Developer, FinServe (Feb 2020 - Feb 2022)",
    "- Maintained Java batch jobs and REST endpoints",
    "",
    "EDUCATION",
    "B.Tech in Computer Engineering, Nirma University, 2020",
])


@pytest.fixture()
def analysed_campaign(client):
    """Four assessed candidates — enough for distribution statistics."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Phase G", "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS backend engineer.",
            "location": "Bengaluru", "vacancies": 3,
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [
        ("priya.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("rahul.pdf", make_cv_pdf(WEAK_CV), PDF_MIME),
        ("anjali.pdf", make_cv_pdf(THIRD_CV), PDF_MIME),
        ("vikram.pdf", make_cv_pdf(FOURTH_CV), PDF_MIME),
        # A genuinely unreadable file — a blank scan is screened and flagged
        # now, not held, so it would no longer exercise files_held/by_reason.
        ("broken.pdf", b"%PDF-1.4 this is not really a pdf at all", PDF_MIME),
    ])
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    candidates = client.get(f"/api/campaigns/{campaign_id}/candidates").json()
    return campaign_id, run["id"], [c["id"] for c in candidates]


# ===========================================================================
# Comparison
# ===========================================================================

def test_comparison_needs_two_candidates(analysed_campaign, client):
    campaign_id, _, candidates = analysed_campaign
    response = client.get(
        f"/api/campaigns/{campaign_id}/compare",
        params={"candidate_ids": [candidates[0]]},
    )
    assert response.status_code == 422


def test_comparison_is_criterion_major(analysed_campaign, client):
    """One row per criterion, one cell per candidate — how the screen reads it."""
    campaign_id, _, candidates = analysed_campaign
    body = client.get(
        f"/api/campaigns/{campaign_id}/compare",
        params={"candidate_ids": candidates[:3]},
    ).json()

    assert len(body["candidates"]) == 3
    assert body["criteria"]
    for row in body["criteria"]:
        assert len(row["cells"]) == 3
        assert {c["candidate_id"] for c in row["cells"]} == set(candidates[:3])


def test_comparison_preserves_requested_order(analysed_campaign, client):
    campaign_id, _, candidates = analysed_campaign
    wanted = [candidates[2], candidates[0]]
    body = client.get(
        f"/api/campaigns/{campaign_id}/compare", params={"candidate_ids": wanted}
    ).json()
    assert [c["candidate_id"] for c in body["candidates"]] == wanted


def test_comparison_identifies_key_differences(analysed_campaign, client):
    campaign_id, _, candidates = analysed_campaign
    body = client.get(
        f"/api/campaigns/{campaign_id}/compare",
        params={"candidate_ids": candidates[:4]},
    ).json()
    assert "key_differences" in body
    for row in body["key_differences"]:
        assert row["is_differentiator"] is True
        assert row["spread"] >= 20


def test_small_spreads_are_not_differentiators():
    """A two-point gap is noise, not a difference worth showing."""
    from types import SimpleNamespace
    from tests.test_challenge import criterion, evaluation

    a = evaluation("e1", criteria=[criterion("pg", raw=80.0)])
    b = evaluation("e2", criteria=[criterion("pg", raw=78.0)])
    for e in (a, b):
        e.rubric_version_id = "v1"
        e.candidate_id = e.id
        e.criteria[0].display_order = 0
        e.criteria[0].category = SimpleNamespace(value="SKILL")
        e.criteria[0].requirement_type = SimpleNamespace(value="MANDATORY")
        e.confidence_band = SimpleNamespace(value="HIGH")
        e.recommendation = SimpleNamespace(value="POTENTIAL_FIT")
        e.eligibility_status = SimpleNamespace(value="ELIGIBLE")
        e.experience_years_total = 5.0
        e.experience_years_relevant = 4.0

    result = analytics.compare([a, b])
    assert result["criteria"][0]["is_differentiator"] is False


def test_comparison_refuses_across_rubric_versions(analysed_campaign, client, db_session):
    """
    Scores from different rubrics are not comparable, and a table would imply
    they were.
    """
    from app.db.models import Evaluation

    campaign_id, _, candidates = analysed_campaign
    victim = db_session.query(Evaluation).filter(
        Evaluation.candidate_id == candidates[1]
    ).first()
    victim.rubric_version_id = "some-other-version"
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign_id}/compare",
        params={"candidate_ids": candidates[:2]},
    )
    assert response.status_code == 422
    assert "not comparable" in str(response.json()["detail"])


def test_comparison_404s_on_unassessed_candidate(analysed_campaign, client):
    campaign_id, _, candidates = analysed_campaign
    response = client.get(
        f"/api/campaigns/{campaign_id}/compare",
        params={"candidate_ids": [candidates[0], "not-a-candidate"]},
    )
    assert response.status_code == 404


# ===========================================================================
# What-if
# ===========================================================================

def test_baseline_returns_the_current_weights(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    body = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    assert body["criteria"]
    assert body["weight_total"] == pytest.approx(100.0, abs=0.01)
    assert body["rubric_version_number"] == 1


def test_what_if_writes_nothing(analysed_campaign, client):
    """
    The requirement in full: preview ranking changes *without changing
    approved results*. Snapshot everything, preview, compare.
    """
    campaign_id, _, _ = analysed_campaign
    before = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    runs_before = client.get(f"/api/campaigns/{campaign_id}/evaluations/runs").json()

    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]
    skewed = {k: 0.0 for k in keys}
    skewed[keys[0]] = 100.0

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if", json={"weights": skewed}
    )
    assert response.status_code == 200
    assert response.json()["persisted"] is False

    after = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    runs_after = client.get(f"/api/campaigns/{campaign_id}/evaluations/runs").json()
    assert before == after
    assert len(runs_before) == len(runs_after)


def test_what_if_does_not_lock_or_alter_the_rubric(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    before = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()

    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]
    weights = {k: round(100.0 / len(keys), 4) for k in keys}
    # Absorb rounding into the first key so the total is exactly 100.
    weights[keys[0]] = round(100.0 - sum(list(weights.values())[1:]), 4)
    client.post(f"/api/campaigns/{campaign_id}/what-if", json={"weights": weights})

    after = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    assert before == after


def test_what_if_reranks(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]
    skewed = {k: 0.0 for k in keys}
    skewed[keys[-1]] = 100.0

    body = client.post(
        f"/api/campaigns/{campaign_id}/what-if", json={"weights": skewed}
    ).json()
    ranks = [c["projected_rank"] for c in body["candidates"]]
    assert ranks == sorted(ranks)
    assert "of" in body["movement"]["statement"]
    for row in body["candidates"]:
        assert row["score_change"] == pytest.approx(
            row["projected_score"] - row["current_score"], abs=0.02
        )


def test_what_if_rejects_unbalanced_weights(analysed_campaign, client):
    """Projected scores on a different scale can't be compared to approved ones."""
    campaign_id, _, _ = analysed_campaign
    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]

    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if",
        json={"weights": {keys[0]: 50.0}},
    )
    assert response.status_code == 422
    assert "not 100" in str(response.json()["detail"])


def test_what_if_rejects_unknown_criterion_keys(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if",
        json={"weights": {"invented_criterion": 100.0}},
    )
    assert response.status_code == 422


def test_what_if_rejects_negative_weights(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]
    response = client.post(
        f"/api/campaigns/{campaign_id}/what-if",
        json={"weights": {keys[0]: 130.0, keys[1]: -30.0}},
    )
    assert response.status_code == 422


def test_what_if_carries_the_eligibility_notice(analysed_campaign, client):
    """
    No reweighting can make an ineligible candidate eligible, and the
    response says so — this is the most misleading thing the screen could
    otherwise imply.
    """
    campaign_id, _, _ = analysed_campaign
    baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
    keys = [c["criterion_key"] for c in baseline["criteria"]]
    weights = {k: 0.0 for k in keys}
    weights[keys[0]] = 100.0

    body = client.post(
        f"/api/campaigns/{campaign_id}/what-if", json={"weights": weights}
    ).json()
    assert "unchanged" in body["eligibility_note"]
    assert "preview only" in body["notice"]


def test_what_if_needs_assessed_candidates(client):
    campaign_id = client.post("/api/campaigns", json={
        "name": "Empty", "job_title": "Engineer", "job_description": "x",
    }).json()["id"]
    assert client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").status_code == 404


# ===========================================================================
# KPI aggregates
# ===========================================================================

def _walk_percentages(node, found):
    """Collect every dict that looks like a reported percentage."""
    if isinstance(node, dict):
        if "value" in node and "statement" in node:
            found.append(node)
        for value in node.values():
            _walk_percentages(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_percentages(item, found)
    return found


def test_kpis_cover_all_six_groups(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    body = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    for group in ("workload", "throughput", "efficiency", "quality",
                  "exceptions", "outcomes"):
        assert group in body, group
    assert "person decides" in body["disclaimer"]


def test_no_percentage_is_reported_without_its_denominator(analysed_campaign, client):
    """web/DATA.md's rule, asserted structurally over the whole payload."""
    campaign_id, _, _ = analysed_campaign
    body = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    percentages = _walk_percentages(body, [])
    assert percentages
    for entry in percentages:
        assert entry["of"] > 0
        assert "of" in entry["statement"]
        assert entry["count"] <= entry["of"]


def test_efficiency_figures_carry_their_assumptions(analysed_campaign, client):
    """
    A dollar saving without its baseline asserts something the system has
    never measured.
    """
    campaign_id, _, _ = analysed_campaign
    efficiency = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["efficiency"]
    assert "assumptions" in efficiency
    assert "not measurements" in efficiency["assumptions"]["note"]
    assert efficiency["baseline"]
    assert efficiency["screening_time_not_spent"]["derivation"]
    assert efficiency["screening_time_not_spent"]["currency"] == "USD"


def test_efficiency_assumptions_are_configurable(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    default = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["efficiency"]
    doubled = client.get(
        f"/api/campaigns/{campaign_id}/kpis",
        params={"hourly_rate": 84.0},
    ).json()["efficiency"]

    assert doubled["assumptions"]["hourly_rate"] == 84.0
    assert doubled["screening_time_not_spent"]["amount"] == pytest.approx(
        default["screening_time_not_spent"]["amount"] * 2, rel=0.01
    )


def test_minutes_saved_is_derived_not_supplied():
    assumptions = EfficiencyAssumptions(
        manual_minutes_per_cv=8.0, assisted_minutes_per_cv=1.1
    )
    assert assumptions.minutes_saved_per_cv == pytest.approx(6.9)


def test_workload_counts_held_files_separately(analysed_campaign, client):
    """The corrupt file must appear as held, not as assessed."""
    campaign_id, _, _ = analysed_campaign
    body = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    assert body["workload"]["cvs_received"] == 5
    assert body["workload"]["files_held"] == 1
    assert body["workload"]["candidates_assessed"] == 4


def test_exceptions_break_down_by_reason(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    exceptions = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["exceptions"]
    assert exceptions["files_held"] == 1
    assert exceptions["by_reason"]
    assert sum(exceptions["by_reason"].values()) == exceptions["files_held"]


def test_scanned_cv_is_screened_and_flagged_not_held(client):
    """
    A photographed/scanned CV with too little text to trust is screened
    along with every other CV, not held out of the batch — but it is still
    flagged, and counted separately from files that were never screened.
    """
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Phase G Scan", "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS backend engineer.",
            "location": "Bengaluru", "vacancies": 1,
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})

    upload(client, campaign_id, [("scan.pdf", make_pdf(blank=True), PDF_MIME)])

    body = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    assert body["workload"]["files_held"] == 0
    assert body["exceptions"]["files_held"] == 0
    assert body["exceptions"]["screened_by_reason"] == {"NO_TEXT_EXTRACTED": 1}

    candidates = client.get(f"/api/campaigns/{campaign_id}/candidates").json()
    assert len(candidates) == 1
    assert candidates[0]["requires_review"] is True


def test_outcomes_count_every_recommendation_band(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    outcomes = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["outcomes"]
    assert set(outcomes["by_recommendation"]) == {
        "STRONG_FIT", "POTENTIAL_FIT", "REVIEW_REQUIRED", "NOT_RECOMMENDED",
    }
    assert sum(outcomes["by_recommendation"].values()) == 4


def test_score_distribution_appears_at_four_candidates(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    outcomes = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["outcomes"]
    assert outcomes["score_distribution"] is not None
    assert outcomes["score_distribution"]["candidates_assessed"] == 4


def test_score_distribution_is_withheld_below_four(client):
    """Consistent with the Challenge Agent and Phase F benchmarks."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Two only", "job_title": "Senior Software Engineer",
            "job_description": "Python and AWS.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "x"})
    upload(client, campaign_id, [
        ("a.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("b.pdf", make_cv_pdf(WEAK_CV), PDF_MIME),
    ])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    outcomes = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["outcomes"]
    assert outcomes["score_distribution"] is None


def test_quality_includes_the_override_rate(analysed_campaign, client):
    campaign_id, _, candidates = analysed_campaign
    evaluations = client.get(f"/api/campaigns/{campaign_id}/evaluations").json()
    mine = next(e for e in evaluations if e["candidate_id"] == candidates[0])
    target = "STRONG_FIT" if mine["recommendation"] != "STRONG_FIT" else "NOT_RECOMMENDED"
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidates[0]}/override",
        json={"overridden_to": target, "reason": "Verified by phone.", "actor": "Fatima"},
    )

    quality = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["quality"]
    assert quality["assessments_the_team_overruled"]["count"] == 1
    assert quality["assessments_the_team_overruled"]["of"] == 4


def test_evidence_coverage_excludes_criteria_with_nothing_to_cite(analysed_campaign, client):
    """
    Criteria scoring zero have no excerpt to cite, so including them would
    flatter the coverage figure.
    """
    campaign_id, _, _ = analysed_campaign
    quality = client.get(f"/api/campaigns/{campaign_id}/kpis").json()["quality"]
    coverage = quality["evidence_coverage"]
    assert coverage is not None
    assert 0 <= coverage["value"] <= 100
    assert coverage["of"] > 0


def test_global_kpis_span_campaigns(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    global_body = client.get("/api/analytics/kpis").json()
    scoped = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    assert global_body["workload"]["campaigns"] >= 1
    assert global_body["workload"]["cvs_received"] >= scoped["workload"]["cvs_received"]


def test_global_kpis_names_the_all_time_period_by_default(analysed_campaign, client):
    body = client.get("/api/analytics/kpis").json()
    assert body["period"]["label"] == "All campaigns to date"
    assert body["period"]["since"] is None
    assert body["role_filter"] is None


def test_global_kpis_filters_by_role(analysed_campaign, client):
    """A role that matches nothing is zero campaigns, not every campaign."""
    campaign_id, _, _ = analysed_campaign
    matched = client.get("/api/analytics/kpis", params={"role": "software engineer"}).json()
    unmatched = client.get("/api/analytics/kpis", params={"role": "no such role"}).json()

    scoped = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    assert matched["workload"]["campaigns"] == 1
    assert matched["workload"]["cvs_received"] == scoped["workload"]["cvs_received"]
    assert matched["role_filter"] == "software engineer"

    assert unmatched["workload"]["campaigns"] == 0
    assert unmatched["workload"]["cvs_received"] == 0


def test_kpis_months_convenience_names_its_own_label(analysed_campaign, client):
    campaign_id, _, _ = analysed_campaign
    body = client.get(
        f"/api/campaigns/{campaign_id}/kpis", params={"months": 3},
    ).json()
    assert body["period"]["label"] == "Last 3 months"
    assert body["period"]["since"] is not None
    # Everything in the fixture happened moments ago, so a 3-month window
    # still includes it — this is a window check, not a data-loss check.
    assert body["workload"]["cvs_received"] == 5


def test_kpis_since_excludes_activity_before_the_window(analysed_campaign, client):
    """An explicit `since` in the future must exclude everything, honestly."""
    from datetime import datetime, timedelta, timezone

    campaign_id, _, _ = analysed_campaign
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    body = client.get(
        f"/api/campaigns/{campaign_id}/kpis", params={"since": future},
    ).json()
    assert body["workload"]["cvs_received"] == 0
    assert body["period"]["label"] == "Custom reporting window"


def test_explicit_since_overrides_the_months_convenience(analysed_campaign, client):
    from datetime import datetime, timedelta, timezone

    campaign_id, _, _ = analysed_campaign
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    body = client.get(
        f"/api/campaigns/{campaign_id}/kpis",
        params={"months": 6, "since": future},
    ).json()
    assert body["workload"]["cvs_received"] == 0
    assert body["period"]["since"][:10] == future[:10]


def test_kpis_on_an_empty_campaign_do_not_divide_by_zero(client):
    campaign_id = client.post("/api/campaigns", json={
        "name": "Nothing", "job_title": "Engineer", "job_description": "x",
    }).json()["id"]
    body = client.get(f"/api/campaigns/{campaign_id}/kpis").json()
    assert body["workload"]["cvs_received"] == 0
    assert body["throughput"]["processed_without_a_problem"] is None
    assert body["outcomes"]["score_distribution"] is None


def test_analytics_routes_are_read_only(client):
    """
    What-if is a POST because it takes a body, not because it writes. Nothing
    here should offer PUT, PATCH or DELETE.
    """
    paths = client.app.openapi()["paths"]
    for path, operations in paths.items():
        if not any(k in path for k in ("compare", "what-if", "kpis")):
            continue
        for method in operations:
            assert method.lower() in ("get", "post"), f"{method.upper()} {path}"


def test_analytics_makes_no_model_calls(analysed_campaign, client):
    """All three features are arithmetic over stored data."""
    campaign_id, _, candidates = analysed_campaign
    with patch(
        "app.core.llm_provider.get_chat_model",
        side_effect=AssertionError(
            "A model client was constructed during a deterministic run"
        ),
    ):
        client.get(f"/api/campaigns/{campaign_id}/kpis")
        client.get(f"/api/campaigns/{campaign_id}/compare",
                   params={"candidate_ids": candidates[:2]})
        baseline = client.get(f"/api/campaigns/{campaign_id}/what-if/baseline").json()
        keys = [c["criterion_key"] for c in baseline["criteria"]]
        weights = {k: 0.0 for k in keys}
        weights[keys[0]] = 100.0
        client.post(f"/api/campaigns/{campaign_id}/what-if", json={"weights": weights})
