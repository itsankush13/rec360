"""
The Recruitment 360 dashboard numbers — W-G / B19.

Every figure is read from `candidate_lifecycle` and `lifecycle_transitions`,
the tables the state machine already writes. These tests build those rows
directly rather than driving the full lifecycle service, because the seam
under test is the read side: does `/api/campaigns/{id}/metrics/...` report
what is really in those two tables.
"""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Campaign, Candidate, CandidateLifecycle, LifecycleTransition
from app.db.session import get_db
from app.api.metrics import router as metrics_router


@pytest.fixture()
def app_client(db_session):
    app = FastAPI()
    app.include_router(metrics_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def campaign(db_session):
    row = Campaign(name="Metrics", job_title="Control Room Operator")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _candidate(db_session, campaign_id, name):
    row = Candidate(campaign_id=campaign_id, full_name=name)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _move(db_session, campaign_id, candidate_id, from_status, to_status, *,
          days_ago, campaign_rank=None):
    """Write one transition plus the current-position row it produces."""
    created_at = datetime(2026, 9, 1) + timedelta(days=days_ago)
    current = db_session.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.campaign_id == campaign_id,
            CandidateLifecycle.candidate_id == candidate_id,
            CandidateLifecycle.is_current.is_(True),
        )
    ).first()
    # campaign_rank is stored once, at entry, and carried forward on later
    # moves (B15) rather than re-derived — mirror that here so a HIRED row
    # still carries the rank it was given at shortlist.
    if campaign_rank is None and current is not None:
        campaign_rank = current.campaign_rank
    if current is not None:
        current.is_current = False
    db_session.add(CandidateLifecycle(
        campaign_id=campaign_id, candidate_id=candidate_id,
        status=to_status, entered_at=created_at, is_current=True,
        campaign_rank=campaign_rank,
    ))
    db_session.add(LifecycleTransition(
        campaign_id=campaign_id, candidate_id=candidate_id,
        from_status=from_status, to_status=to_status,
        created_at=created_at,
    ))
    db_session.commit()


# ---------------------------------------------------------------------------
# /funnel
# ---------------------------------------------------------------------------

def test_funnel_wraps_lifecycle_service_funnel(app_client, db_session, campaign):
    """
    Every stage in stage order, empty stages included — X11 was fixed at the
    service, this route must not undo it.
    """
    a = _candidate(db_session, campaign.id, "A")
    b = _candidate(db_session, campaign.id, "B")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, b.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, b.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=1)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/funnel")
    assert resp.status_code == 200
    rows = resp.json()

    assert [r["status"] for r in rows] == [
        "SHORTLISTED", "WITH_HIRING_MANAGER", "RETURNED_TO_RECRUITER",
        "INTERVIEW_SCHEDULED", "FEEDBACK_COMPLETE", "PENDING_APPROVAL",
        "PENDING_COST_CENTRE", "APPROVED", "OFFER_DRAFTED", "OFFER_SENT",
        "OFFER_ACCEPTED", "HIRED", "ON_HOLD", "WAITLISTED", "OFFER_DECLINED",
        "NOT_PROCEEDING", "WITHDRAWN", "CLOSED",
    ]
    shortlisted = next(r for r in rows if r["status"] == "SHORTLISTED")
    assert shortlisted["count"] == 1
    assert shortlisted["of"] == 2
    assert "basis" in shortlisted
    empty = next(r for r in rows if r["status"] == "HIRED")
    assert empty["count"] == 0


def test_funnel_404s_for_an_unknown_campaign(app_client):
    resp = app_client.get("/api/campaigns/does-not-exist/metrics/funnel")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /flow
# ---------------------------------------------------------------------------

def test_flow_reports_moved_and_of_for_a_stage_pair(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    b = _candidate(db_session, campaign.id, "B")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, a.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=1)
    _move(db_session, campaign.id, b.id, None, "SHORTLISTED", days_ago=0)
    # B never moves on from SHORTLISTED.

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/flow")
    assert resp.status_code == 200
    rows = resp.json()
    first = rows[0]
    assert first["from"] == "SHORTLISTED"
    assert first["to"] == "WITH_HIRING_MANAGER"
    assert first["moved"] == 1
    assert first["of"] == 2
    assert "basis" in first


# ---------------------------------------------------------------------------
# /time-in-stage
# ---------------------------------------------------------------------------

def test_time_in_stage_is_computed_from_consecutive_transitions(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, a.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=4)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/time-in-stage")
    assert resp.status_code == 200
    rows = resp.json()
    shortlisted = next(r for r in rows if r["status"] == "SHORTLISTED")
    assert shortlisted["median_days"] == 4
    assert shortlisted["longest_days"] == 4
    assert shortlisted["count"] == 1
    assert "basis" in shortlisted
    # WITH_HIRING_MANAGER was entered but never left — nothing to compute,
    # so it is omitted rather than estimated.
    assert not any(r["status"] == "WITH_HIRING_MANAGER" for r in rows)


# ---------------------------------------------------------------------------
# /bottleneck
# ---------------------------------------------------------------------------

def test_bottleneck_names_the_one_longest_stage(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    b = _candidate(db_session, campaign.id, "B")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, a.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=2)
    _move(db_session, campaign.id, a.id, "WITH_HIRING_MANAGER", "INTERVIEW_SCHEDULED", days_ago=10)
    _move(db_session, campaign.id, b.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, b.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=1)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/bottleneck")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "WITH_HIRING_MANAGER"
    assert body["median_days"] == 8
    assert "now_here" in body
    assert "basis" in body


def test_bottleneck_is_null_when_nothing_has_completed_a_stage(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/bottleneck")
    assert resp.status_code == 200
    assert resp.json() is None


# ---------------------------------------------------------------------------
# /outcomes
# ---------------------------------------------------------------------------

def test_outcomes_counts_terminal_states_with_denominators(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    b = _candidate(db_session, campaign.id, "B")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)
    _move(db_session, campaign.id, a.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=1)
    _move(db_session, campaign.id, a.id, "WITH_HIRING_MANAGER", "OFFER_SENT", days_ago=2)
    _move(db_session, campaign.id, a.id, "OFFER_SENT", "OFFER_ACCEPTED", days_ago=3)
    _move(db_session, campaign.id, a.id, "OFFER_ACCEPTED", "HIRED", days_ago=4)
    _move(db_session, campaign.id, b.id, None, "SHORTLISTED", days_ago=0)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/outcomes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hired"]["count"] == 1
    assert body["hired"]["of"] == 2
    assert body["still_live"]["count"] == 1
    assert body["offer_acceptance_rate"]["rate"] == 100.0
    assert body["offer_acceptance_rate"]["of"] == 1


def test_offer_acceptance_rate_is_omitted_with_no_offers_sent(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/outcomes")
    assert resp.json()["offer_acceptance_rate"] is None


# ---------------------------------------------------------------------------
# quality_of_hire (B19) — a proxy from stored campaign_rank, not a real
# post-hire outcome.
# ---------------------------------------------------------------------------

def test_quality_of_hire_is_null_with_no_hires(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0, campaign_rank=1)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/outcomes")
    assert resp.json()["quality_of_hire"] is None


def test_quality_of_hire_reports_shortlist_rank_of_hires(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    b = _candidate(db_session, campaign.id, "B")
    # A entered at rank 1 and was hired; the rank is carried forward, not lost.
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0, campaign_rank=1)
    _move(db_session, campaign.id, a.id, "SHORTLISTED", "WITH_HIRING_MANAGER", days_ago=1)
    _move(db_session, campaign.id, a.id, "WITH_HIRING_MANAGER", "OFFER_SENT", days_ago=2)
    _move(db_session, campaign.id, a.id, "OFFER_SENT", "OFFER_ACCEPTED", days_ago=3)
    _move(db_session, campaign.id, a.id, "OFFER_ACCEPTED", "HIRED", days_ago=4)
    # B entered at rank 5 and is still live — not counted as a hire.
    _move(db_session, campaign.id, b.id, None, "SHORTLISTED", days_ago=0, campaign_rank=5)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/outcomes")
    quality = resp.json()["quality_of_hire"]
    assert quality["hired_count"] == 1
    assert quality["with_recorded_rank"] == 1
    assert quality["average_shortlist_rank"] == 1
    assert quality["hired_from_top_3_of_shortlist"]["count"] == 1
    assert quality["hired_from_top_3_of_shortlist"]["of"] == 1
    assert "basis" in quality
    assert "not a post-hire outcome" in quality["basis"]


def test_quality_of_hire_counts_hires_with_no_recorded_rank_separately(
    app_client, db_session, campaign,
):
    """A rank of None is an absent measurement, not evidence of rank 0."""
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "HIRED", days_ago=0)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/outcomes")
    quality = resp.json()["quality_of_hire"]
    assert quality["hired_count"] == 1
    assert quality["with_recorded_rank"] == 0
    assert quality["average_shortlist_rank"] is None
    assert quality["hired_from_top_3_of_shortlist"] is None


# ---------------------------------------------------------------------------
# /overview
# ---------------------------------------------------------------------------

def test_overview_returns_every_metric_in_one_call(app_client, db_session, campaign):
    a = _candidate(db_session, campaign.id, "A")
    _move(db_session, campaign.id, a.id, None, "SHORTLISTED", days_ago=0)

    resp = app_client.get(f"/api/campaigns/{campaign.id}/metrics/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "funnel", "flow", "time_in_stage", "bottleneck", "outcomes",
    }
