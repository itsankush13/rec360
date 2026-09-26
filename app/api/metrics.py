"""Lifecycle metrics for Recruitment 360. All figures come from stored moves."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.db.models import LifecycleTransition
from app.db.session import get_db
from app.services import campaign_service, lifecycle_service

router = APIRouter(prefix="/api/campaigns/{campaign_id}/metrics", tags=["metrics"])


def _require_campaign(db: Session, campaign_id: str) -> None:
    if campaign_service.get_campaign(db, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")


def _pct(numerator: int, denominator: int) -> dict | None:
    """A percentage always carries its denominator. See app.core.analytics._pct."""
    if denominator <= 0:
        return None
    return {
        "value": round(numerator / denominator * 100.0, 1),
        "of": denominator,
        "count": numerator,
        "statement": f"{numerator} of {denominator}",
    }


def _quality_of_hire(db: Session, campaign_id: str) -> dict | None:
    """
    B19: the nearest thing to quality of hire computable from stored
    records today. **Not** a post-hire outcome — `web/performance.html`
    says correctly that a real quality-of-hire figure needs a completed
    probation period and a manager rating, which this system does not
    capture. This is a proxy: how highly the AI score ranked each hired
    candidate against the rest of the field at the moment they entered the
    pipeline, using the `campaign_rank` stored on `CandidateLifecycle` at
    shortlist/waitlist entry (B15) rather than a rank recomputed after the
    fact.
    """
    hired = lifecycle_service.hired_candidates(db, campaign_id)
    if not hired:
        return None
    ranked = [row.campaign_rank for row in hired if row.campaign_rank is not None]
    top_3 = sum(1 for rank in ranked if rank <= 3)
    return {
        "hired_count": len(hired),
        "with_recorded_rank": len(ranked),
        "average_shortlist_rank": round(mean(ranked), 1) if ranked else None,
        "hired_from_top_3_of_shortlist": _pct(top_3, len(ranked)) if ranked else None,
        "basis": (
            "Proxy measure, not a post-hire outcome. Shows where each hired candidate "
            "stood, by AI score, against everyone else shortlisted or waitlisted at the "
            "time they entered the pipeline. A true quality-of-hire figure needs a "
            "completed probation period and a manager rating, which this system does not "
            "yet capture."
        ),
    }


def _moves(db: Session, campaign_id: str) -> list[LifecycleTransition]:
    return list(db.scalars(
        select(LifecycleTransition)
        .where(LifecycleTransition.campaign_id == campaign_id)
        .order_by(LifecycleTransition.candidate_id, LifecycleTransition.created_at,
                  LifecycleTransition.id)
    ).all())


def _funnel(db: Session, campaign_id: str) -> list[dict]:
    rows = lifecycle_service.funnel(db, campaign_id)
    for row in rows:
        row["basis"] = "Current lifecycle position of candidates in this campaign."
    return rows


def _flow(moves: list[LifecycleTransition]) -> list[dict]:
    entered: dict[str, set[str]] = defaultdict(set)
    progressed: dict[tuple[str, str], set[str]] = defaultdict(set)
    for move in moves:
        entered[move.to_status].add(move.candidate_id)
        if move.from_status:
            progressed[(move.from_status, move.to_status)].add(move.candidate_id)
    spine = [stage.value for stage in lifecycle.STAGE_ORDER
             if stage not in lifecycle.OFF_RAMP]
    return [
        {"from": start, "to": end, "from_label": lifecycle.words(start),
         "to_label": lifecycle.words(end),
         "moved": len(progressed[(start, end)]), "of": len(entered[start]),
         "basis": "Distinct candidates who entered the first stage and moved to the next."}
        for start, end in zip(spine, spine[1:])
    ]


def _time_in_stage(moves: list[LifecycleTransition]) -> list[dict]:
    by_candidate: dict[str, list[LifecycleTransition]] = defaultdict(list)
    for move in moves:
        by_candidate[move.candidate_id].append(move)
    durations: dict[str, list[float]] = defaultdict(list)
    for candidate_moves in by_candidate.values():
        for previous, following in zip(candidate_moves, candidate_moves[1:]):
            if following.from_status != previous.to_status:
                continue
            days = (following.created_at - previous.created_at).total_seconds() / 86400
            if days >= 0:
                durations[previous.to_status].append(days)
    return [
        {"status": stage.value, "label": lifecycle.words(stage),
         "median_days": round(median(durations[stage.value]), 2),
         "longest_days": round(max(durations[stage.value]), 2),
         "count": len(durations[stage.value]),
         "basis": "Completed stays only, from entry to the next recorded transition."}
        for stage in lifecycle.STAGE_ORDER if durations[stage.value]
    ]


def _bottleneck(times: list[dict], funnel: list[dict]) -> dict | None:
    if not times:
        return None
    slowest = max(times, key=lambda row: row["median_days"])
    current = next((row["count"] for row in funnel
                    if row["status"] == slowest["status"]), 0)
    return {**slowest, "now_here": current}


def _outcomes(db: Session, campaign_id: str,
              moves: list[LifecycleTransition]) -> dict:
    current = lifecycle_service.statuses_for_campaign(db, campaign_id)
    total = len(current)
    counts: dict[str, int] = defaultdict(int)
    for record in current.values():
        counts[getattr(record.status, "value", record.status)] += 1
    terminal = {status.value for status in lifecycle.TERMINAL}
    def part(status: str) -> dict:
        return {"count": counts[status], "of": total,
                "basis": "Current candidate position in this campaign."}
    sent = {move.candidate_id for move in moves if move.to_status == "OFFER_SENT"}
    accepted = {move.candidate_id for move in moves if move.to_status == "OFFER_ACCEPTED"}
    return {
        "hired": part("HIRED"), "closed": part("CLOSED"),
        "not_proceeding": part("NOT_PROCEEDING"),
        "withdrawn": part("WITHDRAWN"),
        "still_live": {"count": sum(count for status, count in counts.items()
                                     if status not in terminal), "of": total,
                       "basis": "Candidates outside terminal states."},
        "quality_of_hire": _quality_of_hire(db, campaign_id),
        "offer_acceptance_rate": (
            {"count": len(accepted & sent), "of": len(sent),
             "rate": round(100 * len(accepted & sent) / len(sent), 1),
             "basis": "Distinct candidates who accepted among those sent an offer."}
            if sent else None
        ),
    }


def _overview(db: Session, campaign_id: str) -> dict:
    _require_campaign(db, campaign_id)
    moves = _moves(db, campaign_id)
    funnel = _funnel(db, campaign_id)
    times = _time_in_stage(moves)
    return {"funnel": funnel, "flow": _flow(moves), "time_in_stage": times,
            "bottleneck": _bottleneck(times, funnel),
            "outcomes": _outcomes(db, campaign_id, moves)}


@router.get("/overview")
def overview(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)


@router.get("/funnel")
def funnel(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)["funnel"]


@router.get("/flow")
def flow(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)["flow"]


@router.get("/time-in-stage")
def time_in_stage(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)["time_in_stage"]


@router.get("/bottleneck")
def bottleneck(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)["bottleneck"]


@router.get("/outcomes")
def outcomes(campaign_id: str, db: Session = Depends(get_db)):
    return _overview(db, campaign_id)["outcomes"]
