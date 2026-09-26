"""
Recruiter disposition, override, and audit trail.

The governing rule, and the reason this is a separate service rather than a
few columns on `Evaluation`:

    **A recruiter decision never mutates an evaluation.**

An override is a `CandidateAction` row that supersedes the AI recommendation
for display. The evaluation keeps its original score, recommendation,
criteria, evidence and findings untouched. This is not fussiness — the
client's first requirement is that AI recommendations are never presented as
autonomous decisions, and that cuts both ways. If a human overrules the
machine and the machine's output is edited to match, there is no longer any
record that a disagreement happened. That record is exactly what an auditor
asks for.

Actions are append-only for the same reason. Changing your mind adds a row
and marks the previous one superseded; it does not edit history. `is_current`
points at the operative decision.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActionType, AuditAction, AuditEvent, Campaign, Candidate, CandidateAction,
    ConfidenceBand, CriterionOutcome, Disposition, Evaluation, Recommendation,
)


logger = logging.getLogger(__name__)


class DispositionError(Exception):
    """Caller-fixable; the API maps this to 4xx."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


# Two audit rows written back to back can land on the same
# datetime.now(timezone.utc) tick (the wall clock's resolution is coarser
# than two back-to-back writes in a test, or even in a single request that
# writes more than one audit row). audit_trail() and similar reads have no
# other ordering column to fall back on — AuditEvent.id is a random UUID,
# not an insertion-ordered one — so a tie here is an ordering bug, not just
# a display nicety. Force each new event strictly after the last one this
# process has written.
_last_audit_timestamp: datetime | None = None


def _now() -> datetime:
    global _last_audit_timestamp
    now = datetime.now(timezone.utc)
    if _last_audit_timestamp is not None and now <= _last_audit_timestamp:
        now = _last_audit_timestamp + timedelta(microseconds=1)
    _last_audit_timestamp = now
    return now


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

# DATA.md: an enum value never reaches a reader, and the audit screen is the
# one a client auditor reads most literally.
DISPOSITION_WORDS = {
    Disposition.SHORTLIST: "shortlisted",
    Disposition.REJECT: "not taken forward",
    Disposition.HOLD: "put on hold",
    Disposition.REQUEST_REVIEW: "sent for a second look",
    Disposition.INTERVIEW: "invited to interview",
    Disposition.WAITLIST: "kept as a backup candidate",
}

RECOMMENDATION_WORDS = {
    Recommendation.STRONG_FIT: "a strong fit",
    Recommendation.POTENTIAL_FIT: "a potential fit",
    Recommendation.REVIEW_REQUIRED: "one to review",
    Recommendation.NOT_RECOMMENDED: "not recommended",
}

# How many criteria to name in a suggested rationale. Enough to be useful,
# short enough to still be a starting point the recruiter edits rather than
# a wall of text they skim past.
_RATIONALE_CRITERIA_LIMIT = 3

# B05: the recruiter's decision box should read as a scannable brief, not a
# one-liner — enough words that the supporting bullets carry real detail.
_RATIONALE_MIN_WORDS = 120


def _join_prose(items: list[str]) -> str:
    """Join as prose — 'A, B and C' — never a bare comma list or a bullet."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _template_rationale(evaluation: Evaluation) -> tuple[str, str]:
    """
    The deterministic bulleted brief this function returns whenever the LLM
    is unavailable or fails, and the source draft the LLM is asked to
    compress otherwise. B05 wants the pre-filled comment box to read as a
    scannable bullet list of at least `_RATIONALE_MIN_WORDS` words, with the
    single most important point — the overall call — written first and
    bolded (`**...**`) so it is the first thing a recruiter reads, ahead of
    the supporting detail.

    Returns (score_line, bulleted_body) — the score line is kept separate so
    the caller can guarantee it appears verbatim in the final text no matter
    what an LLM does with the rest. Never returns a bare score with no body:
    even with nothing specific to cite, the first bullet states plainly
    whether the candidate looks suitable for the role.
    """
    ordered = sorted(evaluation.criteria, key=lambda c: -c.weight)
    strengths = [
        c.label for c in ordered
        if c.weight > 0 and c.outcome == CriterionOutcome.CONFIRMED_MATCH
    ][:_RATIONALE_CRITERIA_LIMIT]
    concerns = [
        c.label for c in ordered
        if c.weight > 0 and c.outcome in (
            CriterionOutcome.CONTRADICTORY_EVIDENCE, CriterionOutcome.NOT_DEMONSTRATED,
        )
    ][:_RATIONALE_CRITERIA_LIMIT]

    word = RECOMMENDATION_WORDS.get(evaluation.recommendation, "")
    score = round(evaluation.overall_score)
    score_line = f"Score: {score} out of 100" + (f" — {word}." if word else ".")

    verdict = {
        Recommendation.STRONG_FIT:
            "this looks like a strong match for the role, backed by clear, "
            "direct evidence across the criteria that carry the most weight.",
        Recommendation.POTENTIAL_FIT:
            "this looks like a workable match worth a closer look — there is "
            "enough confirmed evidence to justify moving forward.",
        Recommendation.REVIEW_REQUIRED:
            "a person should review this one before deciding either way, "
            "since the evidence on file is mixed or not yet complete enough "
            "to call.",
        Recommendation.NOT_RECOMMENDED:
            "this does not look like a good match for the role, based on the "
            "evidence gathered so far.",
    }.get(
        evaluation.recommendation,
        "there is not yet enough evidence on file to call this one way or "
        "the other.",
    )

    # The headline bullet, first and bolded — everything after it is
    # supporting detail, not the main point.
    bullets = [f"**Overall: {verdict[0].upper()}{verdict[1:]}**"]

    if strengths:
        bullets.append(
            "Confirmed strengths: " + _join_prose(strengths) +
            " — each backed by direct evidence in the CV rather than an "
            "inference."
        )
    if concerns:
        lead = "Gap to probe" if len(concerns) == 1 else "Gaps to probe"
        bullets.append(
            f"{lead}: " + _join_prose(concerns) +
            " — worth a direct question in screening rather than assuming "
            "either way."
        )
    if not strengths and not concerns:
        # Nothing specific enough to cite by name — say so plainly rather
        # than leaving the list thin.
        bullets.append(
            (evaluation.narrative or "").strip()
            or "There is not enough detail in the CV yet to point to a "
               "specific strength or gap by name."
        )

    years_total = round(evaluation.experience_years_total or 0, 1)
    years_relevant = round(evaluation.experience_years_relevant or 0, 1)
    bullets.append(
        f"Experience on file: {years_total:g} years total, of which "
        f"{years_relevant:g} look directly relevant to this role."
    )

    confidence_word = {
        ConfidenceBand.HIGH: "high",
        ConfidenceBand.MEDIUM: "medium",
        ConfidenceBand.LOW: "low",
    }.get(evaluation.confidence_band, "low")
    bullets.append(
        f"Confidence in this read: {confidence_word} "
        f"({round((evaluation.overall_confidence or 0) * 100)} out of 100), "
        "based on how much of the rubric the CV gave clear evidence for."
    )

    if evaluation.narrative and evaluation.narrative.strip() not in bullets[0]:
        bullets.append(evaluation.narrative.strip())

    # Guarantee the word-count floor without inventing a new fact: name what
    # this draft is already grounded in rather than padding with filler.
    if len(" ".join(bullets).split()) < _RATIONALE_MIN_WORDS:
        bullets.append(
            f"This draft is built from the same {len(evaluation.criteria)} "
            "rubric criteria and evidence shown on this page — nothing here "
            "is inferred beyond what the CV supports."
        )

    return score_line, "\n".join("- " + b for b in bullets)


_RATIONALE_SYSTEM_PROMPT = (
    "You rewrite a hiring-evaluation draft into a short bulleted brief that a "
    "non-technical hiring manager can scan in a few seconds. Output plain "
    "text bullet points only, one per line, each line starting with '- ' — "
    "never continuous prose. The very first bullet is the single most "
    "important point, the overall call on whether the candidate looks "
    "suitable for the role, and it alone is wrapped in **double asterisks** "
    "so it reads as bold; every other bullet stays plain text and covers "
    "what is confirmed and what is a concern. Write at least 120 words in "
    "total across all the bullets combined. Never invent a fact that is not "
    "already in the draft. Do not restate the numeric score — it is shown "
    "separately. Never use the phrase 'AI assessment'."
)


def _llm_brief_rationale(template: str) -> str | None:
    """
    Ask an LLM to compress `_template_rationale`'s bullet list into a brief
    of its own, same bulleted shape. Returns None (never raises) on any
    provider/config/network problem — a missing API key, a timeout,
    whatever — so a demo or a test environment with no LLM configured
    silently gets the deterministic bullets instead of a 500. Same
    lazy-import pattern as app/core/summary_generator.py, so importing this
    module never requires provider credentials.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.core.llm_provider import get_cached_chat_model

        model = get_cached_chat_model(temperature=0.3)
        response = model.invoke([
            SystemMessage(content=_RATIONALE_SYSTEM_PROMPT),
            HumanMessage(content=template),
        ])
        text = (getattr(response, "content", None) or "").strip()
        return text or None
    except Exception:
        logger.warning(
            "AI rationale LLM call failed; using the deterministic draft instead.",
            exc_info=True,
        )
        return None


def _is_stale_rationale(text: str) -> bool:
    """
    A cache written before this bulleted rewrite was either a bare score
    line with no body at all, or a continuous prose paragraph with no
    bullets — both read as a wall of text rather than a scannable list with
    the main point first. `Evaluation` is write-once and this cache is meant
    to be too, but a shape this function no longer produces is regenerated
    once rather than kept forever. Word count is deliberately not
    re-validated here: `_RATIONALE_SYSTEM_PROMPT` asks for 120 words but a
    legitimate brief that lands a little short should still be reused, not
    re-billed to the LLM on every read.
    """
    if not text or "\n\n" not in text:
        return True
    body = text.split("\n\n", 1)[1]
    return "\n- " not in body


def _suggested_rationale(db: Session | None, evaluation: Evaluation | None) -> str:
    """
    B05: a starting draft for the disposition comment box, not a decision.
    The recruiter reads, edits and saves it themselves — this only saves
    them from writing the same evidence-backed summary from scratch every
    time. Built from the same evidence the score already carries, so it
    never claims anything the evaluation does not.

    Now genuinely LLM-generated (previously pure string-templating despite
    being labelled "AI"), rewritten as a scannable bullet list of at least
    120 words with the main point first and bolded — never the bare score
    on its own line. An `Evaluation` is write-once (see the class docstring), so
    the result is generated once and cached on `Evaluation.ai_rationale_summary`
    rather than re-billed on every Candidate 360 page view. `db` is optional
    only so callers with no session on hand (there are none today) still get
    an uncached result rather than an error.
    """
    if evaluation is None:
        return ""
    cached = evaluation.ai_rationale_summary
    if cached and not _is_stale_rationale(cached):
        return cached

    score_line, body = _template_rationale(evaluation)
    brief = _llm_brief_rationale(f"{score_line}\n{body}")
    summary = f"{score_line}\n\n{brief or body}"
    # Belt and suspenders: guarantee the forbidden phrase never survives even
    # if the LLM ignores the system prompt.
    summary = re.sub(r"(?i)ai assessment", "assessment", summary)

    if db is not None:
        evaluation.ai_rationale_summary = summary
        db.add(evaluation)
        db.flush()
    return summary


def record_audit(
    db: Session,
    action: AuditAction,
    *,
    campaign_id: str | None = None,
    candidate_id: str | None = None,
    entity_type: str = "",
    entity_id: str = "",
    summary: str = "",
    before: dict | None = None,
    after: dict | None = None,
    actor: str = "",
) -> AuditEvent:
    """
    Append an audit event.

    Never raises on the caller's behalf — an audit write failing must not
    fail the operation being audited, but it must also not pass silently, so
    the exception surfaces to the caller's logging rather than being
    swallowed here.
    """
    event = AuditEvent(
        campaign_id=campaign_id,
        # An event about a candidate carries the candidate, whether or not
        # the caller thought to pass it separately from entity_id.
        candidate_id=candidate_id or (entity_id if entity_type == "candidate" else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id or "",
        summary=summary[:4000],
        before=before,
        after=after,
        actor=actor or "",
        created_at=_now(),
    )
    db.add(event)
    db.flush()
    return event


def audit_trail(
    db: Session,
    campaign_id: str | None = None,
    *,
    action: AuditAction | None = None,
    candidate_id: str | None = None,
    actor: str | None = None,
    since=None,
    until=None,
    limit: int = 200,
) -> list[AuditEvent]:
    """
    Newest first — screen 9 reads the most recent activity.

    Every filter is optional, including the campaign. An auditor's questions
    do not arrive campaign-shaped: "what did this person do last Tuesday",
    "everything that happened to this applicant", "every rubric approval this
    quarter" all cut across campaigns, and a record that can only be read one
    campaign at a time cannot answer them.
    """
    statement = select(AuditEvent)
    if campaign_id is not None:
        statement = statement.where(AuditEvent.campaign_id == campaign_id)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if candidate_id is not None:
        statement = statement.where(AuditEvent.candidate_id == candidate_id)
    if actor:
        statement = statement.where(AuditEvent.actor.ilike(f"%{actor}%"))
    if since is not None:
        statement = statement.where(AuditEvent.created_at >= since)
    if until is not None:
        statement = statement.where(AuditEvent.created_at <= until)
    return list(db.scalars(
        statement.order_by(AuditEvent.created_at.desc()).limit(limit)
    ).all())


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _require_candidate(db: Session, campaign_id: str, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.campaign_id != campaign_id:
        raise DispositionError(
            f"Candidate '{candidate_id}' is not in campaign '{campaign_id}'."
        )
    return candidate


def _current_evaluation(db: Session, candidate_id: str) -> Evaluation | None:
    return db.scalars(
        select(Evaluation)
        .where(Evaluation.candidate_id == candidate_id, Evaluation.is_current.is_(True))
        .order_by(Evaluation.created_at.desc())
    ).first()


def current_action(db: Session, candidate_id: str) -> CandidateAction | None:
    """
    The operative decision for a candidate — the latest DISPOSITION or
    OVERRIDE. Comments are excluded: a note is not a decision.
    """
    return db.scalars(
        select(CandidateAction)
        .where(
            CandidateAction.candidate_id == candidate_id,
            CandidateAction.is_current.is_(True),
            CandidateAction.action_type != ActionType.COMMENT,
        )
        .order_by(CandidateAction.created_at.desc())
    ).first()


def action_history(db: Session, candidate_id: str) -> list[CandidateAction]:
    """Every action ever taken, newest first. Nothing is deleted."""
    return list(db.scalars(
        select(CandidateAction)
        .where(CandidateAction.candidate_id == candidate_id)
        .order_by(CandidateAction.created_at.desc())
    ).all())


def _supersede_previous(db: Session, candidate_id: str, new_action: CandidateAction) -> None:
    """
    Mark earlier decisions superseded. Only decisions — comments accumulate,
    because a thread of notes is not a sequence of contradictions.
    """
    previous = db.scalars(
        select(CandidateAction).where(
            CandidateAction.candidate_id == candidate_id,
            CandidateAction.is_current.is_(True),
            CandidateAction.id != new_action.id,
            CandidateAction.action_type != ActionType.COMMENT,
        )
    ).all()
    for action in previous:
        action.is_current = False
        action.superseded_by_action_id = new_action.id
    db.flush()


def add_comment(
    db: Session, campaign_id: str, candidate_id: str, *,
    comment: str, actor: str = "", actor_role: str = "",
) -> CandidateAction:
    if not (comment or "").strip():
        raise DispositionError("A comment cannot be empty.")
    _require_candidate(db, campaign_id, candidate_id)
    evaluation = _current_evaluation(db, candidate_id)

    action = CandidateAction(
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        evaluation_id=evaluation.id if evaluation else None,
        action_type=ActionType.COMMENT,
        comment=comment.strip(),
        actor=actor,
        actor_role=actor_role,
    )
    db.add(action)
    db.flush()

    record_audit(
        db, AuditAction.COMMENT_ADDED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate", entity_id=candidate_id,
        summary=f"Comment added: {comment.strip()[:200]}", actor=actor,
    )
    return action


def set_disposition(
    db: Session, campaign_id: str, candidate_id: str, *,
    disposition: Disposition, comment: str = "", actor: str = "",
    actor_role: str = "",
) -> CandidateAction:
    """
    Record what a recruiter decided. The evaluation is not touched.

    A rejection against an ELIGIBLE, strongly-recommended candidate is
    allowed — the recruiter is the decision-maker, and the point of this
    system is decision support, not gatekeeping. It is simply recorded, with
    the AI's view alongside it, so the divergence is visible.
    """
    _require_candidate(db, campaign_id, candidate_id)
    evaluation = _current_evaluation(db, candidate_id)

    action = CandidateAction(
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        evaluation_id=evaluation.id if evaluation else None,
        action_type=ActionType.DISPOSITION,
        disposition=disposition,
        ai_recommendation=evaluation.recommendation if evaluation else None,
        comment=(comment or "").strip(),
        actor=actor,
        actor_role=actor_role,
    )
    db.add(action)
    db.flush()
    _supersede_previous(db, candidate_id, action)

    record_audit(
        db, AuditAction.DISPOSITION_SET,
        campaign_id=campaign_id, entity_type="candidate", entity_id=candidate_id,
        candidate_id=candidate_id,
        summary=(
            f"Decision recorded: {DISPOSITION_WORDS.get(disposition, 'reviewed')}"
            + (f", where the system had recommended "
               f"{RECOMMENDATION_WORDS.get(evaluation.recommendation, 'no verdict')}"
               if evaluation else "")
        ),
        before={"ai_recommendation": evaluation.recommendation.value} if evaluation else None,
        after={"disposition": disposition.value},
        actor=actor,
    )
    return action


def override_recommendation(
    db: Session, campaign_id: str, candidate_id: str, *,
    overridden_to: Recommendation, reason: str, disposition: Disposition | None = None,
    actor: str = "", actor_role: str = "",
) -> CandidateAction:
    """
    Record a recruiter disagreeing with the AI recommendation.

    A reason is mandatory. An unexplained override is indistinguishable from
    a misclick in an audit six months later, and this is the one action in
    the system where the human is explicitly contradicting the evidence
    trail — so the justification is part of the record, not optional
    metadata.

    The evaluation's `recommendation` field is deliberately left alone. The
    override supersedes it for display; both remain readable.
    """
    if not (reason or "").strip():
        raise DispositionError(
            "An override requires a reason. This is recorded in the audit trail "
            "as the justification for departing from the assessment."
        )
    _require_candidate(db, campaign_id, candidate_id)
    evaluation = _current_evaluation(db, candidate_id)
    if evaluation is None:
        raise DispositionError(
            "This candidate has no assessment to override. Run an evaluation first."
        )
    if evaluation.recommendation == overridden_to:
        raise DispositionError(
            f"The assessment already recommends {overridden_to.value}; there is "
            "nothing to override. Set a disposition instead."
        )

    action = CandidateAction(
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        evaluation_id=evaluation.id,
        action_type=ActionType.OVERRIDE,
        disposition=disposition,
        ai_recommendation=evaluation.recommendation,
        overridden_to=overridden_to,
        reason=reason.strip(),
        actor=actor,
        actor_role=actor_role,
    )
    db.add(action)
    db.flush()
    _supersede_previous(db, candidate_id, action)

    record_audit(
        db, AuditAction.RECOMMENDATION_OVERRIDDEN,
        campaign_id=campaign_id, entity_type="candidate", entity_id=candidate_id,
        candidate_id=candidate_id,
        summary=(
            f"A person overruled the system: "
            f"{RECOMMENDATION_WORDS.get(evaluation.recommendation, 'no verdict')} "
            f"changed to {RECOMMENDATION_WORDS.get(overridden_to, 'another verdict')}. "
            f"Reason: {reason.strip()[:200]}"
        ),
        before={"recommendation": evaluation.recommendation.value,
                "overall_score": evaluation.overall_score},
        after={"recommendation": overridden_to.value},
        actor=actor,
    )
    return action


# ---------------------------------------------------------------------------
# Effective view
# ---------------------------------------------------------------------------

def effective_recommendation(db: Session, candidate_id: str) -> dict:
    """
    What the UI should show, and where it came from.

    Both values are always returned. A screen that shows only the override
    hides the assessment; one that shows only the assessment hides the
    decision. The client's requirement is that a person decides — so the
    person's decision is surfaced, with the machine's view kept visible
    beside it rather than replaced by it.
    """
    evaluation = _current_evaluation(db, candidate_id)
    action = current_action(db, candidate_id)

    ai_recommendation = evaluation.recommendation.value if evaluation else None
    result = {
        "candidate_id": candidate_id,
        "evaluation_id": evaluation.id if evaluation else None,
        "ai_recommendation": ai_recommendation,
        "effective_recommendation": ai_recommendation,
        "is_overridden": False,
        "disposition": None,
        "override_reason": "",
        "decided_by": "",
        "decided_at": None,
        # B05: a draft for the comment box, not an auto-filed decision — the
        # recruiter still edits and saves it themselves.
        "suggested_rationale": _suggested_rationale(db, evaluation),
    }
    if action is None:
        return result

    result["disposition"] = action.disposition.value if action.disposition else None
    result["decided_by"] = action.actor
    result["decided_at"] = action.created_at.isoformat() if action.created_at else None

    if action.action_type == ActionType.OVERRIDE and action.overridden_to:
        result["effective_recommendation"] = action.overridden_to.value
        result["is_overridden"] = True
        result["override_reason"] = action.reason
    return result


def override_rate(db: Session, campaign_id: str) -> dict:
    """
    How often recruiters disagree with the assessment.

    A quality signal for the KPI dashboard, and reported with its
    denominator: "3 of 48 assessed" rather than a bare 6%, per the language
    rules in web/DATA.md.
    """
    assessed = db.scalars(
        select(Evaluation.candidate_id).where(
            Evaluation.campaign_id == campaign_id, Evaluation.is_current.is_(True)
        )
    ).all()
    total = len(set(assessed))

    overrides = db.scalars(
        select(CandidateAction).where(
            CandidateAction.campaign_id == campaign_id,
            CandidateAction.action_type == ActionType.OVERRIDE,
            CandidateAction.is_current.is_(True),
        )
    ).all()

    return {
        "assessed": total,
        "overridden": len(overrides),
        "statement": (
            f"{len(overrides)} of {total} assessed candidates had the "
            "recommendation overridden by a recruiter."
            if total else "No candidates have been assessed yet."
        ),
    }
