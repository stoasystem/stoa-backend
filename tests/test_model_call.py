"""模型调用 (#436): the one way the service asks Claude for a forced tool answer.

The call itself is tested through the in-memory adapter only (`FakeAdapter`),
which holds every body to the rules measured against Bedrock. The Bedrock
adapter is tested on a real botocore client: CountTokens and the error replies
through `Stubber`, the response stream as event-stream bytes on the wire,
decoded by botocore's own parser (`Stubber` cannot carry a stream body).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import struct
import time
from collections.abc import Mapping
from typing import Any

import boto3
import pytest
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from stoa import aws, config
from stoa.aws import Kind
from stoa.services import model_call
from stoa.services.model_call import bedrock
from stoa.services.model_call.adapter import ProviderError
from stoa.services.model_call.fake import FakeAdapter, Prose, Reply, Unsent, check_body

TOOL = model_call.Tool(
    name="give_it",
    description="Give the whole thing.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    strict=True,
)
INPUT = {"text": "Hallo"}


def _call(
    model: FakeAdapter | None = None,
    *,
    deadline: float | None = None,
    **kwargs: Any,
) -> model_call.Result:
    if model is not None:
        model_call.install(model)
    kwargs.setdefault("system", "System.")
    return model_call.call(
        messages=[{"role": "user", "content": "Frage"}],
        tool=TOOL,
        max_tokens=512,
        temperature=0.4,
        deadline=time.monotonic() + 90 if deadline is None else deadline,
        **kwargs,
    )


# ── The order: build, count, admit, check the deadline, send ────────────────


def test_the_call_counts_admits_and_sends_in_that_order() -> None:
    steps: list[str] = []

    class Recording(FakeAdapter):
        def count_tokens(self, model_id: str, body: Mapping[str, Any]) -> int:
            steps.append("count")
            return super().count_tokens(model_id, body)

        def stream(self, model_id: str, body: Mapping[str, Any]) -> Any:
            steps.append("send")
            return super().stream(model_id, body)

    def admit(input_tokens: int, max_output_tokens: int) -> model_call.Admit:
        steps.append(f"admit {input_tokens} {max_output_tokens}")
        return model_call.Admit()

    result = _call(Recording(answer=INPUT), admission=admit)

    assert steps == ["count", "admit 90 512", "send"]
    assert isinstance(result, model_call.Answered)
    assert json.loads(result.tool_input) == INPUT
    assert result.stop_reason == "tool_use"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (90, 30)


def test_the_request_forces_the_tool_and_reads_the_model_from_the_configuration() -> None:
    model = FakeAdapter(answer=INPUT)

    _call(model)

    [sent] = model.requests
    assert sent["tools"] == [
        {
            "name": "give_it",
            "description": "Give the whole thing.",
            "strict": True,
            "eager_input_streaming": True,
            "input_schema": dict(TOOL.input_schema),
        }
    ]
    assert sent["tool_choice"] == {"type": "tool", "name": "give_it"}
    assert (sent["max_tokens"], sent["temperature"]) == (512, 0.4)
    # The whole system prompt is shared: one block, ending in the cache point.
    assert sent["system"] == [
        {"type": "text", "text": "System.", "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["anthropic_version"] == "bedrock-2023-05-31"


def test_the_body_counted_is_the_body_sent_without_the_stream_only_field() -> None:
    model = FakeAdapter(answer=INPUT)

    _call(model, admission=lambda *_: model_call.Admit())

    [counted] = model.counted_bodies
    [sent] = model.requests
    expected = json.loads(json.dumps(sent))
    del expected["tools"][0]["eager_input_streaming"]
    assert counted == expected


def test_without_an_admission_hook_nothing_is_counted() -> None:
    model = FakeAdapter(answer=INPUT)

    assert isinstance(_call(model), model_call.Answered)
    assert model.counted == 0


def test_a_refusal_is_not_sent_and_keeps_the_hooks_category() -> None:
    model = FakeAdapter(answer=INPUT)

    result = _call(
        model,
        admission=lambda *_: model_call.Refuse("allowance_unavailable", detail="reserve:x"),
    )

    assert result == model_call.NotSent("allowance_unavailable", retryable=True, detail="reserve:x")
    assert model.requests == []


def test_what_the_hook_raises_is_the_callers() -> None:
    def broken(*_: int) -> model_call.Admit:
        raise LookupError("ledger down")

    with pytest.raises(LookupError):
        _call(FakeAdapter(answer=INPUT), admission=broken)


def test_a_count_that_fails_is_not_sent_and_may_be_retried() -> None:
    model = FakeAdapter(Unsent(ProviderError("ThrottlingException", http_status=429)), INPUT)
    admitted: list[int] = []

    result = _call(model, admission=lambda tokens, _limit: admitted.append(tokens) or model_call.Admit())

    assert result == model_call.NotSent("provider_token_count_unavailable", retryable=True)
    assert admitted == []
    assert model.requests == []


# ── The deadline ──────────────────────────────────────────────────────────────


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_a_deadline_already_passed_counts_and_sends_nothing() -> None:
    model = FakeAdapter(answer=INPUT)

    result = _call(model, deadline=10.0, clock=_Clock(10.0), admission=lambda *_: model_call.Admit())

    assert result == model_call.NotSent("deadline_exceeded", retryable=True)
    assert (model.counted, model.requests) == (0, [])


def test_admission_that_used_the_time_up_does_not_send() -> None:
    clock = _Clock()

    def slow_admission(*_: int) -> model_call.Admit:
        clock.now = 25.0
        return model_call.Admit()

    model = FakeAdapter(answer=INPUT)

    result = _call(model, deadline=20.0, clock=clock, admission=slow_admission)

    assert result == model_call.NotSent("deadline_exceeded", retryable=True)
    assert model.requests == []


def test_the_connection_is_opened_with_the_time_left() -> None:
    model = FakeAdapter(answer=INPUT)

    _call(model, deadline=20.0, clock=_Clock(4.0))

    assert model.connections == [16.0]


# ── What comes back ───────────────────────────────────────────────────────────


def test_the_partial_input_is_told_as_it_arrives() -> None:
    model = FakeAdapter(answer=INPUT)
    model.pieces = 3
    seen: list[str] = []

    result = _call(model, on_partial=seen.append)

    assert isinstance(result, model_call.Answered)
    assert len(seen) == 3
    assert seen[-1] == result.tool_input
    assert all(result.tool_input.startswith(piece) for piece in seen)


def test_a_partial_input_that_cannot_be_delivered_does_not_lose_the_answer() -> None:
    def broken(_partial: str) -> None:
        raise RuntimeError("socket gone")

    assert isinstance(_call(FakeAdapter(answer=INPUT), on_partial=broken), model_call.Answered)


def test_a_reply_cut_off_at_the_output_limit_is_paid_and_unusable() -> None:
    result = _call(FakeAdapter(Reply(input=INPUT, stop_reason="max_tokens")))

    assert isinstance(result, model_call.PaidUnusable)
    assert result.category == "incomplete_output"
    assert result.usage.output_tokens == 30


def test_a_reply_without_the_tool_call_is_paid_and_unusable() -> None:
    result = _call(FakeAdapter(Prose(json.dumps(INPUT))))

    assert isinstance(result, model_call.PaidUnusable)
    assert result.category == "malformed_response"


def test_a_reply_whose_usage_does_not_hold_together_is_not_answered() -> None:
    result = _call(FakeAdapter(Reply(input=INPUT, usage={"input_tokens": 3})))

    assert result == model_call.NotSent("malformed_provider_usage", retryable=True)


def test_the_tool_input_is_handed_back_as_written_not_judged() -> None:
    result = _call(FakeAdapter('{"text": "never closes'))

    assert isinstance(result, model_call.Answered)
    assert result.tool_input == '{"text": "never closes'


def test_a_provider_failure_is_not_sent_and_logged_with_what_bedrock_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="stoa.private_telemetry")
    message = "tools.0.custom.eager_input_streaming: Extra inputs are not permitted " + "x" * 400
    refused = ProviderError(
        "ValidationException", http_status=400, request_id="req-refused", message=message
    )

    result = _call(FakeAdapter(refused), correlation_id="corr-1")

    assert result == model_call.NotSent("provider_error", retryable=True)
    [line] = [r.getMessage() for r in caplog.records if "model_call_provider_failed" in r.getMessage()]
    assert "stage=invoke" in line
    assert "provider_error_code=ValidationException" in line
    assert "http_status=400" in line
    assert "provider_request_id=req-refused" in line
    logged = line.split("provider_message=", 1)[1].split(" ", 1)[0]
    assert logged.startswith("tools.0.custom.eager_input_streaming:_Extra_inputs")
    assert len(logged) == 300


def test_a_failure_that_is_not_the_providers_is_logged_by_its_class_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="stoa.private_telemetry")

    result = _call(FakeAdapter(RuntimeError("PRIVATE-CANARY")))

    assert result == model_call.NotSent("provider_error", retryable=True)
    assert "exception_class=RuntimeError" in caplog.text
    assert "PRIVATE-CANARY" not in caplog.text


# ── The fake adapter holds bodies to Bedrock's rules ─────────────────────────


def test_the_fake_refuses_what_countokens_refuses_and_takes_what_invoke_takes() -> None:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "x"}],
        "tools": [{"name": "t", "input_schema": {}, "eager_input_streaming": True}],
        "tool_choice": {"type": "tool", "name": "t"},
    }

    check_body(body, counted=False)
    with pytest.raises(ProviderError) as refused:
        check_body(body, counted=True)

    assert refused.value.code == "ValidationException"
    assert refused.value.http_status == 400
    assert refused.value.message == (
        "tools.0.custom.eager_input_streaming: Extra inputs are not permitted"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"messages": []},
        {"tool_choice": {"type": "tool", "name": "other"}},
        {"tools": [{"name": "t"}]},
        {"max_tokens": 0},
    ],
)
def test_the_fake_refuses_a_malformed_body(change: dict[str, Any]) -> None:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "x"}],
        "tools": [{"name": "t", "input_schema": {}}],
        "tool_choice": {"type": "tool", "name": "t"},
        **change,
    }

    with pytest.raises(ProviderError):
        check_body(body, counted=False)


def test_without_an_installed_adapter_a_test_cannot_reach_bedrock() -> None:
    with pytest.raises(model_call.NotInstalled):
        _call()


# ── The Bedrock adapter, on a real botocore client ──────────────────────────


def _runtime() -> Any:
    return boto3.client(
        "bedrock-runtime",
        region_name="eu-central-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def _header(name: str, value: str) -> bytes:
    encoded_name, encoded_value = name.encode(), value.encode()
    return (
        struct.pack("!B", len(encoded_name))
        + encoded_name
        + struct.pack("!BH", 7, len(encoded_value))
        + encoded_value
    )


def _event_message(event: Mapping[str, Any]) -> bytes:
    """One `chunk` event of InvokeModelWithResponseStream, as it is on the wire."""
    payload = json.dumps(
        {"bytes": base64.b64encode(json.dumps(event).encode()).decode()}
    ).encode()
    headers = (
        _header(":event-type", "chunk")
        + _header(":message-type", "event")
        + _header(":content-type", "application/json")
    )
    prelude = struct.pack("!II", 12 + len(headers) + len(payload) + 4, len(headers))
    prelude += struct.pack("!I", binascii.crc32(prelude) & 0xFFFFFFFF)
    message = prelude + headers + payload
    return message + struct.pack("!I", binascii.crc32(message) & 0xFFFFFFFF)


class _Wire:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def stream(self, *_args: Any, **_kwargs: Any):
        yield self._data

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        return self._data

    def close(self) -> None:
        return None


# A forced tool reply as Bedrock streams it.
_STREAMED = [
    {"type": "message_start", "message": {
        "id": "msg_bdrk_1", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 1450}}},
    {"type": "content_block_start", "index": 0, "content_block": {
        "type": "tool_use", "id": "toolu_bdrk_1", "name": "give_it", "input": {}}},
    {"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": '{"text": "Hal'}},
    {"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": 'lo"}'}},
    {"type": "content_block_stop", "index": 0},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
     "usage": {"output_tokens": 21}},
    {"type": "message_stop"},
]


def _streaming(client: Any, events: list[Mapping[str, Any]], sent: list[bytes]) -> None:
    def send(request: Any, **_kwargs: Any) -> AWSResponse:
        sent.append(request.body)
        return AWSResponse(
            request.url,
            200,
            {
                "x-amzn-RequestId": "req-bdrk-1",
                "content-type": "application/vnd.amazon.eventstream",
            },
            _Wire(b"".join(_event_message(event) for event in events)),
        )

    client.meta.events.register(
        "before-send.bedrock-runtime.InvokeModelWithResponseStream", send
    )


def test_the_bedrock_adapter_counts_against_the_foundation_model() -> None:
    client = _runtime()
    body = {"messages": [{"role": "user", "content": "x"}]}
    profile = config.settings().bedrock_model_id
    with Stubber(client) as stub:
        stub.add_response(
            "count_tokens",
            {"inputTokens": 1450, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c-1"}},
            {
                "modelId": profile.split(".", 1)[1],
                "input": {"invokeModel": {"body": json.dumps(body)}},
            },
        )

        assert bedrock.BedrockAdapter(client).connect(30).count_tokens(profile, body) == 1450


def test_the_bedrock_adapter_hands_back_what_bedrock_said_on_a_refusal() -> None:
    client = _runtime()
    with Stubber(client) as stub:
        stub.add_client_error(
            "count_tokens",
            service_error_code="ValidationException",
            service_message="tools.0.custom.eager_input_streaming: Extra inputs are not permitted",
            http_status_code=400,
            response_meta={"RequestId": "c-refused"},
        )

        with pytest.raises(ProviderError) as refused:
            bedrock.BedrockAdapter(client).connect(30).count_tokens(
                config.settings().bedrock_model_id, {"messages": []}
            )

    assert refused.value.code == "ValidationException"
    assert refused.value.http_status == 400
    assert refused.value.request_id == "c-refused"
    assert "Extra inputs are not permitted" in refused.value.message


def test_a_bedrock_refusal_reaches_the_call_as_an_unsent_count() -> None:
    client = _runtime()
    model_call.install(bedrock.BedrockAdapter(client))
    with Stubber(client) as stub:
        stub.add_client_error(
            "count_tokens", service_error_code="ValidationException", http_status_code=400
        )

        result = _call(admission=lambda *_: model_call.Admit())

    assert result == model_call.NotSent("provider_token_count_unavailable", retryable=True)


def test_the_bedrock_adapter_reads_a_streamed_tool_reply_off_the_wire() -> None:
    client = _runtime()
    sent: list[bytes] = []
    _streaming(client, _STREAMED, sent)
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    assert json.loads(result.tool_input) == INPUT
    assert result.usage.request_id == "req-bdrk-1"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1450, 21)
    [body] = sent
    assert json.loads(body)["tools"][0]["eager_input_streaming"] is True


def test_the_bedrock_client_makes_one_attempt_with_reads_bounded_by_the_time_left() -> None:
    client = _runtime()
    _streaming(client, _STREAMED, [])
    aws.install({Kind.BEDROCK_RUNTIME: client})
    model_call.install(bedrock.BedrockAdapter())

    _call(deadline=20.0, clock=_Clock(0.0))

    [request] = aws.requests()
    assert request.kind is Kind.BEDROCK_RUNTIME
    assert request.config.connect_timeout == 5
    assert request.config.read_timeout == 15  # 20 seconds left, less the 5-second margin
    assert request.config.retries["total_max_attempts"] == 1


def test_a_stream_that_breaks_off_is_a_provider_error_not_an_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="stoa.private_telemetry")
    client = _runtime()

    class BreakingWire(_Wire):
        def stream(self, *_args: Any, **_kwargs: Any):
            yield self._data
            raise ReadTimeoutError(endpoint_url="https://bedrock-runtime.example")

    def send(request: Any, **_kwargs: Any) -> AWSResponse:
        return AWSResponse(
            request.url,
            200,
            {"x-amzn-RequestId": "req-broken", "content-type": "application/vnd.amazon.eventstream"},
            BreakingWire(b"".join(_event_message(event) for event in _STREAMED[:3])),
        )

    client.meta.events.register(
        "before-send.bedrock-runtime.InvokeModelWithResponseStream", send
    )
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert result == model_call.NotSent("provider_error", retryable=True)
    assert "stage=stream" in caplog.text
    assert "provider_error_code=ReadTimeoutError" in caplog.text


# ── The shared prefix is cached (#442) ──────────────────────────────────────


def test_what_changes_from_call_to_call_is_sent_after_the_cache_point() -> None:
    model = FakeAdapter(answer=INPUT)

    _call(model, system_tail="For this student.")

    [sent] = model.requests
    assert sent["system"] == [
        {"type": "text", "text": "System.", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "For this student."},
    ]
    assert model.cached_system() == "System."


def test_a_reply_that_touched_the_cache_counts_every_input_token_it_read() -> None:
    usage = {
        "input_tokens": 40,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 1500,
        "output_tokens": 30,
    }
    result = _call(FakeAdapter(Reply(input=INPUT, usage=usage)))

    assert isinstance(result, model_call.Answered)
    assert result.usage.input_tokens == 1540
    assert result.usage.cache_write_input_tokens == 0
    assert result.usage.cache_read_input_tokens == 1500
    evidence = result.usage.evidence(effect_id="effect-1")
    assert (
        evidence.input_tokens,
        evidence.cache_write_input_tokens,
        evidence.cache_read_input_tokens,
    ) == (1540, 0, 1500)


def test_a_reply_without_cache_counts_touched_no_cache() -> None:
    result = _call(FakeAdapter(answer=INPUT))

    assert isinstance(result, model_call.Answered)
    assert result.usage.input_tokens == 90
    assert (result.usage.cache_write_input_tokens, result.usage.cache_read_input_tokens) == (0, 0)


@pytest.mark.parametrize("count", [-1, 1.5, "12"])
def test_a_cache_count_that_is_not_a_count_is_not_answered(count: object) -> None:
    usage = {"input_tokens": 40, "cache_read_input_tokens": count, "output_tokens": 30}

    result = _call(FakeAdapter(Reply(input=INPUT, usage=usage)))

    assert result == model_call.NotSent("malformed_provider_usage", retryable=True)


@pytest.mark.parametrize(
    "system",
    [
        [{"type": "text", "text": "x", "cache_control": {"type": "forever"}}],
        [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}] * 5,
        [{"type": "text", "text": "   "}],
    ],
)
def test_the_fake_refuses_a_system_prompt_bedrock_refuses(system: list[Any]) -> None:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10,
        "system": system,
        "messages": [{"role": "user", "content": "x"}],
    }

    with pytest.raises(ProviderError):
        check_body(body, counted=False)


def test_the_fake_cache_reads_a_prefix_it_was_sent_before_whatever_follows_it() -> None:
    model = FakeAdapter(answer=INPUT)
    model.cached_tokens = 1500

    first = _call(model, system_tail="Student one.")
    second = _call(model, system_tail="Student two.")
    other = _call(model, system="Another system.")

    assert isinstance(first, model_call.Answered)
    assert isinstance(second, model_call.Answered)
    assert isinstance(other, model_call.Answered)
    assert (first.usage.cache_write_input_tokens, first.usage.cache_read_input_tokens) == (1500, 0)
    assert (second.usage.cache_write_input_tokens, second.usage.cache_read_input_tokens) == (0, 1500)
    assert (other.usage.cache_write_input_tokens, other.usage.cache_read_input_tokens) == (1500, 0)
    assert second.usage.input_tokens == 90 + 1500


def test_the_bedrock_adapter_reads_the_cache_counts_off_the_wire() -> None:
    client = _runtime()
    sent: list[bytes] = []
    start = {"type": "message_start", "message": {
        "id": "msg_bdrk_2", "model": "claude-sonnet-4-6", "usage": {
            "input_tokens": 37,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1413,
            "output_tokens": 1,
        }}}
    _streaming(client, [start, *_STREAMED[1:]], sent)
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1450, 21)
    assert result.usage.cache_read_input_tokens == 1413
    [body] = sent
    assert json.loads(body)["system"][0]["cache_control"] == {"type": "ephemeral"}
