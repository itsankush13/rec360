"""Segment definitions for the demo video pipeline.

This is the executable counterpart of docs/plan/DEMO-VIDEO-SCRIPT-120S.md — keep the two in
sync. Each Segment is one continuous screen recording with one narration line. main.py
generates the narration audio first (to know its duration), then records the segment's video
padded to at least that duration, so nothing ever gets looped by a player to fill a gap (that
was the cause of the "Candidate 360 keeps replaying" bug in the first cut).

Playwright `actions(page, cfg)` callables run in order, each already synchronous (sync API).
Keep them idempotent and defensive — `try_click`/`try_check` swallow a missing selector instead
of failing the whole recording, since exact demo data varies per rehearsal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class Segment:
    key: str
    url_path: str  # relative to base_url, may use {campaign}/{evaluation}/etc. placeholders
    narration: str
    actions: Callable[[object, dict], None] = field(default=lambda page, cfg: None)
    min_hold_seconds: float = 2.0  # floor even if narration is short


def _wait(page, ms=600):
    page.wait_for_timeout(ms)


def try_click(page, selector, timeout=3000):
    try:
        page.locator(selector).first.click(timeout=timeout)
        return True
    except Exception:
        return False


def try_fill(page, selector, text, timeout=3000):
    try:
        page.locator(selector).first.fill(text, timeout=timeout)
        return True
    except Exception:
        return False


def try_check(page, selector, timeout=3000):
    try:
        page.locator(selector).check(timeout=timeout)
        return True
    except Exception:
        return False


def act_start_campaign(page, cfg):
    try_fill(
        page,
        "#ai-start-request",
        "I need a Maintenance Engineer for a plant in Doha.",
    )
    _wait(page, 1200)


def act_new_campaign(page, cfg):
    _wait(page, 1500)
    try_click(page, "button:has-text('Approve')")
    _wait(page, 800)


def act_discover(page, cfg):
    _wait(page, 1800)


def act_leaderboard(page, cfg):
    page.mouse.wheel(0, 400)
    _wait(page, 1500)


def act_candidate_evidence(page, cfg):
    page.mouse.wheel(0, 500)
    _wait(page, 900)
    try_click(page, "#c-strengths")
    page.mouse.wheel(0, 500)
    _wait(page, 900)
    page.mouse.wheel(0, 500)  # reaches #c-ask-questions
    _wait(page, 900)


def act_candidate_close(page, cfg):
    page.mouse.wheel(0, -4000)  # back to the top: hold on the verdict pill, not the questions
    _wait(page, 800)


def act_compare_full_table(page, cfg):
    page.wait_for_selector("table.cx-tbl", timeout=8000)
    _wait(page, 1200)


def act_compare_select(page, cfg):
    checkboxes = page.locator("input[data-select]")
    count = checkboxes.count()
    for i in range(min(2, count)):
        try:
            checkboxes.nth(i).check(timeout=3000)
            _wait(page, 500)
        except Exception:
            pass


def act_compare_result(page, cfg):
    try:
        page.wait_for_selector("#c-table table", timeout=5000)
        page.locator("#c-table").scroll_into_view_if_needed(timeout=3000)
    except Exception:
        page.mouse.wheel(0, 800)
    _wait(page, 1500)


def act_pipeline(page, cfg):
    _wait(page, 1800)


def act_handoff_interview(page, cfg):
    _wait(page, 1500)


def act_offer(page, cfg):
    _wait(page, 1200)


def act_decisions(page, cfg):
    _wait(page, 1800)
    page.mouse.wheel(0, 1200)
    _wait(page, 1500)
    try:
        page.locator("text=Send the report to the hiring manager").scroll_into_view_if_needed(timeout=3000)
    except Exception:
        page.mouse.wheel(0, 800)
    _wait(page, 1800)


def act_audit(page, cfg):
    page.mouse.wheel(0, 600)
    _wait(page, 1500)


def build_segments(cfg: dict) -> List[Segment]:
    campaign = cfg["campaign_id"]
    evaluation = cfg["candidate_evaluation_id"]
    candidate_ids = cfg.get("compare_candidate_ids", [])
    compare_qs = "&".join(f"candidate_ids={cid}" for cid in candidate_ids)

    return [
        Segment(
            "start_campaign",
            "start-campaign.html",
            "This is a recruitment platform that runs a candidate from job requirement to "
            "hire — with AI doing the screening, not just the paperwork.",
            act_start_campaign,
        ),
        Segment(
            "new_campaign",
            f"new-campaign.html?campaign_id={campaign}",
            "One sentence, and it drafts the job description, the requirements, and the "
            "scoring rubric — no blank form.",
            act_new_campaign,
        ),
        Segment(
            "discover",
            f"discover.html?campaign={campaign}",
            "Instead of a recruiter scrolling CVs, it searches a resume repository "
            "semantically and pulls in the candidates who actually match.",
            act_discover,
        ),
        Segment(
            "leaderboard",
            f"leaderboard.html?campaign={campaign}",
            "This is the screening engine. Every CV — including scanned, photographed, "
            "badly formatted ones — goes through OCR and a real LLM evaluation against the "
            "rubric, and comes back ranked with a confirmed-requirement count, not a "
            "black-box score.",
            act_leaderboard,
        ),
        Segment(
            "candidate_evidence",
            f"candidate.html?campaign={campaign}&evaluation={evaluation}",
            "Drilling into one candidate: the evidence for every score, an AI narrative "
            "summary, and suggested interview questions generated straight from the gaps "
            "it found — so the interviewer knows exactly what to probe.",
            act_candidate_evidence,
        ),
        Segment(
            "candidate_close",
            f"candidate.html?campaign={campaign}&evaluation={evaluation}",
            "And that's the AI assessment and the recommended decision for this candidate.",
            act_candidate_close,
        ),
        Segment(
            "compare_full_table",
            f"compare.html?campaign={campaign}",
            "Here's the full shortlist for this campaign, side by side.",
            act_compare_full_table,
        ),
        Segment(
            "compare_select",
            f"compare.html?campaign={campaign}",
            "Selecting the two finalists I want to compare.",
            act_compare_select,
        ),
        Segment(
            "compare_result",
            f"compare.html?campaign={campaign}" + (f"&{compare_qs}" if compare_qs else ""),
            "And here's the criterion-by-criterion comparison for just the two I picked.",
            act_compare_result,
        ),
        Segment(
            "pipeline",
            f"pipeline.html?campaign={campaign}",
            "Every decision — shortlist, hold, reject — writes a real state change and a "
            "real audit event. This is the full recruitment lifecycle for one candidate, "
            "end to end.",
            act_pipeline,
        ),
        Segment(
            "handoff_interview",
            f"handoff.html?campaign={campaign}",
            "From shortlist, it hands off to the hiring manager, schedules the interview, "
            "and captures structured feedback — strengths, concerns, a recommendation. "
            "Calendar and email delivery are simulated in this build and marked as such on "
            "screen; the state, the feedback and the approval trail behind them are real.",
            act_handoff_interview,
        ),
        Segment(
            "offer",
            f"offer.html?campaign={campaign}",
            "Offer drafting, revisions and the candidate's response are tracked the same "
            "way.",
            act_offer,
        ),
        Segment(
            "decisions",
            f"decisions.html?campaign={campaign}",
            "This is the Decisions and Export page — you can take the final call on each "
            "candidate from right here. And as we scroll down, you can send the "
            "shortlisted candidates straight to the hiring manager.",
            act_decisions,
            min_hold_seconds=4.0,
        ),
        Segment(
            "audit",
            f"audit.html?campaign={campaign}",
            "And every one of those steps — screening, shortlist, handoff, interview, "
            "offer — lands in one audit trail, filterable and exportable. Nothing here is "
            "a black box.",
            act_audit,
        ),
    ]
