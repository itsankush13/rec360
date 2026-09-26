"""
B21 — FinOps instrumentation.

Every LLM call goes through `app.core.llm_provider.get_chat_model()` /
`get_cached_chat_model()`, so that is the one place usage can be captured
without editing the dozen agent modules that call `.invoke()` directly (see
that module's `_Instrumented` wrapper). A call site opts a block of work
into being billed to a campaign/run by opening `track()` around it; code
invoked underneath has no idea this module exists. A call made with no
`track()` open is not billed to anything and is silently not recorded — the
same rule `AuditEvent` already follows: no second place a number could
disagree with the first.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core import pricing


@dataclass
class _Context:
    db: Session
    campaign_id: str
    run_id: str | None
    call_type: str


_current: "contextvars.ContextVar[_Context | None]" = contextvars.ContextVar(
    "llm_usage_context", default=None,
)


@contextmanager
def track(db: Session, *, campaign_id: str, run_id: str | None = None, call_type: str):
    """
    Attribute every LLM call made inside this block to `campaign_id` (and,
    where a screening run is already underway, `run_id`). Reentrant-safe:
    nested calls just overwrite and then restore the previous context.
    """
    token = _current.set(_Context(db=db, campaign_id=campaign_id, run_id=run_id, call_type=call_type))
    try:
        yield
    finally:
        _current.reset(token)


def _tokens_from(response) -> tuple[int, int, int] | None:
    """
    LangChain's newer, provider-agnostic `usage_metadata` first; the older
    `response_metadata["token_usage"]` shape (what AzureChatOpenAI/ChatGroq
    actually return today) as a fallback. `None` means neither was present —
    an outage or a mock in a test — and the call is simply not recorded.
    """
    usage = getattr(response, "usage_metadata", None)
    if usage:
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens") or (input_tokens + output_tokens)
        return input_tokens, output_tokens, total

    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage")
    if usage:
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        total = usage.get("total_tokens") or (input_tokens + output_tokens)
        return input_tokens, output_tokens, total

    return None


def record(response, *, model_name: str = "") -> None:
    ctx = _current.get()
    if ctx is None:
        return
    tokens = _tokens_from(response)
    if tokens is None:
        return

    from app.db.models import LLMCallLog

    input_tokens, output_tokens, total_tokens = tokens
    cost = pricing.estimate_cost_usd(input_tokens, output_tokens)
    ctx.db.add(LLMCallLog(
        campaign_id=ctx.campaign_id, run_id=ctx.run_id, call_type=ctx.call_type,
        model_name=model_name, input_tokens=input_tokens, output_tokens=output_tokens,
        total_tokens=total_tokens, estimated_cost_usd=cost,
    ))
    ctx.db.flush()
