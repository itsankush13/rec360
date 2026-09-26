"""
B10/B11 — turn one email reply's text into a structured signal.

Two-tier, per explicit instruction from the person who asked for this:
cheap, deterministic rules first (an exact word, an explicit date, an
explicit amount); the LLM only for what those rules can't confidently read
("go ahead", "whatever works", "sure, schedule it"). A rule that fires skips
the LLM call entirely — tests assert this by mocking the model builder and
asserting it was never invoked on the deterministic path.

Built on first use, not at import time (`_llm()`), the same discipline
`app.core.email_sender` and `app.agents.weight_suggestion_agent` follow:
importing this module must not require provider credentials.

Structured output follows `app.agents.weight_suggestion_agent`'s pattern —
the newest LLM-structured-output code in this repo — rather than
`langchain`'s `.with_structured_output(...)`: prompt for JSON only, strip
markdown fences, `json.loads`, then validate the shape with a pydantic
model. Nothing in this codebase currently calls `.with_structured_output`,
so this keeps the same one pattern rather than introducing a second.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.llm_provider import get_cached_chat_model


class ReplySignal(BaseModel):
    """
    The structured read of one reply. `confidence` and `rationale` exist so
    a proposed decision can be shown to a person with its reasoning attached
    — this is a decision-support signal, never an autonomous action, per the
    same rule `disposition_service` states for AI recommendations generally.
    """

    intent: Literal[
        "approve", "decline", "schedule_confirm", "reschedule_request",
        "need_more_info", "unclear",
    ]
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    extracted_datetime: str | None = None
    extracted_amount: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


def _llm():
    return get_cached_chat_model(temperature=0)


# ---------------------------------------------------------------------------
# Tier 1: deterministic
# ---------------------------------------------------------------------------

_DECLINE_WORDS = re.compile(
    r"\b(declin(?:e|ed|ing)|reject(?:ed|ing)?|not\s+(?:a\s+)?(?:fit|match|interested)|"
    r"pass(?:ing)?\s+on|won'?t\s+(?:be\s+)?(?:proceed|move\s+forward))\b",
    re.IGNORECASE,
)
_APPROVE_WORDS = re.compile(
    r"\b(approved?|confirm(?:ed)?|go\s*ahead|looks?\s+good|sounds?\s+good|works?\s+for\s+(?:me|us))\b",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r"[$₹]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|K|lakh(?:s)?|LPA))?")
_ISO_DATETIME_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")
_PLAIN_DATETIME_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b"
    r"(?:\s*,?\s*\d{1,2}(?::\d{2})?\s?(?:am|pm|AM|PM))?",
    re.IGNORECASE,
)


def _find_datetime(text: str) -> str | None:
    match = _ISO_DATETIME_RE.search(text) or _PLAIN_DATETIME_RE.search(text)
    return match.group(0) if match else None


def _find_amount(text: str) -> str | None:
    match = _AMOUNT_RE.search(text)
    return match.group(0) if match else None


def _deterministic(text: str) -> ReplySignal | None:
    """
    Returns a signal only when the reply contains something unambiguous.
    Anything short of that — including a bare positive/negative tone with no
    exact word or figure — falls through to the LLM rather than guessing.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None

    amount = _find_amount(stripped)
    when = _find_datetime(stripped)

    if _DECLINE_WORDS.search(stripped):
        return ReplySignal(
            intent="decline", sentiment="negative", confidence=0.9,
            extracted_amount=amount,
            rationale="Matched an explicit decline/reject word in the reply.",
        )
    if _APPROVE_WORDS.search(stripped) and when:
        return ReplySignal(
            intent="schedule_confirm", sentiment="positive", confidence=0.9,
            extracted_datetime=when, extracted_amount=amount,
            rationale="Matched an approval word alongside an explicit date or time.",
        )
    if _APPROVE_WORDS.search(stripped):
        return ReplySignal(
            intent="approve", sentiment="positive", confidence=0.85,
            extracted_amount=amount,
            rationale="Matched an explicit approval word in the reply.",
        )
    if when:
        return ReplySignal(
            intent="schedule_confirm", sentiment="neutral", confidence=0.7,
            extracted_datetime=when, extracted_amount=amount,
            rationale="Found an explicit date or time in the reply.",
        )
    return None


# ---------------------------------------------------------------------------
# Tier 2: LLM fallback
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You read one email reply in a recruitment workflow — a reply to an \
interview invite, an approval request, or a hiring-manager report. Classify it.

Return ONLY valid JSON with exactly these keys, no markdown, no explanation:
{"intent": one of "approve" | "decline" | "schedule_confirm" | "reschedule_request" | \
"need_more_info" | "unclear",
"sentiment": one of "positive" | "neutral" | "negative",
"extracted_datetime": a date or time mentioned in the reply, as plain text, or null,
"extracted_amount": a budget or compensation figure mentioned, as plain text, or null,
"confidence": a number from 0 to 1,
"rationale": one short sentence explaining the classification}"""


def _from_llm(text: str) -> ReplySignal:
    response = _llm().invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=text[:4000]),
    ])
    content = re.sub(r"```json|```", "", response.content or "").strip()
    data = json.loads(content)
    return ReplySignal(**data)


def classify_reply(body: str) -> ReplySignal:
    """
    Never raises. Deterministic rules run first and, if one fires, the LLM
    is never called. If the LLM call itself fails, or returns something that
    doesn't validate as a `ReplySignal`, this returns an "unclear" signal at
    zero confidence rather than propagating an exception into whatever is
    walking a mailbox.
    """
    if not (body or "").strip():
        return ReplySignal(
            intent="unclear", sentiment="neutral", confidence=0.0,
            rationale="The reply had no readable text.",
        )

    rule_based = _deterministic(body)
    if rule_based is not None:
        return rule_based

    try:
        return _from_llm((body or "").strip())
    except Exception:
        return ReplySignal(
            intent="unclear", sentiment="neutral", confidence=0.0,
            rationale="Could not confidently classify this reply.",
        )
