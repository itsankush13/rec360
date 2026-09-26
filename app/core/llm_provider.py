"""Central chat-model factory.

Every module that needs an LLM handle calls `get_chat_model()` from here
rather than constructing a provider client directly. This keeps provider
choice in one place, keeps construction lazy, and lets the provider be
switched by configuration rather than by editing call sites.

Construction is deliberately NOT done at import time. Building a client at
module scope means importing the module requires credentials to be present,
which breaks test collection and breaks app startup when a provider is
swapped.

Call sites may pass provider-specific keyword arguments. Each builder keeps
the ones its own client understands and drops the rest, so a caller does not
have to know which provider is active.

Reasoning deployments (the GPT-5 series, o-series) differ from ordinary chat
deployments in two ways that matter here: they require
`max_completion_tokens` rather than `max_tokens`, and they reject a
`temperature` other than the default. The explicit setting remains the source
of truth; a known GPT/o-series deployment name is a safe fallback so a common
configuration mistake cannot silently disable the LLM scoring pass.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings


class LLMProviderError(RuntimeError):
    """Raised when the configured provider is missing required settings.

    Raised eagerly, with the names of the settings that are absent, so a
    misconfiguration surfaces as a readable message rather than as a 404 or
    an authentication error from the provider that reads like a model
    problem.
    """


class _InstrumentedChatModel:
    """
    B21: wraps whatever `.invoke()` the real client offers, records token
    usage from the response, and forwards everything else unchanged. Every
    call site in `app/agents/` and `app/core/` keeps calling `.invoke(...)`
    exactly as before — this is the one seam usage can be captured at
    without touching each of them.
    """

    def __init__(self, model):
        self._model = model

    def invoke(self, *args, **kwargs):
        response = self._model.invoke(*args, **kwargs)
        from app.core import llm_usage
        model_name = (
            getattr(self._model, "model_name", None)
            or getattr(self._model, "deployment_name", None)
            or getattr(self._model, "model", None)
            or ""
        )
        llm_usage.record(response, model_name=model_name)
        return response

    def __getattr__(self, name):
        return getattr(self._model, name)


# Accepted by ChatGroq, rejected by AzureChatOpenAI.
_GROQ_ONLY = ("reasoning_format",)


def _missing(*names: str) -> list[str]:
    return [n for n in names if not getattr(settings, n, None)]


def _build_azure(**kwargs: Any):
    absent = _missing(
        "azure_openai_endpoint",
        "azure_openai_api_key",
        "azure_openai_deployment",
        "azure_openai_api_version",
    )
    if absent:
        raise LLMProviderError(
            "LLM_PROVIDER is 'azure' but these settings are not set: "
            + ", ".join(absent)
            + ". Note that azure_openai_deployment is the deployment name "
            "chosen when the resource was provisioned, which is often not "
            "the same as the model name."
        )

    for key in _GROQ_ONLY:
        kwargs.pop(key, None)
    # Azure routes by deployment; a model name here is meaningless.
    kwargs.pop("model", None)

    # Reasoning deployments reject max_tokens. Keep the explicit setting as
    # the source of truth, with a conservative fallback for standard GPT-5/o-
    # series deployment names. This fixes the common failure where the model
    # is configured correctly but the request is rejected before inference.
    deployment = (settings.azure_openai_deployment or "").strip().lower()
    inferred_reasoning = deployment.startswith(("gpt-5", "o1", "o3", "o4", "o5"))
    if (settings.azure_openai_uses_completion_tokens or inferred_reasoning) and "max_tokens" in kwargs:
        kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")

    # Reasoning deployments reject any temperature but the default, so the
    # parameter is omitted entirely rather than sent as 0. Determinism then
    # has to come from the prompt and from the deterministic engine, which
    # is where it already comes from in this codebase.
    if settings.azure_openai_temperature is not None:
        kwargs.setdefault("temperature", settings.azure_openai_temperature)
    else:
        kwargs.pop("temperature", None)

    if settings.azure_openai_reasoning_effort:
        kwargs.setdefault("reasoning_effort", settings.azure_openai_reasoning_effort)

    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        **kwargs,
    )


def _build_groq(**kwargs: Any):
    absent = _missing("groq_api_key")
    if absent:
        raise LLMProviderError(
            "LLM_PROVIDER is 'groq' but groq_api_key is not set."
        )

    from langchain_groq import ChatGroq

    return ChatGroq(
        model=kwargs.pop("model", None) or settings.model_name,
        api_key=settings.groq_api_key,
        temperature=kwargs.pop("temperature", 0),
        **kwargs,
    )


_BUILDERS = {
    "azure": _build_azure,
    "groq": _build_groq,
}


def get_chat_model(**kwargs: Any):
    """Return a chat model for the configured provider, instrumented for B21 usage capture."""
    provider = (getattr(settings, "llm_provider", None) or "groq").strip().lower()
    builder = _BUILDERS.get(provider)
    if builder is None:
        raise LLMProviderError(
            f"Unknown LLM_PROVIDER {provider!r}. "
            f"Expected one of: {', '.join(sorted(_BUILDERS))}."
        )
    return _InstrumentedChatModel(builder(**kwargs))

# Clients are cached per (provider, kwargs) so that a call site can ask for a
# model on every use without paying construction each time. The provider is
# part of the key: switching provider must not hand back the previous
# provider's client.
_CACHE: dict[tuple, Any] = {}


def get_cached_chat_model(**kwargs: Any):
    """`get_chat_model`, built once per distinct configuration."""
    key = (
        (getattr(settings, "llm_provider", None) or "groq").strip().lower(),
        tuple(sorted(kwargs.items())),
    )
    if key not in _CACHE:
        _CACHE[key] = get_chat_model(**kwargs)
    return _CACHE[key]


def reset_cache() -> None:
    """Drop cached clients. Tests use this; nothing else should need it."""
    _CACHE.clear()
