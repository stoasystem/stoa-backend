"""The probe of both model-call requests (#439): on the fake adapter, and on the wire."""

from __future__ import annotations

import base64
import json

from botocore.awsrequest import AWSResponse

from fakes.bedrock import Wire, runtime, streaming
from scripts import probe_ask_answer_request, probe_bedrock_token_count as probe
from scripts import probe_weekly_report_request
from stoa import config
from stoa.services import model_call
from stoa.services.model_call.fake import FakeAdapter, Reply

MODEL_ID = "eu.anthropic.claude-sonnet-4-6"


def _cut_off(**usage: int) -> Reply:
    return Reply(input={"x": "y"}, stop_reason="max_tokens", usage=usage)


def _but_the_turn(body: dict) -> dict:
    return {key: value for key, value in body.items() if key != "messages"}


def _counted(request) -> dict:
    """The body a CountTokens request on the wire asks to count (a base64 blob)."""
    return json.loads(base64.b64decode(json.loads(request.body)["input"]["invokeModel"]["body"]))


def test_it_counts_and_sends_the_ask_answer_and_the_weekly_report(capsys) -> None:
    model = FakeAdapter(
        _cut_off(input_tokens=1400, output_tokens=1),
        _cut_off(input_tokens=800, output_tokens=1),
    )

    assert probe.main([], adapter=model) == 0

    # Each request counted as it is sent, and sent as production sends it but
    # for `max_tokens`. The Ask turn's tags are drawn afresh for every answer.
    _, ask_sent = probe_ask_answer_request.ask_bodies()
    _, report_sent = probe_weekly_report_request.report_bodies()
    assert len(model.counted_bodies) == len(model.calls) == 2
    for counted, sent, production in zip(
        model.counted_bodies, model.calls, (ask_sent, report_sent), strict=True
    ):
        assert sent["max_tokens"] == 1
        assert counted == model_call._count_body({**sent, "max_tokens": production["max_tokens"]})
        assert _but_the_turn(sent) == _but_the_turn({**production, "max_tokens": 1})
    assert model.calls[1] == {**report_sent, "max_tokens": 1}
    out = capsys.readouterr().out
    assert f"Probing the model-call requests on {config.settings().bedrock_model_id}" in out
    assert out.splitlines()[1:] == [
        "PASS ask count: CountTokens took the body, input_tokens=90",
        "PASS ask invoke: InvokeModelWithResponseStream took the body (max_tokens 1), "
        "stop_reason=max_tokens input_tokens=1400 output_tokens=1",
        "PASS report count: CountTokens took the body, input_tokens=90",
        "PASS report invoke: InvokeModelWithResponseStream took the body (max_tokens 1), "
        "stop_reason=max_tokens input_tokens=800 output_tokens=1",
    ]


def test_count_only_sends_nothing_and_measures_the_input_tokens(capsys) -> None:
    model = FakeAdapter()

    assert probe.main(["--count-only"], adapter=model) == 0

    assert model.counted == 2
    assert model.calls == []
    assert capsys.readouterr().out.splitlines()[1:] == [
        "PASS ask count: CountTokens took the body, input_tokens=90",
        "PASS report count: CountTokens took the body, input_tokens=90",
    ]


def test_the_cache_tokens_bedrock_reports_are_printed() -> None:
    model = FakeAdapter(
        _cut_off(
            input_tokens=12,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=1388,
            output_tokens=1,
        ),
        _cut_off(input_tokens=800, output_tokens=1),
    )

    lines = probe.probe(model, model_id=MODEL_ID)

    assert lines[1].endswith(
        "stop_reason=max_tokens input_tokens=12 cache_creation_input_tokens=0 "
        "cache_read_input_tokens=1388 output_tokens=1"
    )


def test_a_refused_body_fails_the_run_with_what_bedrock_said(monkeypatch, capsys) -> None:
    # As before #430 was fixed: the stream-only field left in the counted body.
    monkeypatch.setattr(model_call, "_STREAM_ONLY_TOOL_FIELDS", frozenset())

    assert probe.main(["--count-only"], adapter=FakeAdapter()) == 1

    out = capsys.readouterr().out
    for name in ("ask", "report"):
        assert (
            f"FAIL {name} count: ValidationException HTTP 400: "
            "tools.0.custom.eager_input_streaming: Extra inputs are not permitted"
        ) in out


def test_it_reaches_bedrock_through_the_bedrock_adapter() -> None:
    """CountTokens and InvokeModelWithResponseStream, on a real botocore client
    answered on the wire; never the buffered InvokeModel."""
    from stoa.services.model_call.bedrock import BedrockAdapter

    client = runtime()
    operations: list[str] = []

    def count(request, **_kwargs):
        operations.append("CountTokens")
        body = _counted(request)
        tokens = 1400 if body["tools"][0]["name"] == "give_answer" else 800
        return AWSResponse(
            request.url,
            200,
            {"x-amzn-RequestId": "c", "content-type": "application/json"},
            Wire(json.dumps({"inputTokens": tokens}).encode()),
        )

    def buffered(request, **_kwargs):
        raise AssertionError("the probe never calls the buffered InvokeModel")

    client.meta.events.register("before-send.bedrock-runtime.CountTokens", count)
    client.meta.events.register("before-send.bedrock-runtime.InvokeModel", buffered)
    sent: list[bytes] = []
    streaming(
        client,
        [
            {"type": "message_start", "message": {
                "id": "msg_1", "model": "claude", "usage": {"input_tokens": 1400}}},
            {"type": "message_delta", "delta": {"stop_reason": "max_tokens"},
             "usage": {"output_tokens": 1}},
        ],
        sent,
    )

    lines = probe.probe(BedrockAdapter(client), model_id=MODEL_ID)

    assert operations == ["CountTokens", "CountTokens"]
    assert [json.loads(body)["tools"][0]["name"] for body in sent] == [
        "give_answer",
        "give_weekly_report",
    ]
    assert all(json.loads(body)["max_tokens"] == 1 for body in sent)
    assert [line.split(":")[0] for line in lines] == [
        "PASS ask count",
        "PASS ask invoke",
        "PASS report count",
        "PASS report invoke",
    ]
    assert lines[0].endswith("input_tokens=1400")
    assert lines[2].endswith("input_tokens=800")
