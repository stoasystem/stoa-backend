"""The probe of the weekly report's request (#438), on the fake adapter."""

from __future__ import annotations

import base64
import json

from botocore.awsrequest import AWSResponse

from fakes.bedrock import Wire, runtime, streaming
from scripts import probe_weekly_report_request as probe
from stoa import config
from stoa.services import model_call, report_service
from stoa.services.model_call.adapter import ProviderError
from stoa.services.model_call.fake import FakeAdapter


def test_the_probed_bodies_are_the_ones_the_report_sends_and_would_count() -> None:
    model = FakeAdapter({"summary": "x"})
    model_call.install(model)

    report_service.generate_weekly_report_content(probe.SYNTHETIC_PAYLOAD)
    counted, sent = probe.report_bodies()

    assert sent == model.calls[0]
    assert counted == model_call._count_body(model.calls[0])
    [tool] = sent["tools"]
    assert tool["name"] == report_service.REPORT_TOOL.name
    assert tool["input_schema"] == report_service.REPORT_TOOL.input_schema
    assert tool["strict"] is True
    assert tool["eager_input_streaming"] is True
    assert sent["tool_choice"] == {"type": "tool", "name": "give_weekly_report"}
    unstreamed = {key: value for key, value in tool.items() if key != "eager_input_streaming"}
    assert counted == {**sent, "tools": [unstreamed]}


def test_the_probe_streams_through_the_bedrock_adapter_production_uses() -> None:
    """The invoke is the adapter's InvokeModelWithResponseStream, never a buffered InvokeModel.

    On a real botocore client, answered on the wire.
    """
    from stoa.services.model_call.bedrock import BedrockAdapter

    client = runtime()
    counted: list[bytes] = []

    def count(request, **_kwargs):
        counted.append(request.body)
        return AWSResponse(
            request.url,
            200,
            {"x-amzn-RequestId": "c", "content-type": "application/json"},
            Wire(b'{"inputTokens": 12}'),
        )

    def buffered(request, **_kwargs):
        raise AssertionError("the report never calls the buffered InvokeModel")

    client.meta.events.register("before-send.bedrock-runtime.CountTokens", count)
    client.meta.events.register("before-send.bedrock-runtime.InvokeModel", buffered)
    sent: list[bytes] = []
    streaming(
        client,
        [
            {"type": "message_start", "message": {
                "id": "msg_1", "model": "claude", "usage": {"input_tokens": 12}}},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
             "usage": {"output_tokens": 1}},
        ],
        sent,
    )

    lines = probe.probe(
        BedrockAdapter(client), model_id="eu.anthropic.claude-sonnet-4-6", invoke=True, exact=True
    )

    assert len(counted) == 1
    counted_body, sent_body = probe.report_bodies()
    counted_on_the_wire = json.loads(counted[0])["input"]["invokeModel"]["body"]
    assert json.loads(base64.b64decode(counted_on_the_wire)) == counted_body
    assert [json.loads(body) for body in sent] == [sent_body]
    assert lines[0] == "PASS count: CountTokens took the report body, input_tokens=12"
    assert lines[1] == (
        "PASS invoke: InvokeModelWithResponseStream took the exact report body, "
        "stop_reason=tool_use"
    )


def test_without_invoke_the_probe_only_counts(capsys) -> None:
    model = FakeAdapter()

    status = probe.main([], adapter=model)

    assert status == 0
    assert model.counted == 1
    assert model.calls == []
    out = capsys.readouterr().out
    assert "PASS count: CountTokens took the report body, input_tokens=90" in out
    assert "SKIP invoke" in out
    assert config.settings().bedrock_model_id in out


def test_with_invoke_the_probe_sends_the_body_cut_to_one_token(capsys) -> None:
    model = FakeAdapter({"summary": "x"})

    status = probe.main(["--invoke"], adapter=model)

    assert status == 0
    _, sent = probe.report_bodies()
    assert model.calls == [{**sent, "max_tokens": 1}]
    assert (
        "PASS invoke: InvokeModelWithResponseStream took the report body (max_tokens 1), "
        "stop_reason=tool_use"
    ) in capsys.readouterr().out


def test_with_exact_the_probe_sends_the_production_body_unchanged(capsys) -> None:
    model = FakeAdapter({"summary": "x"})

    assert probe.main(["--invoke", "--exact"], adapter=model) == 0

    _, sent = probe.report_bodies()
    assert model.calls == [sent]
    assert sent["max_tokens"] == min(config.settings().bedrock_max_tokens, 1200)


def test_exact_without_invoke_is_refused() -> None:
    model = FakeAdapter()

    assert probe.main(["--exact"], adapter=model) == 2
    assert model.counted == 0


def test_a_refused_body_fails_the_probe_with_what_bedrock_said(monkeypatch, capsys) -> None:
    # As before #430 was fixed: the stream-only field left in the counted body.
    monkeypatch.setattr(model_call, "_STREAM_ONLY_TOOL_FIELDS", frozenset())
    model = FakeAdapter(
        answer=ProviderError(
            "ValidationException", http_status=400, message="max_tokens: too small"
        )
    )

    status = probe.main(["--invoke"], adapter=model)

    assert status == 1
    out = capsys.readouterr().out
    assert (
        "FAIL count: ValidationException HTTP 400: "
        "tools.0.custom.eager_input_streaming: Extra inputs are not permitted"
    ) in out
    assert "FAIL invoke: ValidationException HTTP 400: max_tokens: too small" in out
