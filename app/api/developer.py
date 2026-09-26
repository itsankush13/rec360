"""
B21 — FinOps / developer metrics, serving `web/developer.html`.

Every figure here is derived from `LLMCallLog` and `EvaluationRun` rows
written by `app.core.llm_usage` during a real JD extraction or screening run
— none of it is a manually measured constant. Prompt, JD, CV and candidate
content is never read or stored by this module; only token counts and a
derived cost estimate ever reach `LLMCallLog`.
"""
from __future__ import annotations

from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import pricing
from app.db.models import Campaign, EvaluationRun, LLMCallLog, RunStatus
from app.db.session import get_db

router = APIRouter(prefix="/api/developer", tags=["developer"])

_STATUS_WORDS = {
    RunStatus.COMPLETED: "completed",
    RunStatus.COMPLETED_WITH_ERRORS: "completed",
    RunStatus.CANCELLED: "failed",
    RunStatus.RUNNING: "running",
    RunStatus.PENDING: "running",
}


def _duration_ms(run: EvaluationRun) -> float:
    if not run.started_at or not run.completed_at:
        return 0.0
    return max((run.completed_at - run.started_at).total_seconds() * 1000, 0.0)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    runs = list(db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)
    ).all())
    calls = list(db.scalars(select(LLMCallLog)).all())

    by_run: dict[str, list[LLMCallLog]] = {}
    by_campaign: dict[str, dict] = {}
    # X56: JD extraction and weight suggestion run at campaign-setup time,
    # before an EvaluationRun exists, so those rows carry campaign_id and no
    # run_id. They are real spend. Bucketing only by run_id hid them, and the
    # per-run average then looked broken next to the total.
    unattributed: list[LLMCallLog] = []
    for call in calls:
        if call.run_id:
            by_run.setdefault(call.run_id, []).append(call)
        else:
            unattributed.append(call)
        agg = by_campaign.setdefault(
            call.campaign_id, {"total_cost_usd": 0.0, "total_tokens": 0, "call_count": 0}
        )
        agg["total_cost_usd"] += call.estimated_cost_usd
        agg["total_tokens"] += call.total_tokens
        agg["call_count"] += 1

    rates = pricing.get_pricing()
    campaign_names = dict(db.execute(select(Campaign.id, Campaign.name)).all())

    run_rows = []
    tokens_per_run: list[int] = []
    cost_per_run: list[float] = []
    for run in runs:
        run_calls = by_run.get(run.id, [])
        total_tokens = sum(c.total_tokens for c in run_calls)
        cost = sum(c.estimated_cost_usd for c in run_calls)
        tokens_per_run.append(total_tokens)
        cost_per_run.append(cost)
        run_rows.append({
            "run_id": run.id,
            "campaign_id": run.campaign_id,
            "campaign_name": campaign_names.get(run.campaign_id),
            "status": _STATUS_WORDS.get(run.status, "running"),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "duration_ms": _duration_ms(run),
            "llm_call_count": len(run_calls),
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(cost, 4),
        })

    total_calls = len(calls)
    total_tokens_all = sum(c.total_tokens for c in calls)
    total_cost_all = sum(c.estimated_cost_usd for c in calls)
    # "Cost per CV" is spend against candidates actually evaluated, not
    # against every LLM call (JD extraction is per-campaign, not per-CV).
    evaluated_candidates = sum(r.evaluated_count for r in runs)
    completed_durations = [_duration_ms(r) for r in runs if r.started_at and r.completed_at]

    cost_per_candidate = (
        round(total_cost_all / evaluated_candidates, 6) if evaluated_candidates else None
    )

    summary = {
        "run_count": len(runs),
        "average_run_duration_ms": round(mean(completed_durations), 1) if completed_durations else 0,
        "average_tokens_per_run": round(mean(tokens_per_run), 1) if tokens_per_run else 0,
        "average_estimated_cost_usd": round(mean(cost_per_run), 4) if cost_per_run else 0,
        "cost_configured": rates["cost_configured"],
        "llm_call_count": total_calls,
        "total_tokens": total_tokens_all,
        "total_estimated_cost_usd": round(total_cost_all, 4),
        "pricing_source": rates["source"],
        "pricing_effective_start_date": rates["effective_start_date"],
        "input_cost_per_1m": rates["input_cost_per_1m"],
        "output_cost_per_1m": rates["output_cost_per_1m"],
        # B21: the FinOps calculation contract beyond per-run averages —
        # spend to date and the 10,000-CV scenario the backlog asks for,
        # both derived from these same rows rather than a hand-measured
        # constant.
        "operating_cost_to_date_usd": round(total_cost_all, 4),
        # X56: campaign-setup spend, which belongs to no run. Reported
        # separately so the run rows plus this figure reconcile to
        # total_estimated_cost_usd instead of silently falling short.
        "setup_call_count": len(unattributed),
        "setup_total_tokens": sum(c.total_tokens for c in unattributed),
        "setup_estimated_cost_usd": round(sum(c.estimated_cost_usd for c in unattributed), 4),
        "cost_per_candidate_usd": cost_per_candidate,
        "projected_cost_10000_cvs_usd": (
            round(cost_per_candidate * 10000, 2) if cost_per_candidate is not None else None
        ),
    }
    # X56: rows pointing at deleted campaigns rendered as bare UUIDs. Name
    # them in words instead. They are NOT dropped - that spend really happened,
    # and removing the rows would stop the table summing to the total.
    campaign_costs = [
        {
            "campaign_id": campaign_id,
            "campaign_name": campaign_names.get(campaign_id) or "Deleted campaign",
            "total_cost_usd": round(agg["total_cost_usd"], 4),
            "total_tokens": agg["total_tokens"],
            "llm_call_count": agg["call_count"],
        }
        for campaign_id, agg in by_campaign.items()
    ]
    return {"summary": summary, "runs": run_rows, "campaign_costs": campaign_costs}
