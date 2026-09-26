"""
Interview scheduling and feedback — journey steps 5 and 6 (ticket W-B).

The production app registers this router; tests use the same app and client.
"""
from unittest.mock import patch
from app.core import outlook_com
from app.core.calendar_adapter import InviteResult

import pytest

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf


@pytest.fixture(autouse=True)
def _clear_sender_cache():
    """Every test starts as if it were a fresh process, so an earlier
    test's discovered sender never leaks into a later one."""
    outlook_com.reset_sender_cache()
    yield
    outlook_com.reset_sender_cache()


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
        "panelist": make("Layla Haddad", "layla@example.com", "HIRING_MANAGER"),
    }


@pytest.fixture()
def with_manager(client, people):
    """A candidate already handed to the hiring manager."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Interviews", "job_title": "Control Room Operator",
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
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"]},
    )
    return campaign_id, candidate_id


def _schedule(client, campaign_id, candidate_id, people, **overrides):
    body = {
        "when": "2026-09-20T10:00:00",
        "duration_minutes": 45,
        "mode": "VIDEO",
        "location_or_link": "https://meet.example.com/room",
        "panel": [people["manager"]["id"], people["panelist"]["id"]],
        "round": 1,
        "actor_id": people["manager"]["id"],
    }
    body.update(overrides)
    return client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/schedule", json=body,
    )


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def test_scheduling_moves_the_candidate_to_interview_scheduled(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    scheduled = _schedule(client, campaign_id, candidate_id, people)

    assert scheduled.status_code == 201
    body = scheduled.json()
    assert body["round"] == 1
    assert body["mode"] == "VIDEO"
    assert body["panel"] == ["Aziz Rahman", "Layla Haddad"]


def test_scheduling_records_a_simulated_calendar_invite_by_default(client, with_manager, people):
    """B11: calendar_backend defaults to simulated, same opt-in shape as B10/B12."""
    campaign_id, candidate_id = with_manager
    scheduled = _schedule(client, campaign_id, candidate_id, people)

    body = scheduled.json()
    assert body["invite_simulated"] is True
    assert "attendee" in body["invite_detail"]

    listed = client.get(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}"
    ).json()[0]
    assert listed["invite_simulated"] is True
    assert listed["invite_detail"] == body["invite_detail"]


def test_demo_invite_sends_only_approved_people_and_reports_sent(client, with_manager, people):
    campaign_id, candidate_id = with_manager

    class CapturingAdapter:
        def __init__(self):
            self.calls = []

        def send_invite(self, **kwargs):
            self.calls.append(kwargs)
            return InviteResult(sent=True, simulated=False, detail="Sent from Outlook")

    adapter = CapturingAdapter()
    with patch("app.api.interviews.get_calendar_adapter", return_value=adapter):
        response = _schedule(
            client, campaign_id, candidate_id, people,
            co_manager_email="daipayan.r@protivitiglobal.in",
            recipient_email="chiranjib.sarma@protivitiglobal.in",
        )
    assert response.status_code == 201
    assert response.json()["invite_sent"] is True
    assert adapter.calls[0]["required_attendees"] == [
        "daipayan.r@protivitiglobal.in", "chiranjib.sarma@protivitiglobal.in",
    ]
    assert "Control Room Operator" in adapter.calls[0]["body"]
    assert "45 minutes" in adapter.calls[0]["body"]


def test_demo_invite_rejects_unapproved_address(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    response = _schedule(client, campaign_id, candidate_id, people,
                         recipient_email="candidate@outside.example")
    assert response.status_code == 422
    assert "approved" in response.json()["detail"].lower()


def test_live_invite_requires_sender_as_actor(client, with_manager, people, monkeypatch):
    """The acting user must be whoever the invite actually sends as — here
    an explicit CALENDAR_SENDER_EMAIL override — otherwise the audit trail
    would name the wrong person for a real, delivered invite."""
    from app.api import interviews
    monkeypatch.setattr(interviews.settings, "calendar_backend", "outlook")
    monkeypatch.setattr(interviews.settings, "calendar_sender_email", "subhadeep.m@protivitiglobal.in")
    campaign_id, candidate_id = with_manager
    response = _schedule(
        client, campaign_id, candidate_id, people,
        co_manager_email="daipayan.r@protivitiglobal.in",
        recipient_email="chiranjib.sarma@protivitiglobal.in",
    )
    assert response.status_code == 422
    assert "sender" in response.json()["detail"].lower()


def test_live_invite_rejects_when_no_outlook_account_can_be_resolved(client, with_manager, people, monkeypatch):
    """B22 portability: no hardcoded person is required — but if this
    machine has no configured sender AND no signed-in Outlook profile to
    discover, the request must fail honestly instead of guessing."""
    from app.api import interviews
    monkeypatch.setattr(interviews.settings, "calendar_backend", "outlook")
    monkeypatch.setattr(interviews.settings, "calendar_sender_email", "")
    monkeypatch.setattr(
        outlook_com, "_dispatch_outlook",
        lambda: (_ for _ in ()).throw(RuntimeError("Outlook is not installed")),
    )
    campaign_id, candidate_id = with_manager
    response = _schedule(
        client, campaign_id, candidate_id, people,
        co_manager_email="daipayan.r@protivitiglobal.in",
        recipient_email="chiranjib.sarma@protivitiglobal.in",
    )
    assert response.status_code == 422
    assert "outlook account" in response.json()["detail"].lower()


def test_manager_verdict_can_be_followed_by_an_actual_schedule(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    verdict = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    assert verdict.status_code == 201
    assert client.get(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}"
    ).json()["status"] == "INTERVIEW_SCHEDULED"

    arranged = _schedule(client, campaign_id, candidate_id, people)
    assert arranged.status_code == 201
    assert arranged.json()["when"]
    assert len(client.get(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}"
    ).json()) == 1

    status = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert status["status"] == "INTERVIEW_SCHEDULED"


def test_scheduling_refuses_a_duplicate_round_after_manager_verdict(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    assert _schedule(client, campaign_id, candidate_id, people).status_code == 201
    again = _schedule(client, campaign_id, candidate_id, people)
    assert again.status_code == 422
    assert "reschedule" in again.json()["detail"]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def test_feedback_needs_a_recorded_appointment(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    response = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback",
        json={"recommendation": "PROCEED", "actor_id": people["manager"]["id"]},
    )
    assert response.status_code == 422
    assert "schedule" in response.json()["detail"].lower()


def test_reschedule_needs_an_existing_appointment(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    response = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/reschedule",
        json={"when": "2026-09-21T10:00:00", "actor_id": people["manager"]["id"]},
    )
    assert response.status_code == 422
    assert "schedule" in response.json()["detail"].lower()

def test_feedback_moves_the_candidate_to_feedback_complete(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    _schedule(client, campaign_id, candidate_id, people)

    feedback = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback",
        json={
            "recommendation": "PROCEED",
            "scores": {"technical": 4, "communication": 5},
            "strengths": "Deep console experience.",
            "concerns": "",
            "actor_id": people["manager"]["id"],
        },
    )
    assert feedback.status_code == 200
    body = feedback.json()
    assert body["feedback_in"] is True
    assert body["recommendation"] == "PROCEED"

    status = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert status["status"] == "FEEDBACK_COMPLETE"


def test_a_decline_needs_a_reason(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    _schedule(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback",
        json={
            "recommendation": "DECLINE",
            "scores": {"technical": 2},
            "actor_id": people["manager"]["id"],
        },
    )
    assert refused.status_code == 422
    assert "reason" in refused.json()["detail"]

    status = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert status["status"] == "INTERVIEW_SCHEDULED"


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------

def test_reschedule_is_an_audit_row_not_a_state_change(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    _schedule(client, campaign_id, candidate_id, people)

    rescheduled = client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/reschedule",
        json={"when": "2026-09-22T14:00:00", "reason": "Panelist travelling",
              "actor_id": people["recruiter"]["id"]},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["when"] == "2026-09-22T14:00:00"

    status = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert status["status"] == "INTERVIEW_SCHEDULED"

    history = client.get(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}"
    ).json()
    assert len(history) == 1
    assert history[0]["when"] == "2026-09-22T14:00:00"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_the_campaign_list_reads_back_scheduled_and_fed_back_interviews(
    client, with_manager, people
):
    campaign_id, candidate_id = with_manager
    _schedule(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback",
        json={"recommendation": "ANOTHER_ROUND", "actor_id": people["manager"]["id"]},
    )

    rows = client.get(f"/api/campaigns/{campaign_id}/interviews").json()
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == candidate_id
    assert rows[0]["feedback_in"] is True
    assert rows[0]["recommendation"] == "ANOTHER_ROUND"
