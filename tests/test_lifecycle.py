"""
The recruitment lifecycle — phase 0 (identity) and phase 1 (status, handover,
hiring manager review).

What is being protected here is the record. Screening produces a
recommendation; these steps produce a hiring decision with money behind it.
So every move has a named actor, a from-state and a to-state, and a reason
wherever somebody will later be asked to account for it. Nothing about a
candidate's position is derived on read — a status nobody can point at a
transition for is a status nobody can audit.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core import lifecycle
from app.core.lifecycle import TransitionError
from app.db.models import (
    AuditAction, AuditEvent, LifecycleStatus, ManagerReviewOutcome, UserRole,
)
from app.services import lifecycle_service

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def people(client):
    def make(name, email, role):
        return client.post("/api/users", json={
            "full_name": name, "email": email, "role": role,
        }).json()

    return {
        "recruiter": make("Fatima Al-Rashid", "fatima@example.com", "RECRUITER"),
        "manager": make("Aziz Rahman", "aziz@example.com", "HIRING_MANAGER"),
        "admin": make("Sara Khan", "sara@example.com", "ADMIN"),
    }


@pytest.fixture()
def shortlisted(client):
    """A campaign with one assessed, shortlisted candidate."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Lifecycle", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    return campaign_id, candidate_id


# ---------------------------------------------------------------------------
# Identity — phase 0
# ---------------------------------------------------------------------------

def test_people_are_on_file_with_a_role(client):
    created = client.post("/api/users", json={
        "full_name": "Fatima Al-Rashid", "email": "f@example.com",
        "role": "RECRUITER", "business_unit": "Refining",
    })
    assert created.status_code == 201
    assert created.json()["role_label"] == "Recruiter"


def test_one_address_belongs_to_one_person(client, people):
    again = client.post("/api/users", json={
        "full_name": "Someone Else", "email": "fatima@example.com",
        "role": "RECRUITER",
    })
    assert again.status_code == 422
    assert "already on file" in again.json()["detail"]


def test_a_persons_role_can_be_changed(client, people):
    response = client.patch(
        f"/api/users/{people['recruiter']['id']}/role", json={"role": "ADMIN"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "ADMIN"
    assert body["role_label"] == "Administrator"
    assert body["id"] == people["recruiter"]["id"]
    # Name/email are the account's identity and are not touched by this.
    assert body["full_name"] == people["recruiter"]["full_name"]
    assert body["email"] == people["recruiter"]["email"]

    listed = client.get("/api/users?role=ADMIN").json()
    assert any(u["id"] == people["recruiter"]["id"] for u in listed)


def test_changing_an_unknown_persons_role_is_refused(client):
    response = client.patch("/api/users/nobody/role", json={"role": "ADMIN"})
    assert response.status_code == 422
    assert "not on file" in response.json()["detail"]


def test_nothing_moves_without_a_named_person(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": "nobody", "manager_id": people["manager"]["id"]},
    )
    assert refused.status_code == 422
    assert "not on file" in refused.json()["detail"]


# ---------------------------------------------------------------------------
# Entering the process
# ---------------------------------------------------------------------------

def test_only_a_shortlisted_candidate_enters(client, shortlisted, people):
    """
    The lifecycle is a record of a hiring process, not of everyone who
    applied. A rejection at screening never enters it.
    """
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "REJECT", "actor": "Fatima Al-Rashid"},
    )
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    assert refused.status_code == 422
    assert "shortlisted" in refused.json()["detail"]


def test_a_candidate_not_in_the_process_says_so_plainly(client, shortlisted):
    campaign_id, candidate_id = shortlisted
    missing = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}")
    assert missing.status_code == 404
    assert "not in the hiring process" in missing.json()["detail"]


# ---------------------------------------------------------------------------
# Handover
# ---------------------------------------------------------------------------

def test_a_candidate_is_handed_to_a_named_manager(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    sent = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"],
              "note": "Strongest of the four on console hours."},
    ).json()

    assert sent["status"] == "WITH_HIRING_MANAGER"
    assert sent["status_label"] == "With the hiring manager"
    # Whose turn it is, by name. A queue nobody owns is a queue nobody clears.
    assert sent["owner_name"] == "Aziz Rahman"
    # No QUESTION is on file for the first handoff — the manager already
    # knows a report is coming, so nothing is emailed for it.
    assert sent["mail_sent"] is None
    assert sent["mail_detail"] is None


def test_answering_a_managers_question_emails_them_the_answer(client, shortlisted, people):
    """
    X66 follow-up: `returned, with a question` on `handoff.html` re-sends to
    a manager through this same endpoint — this time it must actually notify
    the manager of the recruiter's answer, not just move the state.
    """
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "QUESTION",
              "reason": "Is the safety certification still current?"},
    )

    sent = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"],
              "note": "Confirmed directly with the candidate — valid through 2027."},
    ).json()

    assert sent["status"] == "WITH_HIRING_MANAGER"
    # Test settings run the simulated mail backend (tests/conftest.py), so
    # nothing is actually transmitted, but the send is still attempted and
    # reported back.
    assert sent["mail_sent"] is False
    assert people["manager"]["email"] in sent["mail_detail"]


def test_a_candidate_cannot_be_sent_to_someone_who_is_not_a_manager(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["recruiter"]["id"]},
    )
    assert refused.status_code == 422
    assert "not a hiring manager" in refused.json()["detail"]


def test_the_screen_is_told_where_the_candidate_can_go_next(
    client, shortlisted, people
):
    """
    The state machine lives in one place. A screen that encoded it a second
    time would drift from it the first time a state was added.
    """
    campaign_id, candidate_id = shortlisted
    sent = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"]},
    ).json()

    next_states = {step["status"] for step in sent["next_steps"]}
    assert "INTERVIEW_SCHEDULED" in next_states
    assert "RETURNED_TO_RECRUITER" in next_states
    assert all(step["label"] and step["label"] != step["status"]
               for step in sent["next_steps"])


# ---------------------------------------------------------------------------
# The hiring manager's review
# ---------------------------------------------------------------------------

def _hand_over(client, campaign_id, candidate_id, people):
    return client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"]},
    )


def test_proceeding_moves_the_candidate_to_interview(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    review = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    ).json()

    assert review["outcome_label"] == "Wants to interview"
    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "INTERVIEW_SCHEDULED"


def test_a_decline_without_a_reason_is_refused(client, shortlisted, people):
    """
    The reason is the first thing anyone reviewing this decision looks for,
    and optional means empty.
    """
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "DECLINE"},
    )
    assert refused.status_code == 422
    assert "needs a reason" in refused.json()["detail"]


def test_a_decline_with_a_reason_ends_the_process(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "DECLINE",
              "reason": "No live petrochemical console hours."},
    )
    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "NOT_PROCEEDING"
    assert now["next_steps"] == []


def test_the_review_is_pinned_to_the_assessment_the_manager_saw(
    client, shortlisted, people
):
    """
    If the rubric is re-approved and candidates re-assessed later, the
    manager's decision stays attributable to what was actually on screen.
    """
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    review = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    ).json()
    assert review["evaluation_id"]


def test_a_recruiter_cannot_record_the_managers_verdict(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["recruiter"]["id"], "outcome": "PROCEED"},
    )
    assert refused.status_code == 422
    assert "not a hiring manager" in refused.json()["detail"]


def test_a_review_needs_the_candidate_to_be_with_a_manager(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    client.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
                params={"actor_id": people["recruiter"]["id"]})

    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    assert refused.status_code == 422
    assert "not currently with a hiring manager" in refused.json()["detail"]


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

def test_an_impossible_move_is_refused_in_words_a_person_can_act_on(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    client.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
                params={"actor_id": people["recruiter"]["id"]})

    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "APPROVED", "actor_id": people["admin"]["id"]},
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "cannot move to" in detail
    # It names where they can go instead, and never in enum values.
    assert "From here they can go to" in detail
    assert "SHORTLISTED" not in detail


def test_a_terminal_candidate_accepts_nothing_further(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "DECLINE",
              "reason": "Not enough console hours."},
    )
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "INTERVIEW_SCHEDULED", "actor_id": people["admin"]["id"]},
    )
    assert refused.status_code == 422
    assert "nothing further" in refused.json()["detail"]


def test_a_hold_resumes_where_it_paused(client, shortlisted, people):
    """
    A hold is a pause, not a reset. Sending someone back to the start of the
    process because the business waited a fortnight would be a lie about
    where they actually are.
    """
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "ON_HOLD", "actor_id": people["admin"]["id"],
              "reason": "Headcount frozen until the quarter closes."},
    )
    held = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert held["status"] == "ON_HOLD"
    assert "WITH_HIRING_MANAGER" in {s["status"] for s in held["next_steps"]}
    # X15: the stage a hold paused is a stored field a screen can read
    # directly, not something it has to re-derive by walking transition
    # history backwards.
    assert held["held_from_status"] == "WITH_HIRING_MANAGER"
    assert held["held_from_label"]

    resumed = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "WITH_HIRING_MANAGER", "actor_id": people["recruiter"]["id"]},
    )
    assert resumed.status_code == 200
    assert resumed.json()["held_from_status"] is None


def test_a_hold_without_a_reason_is_refused(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    client.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
                params={"actor_id": people["recruiter"]["id"]})
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "ON_HOLD", "actor_id": people["admin"]["id"]},
    )
    assert refused.status_code == 422
    assert "needs a reason" in refused.json()["detail"]


def test_a_role_cannot_make_a_move_it_does_not_own(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "FEEDBACK_COMPLETE", "actor_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_APPROVAL", "actor_id": people["recruiter"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_COST_CENTRE", "actor_id": people["admin"]["id"]},
    )
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "APPROVED", "actor_id": people["recruiter"]["id"]},
    )
    assert refused.status_code == 422
    assert "role does not allow" in refused.json()["detail"]


def test_every_state_has_words_of_its_own():
    """An unmapped state would render as a blank cell on the leaderboard."""
    for status in LifecycleStatus:
        assert lifecycle.words(status)
        assert lifecycle.words(status) != status.value


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def test_the_timeline_reads_forwards_and_names_everyone(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )

    timeline = client.get(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/timeline"
    ).json()

    assert [t["to_status"] for t in timeline] == [
        "SHORTLISTED", "WITH_HIRING_MANAGER", "INTERVIEW_SCHEDULED",
    ]
    assert timeline[1]["actor_name"] == "Fatima Al-Rashid"
    assert timeline[2]["actor_name"] == "Aziz Rahman"
    assert all(t["to_label"] for t in timeline)


def test_every_move_reaches_the_audit_trail(client, shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )

    recorded = {
        e.action for e in db_session.scalars(
            select(AuditEvent).where(AuditEvent.candidate_id == candidate_id)
        ).all()
    }
    assert AuditAction.SENT_TO_HIRING_MANAGER in recorded
    assert AuditAction.MANAGER_REVIEWED in recorded
    assert AuditAction.STATUS_CHANGED in recorded


def test_the_audit_summary_is_written_for_a_person(client, shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    event = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.SENT_TO_HIRING_MANAGER
        )
    ).first()
    assert "with the hiring manager" in event.summary.lower()
    assert "WITH_HIRING_MANAGER" not in event.summary
    assert event.actor == "Fatima Al-Rashid"


def test_a_position_is_superseded_not_overwritten(client, shortlisted, people, db_session):
    """
    The sequence of positions is itself evidence. Editing one in place would
    lose the fact that a candidate was ever somewhere else.
    """
    from app.db.models import CandidateLifecycle

    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    rows = db_session.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.candidate_id == candidate_id
        )
    ).all()
    assert len(rows) == 2
    assert sum(1 for r in rows if r.is_current) == 1


def test_the_campaign_funnel_counts_carry_their_denominator(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)

    funnel = client.get(f"/api/campaigns/{campaign_id}/lifecycle/funnel").json()
    assert funnel
    assert funnel[0]["of"] >= funnel[0]["count"]
    assert funnel[0]["label"]


# ---------------------------------------------------------------------------
# The offer stages and HIRED (D1 / B02)
# ---------------------------------------------------------------------------

def test_every_lifecycle_status_is_a_key_in_allowed():
    """
    A guard against the next person adding a state and forgetting the map. A
    state with no entry in ALLOWED silently refuses every move out of it.
    """
    for status in LifecycleStatus:
        assert status in lifecycle.ALLOWED


def test_every_allowed_target_is_a_real_lifecycle_status():
    for targets in lifecycle.ALLOWED.values():
        for target in targets:
            assert target in LifecycleStatus


def test_every_status_has_reader_facing_words():
    """An enum name must never reach a reader."""
    import re

    for status in LifecycleStatus:
        word = lifecycle.words(status)
        assert word
        assert "_" not in word
        assert not re.search(r"[A-Z]{2,}", word)


def test_the_full_offer_walk_succeeds():
    lifecycle.check(
        LifecycleStatus.APPROVED, LifecycleStatus.OFFER_DRAFTED,
        role=UserRole.RECRUITER,
    )
    lifecycle.check(
        LifecycleStatus.OFFER_DRAFTED, LifecycleStatus.OFFER_SENT,
        role=UserRole.RECRUITER,
    )
    lifecycle.check(
        LifecycleStatus.OFFER_SENT, LifecycleStatus.OFFER_ACCEPTED,
        role=UserRole.RECRUITER,
    )
    lifecycle.check(
        LifecycleStatus.OFFER_ACCEPTED, LifecycleStatus.HIRED,
        role=UserRole.ADMIN,
    )


def test_hired_is_terminal():
    with pytest.raises(TransitionError):
        lifecycle.check(LifecycleStatus.HIRED, LifecycleStatus.CLOSED)


def test_offer_declined_requires_a_reason():
    with pytest.raises(TransitionError):
        lifecycle.check(
            LifecycleStatus.OFFER_SENT, LifecycleStatus.OFFER_DECLINED,
            role=UserRole.RECRUITER,
        )
    lifecycle.check(
        LifecycleStatus.OFFER_SENT, LifecycleStatus.OFFER_DECLINED,
        role=UserRole.RECRUITER, reason="Took a counter-offer.",
    )


def test_a_revised_offer_can_be_reissued():
    """OFFER_SENT back to OFFER_DRAFTED — a revised offer can be re-issued."""
    lifecycle.check(
        LifecycleStatus.OFFER_SENT, LifecycleStatus.OFFER_DRAFTED,
        role=UserRole.RECRUITER,
    )


def test_an_accepted_offer_can_still_fall_through():
    """Accepted, then did not join. WITHDRAWN stays reachable."""
    lifecycle.check(
        LifecycleStatus.OFFER_ACCEPTED, LifecycleStatus.WITHDRAWN,
        reason="Took another role before their start date.",
    )


def test_offer_declined_closes_but_never_hires():
    lifecycle.check(LifecycleStatus.OFFER_DECLINED, LifecycleStatus.CLOSED)
    with pytest.raises(TransitionError):
        lifecycle.check(
            LifecycleStatus.OFFER_DECLINED, LifecycleStatus.HIRED,
            role=UserRole.ADMIN,
        )


def test_a_recruiter_may_send_an_offer_but_not_hire():
    lifecycle.check(
        LifecycleStatus.OFFER_DRAFTED, LifecycleStatus.OFFER_SENT,
        role=UserRole.RECRUITER,
    )
    with pytest.raises(TransitionError):
        lifecycle.check(
            LifecycleStatus.OFFER_ACCEPTED, LifecycleStatus.HIRED,
            role=UserRole.RECRUITER,
        )
    lifecycle.check(
        LifecycleStatus.OFFER_ACCEPTED, LifecycleStatus.HIRED,
        role=UserRole.ADMIN,
    )


def test_a_hold_from_offer_sent_resumes_to_offer_sent():
    """The held_from path still works with the new offer states."""
    targets = lifecycle.targets(
        LifecycleStatus.ON_HOLD, held_from=LifecycleStatus.OFFER_SENT,
    )
    assert LifecycleStatus.OFFER_SENT in targets
    lifecycle.check(
        LifecycleStatus.ON_HOLD, LifecycleStatus.OFFER_SENT,
        role=UserRole.RECRUITER, held_from=LifecycleStatus.OFFER_SENT,
    )


def test_a_service_level_walk_through_the_offer_stages_ends_hired(
    client, shortlisted, people, db_session
):
    """
    The other tests in this file exercise the offer stages through `check()`
    directly. This one drives the service layer, past APPROVED, so the
    transitions that actually get persisted are the ones under test.
    """
    campaign_id, candidate_id = shortlisted
    _hand_over(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "FEEDBACK_COMPLETE", "actor_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_APPROVAL", "actor_id": people["recruiter"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_COST_CENTRE", "actor_id": people["admin"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "APPROVED", "actor_id": people["admin"]["id"]},
    )

    lifecycle_service.transition(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.OFFER_DRAFTED, actor_id=people["recruiter"]["id"],
    )
    lifecycle_service.transition(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.OFFER_SENT, actor_id=people["recruiter"]["id"],
    )
    lifecycle_service.transition(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.OFFER_ACCEPTED, actor_id=people["recruiter"]["id"],
    )
    lifecycle_service.transition(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.HIRED, actor_id=people["admin"]["id"],
    )

    final = lifecycle_service.current(db_session, campaign_id, candidate_id)
    assert final.status == LifecycleStatus.HIRED.value

    transitions = lifecycle_service.timeline(db_session, campaign_id, candidate_id)
    assert [t.to_status for t in transitions[-4:]] == [
        "OFFER_DRAFTED", "OFFER_SENT", "OFFER_ACCEPTED", "HIRED",
    ]

    hire_event = db_session.scalars(
        select(AuditEvent)
        .where(AuditEvent.candidate_id == candidate_id)
        .order_by(AuditEvent.created_at.desc())
    ).first()
    assert hire_event.action == AuditAction.CANDIDATE_HIRED.value
