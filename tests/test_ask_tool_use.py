"""The Ask answer comes back as one forced tool call, not as hand-written JSON (#412).

Asked to write its answer as a JSON string, the model now and then left a `"`
unescaped inside a step - German quotes a word that way - and the whole reply
failed to parse (#389, about one German answer in ten). The answer is now
handed over as the input of one tool the request forces, so the JSON is the
API's to write, and the steps are read from that input as it streams.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from fakes import model_reply
from fakes.ask_question import _client, _generation, _send
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.bedrock import FakeBedrock
from stoa.services import ai_service, ask_answer

# Straight, German and French quotation marks, all inside step strings.
QUOTED_STEPS = [
    'Das Wort "von" bedeutet hier eine Multiplikation.',
    "Im Satz „Wer entscheidet?“ steht das Verb am Ende.",
    "Auf Französisch heisst «diviser» teilen.",
]
QUOTED_REPLY: dict[str, Any] = {
    "language": "de",
    "steps": QUOTED_STEPS,
    "answer": 'Also ist "3/5 von 20" gleich 12, und „von“ heisst «mal».',
    "hints": ['Was heisst "von" hier?'],
    "similar_exercises": ["Berechne 2/3 von 9."],
    "knowledge_points": ["Brüche"],
    "suggest_teacher": False,
}


def _invoke(model: FakeBedrock, *, streamed: bool, reported: list[tuple[int, str]] | None = None):
    kwargs: dict[str, Any] = {
        "input_size": 12,
        "client": model,
        "effect_id": "effect-412",
        "tool": ask_answer.answer_tool(star_map=False),
    }
    if streamed:
        kwargs["on_step"] = lambda index, step: (reported if reported is not None else []).append(
            (index, step)
        )
    return ai_service.invoke_answer("system", [{"role": "user", "content": "Frage"}], **kwargs)


# ── The request ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("streamed", [False, True])
def test_the_answer_is_asked_for_as_one_forced_tool_call(streamed: bool) -> None:
    model = FakeBedrock(QUOTED_REPLY)

    _invoke(model, streamed=streamed)

    request = model.requests[-1]
    tool = ask_answer.answer_tool(star_map=False)
    assert request["tools"] == [tool]
    assert request["tool_choice"] == {"type": "tool", "name": tool["name"]}
    # Constrained to the schema, and streamed as the model writes it, so a
    # step can be shown the moment it closes.
    assert tool["strict"] is True
    assert tool["eager_input_streaming"] is True


def test_the_tool_asks_for_every_section_of_an_answer() -> None:
    schema = ask_answer.answer_tool(star_map=False)["input_schema"]

    assert set(schema["required"]) == {
        "language", "steps", "answer", "hints", "similar_exercises",
        "knowledge_points", "suggest_teacher",
    }
    assert schema["additionalProperties"] is False
    assert "target_unit_id" not in schema["properties"]


def test_with_a_star_map_the_tool_also_takes_the_star_to_go_to() -> None:
    schema = ask_answer.answer_tool(star_map=True)["input_schema"]

    assert "target_unit_id" in schema["properties"]
    assert "target_unit_id" not in schema["required"]


def test_the_prompt_no_longer_asks_for_hand_written_json() -> None:
    assert "Respond ONLY with valid JSON" not in ask_answer.SYSTEM_PROMPT
    assert ask_answer.ANSWER_TOOL_NAME in ask_answer.SYSTEM_PROMPT
    for style in ("concise", "encouraging", "vivid"):
        rule = ask_answer.answer_style_rule(style)
        assert "two backslashes" not in rule
        assert "straight double quote" not in rule


# ── Quotes inside the steps ──────────────────────────────────────────────────


@pytest.mark.parametrize("streamed", [False, True])
def test_steps_with_quotation_marks_come_back_whole(streamed: bool) -> None:
    result = _invoke(FakeBedrock(QUOTED_REPLY), streamed=streamed)

    assert result.content["steps"] == QUOTED_STEPS
    assert result.content["answer"] == QUOTED_REPLY["answer"]
    assert result.content["hints"] == QUOTED_REPLY["hints"]


@pytest.mark.parametrize("pieces", [1, 2, 7, 40, 400])
def test_each_quoted_step_is_reported_once_and_whole(pieces: int) -> None:
    model = FakeBedrock(QUOTED_REPLY)
    model.pieces = pieces
    reported: list[tuple[int, str]] = []

    _invoke(model, streamed=True, reported=reported)

    assert reported == list(enumerate(QUOTED_STEPS))


def test_text_outside_the_tool_call_is_not_read_as_the_answer() -> None:
    model = FakeBedrock(QUOTED_REPLY)
    original = model.invoke_model_with_response_stream

    def with_preamble(**kwargs: Any) -> dict[str, Any]:
        response = original(**kwargs)
        preamble = {"type": "content_block_delta", "index": 1,
                    "delta": {"type": "text_delta", "text": '{"steps": ["falsch"]}'}}
        response["body"].insert(1, {"chunk": {"bytes": json.dumps(preamble).encode()}})
        return response

    model.invoke_model_with_response_stream = with_preamble  # type: ignore[method-assign]
    reported: list[tuple[int, str]] = []

    result = _invoke(model, streamed=True, reported=reported)

    assert result.content["steps"] == QUOTED_STEPS
    assert reported == list(enumerate(QUOTED_STEPS))


# ── A tool input that cannot be used ─────────────────────────────────────────


def _cut_after_two_steps() -> str:
    text = json.dumps(QUOTED_REPLY, ensure_ascii=False)
    return text[: text.index(QUOTED_STEPS[2]) - 1]


@pytest.mark.parametrize("streamed", [False, True])
def test_tool_input_that_never_closes_is_malformed(streamed: bool) -> None:
    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeBedrock(_cut_after_two_steps()), streamed=streamed)

    assert failure.value.category == "malformed_response"
    # It was paid for: the usage rides on the failure.
    assert failure.value.usage is not None


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("missing", ["steps", "answer"])
def test_tool_input_without_a_section_is_malformed(streamed: bool, missing: str) -> None:
    reply = {key: value for key, value in QUOTED_REPLY.items() if key != missing}

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeBedrock(reply), streamed=streamed)

    assert failure.value.category == "malformed_response"
    assert failure.value.usage is not None


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize(
    ("key", "value"),
    [("steps", "Erst kürzen."), ("steps", [1, 2]), ("answer", ["12"]), ("answer", None)],
)
def test_tool_input_of_the_wrong_shape_is_malformed(streamed: bool, key: str, value: object) -> None:
    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeBedrock({**QUOTED_REPLY, key: value}), streamed=streamed)

    assert failure.value.category == "malformed_response"


@pytest.mark.parametrize("streamed", [False, True])
def test_a_reply_that_calls_no_tool_is_malformed(streamed: bool) -> None:
    prose = model_reply.Prose(json.dumps(QUOTED_REPLY, ensure_ascii=False))

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeBedrock(prose), streamed=streamed)

    assert failure.value.category == "malformed_response"
    assert failure.value.usage is not None


def test_an_unusable_reply_is_logged_as_a_parse_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="stoa.private_telemetry")

    with pytest.raises(ai_service.AIInvocationFailure):
        _invoke(FakeBedrock(_cut_after_two_steps()), streamed=True)

    assert "event_category=model_output_parse_failed" in caplog.text


# ── Through the Ask command ──────────────────────────────────────────────────


def test_a_quoted_answer_is_stored_with_its_steps(table, model) -> None:
    model.outcomes = [QUOTED_REPLY]
    client = _client()

    response = _send(client, "key-1")

    assert response.status_code == 200, response.text
    generation = _generation(client, "key-1")
    assert generation["steps"] == QUOTED_STEPS


def test_an_unfinished_tool_input_fails_without_steps_and_names_no_upload(table, model) -> None:
    # Two whole steps arrive and are published, then the input never closes.
    model.outcomes = [_cut_after_two_steps()]
    client = _client()

    response = _send(client, "key-1")

    assert "upload_service_unavailable" not in response.text
    assert "message_failed" in response.text
    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "malformed_response"
    assert generation["steps"] == []
