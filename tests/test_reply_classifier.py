"""
B10/B11 — classifying one email reply into a structured `ReplySignal`.

Two tiers, tested separately: the deterministic rules (asserted to never
call the LLM — the mock model is asserted un-invoked) and the LLM fallback
(the model is mocked; no real API call is made in these tests).
"""
from unittest.mock import Mock

from app.core import reply_classifier
from app.core.reply_classifier import classify_reply


# ---------------------------------------------------------------------------
# Tier 1: deterministic — the LLM must never be built or called
# ---------------------------------------------------------------------------

def test_decline_word_is_deterministic_and_never_calls_the_llm(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("Thanks, but we'll decline moving forward with this candidate.")

    assert signal.intent == "decline"
    assert signal.sentiment == "negative"
    assert signal.confidence >= 0.8
    mock_llm_builder.assert_not_called()


def test_approve_word_with_an_explicit_datetime_is_deterministic(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("Approved -- let's schedule it for 2026-09-20 10:00.")

    assert signal.intent == "schedule_confirm"
    assert signal.extracted_datetime == "2026-09-20 10:00"
    mock_llm_builder.assert_not_called()


def test_bare_approve_word_is_deterministic(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("Confirmed, this candidate looks good to us.")

    assert signal.intent == "approve"
    assert signal.sentiment == "positive"
    mock_llm_builder.assert_not_called()


def test_bare_explicit_datetime_with_no_decision_word_is_deterministic(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("How about 15 Sep 2026, 3pm?")

    assert signal.intent == "schedule_confirm"
    assert signal.extracted_datetime is not None
    mock_llm_builder.assert_not_called()


def test_an_amount_is_captured_alongside_a_deterministic_decline(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("We'll pass on this one -- budget was capped at $80,000 anyway.")

    assert signal.intent == "decline"
    assert signal.extracted_amount == "$80,000"
    mock_llm_builder.assert_not_called()


def test_empty_body_is_deterministic_unclear_with_no_llm_call(monkeypatch):
    mock_llm_builder = Mock()
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", mock_llm_builder)

    signal = classify_reply("")

    assert signal.intent == "unclear"
    assert signal.confidence == 0.0
    mock_llm_builder.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 2: LLM fallback — mocked, never a real API call
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    def __init__(self, content):
        self._content = content
        self.invoke_calls = []

    def invoke(self, messages):
        self.invoke_calls.append(messages)
        return _FakeResponse(self._content)


def test_ambiguous_reply_falls_back_to_the_llm(monkeypatch):
    fake_model = _FakeModel(
        '{"intent": "need_more_info", "sentiment": "neutral", '
        '"extracted_datetime": null, "extracted_amount": null, '
        '"confidence": 0.6, "rationale": "Asked a clarifying question."}'
    )
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", lambda **kwargs: fake_model)

    signal = classify_reply("Let me think it over and get back to you next week.")

    assert signal.intent == "need_more_info"
    assert signal.confidence == 0.6
    assert len(fake_model.invoke_calls) == 1


def test_llm_json_wrapped_in_a_markdown_fence_is_still_parsed(monkeypatch):
    fake_model = _FakeModel(
        '```json\n{"intent": "unclear", "sentiment": "neutral", '
        '"confidence": 0.2, "rationale": "Not sure what this means."}\n```'
    )
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", lambda **kwargs: fake_model)

    signal = classify_reply("Hmm, interesting, I suppose.")

    assert signal.intent == "unclear"
    assert signal.confidence == 0.2


def test_llm_failure_returns_unclear_rather_than_raising(monkeypatch):
    def _broken(**kwargs):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", _broken)

    signal = classify_reply("Not entirely sure what to make of this reply honestly.")

    assert signal.intent == "unclear"
    assert signal.confidence == 0.0


def test_llm_output_that_fails_schema_validation_returns_unclear(monkeypatch):
    fake_model = _FakeModel('{"intent": "not_a_real_intent", "confidence": 0.5}')
    monkeypatch.setattr(reply_classifier, "get_cached_chat_model", lambda **kwargs: fake_model)

    signal = classify_reply("A reply the model classifies as something invalid.")

    assert signal.intent == "unclear"
    assert signal.confidence == 0.0
