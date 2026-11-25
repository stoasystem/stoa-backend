"""模型调用 (#436): the one way the service asks Claude for a forced tool answer.

The call itself is tested through the in-memory adapter only (`FakeAdapter`),
which holds every body to the rules measured against Bedrock. The Bedrock
adapter is tested on a real botocore client: CountTokens and the error replies
through `Stubber`, the response stream as event-stream bytes on the wire,
decoded by botocore's own parser (`Stubber` cannot carry a stream body).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Any

import pytest
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from fakes.bedrock import Wire, event_message, runtime, streaming
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
        def count(self, model_id: str, body: Mapping[str, Any]) -> int:
            steps.append("count")
            return super().count(model_id, body)

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


def test_the_bedrock_adapter_counts_against_the_foundation_model() -> None:
    client = runtime()
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

        assert bedrock.BedrockAdapter(client).connect(30).count(profile, body) == 1450


@pytest.mark.parametrize(
    ("model_id", "counted_as"),
    [
        ("eu.anthropic.claude-sonnet-4-6", "anthropic.claude-sonnet-4-6"),
        ("global.anthropic.claude-sonnet-4-6", "anthropic.claude-sonnet-4-6"),
        ("anthropic.claude-sonnet-4-6", "anthropic.claude-sonnet-4-6"),
        ("eu.", "eu."),
    ],
)
def test_the_bedrock_adapter_counts_an_inference_profile_as_its_foundation_model(
    model_id: str, counted_as: str
) -> None:
    client = runtime()
    with Stubber(client) as stub:
        stub.add_response(
            "count_tokens",
            {"inputTokens": 7, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c-2"}},
            {"modelId": counted_as, "input": {"invokeModel": {"body": "{}"}}},
        )

        assert bedrock.BedrockAdapter(client).connect(30).count(model_id, {}) == 7


@pytest.mark.parametrize(
    "response",
    [
        {"inputTokens": -1, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c"}},
        {"inputTokens": 37, "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "c"}},
        {"inputTokens": 37, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": " "}},
    ],
)
def test_a_count_reply_that_does_not_hold_together_is_not_a_count(
    response: dict[str, Any],
) -> None:
    client = runtime()
    with Stubber(client) as stub:
        stub.add_response("count_tokens", response)

        with pytest.raises(ProviderError) as malformed:
            bedrock.BedrockAdapter(client).connect(30).count(
                config.settings().bedrock_model_id, {"messages": []}
            )

    assert malformed.value.code == "MalformedCountResponse"


def test_the_bedrock_adapter_hands_back_what_bedrock_said_on_a_refusal() -> None:
    client = runtime()
    with Stubber(client) as stub:
        stub.add_client_error(
            "count_tokens",
            service_error_code="ValidationException",
            service_message="tools.0.custom.eager_input_streaming: Extra inputs are not permitted",
            http_status_code=400,
            response_meta={"RequestId": "c-refused"},
        )

        with pytest.raises(ProviderError) as refused:
            bedrock.BedrockAdapter(client).connect(30).count(
                config.settings().bedrock_model_id, {"messages": []}
            )

    assert refused.value.code == "ValidationException"
    assert refused.value.http_status == 400
    assert refused.value.request_id == "c-refused"
    assert "Extra inputs are not permitted" in refused.value.message


def test_a_bedrock_refusal_reaches_the_call_as_an_unsent_count() -> None:
    client = runtime()
    model_call.install(bedrock.BedrockAdapter(client))
    with Stubber(client) as stub:
        stub.add_client_error(
            "count_tokens", service_error_code="ValidationException", http_status_code=400
        )

        result = _call(admission=lambda *_: model_call.Admit())

    assert result == model_call.NotSent("provider_token_count_unavailable", retryable=True)


def test_the_bedrock_adapter_reads_a_streamed_tool_reply_off_the_wire() -> None:
    client = runtime()
    sent: list[bytes] = []
    streaming(client, _STREAMED, sent)
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    assert json.loads(result.tool_input) == INPUT
    assert result.usage.request_id == "req-bdrk-1"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1450, 21)
    [body] = sent
    assert json.loads(body)["tools"][0]["eager_input_streaming"] is True


def test_the_bedrock_client_makes_one_attempt_with_reads_bounded_by_the_time_left() -> None:
    client = runtime()
    streaming(client, _STREAMED, [])
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
    client = runtime()

    class BreakingWire(Wire):
        def stream(self, *_args: Any, **_kwargs: Any):
            yield self._data
            raise ReadTimeoutError(endpoint_url="https://bedrock-runtime.example")

    def send(request: Any, **_kwargs: Any) -> AWSResponse:
        return AWSResponse(
            request.url,
            200,
            {"x-amzn-RequestId": "req-broken", "content-type": "application/vnd.amazon.eventstream"},
            BreakingWire(b"".join(event_message(event) for event in _STREAMED[:3])),
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


@pytest.mark.parametrize(
    "end_usage",
    [
        # The end of the message repeats the cache counts as 0 ...
        {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        # ... or as null, with the input count as well.
        {
            "input_tokens": None,
            "cache_creation_input_tokens": None,
            "cache_read_input_tokens": None,
        },
    ],
)
def test_the_end_of_the_message_does_not_undo_the_cache_counts_of_its_start(
    end_usage: dict[str, Any],
) -> None:
    """#612: `message_delta` carries usage too, and what it repeats must not
    turn a reply that read the cache into one that did not."""
    usage = {
        "input_tokens": 40,
        "cache_creation_input_tokens": 200,
        "cache_read_input_tokens": 1500,
        "output_tokens": 30,
    }
    result = _call(FakeAdapter(Reply(input=INPUT, usage=usage, end_usage=end_usage)))

    assert isinstance(result, model_call.Answered)
    assert result.usage.input_tokens == 1740
    assert result.usage.cache_write_input_tokens == 200
    assert result.usage.cache_read_input_tokens == 1500
    assert result.usage.output_tokens == 30


def test_the_end_of_the_message_may_raise_a_count_and_correct_the_others() -> None:
    """Totals reported at the end stand: a cache count that grew, and any other
    count, which the end states for the whole reply."""
    usage = {"input_tokens": 40, "cache_read_input_tokens": 0, "output_tokens": 1}
    end_usage = {"input_tokens": 37, "cache_read_input_tokens": 1500, "output_tokens": 30}

    result = _call(FakeAdapter(Reply(input=INPUT, usage=usage, end_usage=end_usage)))

    assert isinstance(result, model_call.Answered)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1537, 30)
    assert result.usage.cache_read_input_tokens == 1500


def test_a_cache_count_the_end_of_the_message_garbles_is_still_not_a_count() -> None:
    usage = {"input_tokens": 40, "cache_read_input_tokens": 1500, "output_tokens": 30}

    result = _call(
        FakeAdapter(Reply(input=INPUT, usage=usage, end_usage={"cache_read_input_tokens": -1}))
    )

    assert result == model_call.NotSent("malformed_provider_usage", retryable=True)


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
    client = runtime()
    sent: list[bytes] = []
    start = {"type": "message_start", "message": {
        "id": "msg_bdrk_2", "model": "claude-sonnet-4-6", "usage": {
            "input_tokens": 37,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1413,
            "output_tokens": 1,
        }}}
    streaming(client, [start, *_STREAMED[1:]], sent)
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1450, 21)
    assert result.usage.cache_read_input_tokens == 1413
    [body] = sent
    assert json.loads(body)["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize(
    "end_usage",
    [
        # Bedrock today: the end of the message reports only the output.
        {"output_tokens": 21},
        # The Messages API's newer shape: the end repeats every count, and a
        # provider may send a cache count it does not track there as 0 ...
        {
            "input_tokens": 37,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 21,
        },
        # ... or as null.
        {
            "input_tokens": None,
            "cache_creation_input_tokens": None,
            "cache_read_input_tokens": None,
            "output_tokens": 21,
        },
    ],
    ids=["output-only", "cache-as-zero", "cache-as-null"],
)
def test_a_cache_read_survives_the_end_of_a_bedrock_stream(end_usage: dict[str, Any]) -> None:
    """#612, on the wire: a reply that read the cache, streamed as Bedrock
    streams it (usage at `message_start`, usage again at `message_delta`, the
    invocation metrics at `message_stop`), is recorded with the counts it was
    billed at, whatever the end of the message repeats."""
    client = runtime()
    events = [
        {"type": "message_start", "message": {
            "id": "msg_bdrk_3", "type": "message", "role": "assistant",
            "model": "claude-sonnet-4-6", "content": [], "stop_reason": None,
            "stop_sequence": None, "usage": {
                "input_tokens": 37,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 2186,
                "output_tokens": 1,
            }}},
        *_STREAMED[1:5],
        {"type": "message_delta",
         "delta": {"stop_reason": "tool_use", "stop_sequence": None},
         "usage": end_usage},
        {"type": "message_stop", "amazon-bedrock-invocationMetrics": {
            "inputTokenCount": 37,
            "outputTokenCount": 21,
            "invocationLatency": 1830,
            "firstByteLatency": 640,
            "cacheReadInputTokenCount": 2186,
            "cacheWriteInputTokenCount": 0,
        }},
    ]
    streaming(client, events, [])
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    assert result.tool_input == '{"text": "Hallo"}'
    assert result.usage.cache_read_input_tokens == 2186
    assert result.usage.cache_write_input_tokens == 0
    assert (result.usage.input_tokens, result.usage.output_tokens) == (37 + 2186, 21)


def test_the_body_counted_keeps_the_cache_point() -> None:
    """CountTokens takes `cache_control` and counts the same with it (measured, #442)."""
    model = FakeAdapter(answer=INPUT)

    result = _call(model, system_tail="For this student.", admission=lambda *_: model_call.Admit())

    assert isinstance(result, model_call.Answered)
    [counted] = model.counted_bodies
    assert counted["system"] == model.requests[0]["system"]


# ── Invoked through an application inference profile (#612) ─────────────────

PRODUCT_PROFILE = "arn:aws:bedrock:eu-central-2:111122223333:application-inference-profile/abc123"


class _Routed(FakeAdapter):
    """The fake, keeping which id each body was counted on and sent through."""

    def __init__(self, *outcomes: Any, **kwargs: Any) -> None:
        super().__init__(*outcomes, **kwargs)
        self.counted_on: list[str] = []
        self.sent_through: list[str] = []

    def count(self, model_id: str, body: Mapping[str, Any]) -> int:
        self.counted_on.append(model_id)
        return super().count(model_id, body)

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Any:
        self.sent_through.append(model_id)
        return super().stream(model_id, body)


def test_without_a_profile_the_model_id_is_counted_and_invoked() -> None:
    model = _Routed(answer=INPUT)

    result = _call(model, admission=lambda _tokens, _limit: model_call.Admit())

    model_id = config.settings().bedrock_model_id
    assert isinstance(result, model_call.Answered)
    assert (model.counted_on, model.sent_through) == ([model_id], [model_id])
    assert result.usage.inference_profile_id == model_id


def test_with_a_profile_the_call_is_sent_through_it_and_counted_on_the_model() -> None:
    """The profile is where the cost is booked; CountTokens takes a model, not a profile."""
    config.install(
        config.settings().model_copy(
            update={"bedrock_inference_profile_arn": f" {PRODUCT_PROFILE} "}
        )
    )
    model = _Routed(answer=INPUT)

    result = _call(model, admission=lambda _tokens, _limit: model_call.Admit())

    assert isinstance(result, model_call.Answered)
    assert model.counted_on == [config.settings().bedrock_model_id]
    assert model.sent_through == [PRODUCT_PROFILE]
    assert result.usage.inference_profile_id == PRODUCT_PROFILE


def test_the_bedrock_adapter_invokes_through_the_profile_s_arn_on_the_wire() -> None:
    config.install(
        config.settings().model_copy(update={"bedrock_inference_profile_arn": PRODUCT_PROFILE})
    )
    client = runtime()
    urls: list[str] = []
    client.meta.events.register(
        "before-send.bedrock-runtime.InvokeModelWithResponseStream",
        lambda request, **_: urls.append(request.url),
    )
    streaming(client, _STREAMED, [])
    model_call.install(bedrock.BedrockAdapter(client))

    result = _call()

    assert isinstance(result, model_call.Answered)
    [url] = urls
    assert url.endswith(
        "/model/arn%3Aaws%3Abedrock%3Aeu-central-2%3A111122223333%3A"
        "application-inference-profile%2Fabc123/invoke-with-response-stream"
    )
