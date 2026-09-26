"""
B21 — FinOps instrumentation and `/api/developer/metrics`.

`app.core.llm_usage` is tested directly against a plain object shaped like a
LangChain response, since exercising it end to end would require a real
model call. The endpoint tests seed `LLMCallLog`/`EvaluationRun` rows
directly for the same reason — these are the rows a real run would write,
via `app.core.llm_provider._InstrumentedChatModel`, not a mock of the
provider itself.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core import llm_usage, pricing
from app.db.models import EvaluationRun, LLMCallLog, RunStatus, RunTrigger, ScoringMode


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_pricing_falls_back_when_nothing_is_configured(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.azure_openai_input_cost_per_1m", None)
    monkeypatch.setattr("app.core.config.settings.azure_openai_output_cost_per_1m", None)
    rates = pricing.get_pricing()
    assert rates["source"] == "bundled_azure_retail_fallback"
    assert rates["cost_configured"] is True
    assert rates["input_cost_per_1m"] > 0


def test_pricing_prefers_explicit_configuration(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.azure_openai_input_cost_per_1m", 1.0)
    monkeypatch.setattr("app.core.config.settings.azure_openai_output_cost_per_1m", 3.0)
    rates = pricing.get_pricing()
    assert rates["source"] == "configuration"
    assert rates["input_cost_per_1m"] == 1.0
    assert rates["output_cost_per_1m"] == 3.0


def test_estimate_cost_usd_is_proportional_to_tokens():
    cheap = pricing.estimate_cost_usd(1000, 0)
    double = pricing.estimate_cost_usd(2000, 0)
    assert double == round(cheap * 2, 6)


# ---------------------------------------------------------------------------
# app.core.llm_usage
# ---------------------------------------------------------------------------

def _fake_response(input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        content="{}",
        usage_metadata={
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        response_metadata={},
    )


def test_record_is_a_no_op_with_no_track_open(db_session):
    llm_usage.record(_fake_response(), model_name="gpt-x")
    assert db_session.query(LLMCallLog).count() == 0


def test_track_records_usage_against_the_open_context(db_session):
    with llm_usage.track(db_session, campaign_id="camp-1", call_type="jd_extraction"):
        llm_usage.record(_fake_response(120, 30), model_name="gpt-x")

    rows = db_session.query(LLMCallLog).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.campaign_id == "camp-1"
    assert row.run_id is None
    assert row.call_type == "jd_extraction"
    assert row.input_tokens == 120
    assert row.output_tokens == 30
    assert row.total_tokens == 150
    assert row.estimated_cost_usd > 0


def test_track_context_does_not_leak_after_the_block_exits(db_session):
    with llm_usage.track(db_session, campaign_id="camp-1", call_type="jd_extraction"):
        pass
    llm_usage.record(_fake_response(), model_name="gpt-x")
    assert db_session.query(LLMCallLog).count() == 0


def test_response_with_no_usage_metadata_is_not_recorded(db_session):
    """A response from a client that never returns usage info (or a plain
    mock in an unrelated test) must not crash — it is simply not recorded."""
    with llm_usage.track(db_session, campaign_id="camp-1", call_type="jd_extraction"):
        llm_usage.record(SimpleNamespace(content="hi"), model_name="gpt-x")
    assert db_session.query(LLMCallLog).count() == 0


def test_older_response_metadata_shape_is_also_recorded(db_session):
    """AzureChatOpenAI/ChatGroq responses carry usage under
    response_metadata['token_usage'] rather than the newer usage_metadata
    attribute — both have to work."""
    response = SimpleNamespace(
        content="{}",
        response_metadata={"token_usage": {
            "prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100,
        }},
    )
    with llm_usage.track(db_session, campaign_id="camp-1", call_type="screening"):
        llm_usage.record(response, model_name="gpt-x")
    row = db_session.query(LLMCallLog).one()
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (80, 20, 100)


# ---------------------------------------------------------------------------
# /api/developer/metrics
# ---------------------------------------------------------------------------

def _seed_run(db_session, *, campaign_id, minutes_ago=10, duration_seconds=30,
             status=RunStatus.COMPLETED, evaluated_count=4):
    started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    run = EvaluationRun(
        campaign_id=campaign_id, rubric_version_id="rv-1", status=status,
        trigger=RunTrigger.MANUAL, scoring_mode=ScoringMode.DETERMINISTIC,
        total_candidates=evaluated_count, evaluated_count=evaluated_count,
        started_at=started, completed_at=started + timedelta(seconds=duration_seconds),
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_metrics_are_empty_but_well_shaped_with_no_runs(client):
    body = client.get("/api/developer/metrics").json()
    assert body["summary"]["run_count"] == 0
    assert body["summary"]["cost_configured"] is True
    assert body["summary"]["cost_per_candidate_usd"] is None
    assert body["runs"] == []
    assert body["campaign_costs"] == []


def test_metrics_aggregate_calls_onto_their_run_and_campaign(client, db_session):
    run = _seed_run(db_session, campaign_id="camp-a")
    db_session.add_all([
        LLMCallLog(campaign_id="camp-a", run_id=run.id, call_type="screening",
                   input_tokens=1000, output_tokens=500, total_tokens=1500,
                   estimated_cost_usd=0.01),
        LLMCallLog(campaign_id="camp-a", run_id=run.id, call_type="screening",
                   input_tokens=1000, output_tokens=500, total_tokens=1500,
                   estimated_cost_usd=0.01),
        # A JD-extraction call made before any run existed — no run_id, but
        # still billed to the campaign.
        LLMCallLog(campaign_id="camp-a", run_id=None, call_type="jd_extraction",
                   input_tokens=2000, output_tokens=200, total_tokens=2200,
                   estimated_cost_usd=0.02),
    ])
    db_session.commit()

    body = client.get("/api/developer/metrics").json()
    summary = body["summary"]
    assert summary["run_count"] == 1
    assert summary["llm_call_count"] == 3
    assert summary["total_tokens"] == 5200
    assert summary["total_estimated_cost_usd"] == 0.04
    assert summary["operating_cost_to_date_usd"] == 0.04
    # 4 candidates evaluated, $0.04 total spend (screening + JD extraction
    # both billed to the one campaign this run belongs to).
    assert summary["cost_per_candidate_usd"] == round(0.04 / 4, 6)
    assert summary["projected_cost_10000_cvs_usd"] == round((0.04 / 4) * 10000, 2)

    run_row = body["runs"][0]
    assert run_row["run_id"] == run.id
    assert run_row["llm_call_count"] == 2  # only the two run-linked calls
    assert run_row["total_tokens"] == 3000
    assert run_row["status"] == "completed"
    assert run_row["duration_ms"] == 30000

    campaign_row = next(c for c in body["campaign_costs"] if c["campaign_id"] == "camp-a")
    assert campaign_row["llm_call_count"] == 3
    assert campaign_row["total_cost_usd"] == 0.04


def test_a_run_still_in_progress_reports_zero_duration_and_is_not_completed(
    client, db_session,
):
    run = EvaluationRun(
        campaign_id="camp-b", rubric_version_id="rv-1", status=RunStatus.RUNNING,
        trigger=RunTrigger.MANUAL, scoring_mode=ScoringMode.DETERMINISTIC,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(run)
    db_session.commit()

    body = client.get("/api/developer/metrics").json()
    run_row = next(r for r in body["runs"] if r["run_id"] == run.id)
    assert run_row["status"] == "running"
    assert run_row["duration_ms"] == 0


def test_campaign_setup_spend_is_reported_and_reconciles(client, db_session):
    """X56: JD extraction and weight suggestion run before any EvaluationRun
    exists, so they carry no run_id. They were invisible on the page, which
    made the per-run average look broken next to the total. The run rows plus
    the setup figure must now add up to the total."""
    run = _seed_run(db_session, campaign_id="camp-a")
    db_session.add_all([
        LLMCallLog(campaign_id="camp-a", run_id=run.id, call_type="screening",
                   input_tokens=1000, output_tokens=500, total_tokens=1500,
                   estimated_cost_usd=0.01),
        LLMCallLog(campaign_id="camp-a", run_id=None, call_type="jd_extraction",
                   input_tokens=2000, output_tokens=200, total_tokens=2200,
                   estimated_cost_usd=0.02),
        LLMCallLog(campaign_id="camp-a", run_id=None, call_type="weight_suggestion",
                   input_tokens=500, output_tokens=100, total_tokens=600,
                   estimated_cost_usd=0.03),
    ])
    db_session.commit()

    summary = client.get("/api/developer/metrics").json()["summary"]
    assert summary["setup_call_count"] == 2
    assert summary["setup_total_tokens"] == 2800
    assert summary["setup_estimated_cost_usd"] == 0.05

    body = client.get("/api/developer/metrics").json()
    run_total = sum(r["estimated_cost_usd"] for r in body["runs"])
    assert round(run_total + summary["setup_estimated_cost_usd"], 4) == \
        summary["total_estimated_cost_usd"]


def test_spend_on_a_deleted_campaign_is_named_not_dropped(client, db_session):
    """X56: rows for campaigns that no longer exist rendered as bare UUIDs.
    They are named in words now, and kept, so campaign_costs still sums to the
    total spend."""
    db_session.add(
        LLMCallLog(campaign_id="gone-for-good", run_id=None, call_type="jd_extraction",
                   input_tokens=100, output_tokens=10, total_tokens=110,
                   estimated_cost_usd=0.004)
    )
    db_session.commit()

    body = client.get("/api/developer/metrics").json()
    row = next(c for c in body["campaign_costs"] if c["campaign_id"] == "gone-for-good")
    assert row["campaign_name"] == "Deleted campaign"
    assert round(sum(c["total_cost_usd"] for c in body["campaign_costs"]), 4) == \
        body["summary"]["total_estimated_cost_usd"]
