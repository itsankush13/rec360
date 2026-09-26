"""
B21 — Azure OpenAI cost estimation.

Two sources, in order: an explicit rate configured for this deployment
(`azure_openai_input_cost_per_1m` / `_output_cost_per_1m`), or a bundled
fallback — the last verified Azure OpenAI "Global Standard" GPT-4o retail
rate, checked into this file rather than fetched live. A live call to the
Azure Retail Prices API would be a more accurate third source and is a
deliberate omission here: it would make every metrics request depend on an
outbound call to a Microsoft endpoint that a test run or an air-gapped demo
box cannot reach, for a number the fallback already approximates closely.
`pricing_source` is still reported to the caller so nothing pretends to be
more current than it is — `web/developer.html` already renders that field.
"""
from __future__ import annotations

from datetime import date

from app.core.config import settings

# Azure OpenAI GPT-4o, Global Standard, last verified 2026-01-01.
_FALLBACK_INPUT_PER_1M = 2.50
_FALLBACK_OUTPUT_PER_1M = 10.00
_FALLBACK_EFFECTIVE_DATE = date(2026, 1, 1)


def get_pricing() -> dict:
    configured = (
        getattr(settings, "azure_openai_input_cost_per_1m", None) is not None
        and getattr(settings, "azure_openai_output_cost_per_1m", None) is not None
    )
    if configured:
        return {
            "source": "configuration",
            "input_cost_per_1m": settings.azure_openai_input_cost_per_1m,
            "output_cost_per_1m": settings.azure_openai_output_cost_per_1m,
            "effective_start_date": None,
            "cost_configured": True,
        }
    return {
        "source": "bundled_azure_retail_fallback",
        "input_cost_per_1m": _FALLBACK_INPUT_PER_1M,
        "output_cost_per_1m": _FALLBACK_OUTPUT_PER_1M,
        "effective_start_date": _FALLBACK_EFFECTIVE_DATE.isoformat(),
        "cost_configured": True,
    }


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    rates = get_pricing()
    return round(
        (input_tokens / 1_000_000) * rates["input_cost_per_1m"]
        + (output_tokens / 1_000_000) * rates["output_cost_per_1m"],
        6,
    )
