"""
The recruitment lifecycle state machine.

Pure logic: no database session, no HTTP. Which moves are legal, who may make
them, and what a state means in words a recruiter would use.

Two rules shape everything here.

**Transitions are explicit and total.** Every move has a from-state, a
to-state, a named actor and a timestamp. Nothing about a candidate's position
is derived on read, because a status nobody can point at a transition for is a
status nobody can audit — and this is a process with money at the end of it.

**A transition is never destructive.** Moving backwards is a legitimate
outcome: an approval chain can return someone to interview. That records as a
new transition with a reason, not by rewinding history.
"""
from __future__ import annotations

from app.db.models import LifecycleStatus as S
from app.db.models import UserRole

# What each state means to a person. DATA.md: an enum value never reaches a
# reader, and this one appears on the leaderboard, the timeline and the audit
# screen.
STATUS_WORDS = {
    S.SHORTLISTED: "Shortlisted, not yet sent to the hiring manager",
    S.WITH_HIRING_MANAGER: "With the hiring manager",
    S.RETURNED_TO_RECRUITER: "Back with the recruiter, question asked",
    S.INTERVIEW_SCHEDULED: "Interview arranged",
    S.FEEDBACK_COMPLETE: "Interview feedback in",
    S.PENDING_APPROVAL: "Waiting for approval",
    S.PENDING_COST_CENTRE: "Waiting for budget approval",
    S.APPROVED: "Approved",
    S.OFFER_DRAFTED: "Offer drafted, not yet sent",
    S.OFFER_SENT: "Offer with the candidate",
    S.OFFER_ACCEPTED: "Offer accepted",
    S.OFFER_DECLINED: "Offer declined by the candidate",
    S.HIRED: "Hired",
    S.CLOSED: "Closed",
    S.ON_HOLD: "On hold",
    S.NOT_PROCEEDING: "Not proceeding",
    S.WITHDRAWN: "Withdrew",
    S.WAITLISTED: "Waitlisted as a backup candidate",
}

# The moves that exist. Anything not listed is refused.
ALLOWED: dict[S, set[S]] = {
    S.SHORTLISTED: {S.WITH_HIRING_MANAGER, S.NOT_PROCEEDING, S.WITHDRAWN, S.ON_HOLD},
    S.WITH_HIRING_MANAGER: {
        S.INTERVIEW_SCHEDULED, S.RETURNED_TO_RECRUITER, S.NOT_PROCEEDING,
        S.WITHDRAWN, S.ON_HOLD,
    },
    S.RETURNED_TO_RECRUITER: {
        S.WITH_HIRING_MANAGER, S.NOT_PROCEEDING, S.WITHDRAWN, S.ON_HOLD,
    },
    S.INTERVIEW_SCHEDULED: {
        S.FEEDBACK_COMPLETE, S.NOT_PROCEEDING, S.WITHDRAWN, S.ON_HOLD,
    },
    S.FEEDBACK_COMPLETE: {
        # Back to interview is legitimate — a second round, or a panel that
        # wants another conversation before committing.
        S.PENDING_APPROVAL, S.INTERVIEW_SCHEDULED, S.NOT_PROCEEDING,
        S.WITHDRAWN, S.ON_HOLD,
    },
    S.PENDING_APPROVAL: {
        S.PENDING_COST_CENTRE, S.FEEDBACK_COMPLETE, S.NOT_PROCEEDING,
        S.WITHDRAWN, S.ON_HOLD,
    },
    S.PENDING_COST_CENTRE: {
        S.APPROVED, S.PENDING_APPROVAL, S.NOT_PROCEEDING, S.WITHDRAWN, S.ON_HOLD,
    },
    S.APPROVED: {S.OFFER_DRAFTED, S.CLOSED, S.WITHDRAWN, S.ON_HOLD},
    S.OFFER_DRAFTED: {
        # Back to APPROVED so a draft can be revised without leaving the
        # lifecycle.
        S.OFFER_SENT, S.APPROVED, S.NOT_PROCEEDING, S.WITHDRAWN, S.ON_HOLD,
    },
    S.OFFER_SENT: {
        # Back to OFFER_DRAFTED so a revised offer can be re-issued.
        S.OFFER_ACCEPTED, S.OFFER_DECLINED, S.OFFER_DRAFTED, S.WITHDRAWN,
        S.ON_HOLD,
    },
    S.OFFER_ACCEPTED: {
        # WITHDRAWN stays reachable: a candidate who accepts can still not
        # join.
        S.HIRED, S.WITHDRAWN, S.ON_HOLD,
    },
    S.OFFER_DECLINED: {S.CLOSED},
    # Terminal. Reopening is a new campaign decision, not a state change.
    S.CLOSED: set(),
    S.NOT_PROCEEDING: set(),
    S.WITHDRAWN: set(),
    S.HIRED: set(),
    # A hold resumes wherever it paused, so its targets are computed from the
    # state it was held from rather than listed here.
    S.ON_HOLD: set(),
    # B15: a waitlisted candidate can be promoted into the active pipeline
    # (typically once the leading candidate declines or does not join), or
    # the campaign can close them out directly.
    S.WAITLISTED: {S.SHORTLISTED, S.NOT_PROCEEDING, S.WITHDRAWN},
}

# Who may move a candidate into a state. A recruiter cannot decide the
# hiring manager's verdict, and vice versa.
WHO_MAY: dict[S, set[UserRole]] = {
    S.WITH_HIRING_MANAGER: {UserRole.RECRUITER, UserRole.ADMIN},
    S.RETURNED_TO_RECRUITER: {UserRole.HIRING_MANAGER, UserRole.ADMIN},
    S.INTERVIEW_SCHEDULED: {
        UserRole.HIRING_MANAGER, UserRole.RECRUITER, UserRole.ADMIN,
    },
    S.FEEDBACK_COMPLETE: {
        UserRole.HIRING_MANAGER, UserRole.RECRUITER, UserRole.ADMIN,
    },
    S.PENDING_APPROVAL: {UserRole.RECRUITER, UserRole.HIRING_MANAGER, UserRole.ADMIN},
    # B25: routing to the cost centre is HR's own "proceed" step (naming the
    # budget and its holder), so the recruiter who requested approval needs
    # to be able to make this move too, not just a manager/admin standing in.
    S.PENDING_COST_CENTRE: {UserRole.ADMIN, UserRole.HIRING_MANAGER, UserRole.RECRUITER},
    # B25: the actual budget grant belongs to whoever holds the budget — the
    # REVIEWER role (labelled "Budget approver", app/api/lifecycle.py
    # ROLE_WORDS), not just an admin standing in for the demo.
    S.APPROVED: {UserRole.ADMIN, UserRole.REVIEWER},
    S.OFFER_DRAFTED: {UserRole.RECRUITER, UserRole.ADMIN},
    S.OFFER_SENT: {UserRole.RECRUITER, UserRole.ADMIN},
    S.OFFER_ACCEPTED: {UserRole.RECRUITER, UserRole.ADMIN},
    S.OFFER_DECLINED: {UserRole.RECRUITER, UserRole.ADMIN},
    S.HIRED: {UserRole.ADMIN},
    S.CLOSED: {UserRole.RECRUITER, UserRole.ADMIN},
}

# States where a reason is not optional. Every one of these is a moment
# somebody will later be asked to account for.
REASON_REQUIRED = {
    S.NOT_PROCEEDING, S.RETURNED_TO_RECRUITER, S.ON_HOLD, S.WITHDRAWN,
    # Why a candidate declined is the first thing anyone reviewing the
    # campaign will ask.
    S.OFFER_DECLINED,
}

# Where the clock stops. An SLA that keeps running while the business has
# deliberately paused produces noise, and a noisy SLA gets ignored.
CLOCK_STOPPED = {
    S.ON_HOLD, S.CLOSED, S.NOT_PROCEEDING, S.WITHDRAWN, S.HIRED, S.WAITLISTED,
}

TERMINAL = {S.CLOSED, S.NOT_PROCEEDING, S.WITHDRAWN, S.HIRED}

# B02 phase 5: target duration per stage, in hours, and how long before that
# deadline a reminder is due. No client-specified policy exists yet
# (`docs/DECISIONS.md`), so these are placeholder business defaults sized to
# the stage — a hiring-manager review gets longer than an offer draft. A
# state with no entry here never gets a due date: that is every member of
# `CLOCK_STOPPED`, by construction, since a paused or finished stage has
# nothing left to be late for.
SLA_HOURS: dict[S, tuple[int, int]] = {
    S.SHORTLISTED: (48, 12),
    S.WITH_HIRING_MANAGER: (72, 24),
    S.RETURNED_TO_RECRUITER: (24, 8),
    S.INTERVIEW_SCHEDULED: (120, 24),
    S.FEEDBACK_COMPLETE: (48, 12),
    S.PENDING_APPROVAL: (72, 24),
    S.PENDING_COST_CENTRE: (72, 24),
    S.APPROVED: (48, 12),
    S.OFFER_DRAFTED: (24, 8),
    S.OFFER_SENT: (120, 24),
    S.OFFER_ACCEPTED: (120, 24),
}


def sla_target_hours(status: S) -> int | None:
    """Hours a candidate may sit in this stage before it is overdue."""
    pair = SLA_HOURS.get(status)
    return pair[0] if pair else None


def sla_reminder_lead_hours(status: S) -> int | None:
    """How long before the due time this stage's reminder fires."""
    pair = SLA_HOURS.get(status)
    return pair[1] if pair else None

# The order a funnel is read in. It is the progression, not the counts.
#
# `funnel()` used to sort by how many people sat in each state and to omit any
# state nobody was in. Both are wrong on a chart: sorting by size reorders the
# stages every time somebody moves, and an omitted stage makes a gap in the
# pipeline look like it is not part of the process. A stage with nobody in it
# is a fact about the campaign, and often the most important one on the page.
#
# The off-ramps come last, after the line a candidate is meant to travel,
# because they are outcomes rather than steps.
STAGE_ORDER = [
    S.SHORTLISTED,
    S.WITH_HIRING_MANAGER,
    S.RETURNED_TO_RECRUITER,
    S.INTERVIEW_SCHEDULED,
    S.FEEDBACK_COMPLETE,
    S.PENDING_APPROVAL,
    S.PENDING_COST_CENTRE,
    S.APPROVED,
    S.OFFER_DRAFTED,
    S.OFFER_SENT,
    S.OFFER_ACCEPTED,
    S.HIRED,
    # off-ramps
    S.ON_HOLD,
    S.WAITLISTED,
    S.OFFER_DECLINED,
    S.NOT_PROCEEDING,
    S.WITHDRAWN,
    S.CLOSED,
]

# Where the funnel's visible spine ends and the off-ramps begin.
OFF_RAMP = {
    S.ON_HOLD, S.WAITLISTED, S.OFFER_DECLINED, S.NOT_PROCEEDING, S.WITHDRAWN,
    S.CLOSED,
}


class TransitionError(ValueError):
    """Refused move. The message is shown to a person, so it reads as one."""


def words(status) -> str:
    try:
        return STATUS_WORDS[S(status)]
    except (ValueError, KeyError):
        return "In progress"


def targets(current: S, held_from: S | None = None) -> set[S]:
    """Where this candidate can go next."""
    if current == S.ON_HOLD:
        # A hold resumes where it paused. Without the origin recorded the
        # only honest answer is the start of the lifecycle.
        resume = held_from or S.SHORTLISTED
        return {resume, S.NOT_PROCEEDING, S.WITHDRAWN}
    return ALLOWED.get(current, set())


def check(current: S, target: S, *, role: UserRole | None = None,
          reason: str = "", held_from: S | None = None) -> None:
    """
    Raise if this move is not allowed. Silence means it is.

    Ordered so the person gets the most useful objection first: whether the
    move exists at all, then whether they may make it, then whether they have
    given a reason.
    """
    if current in TERMINAL:
        raise TransitionError(
            f"This candidate is already {words(current).lower()}, so nothing "
            "further can be recorded against them in this campaign."
        )

    if target not in targets(current, held_from):
        allowed = sorted(words(s) for s in targets(current, held_from))
        raise TransitionError(
            f"A candidate who is {words(current).lower()} cannot move to "
            f"{words(target).lower()}. From here they can go to: "
            + (", ".join(allowed) if allowed else "nowhere") + "."
        )

    permitted = WHO_MAY.get(target)
    if permitted is not None and role is not None and role not in permitted:
        raise TransitionError(
            f"Your role does not allow you to move a candidate to "
            f"{words(target).lower()}."
        )

    if target in REASON_REQUIRED and not reason.strip():
        raise TransitionError(
            f"Moving a candidate to {words(target).lower()} needs a reason. "
            "It is the first thing anyone reviewing this decision will look for."
        )
