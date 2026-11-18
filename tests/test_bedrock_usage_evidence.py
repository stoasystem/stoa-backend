from __future__ import annotations

import ast
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
from stoa.services.bedrock_token_count_service import (
    ProviderTokenCountUnavailable,
    TokenCountEndpoint,
    count_input_tokens,
)


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
    return ai_service.provider_result(result, effect_id=EFFECT_ID)


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


class _RuntimeCountClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def count_tokens(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


class _MantleCountClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def count_tokens(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


def _request_body() -> str:
    return json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0.4,
            "system": "Synthetic non-private system text.",
            "messages": [{"role": "user", "content": "Synthetic non-private input."}],
        }
    )


def test_configured_eu_profile_uses_runtime_foundation_model_count_only() -> None:
    mantle = _MantleCountClient(
        {
            "input_tokens": 23,
            "request_id": "mantle-request-private-coordinate",
            "http_status": 200,
        }
    )
    runtime = _RuntimeCountClient(
        {
            "inputTokens": 37,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "runtime-request-private-coordinate",
            },
        }
    )

    count = count_input_tokens(
        _request_body(),
        model_id=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        region="eu-central-1",
        mantle_client=mantle,
        runtime_client=runtime,
    )

    assert count == 37
    assert mantle.calls == []
    assert runtime.calls == [
        {
            "modelId": MODEL_ID,
            "input": {"invokeModel": {"body": _request_body()}},
        }
    ]


def test_regional_model_uses_sdk_count_tokens_with_identical_body() -> None:
    runtime = _RuntimeCountClient(
        {
            "inputTokens": 19,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "runtime-request-private-coordinate",
            },
        }
    )
    request_body = _request_body()

    count = count_input_tokens(
        request_body,
        model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
        inference_profile_id=None,
        region="eu-central-1",
        runtime_client=runtime,
    )

    assert count == 19
    assert runtime.calls == [
        {
            "modelId": "anthropic.claude-3-5-haiku-20241022-v1:0",
            "input": {"invokeModel": {"body": request_body}},
        }
    ]


def _answer_tool_request_body() -> str:
    """The body an Ask answer is sent with: the forced `give_answer` tool (#412)."""
    body = model_call._invoke_body(
        system="Synthetic non-private system text.",
        messages=[{"role": "user", "content": "Synthetic non-private input."}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=0.4,
    )
    return json.dumps(body)


def test_runtime_count_drops_eager_input_streaming_the_count_api_refuses() -> None:
    """CountTokens rejects `eager_input_streaming` ("Extra inputs are not
    permitted"); it only shapes the stream and adds no input tokens, so the
    count is asked without it and with every other field as sent."""
    runtime = _RuntimeCountClient(
        {
            "inputTokens": 705,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-id"},
        }
    )
    request_body = _answer_tool_request_body()
    assert json.loads(request_body)["tools"][0]["eager_input_streaming"] is True

    count = count_input_tokens(
        request_body,
        model_id=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        region="eu-central-1",
        runtime_client=runtime,
    )

    assert count == 705
    counted = json.loads(runtime.calls[0]["input"]["invokeModel"]["body"])
    expected = json.loads(request_body)
    del expected["tools"][0]["eager_input_streaming"]
    assert counted == expected
    assert counted["tools"][0]["strict"] is True
    assert counted["tool_choice"] == {"type": "tool", "name": "give_answer"}


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


def test_mantle_count_drops_eager_input_streaming() -> None:
    mantle = _MantleCountClient(
        {"input_tokens": 705, "request_id": "request-id", "http_status": 200}
    )

    count_input_tokens(
        _answer_tool_request_body(),
        model_id=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        region="eu-central-1",
        count_endpoint=TokenCountEndpoint.MANTLE,
        mantle_client=mantle,
    )

    payload = mantle.calls[0]["payload"]
    assert "eager_input_streaming" not in payload["tools"][0]
    assert payload["tool_choice"] == {"type": "tool", "name": "give_answer"}


def test_count_failure_logs_its_kind_but_no_provider_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from botocore.exceptions import ClientError

    class RefusingRuntime:
        def count_tokens(self, **_kwargs: object) -> dict[str, object]:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ValidationException",
                        "Message": "PRIVATE-PROMPT-CANARY is not permitted",
                    }
                },
                "CountTokens",
            )

    with caplog.at_level("WARNING"), pytest.raises(ProviderTokenCountUnavailable):
        count_input_tokens(
            _request_body(),
            model_id=MODEL_ID,
            inference_profile_id=PROFILE_ID,
            region="eu-central-1",
            runtime_client=RefusingRuntime(),
        )

    assert "provider_token_count_failed" in caplog.text
    assert "ValidationException" in caplog.text
    assert "PRIVATE" not in caplog.text


def test_explicit_mantle_capability_remains_count_only() -> None:
    mantle = _MantleCountClient(
        {
            "input_tokens": 23,
            "request_id": "mantle-request-private-coordinate",
            "http_status": 200,
        }
    )
    runtime = _RuntimeCountClient(
        {
            "inputTokens": 999,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "runtime-request-private-coordinate",
            },
        }
    )

    count = count_input_tokens(
        _request_body(),
        model_id=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        region="eu-central-1",
        count_endpoint=TokenCountEndpoint.MANTLE,
        mantle_client=mantle,
        runtime_client=runtime,
    )

    assert count == 23
    assert runtime.calls == []
    assert len(mantle.calls) == 1
    payload = mantle.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == MODEL_ID
    assert payload["messages"] == [
        {"role": "user", "content": "Synthetic non-private input."}
    ]
    assert payload["system"] == "Synthetic non-private system text."
    assert "max_tokens" not in payload
    assert "temperature" not in payload


@pytest.mark.parametrize(
    "response",
    [
        {},
        {
            "inputTokens": True,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-id"},
        },
        {
            "inputTokens": 1.5,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-id"},
        },
        {
            "inputTokens": -1,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-id"},
        },
        {
            "inputTokens": "37",
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-id"},
        },
        {
            "inputTokens": 37,
            "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "request-id"},
        },
        {
            "inputTokens": 37,
            "ResponseMetadata": {"HTTPStatusCode": 200},
        },
    ],
)
def test_unavailable_or_malformed_runtime_count_is_stable_failure(
    response: dict[str, object],
) -> None:
    mantle = _MantleCountClient(
        {
            "input_tokens": 99,
            "request_id": "must-not-fallback",
            "http_status": 200,
        }
    )

    with pytest.raises(ProviderTokenCountUnavailable) as captured:
        count_input_tokens(
            _request_body(),
            model_id=MODEL_ID,
            inference_profile_id=PROFILE_ID,
            region="eu-central-1",
            mantle_client=mantle,
            runtime_client=_RuntimeCountClient(response),
        )

    assert str(captured.value) == "provider_token_count_unavailable"
    assert captured.value.category == "provider_token_count_unavailable"
    assert mantle.calls == []


def test_runtime_failure_does_not_guess_or_fallback_to_mantle() -> None:
    class UnsupportedRuntime:
        def count_tokens(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("unsupported configured count path")

    mantle = _MantleCountClient(
        {
            "input_tokens": 99,
            "request_id": "must-not-fallback",
            "http_status": 200,
        }
    )

    with pytest.raises(ProviderTokenCountUnavailable):
        count_input_tokens(
            _request_body(),
            model_id=MODEL_ID,
            inference_profile_id=PROFILE_ID,
            region="eu-central-1",
            mantle_client=mantle,
            runtime_client=UnsupportedRuntime(),
        )

    assert mantle.calls == []


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"input_tokens": True},
        {"input_tokens": 1.5},
        {"input_tokens": -1},
        {"input_tokens": "23"},
        {"input_tokens": 23, "http_status": 403},
    ],
)
def test_unavailable_or_malformed_mantle_count_is_stable_failure(
    response: dict[str, object],
) -> None:
    with pytest.raises(ProviderTokenCountUnavailable) as captured:
        count_input_tokens(
            _request_body(),
            model_id=MODEL_ID,
            inference_profile_id=PROFILE_ID,
            region="eu-central-1",
            count_endpoint=TokenCountEndpoint.MANTLE,
            mantle_client=_MantleCountClient(response),
        )

    assert str(captured.value) == "provider_token_count_unavailable"
    assert captured.value.category == "provider_token_count_unavailable"


def test_count_transport_exception_is_redacted_and_fail_closed() -> None:
    class FailingMantle:
        def count_tokens(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("PRIVATE-CREDENTIAL-AND-PROMPT-CANARY")

    with pytest.raises(ProviderTokenCountUnavailable) as captured:
        count_input_tokens(
            _request_body(),
            model_id=MODEL_ID,
            inference_profile_id=PROFILE_ID,
            region="eu-central-1",
            count_endpoint=TokenCountEndpoint.MANTLE,
            mantle_client=FailingMantle(),
        )

    assert str(captured.value) == "provider_token_count_unavailable"
    assert "PRIVATE" not in repr(captured.value)


def test_inventory_classifies_every_source_invoke_model_call() -> None:
    inventory = ai_service.inventory_ai_invocation_classes()

    assert inventory == {
        "src/stoa/services/model_call/bedrock.py:invoke_model_with_response_stream": (
            ai_service.AIInvocationClass.USER_ALLOWANCE
        ),
    }

    discovered: set[str] = set()

    class InvokeModelVisitor(ast.NodeVisitor):
        def __init__(self, source_path: Path) -> None:
            self.source_path = source_path
            self.functions: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"invoke_model", "invoke_model_with_response_stream"}
                and self.functions
            ):
                # The adapter is listed by the provider operation it calls,
                # every other caller by the function that calls it.
                where = (
                    node.func.attr
                    if self.source_path.parent.name == "model_call"
                    else self.functions[-1]
                )
                discovered.add(f"{self.source_path.as_posix()}:{where}")
            self.generic_visit(node)

    for source_path in (
        Path("src/stoa/services/ask_question/_admission.py"),
        Path("src/stoa/services/ai_service.py"),
        Path("src/stoa/services/ask_answer.py"),
        *sorted(Path("src/stoa/services/model_call").glob("*.py")),
        Path("src/stoa/services/report_service.py"),
    ):
        tree = ast.parse(source_path.read_text())
        InvokeModelVisitor(source_path).visit(tree)

    assert discovered == set(inventory)


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


def test_probe_fixture_is_redacted_nonpassing_and_never_invokes_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import probe_bedrock_token_count

    class Sts:
        def get_caller_identity(self) -> dict[str, object]:
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:iam::123456789012:role/private-operator-role",
                "UserId": "PRIVATEUSERID",
                "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "private-sts-id"},
            }

    class CountOnly:
        def __init__(self) -> None:
            self.generation_calls = 0

        def count_tokens(self, **_kwargs: object) -> dict[str, object]:
            return {
                "inputTokens": 17,
                "ResponseMetadata": {
                    "HTTPStatusCode": 200,
                    "RequestId": "private-runtime-id",
                },
            }

        def invoke_model(self, **_kwargs: object) -> dict[str, object]:
            self.generation_calls += 1
            raise AssertionError("generation must never be called")

    count_only = CountOnly()
    monkeypatch.setattr(
        probe_bedrock_token_count,
        "_git_source_sha",
        lambda: "a" * 40,
    )
    output = tmp_path / "preflight.json"
    receipt = probe_bedrock_token_count.capture_preflight(
        output,
        sts_client=Sts(),
        runtime_client=count_only,
        fixture=True,
        captured_at=OBSERVED_AT,
    )

    assert receipt["status"] == "fixture_only"
    assert receipt["mocked"] is True
    assert count_only.generation_calls == 0
    rendered = output.read_text()
    for private_value in (
        "123456789012",
        "private-operator-role",
        "PRIVATEUSERID",
        "private-sts-id",
        "private-runtime-id",
        "Synthetic STOA Bedrock token-count preflight",
        MODEL_ID,
        PROFILE_ID,
    ):
        assert private_value not in rendered

    with pytest.raises(probe_bedrock_token_count.PreflightVerificationError):
        probe_bedrock_token_count.verify_preflight(output)


def test_probe_verify_rejects_source_drift_before_provider_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import probe_bedrock_token_count

    output = tmp_path / "preflight.json"
    output.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "status": "passing",
                "mocked": False,
                "sourceSha": "a" * 40,
                "environmentDigest": "b" * 64,
                "modelDigest": "c" * 64,
                "inferenceProfileDigest": "d" * 64,
                "identityDigest": "e" * 64,
                "action": "bedrock:CountTokens",
                "syntheticInputTokens": 17,
                "responseShape": "valid_exact_integer",
                "correlationDigest": "f" * 64,
                "capturedAt": OBSERVED_AT.isoformat(),
            }
        )
    )
    monkeypatch.setattr(
        probe_bedrock_token_count,
        "_git_source_sha",
        lambda: "9" * 40,
    )

    with pytest.raises(
        probe_bedrock_token_count.PreflightVerificationError,
        match="source_drift",
    ):
        probe_bedrock_token_count.verify_preflight(output)
