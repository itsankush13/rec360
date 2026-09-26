"""
B02 phase 5 — SLA reminders and escalations.

A target duration per stage, a due date, reminders before and escalation
after, clocks stopping on hold, every reminder itself an audit event
(`02-LIFECYCLE-MODEL.md`). The demo-facing half (an amber badge on
`timeline.html`) is out of scope here — this is the stored state, the
derivation rule and the audit trail behind it.
"""
from datetime import datetime, timedelta

from app.core import lifecycle
from app.db.models import AuditAction, AuditEvent, LifecycleStatus
from app.services import lifecycle_service, sla_service

from tests.test_lifecycle import people, shortlisted  # noqa: F401


def test_entering_the_lifecycle_sets_a_due_date(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    out = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert out["due_at"]
    assert out["sla_status"] == "ON_TRACK"


def test_going_on_hold_stops_the_clock(client, shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    held = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={
            "to_status": "ON_HOLD", "actor_id": people["recruiter"]["id"],
            "reason": "Waiting on a budget decision",
        },
    ).json()
    assert held["due_at"] is None
    assert held["sla_status"] == "ON_TRACK"


def test_status_reads_due_soon_and_overdue_from_the_stored_due_date(shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    record = lifecycle_service.enter(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        actor_id=people["recruiter"]["id"],
    )
    target, lead = lifecycle.SLA_HOURS[LifecycleStatus.SHORTLISTED]

    on_track_at = record.due_at - timedelta(hours=target)
    assert sla_service.sla_status(record, now=on_track_at) == sla_service.ON_TRACK

    due_soon_at = record.due_at - timedelta(hours=lead - 1)
    assert sla_service.sla_status(record, now=due_soon_at) == sla_service.DUE_SOON

    overdue_at = record.due_at + timedelta(hours=1)
    assert sla_service.sla_status(record, now=overdue_at) == sla_service.OVERDUE


def test_evaluate_sends_one_reminder_and_does_not_repeat_it(shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    record = lifecycle_service.enter(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        actor_id=people["recruiter"]["id"],
    )
    _, lead = lifecycle.SLA_HOURS[LifecycleStatus.SHORTLISTED]
    due_soon_at = record.due_at - timedelta(hours=lead - 1)

    result = sla_service.evaluate(db_session, campaign_id=campaign_id, now=due_soon_at)
    assert result == {"reminders_sent": 1, "escalations_sent": 0}

    again = sla_service.evaluate(db_session, campaign_id=campaign_id, now=due_soon_at + timedelta(minutes=1))
    assert again == {"reminders_sent": 0, "escalations_sent": 0}

    events = db_session.query(AuditEvent).filter_by(
        entity_id=record.id, action=AuditAction.SLA_REMINDER_SENT,
    ).all()
    assert len(events) == 1
    assert events[0].actor == "system"


def test_evaluate_escalates_once_overdue_and_never_duplicates(shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    record = lifecycle_service.enter(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        actor_id=people["recruiter"]["id"],
    )
    overdue_at = record.due_at + timedelta(hours=1)

    first = sla_service.evaluate(db_session, campaign_id=campaign_id, now=overdue_at)
    assert first == {"reminders_sent": 0, "escalations_sent": 1}

    second = sla_service.evaluate(db_session, campaign_id=campaign_id, now=overdue_at + timedelta(hours=1))
    assert second == {"reminders_sent": 0, "escalations_sent": 0}

    events = db_session.query(AuditEvent).filter_by(
        entity_id=record.id, action=AuditAction.SLA_ESCALATED,
    ).all()
    assert len(events) == 1


def test_evaluate_ignores_a_held_candidate(shortlisted, people, db_session):
    campaign_id, candidate_id = shortlisted
    lifecycle_service.enter(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        actor_id=people["recruiter"]["id"],
    )
    lifecycle_service.transition(
        db_session, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.ON_HOLD, actor_id=people["recruiter"]["id"],
        reason="Paused",
    )
    far_future = datetime.now() + timedelta(days=365)
    result = sla_service.evaluate(db_session, campaign_id=campaign_id, now=far_future)
    assert result == {"reminders_sent": 0, "escalations_sent": 0}


def test_evaluate_endpoint_is_scoped_by_campaign(client, shortlisted, people):
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    result = client.post(
        "/api/lifecycle/sla/evaluate", params={"campaign_id": campaign_id},
    )
    assert result.status_code == 200
    assert set(result.json()) == {"reminders_sent", "escalations_sent"}
