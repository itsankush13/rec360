"""
B15 — historical candidate reuse.

Preserve the campaign ranking, keep a backup/waitlisted candidate alongside
the one taken forward, and surface that backup the moment the leading
candidate declines an offer or withdraws after accepting one. Rank is
recorded once, at the moment a candidate enters the lifecycle (shortlisted
or waitlisted) — a later re-evaluation moving scores around must not
retroactively change the ranking a decision was actually made against.
"""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, WEAK_CV, make_cv_pdf

FUTURE_START = (date.today() + timedelta(days=30)).isoformat()
FUTURE_EXPIRY = (date.today() + timedelta(days=10)).isoformat()


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
def ranked_pair(client):
    """
    One campaign, two assessed candidates with distinct scores: Priya
    (STRONG_CV) ranks 1, Rahul (WEAK_CV) ranks 2 against a Python/AWS rubric.
    Returns (campaign_id, strong_candidate_id, weak_candidate_id).
    """
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Reuse", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
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
    ])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    board = client.get(f"/api/campaigns/{campaign_id}/leaderboard").json()
    assert len(board) == 2
    board.sort(key=lambda entry: entry["rank"])
    strong_id, weak_id = board[0]["candidate_id"], board[1]["candidate_id"]
    assert board[0]["rank"] == 1 and board[1]["rank"] == 2
    return campaign_id, strong_id, weak_id


@pytest.fixture()
def approved_with_backup(client, ranked_pair, people):
    """
    The top-ranked candidate walked to APPROVED and offered; the runner-up
    waitlisted as a backup.
    """
    campaign_id, strong_id, weak_id = ranked_pair

    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{strong_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{weak_id}/disposition",
        json={"disposition": "WAITLIST", "actor": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{weak_id}/waitlist",
        params={"actor_id": people["recruiter"]["id"]},
    )

    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"], "manager_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "FEEDBACK_COMPLETE", "actor_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "PENDING_APPROVAL", "actor_id": people["recruiter"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "PENDING_COST_CENTRE", "actor_id": people["admin"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "APPROVED", "actor_id": people["admin"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/offers/{strong_id}/draft",
        json={
            "actor_id": people["recruiter"]["id"], "base_salary": 12000,
            "currency": "QAR", "grade": "G7", "start_date": FUTURE_START,
            "expiry_date": FUTURE_EXPIRY, "allowances": {"housing": 1500},
            "notes": "",
        },
    )
    client.post(
        f"/api/campaigns/{campaign_id}/offers/{strong_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    return campaign_id, strong_id, weak_id


# ---------------------------------------------------------------------------
# Entering the lifecycle as a backup
# ---------------------------------------------------------------------------

def test_only_a_waitlisted_candidate_enters_as_a_backup(client, ranked_pair, people):
    """
    Symmetric with the existing shortlist gate: a screening decision, not a
    score alone, admits a candidate to the lifecycle — even as a backup.
    """
    campaign_id, strong_id, weak_id = ranked_pair
    refused = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{weak_id}/waitlist",
        params={"actor_id": people["recruiter"]["id"]},
    )
    assert refused.status_code == 422
    assert "waitlisted" in refused.json()["detail"]


def test_waitlisting_persists_the_leaderboard_rank(client, ranked_pair, people):
    campaign_id, strong_id, weak_id = ranked_pair
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{weak_id}/disposition",
        json={"disposition": "WAITLIST", "actor": "Fatima Al-Rashid"},
    )
    entered = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{weak_id}/waitlist",
        params={"actor_id": people["recruiter"]["id"]},
    ).json()
    assert entered["status"] == "WAITLISTED"
    assert entered["status_label"] == "Waitlisted as a backup candidate"
    assert entered["campaign_rank"] == 2


def test_shortlist_entry_also_persists_a_rank(client, ranked_pair, people):
    """B15's "preserve the campaign ranking" is not waitlist-only."""
    campaign_id, strong_id, weak_id = ranked_pair
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{strong_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    entered = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    ).json()
    assert entered["campaign_rank"] == 1


# ---------------------------------------------------------------------------
# The backups list
# ---------------------------------------------------------------------------

def test_the_backups_endpoint_lists_waitlisted_candidates_by_rank(
    client, approved_with_backup
):
    campaign_id, strong_id, weak_id = approved_with_backup
    backups = client.get(f"/api/campaigns/{campaign_id}/lifecycle/backups").json()
    assert len(backups) == 1
    assert backups[0]["candidate_id"] == weak_id
    assert backups[0]["candidate_name"] == "Rahul Verma"
    assert backups[0]["campaign_rank"] == 2


# ---------------------------------------------------------------------------
# Surfacing the next candidate
# ---------------------------------------------------------------------------

def test_declining_the_offer_surfaces_the_waitlisted_backup(
    client, approved_with_backup, people
):
    campaign_id, strong_id, weak_id = approved_with_backup
    declined = client.post(
        f"/api/campaigns/{campaign_id}/offers/{strong_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "DECLINED",
              "reason": "Took a counter-offer.", "reason_code": "COUNTER_OFFER"},
    )
    assert declined.status_code == 200
    body = declined.json()
    assert body["status"] == "OFFER_DECLINED"
    assert body["next_backup_candidate_id"] == weak_id
    assert body["next_backup_candidate_name"] == "Rahul Verma"
    assert body["next_backup_rank"] == 2


def test_accepting_never_surfaces_a_backup(client, approved_with_backup, people):
    campaign_id, strong_id, weak_id = approved_with_backup
    accepted = client.post(
        f"/api/campaigns/{campaign_id}/offers/{strong_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "ACCEPTED"},
    ).json()
    assert accepted["next_backup_candidate_id"] is None
    assert accepted["next_backup_candidate_name"] == ""


def test_not_joining_after_acceptance_also_surfaces_the_backup(
    client, approved_with_backup, people
):
    """
    B15's second trigger: "does not join" after accepting. There is no
    dedicated endpoint for this — it is recorded as the same
    OFFER_ACCEPTED -> WITHDRAWN move any other lifecycle exit uses.
    """
    campaign_id, strong_id, weak_id = approved_with_backup
    client.post(
        f"/api/campaigns/{campaign_id}/offers/{strong_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "ACCEPTED"},
    )
    withdrawn = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "WITHDRAWN", "actor_id": people["recruiter"]["id"],
              "reason": "Did not show up on the agreed start date."},
    )
    assert withdrawn.status_code == 200
    body = withdrawn.json()
    assert body["next_backup_candidate_id"] == weak_id
    assert body["next_backup_rank"] == 2


def test_no_backup_surfaces_when_nobody_is_waitlisted(client, ranked_pair, people):
    """Only the top candidate proceeds; the runner-up is never waitlisted."""
    campaign_id, strong_id, weak_id = ranked_pair
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{strong_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/enter",
        params={"actor_id": people["recruiter"]["id"]},
    )
    withdrawn = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{strong_id}/transition",
        json={"to_status": "WITHDRAWN", "actor_id": people["recruiter"]["id"],
              "reason": "Withdrew before the process finished."},
    ).json()
    assert withdrawn["next_backup_candidate_id"] is None
    assert withdrawn["next_backup_candidate_name"] == ""
    assert withdrawn["next_backup_rank"] is None


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

def test_a_waitlisted_candidate_can_be_promoted_into_the_active_pipeline(
    client, approved_with_backup, people
):
    campaign_id, strong_id, weak_id = approved_with_backup
    promoted = client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{weak_id}/transition",
        json={"to_status": "SHORTLISTED", "actor_id": people["recruiter"]["id"]},
    )
    assert promoted.status_code == 200
    body = promoted.json()
    assert body["status"] == "SHORTLISTED"
    # The rank recorded at waitlist entry carries forward through promotion —
    # it is not recomputed, and not lost.
    assert body["campaign_rank"] == 2

    backups = client.get(f"/api/campaigns/{campaign_id}/lifecycle/backups").json()
    assert backups == []
