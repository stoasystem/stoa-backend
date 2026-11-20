"""The probe of the weekly report's request (#438), on the fake adapter."""

from __future__ import annotations

import json

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
    """The invoke is the adapter's InvokeModelWithResponseStream, never a buffered InvokeModel."""
    from stoa.services.model_call.bedrock import BedrockAdapter

    class Client:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def count_tokens(self, **kwargs):
            self.operations.append("count_tokens")
            return {
                "inputTokens": 12,
                "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c"},
            }

        def invoke_model_with_response_stream(self, **kwargs):
            self.operations.append("invoke_model_with_response_stream")
            self.body = kwargs["body"]
            return {"body": [], "ResponseMetadata": {"RequestId": "r"}}

        def invoke_model(self, **kwargs):
            raise AssertionError("the report never calls the buffered InvokeModel")

    client = Client()
    lines = probe.probe(
        BedrockAdapter(client), model_id="eu.anthropic.claude-sonnet-4-6", invoke=True, exact=True
    )

    assert client.operations == ["count_tokens", "invoke_model_with_response_stream"]
    _, sent = probe.report_bodies()
    assert json.loads(client.body) == sent
    assert lines[0].startswith("PASS count")
    assert lines[1].startswith("PASS invoke: InvokeModelWithResponseStream took the exact report body")


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
