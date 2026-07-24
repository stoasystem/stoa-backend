from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from stoa.models.allowance import ProviderUsageEvidence
from stoa.services import ai_service
from stoa.services.bedrock_token_count_service import (
    ProviderTokenCountUnavailable,
    count_input_tokens,
)


MODEL_ID = "anthropic.claude-sonnet-4-6"
PROFILE_ID = "eu.anthropic.claude-sonnet-4-6"
EFFECT_ID = "question-effect-476-16"
OBSERVED_AT = datetime(2026, 7, 24, 10, 30, tzinfo=timezone.utc)


class _Body:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.closed = False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


def _provider_payload(
    *,
    input_tokens: object = 37,
    output_tokens: object = 11,
) -> dict[str, object]:
    return {
        "id": "msg_01JPRIVATEPROVIDERID",
        "model": MODEL_ID,
        "content": [
            {
                "text": json.dumps(
                    {
                        "steps": ["First inspect the known values."],
                        "answer": "Continue with the next algebraic step.",
                        "hints": [],
                        "similar_exercises": [],
                        "knowledge_points": ["linear equations"],
                    }
                )
            }
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


class _InvokeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.body = _Body(payload)
        self.calls: list[dict[str, object]] = []

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {
            "body": self.body,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "request-private-provider-coordinate",
            },
        }


def test_answer_result_embeds_exact_provider_usage_without_content() -> None:
    client = _InvokeClient(_provider_payload())

    result = ai_service.get_ai_answer(
        content="PRIVATE-STUDENT-PROMPT",
        subject="math",
        grade="Sek1",
        correlation_id="server-correlation",
        effect_id=EFFECT_ID,
        observed_at=OBSERVED_AT,
        client=client,
    )

    assert isinstance(result, ai_service.AIProviderResult)
    assert result.content["knowledge_points"] == ["linear equations"]
    assert isinstance(result.usage, ProviderUsageEvidence)
    assert result.usage.input_tokens == 37
    assert result.usage.output_tokens == 11
    assert result.usage.effect_id == EFFECT_ID
    assert result.usage.observed_at == OBSERVED_AT
    assert result.stop_reason == "end_turn"
    assert result.model_id == MODEL_ID
    assert result.inference_profile_id == PROFILE_ID
    assert len(result.provider_message_id_digest) == 64
    assert client.body.closed is True

    evidence = result.usage.model_dump_json()
    assert "PRIVATE-STUDENT-PROMPT" not in evidence
    assert "Continue with the next algebraic step." not in evidence
    assert "msg_01JPRIVATEPROVIDERID" not in evidence
    assert "request-private-provider-coordinate" not in evidence
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
    payload = _provider_payload()
    usage = payload["usage"]
    assert isinstance(usage, dict)
    if value is None:
        usage.pop(field)
    else:
        usage[field] = value

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service.get_ai_answer(
            content="question",
            subject="math",
            grade="Sek1",
            effect_id=EFFECT_ID,
            client=_InvokeClient(payload),
        )

    assert captured.value.category == "malformed_provider_usage"


def test_parse_provider_usage_is_stable_and_strict() -> None:
    parsed = ai_service.parse_provider_usage(
        _provider_payload(),
        provider_request_id="request-private-provider-coordinate",
        inference_profile_id=PROFILE_ID,
        effect_id=EFFECT_ID,
        observed_at=OBSERVED_AT,
    )

    assert parsed.input_tokens == 37
    assert parsed.output_tokens == 11
    assert parsed.provider_cost_retained is True
    assert parsed.effect_id == EFFECT_ID
    assert len(parsed.evidence_id) == 64
    assert len(parsed.model_id_digest) == 64
    assert len(parsed.provider_request_id_digest) == 64


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


def test_configured_eu_profile_uses_mantle_count_only() -> None:
    mantle = _MantleCountClient(
        {
            "input_tokens": 23,
            "request_id": "mantle-request-private-coordinate",
            "http_status": 200,
        }
    )
    runtime = _RuntimeCountClient({"inputTokens": 999})

    count = count_input_tokens(
        _request_body(),
        model_id=MODEL_ID,
        inference_profile_id=PROFILE_ID,
        region="eu-central-1",
        mantle_client=mantle,
        runtime_client=runtime,
    )

    assert count == 23
    assert runtime.calls == []
    assert len(mantle.calls) == 1
    request = mantle.calls[0]
    assert request["region"] == "eu-central-1"
    assert request["model_id"] == MODEL_ID
    payload = request["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == MODEL_ID
    assert payload["messages"] == [
        {"role": "user", "content": "Synthetic non-private input."}
    ]
    assert payload["system"] == "Synthetic non-private system text."
    assert "max_tokens" not in payload
    assert "temperature" not in payload


def test_regional_model_uses_sdk_count_tokens_with_identical_body() -> None:
    runtime = _RuntimeCountClient({"inputTokens": 19})
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
            mantle_client=FailingMantle(),
        )

    assert str(captured.value) == "provider_token_count_unavailable"
    assert "PRIVATE" not in repr(captured.value)


def test_inventory_classifies_every_source_invoke_model_call() -> None:
    inventory = ai_service.inventory_ai_invocation_classes()

    assert inventory == {
        "src/stoa/routers/conversations.py:_generate_title": (
            ai_service.AIInvocationClass.PROVIDER_COST_ONLY
        ),
        "src/stoa/services/ai_service.py:get_ai_answer": (
            ai_service.AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/ai_service.py:get_hint_answer": (
            ai_service.AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/report_service.py:generate_weekly_report_content": (
            ai_service.AIInvocationClass.PROVIDER_COST_ONLY
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
                and node.func.attr == "invoke_model"
                and self.functions
            ):
                discovered.add(f"{self.source_path.as_posix()}:{self.functions[-1]}")
            self.generic_visit(node)

    for source_path in (
        Path("src/stoa/routers/conversations.py"),
        Path("src/stoa/services/ai_service.py"),
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
                "input_tokens": 17,
                "request_id": "private-mantle-id",
                "http_status": 200,
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
        mantle_client=count_only,
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
        "private-mantle-id",
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
                "action": "bedrock-mantle:CountTokens",
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
