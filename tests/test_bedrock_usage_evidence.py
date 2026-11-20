from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pytest

from stoa.models.allowance import ProviderUsageEvidence
from stoa.services import ai_service
from stoa.services import ask_answer
from stoa.services import model_call
from stoa.services.model_call.fake import FakeAdapter, Reply


MODEL_ID = "anthropic.claude-sonnet-4-6"
PROFILE_ID = "eu.anthropic.claude-sonnet-4-6"
EFFECT_ID = "question-effect-476-16"
OBSERVED_AT = datetime(2026, 7, 24, 10, 30, tzinfo=timezone.utc)


def _ask(model: FakeAdapter) -> ai_service.AIProviderResult[dict]:
    """Ask `model` for the answer tool's input through the model call, read as an answer."""
    model_call.install(model)
    result = model_call.call(
        system="Answer the question.",
        messages=[{"role": "user", "content": "PRIVATE-STUDENT-PROMPT"}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=0.4,
        deadline=time.monotonic() + 90,
        correlation_id="server-correlation",
    )
    return ask_answer.provider_result(result, effect_id=EFFECT_ID)


_TOOL_INPUT = {
    "steps": ["First inspect the known values."],
    "answer": "Continue with the next algebraic step.",
    "hints": [],
    "similar_exercises": [],
    "knowledge_points": ["linear equations"],
}


def test_answer_result_embeds_exact_provider_usage_without_content() -> None:
    model = FakeAdapter(
        Reply(
            input=_TOOL_INPUT,
            stop_reason="end_turn",
            usage={"input_tokens": 37, "output_tokens": 11},
        )
    )

    result = _ask(model)

    assert isinstance(result, ai_service.AIProviderResult)
    assert result.content["knowledge_points"] == ["linear equations"]
    assert isinstance(result.usage, ProviderUsageEvidence)
    assert result.usage.input_tokens == 37
    assert result.usage.output_tokens == 11
    assert result.usage.effect_id == EFFECT_ID
    assert result.usage.observed_at.tzinfo is not None
    assert result.stop_reason == "end_turn"
    assert result.inference_profile_id == PROFILE_ID
    assert len(result.provider_message_id_digest) == 64

    evidence = result.usage.model_dump_json()
    assert "PRIVATE-STUDENT-PROMPT" not in evidence
    assert "Continue with the next algebraic step." not in evidence
    assert "msg_1" not in evidence
    assert "req-1" not in evidence
    assert PROFILE_ID not in evidence


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_tokens", None),
        ("input_tokens", True),
        ("input_tokens", 1.5),
        ("input_tokens", -1),
        ("input_tokens", "37"),
        ("output_tokens", None),
        ("output_tokens", False),
        ("output_tokens", 2.25),
        ("output_tokens", -1),
        ("output_tokens", "11"),
    ],
)
def test_missing_or_malformed_usage_fails_closed(field: str, value: object) -> None:
    usage: dict[str, object] = {"input_tokens": 37, "output_tokens": 11}
    if value is None:
        usage.pop(field)
    else:
        usage[field] = value

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        _ask(FakeAdapter(Reply(input=_TOOL_INPUT, usage=usage)))

    assert captured.value.category == "malformed_provider_usage"
    assert captured.value.usage is None


def test_usage_evidence_is_stable_and_strict() -> None:
    usage = model_call.Usage(
        input_tokens=37,
        output_tokens=11,
        request_id="request-private-provider-coordinate",
        message_id="msg_01JPRIVATEPROVIDERID",
        model=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        observed_at=OBSERVED_AT,
        cost_class=model_call.CostClass.USER_ALLOWANCE,
    )

    parsed = usage.evidence(effect_id=EFFECT_ID)

    assert parsed == usage.evidence(effect_id=EFFECT_ID)
    assert parsed.input_tokens == 37
    assert parsed.output_tokens == 11
    assert parsed.provider_cost_retained is True
    assert parsed.effect_id == EFFECT_ID
    assert parsed.observed_at == OBSERVED_AT
    assert len(parsed.evidence_id) == 64
    assert len(parsed.model_id_digest) == 64
    assert len(parsed.provider_request_id_digest) == 64
    with pytest.raises(ValueError):
        usage.evidence(effect_id=" ")


def _answer_call(model: FakeAdapter, admitted: list[tuple[int, int]]) -> model_call.Result:
    model_call.install(model)

    def admit(input_tokens: int, max_output_tokens: int) -> model_call.Admit:
        admitted.append((input_tokens, max_output_tokens))
        return model_call.Admit()

    return model_call.call(
        system="Synthetic non-private system text.",
        messages=[{"role": "user", "content": "Synthetic non-private input."}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=0.4,
        deadline=time.monotonic() + 90,
        admission=admit,
    )


def test_fake_bedrock_refuses_the_count_body_the_real_one_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#430: the fake adapter the Ask tests run on refuses a CountTokens body
    as Bedrock does, so a request the count cannot take fails here too.

    The model call counts the body it sends without the stream-only field and
    is admitted; with the field left in the counted body, the count is refused,
    the hook is never asked, nothing is sent, and the call may be retried."""
    admitted: list[tuple[int, int]] = []
    model = FakeAdapter(answer=_TOOL_INPUT)

    result = _answer_call(model, admitted)

    assert isinstance(result, model_call.Answered)
    assert admitted == [(90, 2048)]
    assert model.requests[0]["tools"][0]["eager_input_streaming"] is True
    counted = model.counted_bodies[0]
    assert "eager_input_streaming" not in counted["tools"][0]
    expected = json.loads(json.dumps(model.requests[0]))
    del expected["tools"][0]["eager_input_streaming"]
    assert counted == expected

    monkeypatch.setattr(model_call, "_STREAM_ONLY_TOOL_FIELDS", frozenset())
    admitted.clear()
    model = FakeAdapter(answer=_TOOL_INPUT)

    result = _answer_call(model, admitted)

    assert result == model_call.NotSent("provider_token_count_unavailable", retryable=True)
    assert model.counted == 1
    assert admitted == []
    assert model.requests == []


def test_ai_service_contains_no_allowance_counter_mutation() -> None:
    source = Path(ai_service.__file__).read_text()
    for forbidden in (
        "reserve_token_allowance",
        "record_provider_usage",
        "finalize_token_allowance",
        "restore_user_allowance",
        "allowance_repo",
    ):
        assert forbidden not in source
