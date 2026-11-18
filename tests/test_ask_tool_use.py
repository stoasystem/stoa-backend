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
import time
from typing import Any

import pytest

from fakes.ask_question import _client, _generation, _send
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.model import FakeModel, Prose, install
from stoa.services import ai_service, ask_answer, model_call
from stoa.services.model_call.adapter import Stream

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


def _invoke(model: FakeModel, *, reported: list[tuple[int, str]] | None = None):
    """Ask `model` for the answer tool's input as `ask_answer` does, and read it as an answer."""
    install(model)
    steps = reported if reported is not None else []
    result = model_call.call(
        system="system",
        messages=[{"role": "user", "content": "Frage"}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=1024,
        temperature=ask_answer.ANSWER_TEMPERATURE,
        deadline=time.monotonic() + 90,
        on_partial=ask_answer._step_reporter(lambda index, step: steps.append((index, step))),
    )
    return ask_answer.provider_result(result, effect_id="effect-412")


# ── The request ──────────────────────────────────────────────────────────────


def test_the_answer_is_asked_for_as_one_forced_tool_call() -> None:
    model = FakeModel(QUOTED_REPLY)

    _invoke(model)

    request = model.requests[-1]
    tool = ask_answer.answer_tool(star_map=False)
    [sent] = request["tools"]
    assert sent["name"] == tool.name
    assert sent["input_schema"] == tool.input_schema
    assert request["tool_choice"] == {"type": "tool", "name": tool.name}
    # Constrained to the schema, and streamed as the model writes it, so a
    # step can be shown the moment it closes.
    assert sent["strict"] is True
    assert sent["eager_input_streaming"] is True


def test_the_tool_asks_for_every_section_of_an_answer() -> None:
    schema = ask_answer.answer_tool(star_map=False).input_schema

    assert set(schema["required"]) == {
        "language", "steps", "answer", "hints", "similar_exercises",
        "knowledge_points", "suggest_teacher", "quick_replies",
    }
    assert schema["additionalProperties"] is False
    assert "target_unit_id" not in schema["properties"]


def test_the_quick_replies_are_texts_with_no_constraint_beyond_those_already_used() -> None:
    # #430: the schema only uses what the rest of it already does; how many
    # there may be and how long each is are the checks' to decide.
    schema = ask_answer.answer_tool(star_map=False).input_schema
    quick = schema["properties"]["quick_replies"]

    assert {key: value for key, value in quick.items() if key != "description"} == {
        "type": "array", "items": {"type": "string"},
    }
    assert quick == {**schema["properties"]["steps"], "description": quick["description"]}


def test_with_a_star_map_the_tool_also_takes_the_star_to_go_to() -> None:
    schema = ask_answer.answer_tool(star_map=True).input_schema

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


def test_steps_with_quotation_marks_come_back_whole() -> None:
    result = _invoke(FakeModel(QUOTED_REPLY))

    assert result.content["steps"] == QUOTED_STEPS
    assert result.content["answer"] == QUOTED_REPLY["answer"]
    assert result.content["hints"] == QUOTED_REPLY["hints"]


@pytest.mark.parametrize("pieces", [1, 2, 7, 40, 400])
def test_each_quoted_step_is_reported_once_and_whole(pieces: int) -> None:
    model = FakeModel(QUOTED_REPLY)
    model.pieces = pieces
    reported: list[tuple[int, str]] = []

    _invoke(model, reported=reported)

    assert reported == list(enumerate(QUOTED_STEPS))


def test_text_outside_the_tool_call_is_not_read_as_the_answer() -> None:
    class WithPreamble(FakeModel):
        def stream(self, model_id: str, body: Any) -> Stream:
            sent = super().stream(model_id, body)
            events = list(sent.events)
            preamble = {"type": "content_block_delta", "index": 1,
                        "delta": {"type": "text_delta", "text": '{"steps": ["falsch"]}'}}
            events.insert(1, preamble)
            return Stream(request_id=sent.request_id, events=events)

    model = WithPreamble(QUOTED_REPLY)
    reported: list[tuple[int, str]] = []

    result = _invoke(model, reported=reported)

    assert result.content["steps"] == QUOTED_STEPS
    assert reported == list(enumerate(QUOTED_STEPS))


# ── A tool input that cannot be used ─────────────────────────────────────────


def _cut_after_two_steps() -> str:
    text = json.dumps(QUOTED_REPLY, ensure_ascii=False)
    return text[: text.index(QUOTED_STEPS[2]) - 1]


def test_tool_input_that_never_closes_is_malformed() -> None:
    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeModel(_cut_after_two_steps()))

    assert failure.value.category == "malformed_response"
    # It was paid for: the usage rides on the failure.
    assert failure.value.usage is not None


@pytest.mark.parametrize("missing", ["steps", "answer"])
def test_tool_input_without_a_section_is_malformed(missing: str) -> None:
    reply = {key: value for key, value in QUOTED_REPLY.items() if key != missing}

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeModel(reply))

    assert failure.value.category == "malformed_response"
    assert failure.value.usage is not None


@pytest.mark.parametrize(
    ("key", "value"),
    [("steps", "Erst kürzen."), ("steps", [1, 2]), ("answer", ["12"]), ("answer", None)],
)
def test_tool_input_of_the_wrong_shape_is_malformed(key: str, value: object) -> None:
    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeModel({**QUOTED_REPLY, key: value}))

    assert failure.value.category == "malformed_response"


def test_a_reply_that_calls_no_tool_is_malformed() -> None:
    prose = Prose(json.dumps(QUOTED_REPLY, ensure_ascii=False))

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeModel(prose))

    assert failure.value.category == "malformed_response"
    assert failure.value.usage is not None


def test_an_unusable_reply_is_logged_as_a_parse_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="stoa.private_telemetry")

    with pytest.raises(ai_service.AIInvocationFailure):
        _invoke(FakeModel(_cut_after_two_steps()))

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


# ── A text with no words in it (#507) ────────────────────────────────────────
#
# The model opened a German quotation with „ and closed it with a straight ",
# which ends the JSON string: the step stopped before its closing quote, and
# the leftover ` , ` became a step of its own. The input is valid JSON and
# satisfies the schema, so it is read; a text with no letter or digit in it is
# left out, while streaming and in the stored answer alike.

CUT_STEPS = [
    "Die Ableitung misst, wie schnell sich eine Funktion ändert.",
    "Für eine Funktion $f(x)$ fragt die Ableitung $f'(x)$: „Wenn ich $x$ ein kleines "
    "bisschen vergrößere, wie stark verändert sich dann $f(x)$?",
    " , ",
    "Ein einfaches Beispiel: $f(x) = x^2$ hat die Ableitung $f'(x) = 2x$.",
    "Bei $x = 3$ wächst $f$ also etwa sechsmal so schnell wie $x$.",
]
WORDED_STEPS = [step for step in CUT_STEPS if step != " , "]
CUT_REPLY: dict[str, Any] = {**QUOTED_REPLY, "steps": CUT_STEPS}


def test_a_step_cut_short_by_a_straight_quote_leaves_no_stray_step_in_the_answer() -> None:
    result = _invoke(FakeModel(CUT_REPLY))

    assert result.content["steps"] == WORDED_STEPS


@pytest.mark.parametrize("pieces", [1, 2, 7, 40, 400])
def test_a_stray_step_of_punctuation_is_never_streamed(pieces: int) -> None:
    model = FakeModel(CUT_REPLY)
    model.pieces = pieces
    reported: list[tuple[int, str]] = []

    _invoke(model, reported=reported)

    # Numbered as the stored answer numbers them, with no gap.
    assert reported == list(enumerate(WORDED_STEPS))


def test_the_partial_input_reads_no_step_of_punctuation() -> None:
    text = json.dumps(CUT_REPLY, ensure_ascii=False)
    after_stray = text[: text.index(CUT_STEPS[3]) - 1]

    assert ask_answer.completed_steps(after_stray) == CUT_STEPS[:2]
    assert ask_answer.completed_steps(text) == WORDED_STEPS


@pytest.mark.parametrize("stray", ["", "   ", " , ", "?!", "„", "…", " – ", "$$", "\n"])
def test_no_text_without_a_letter_or_digit_is_kept(stray: str) -> None:
    reply = {
        **QUOTED_REPLY,
        "steps": [stray, *QUOTED_STEPS, stray],
        "hints": [stray, *QUOTED_REPLY["hints"]],
        "similar_exercises": [stray, *QUOTED_REPLY["similar_exercises"], stray],
        "knowledge_points": [stray, *QUOTED_REPLY["knowledge_points"]],
        "quick_replies": [stray, "Noch ein Beispiel?"],
    }

    content = _invoke(FakeModel(reply)).content

    assert content["steps"] == QUOTED_STEPS
    assert content["hints"] == QUOTED_REPLY["hints"]
    assert content["similar_exercises"] == QUOTED_REPLY["similar_exercises"]
    assert content["knowledge_points"] == QUOTED_REPLY["knowledge_points"]
    assert content["quick_replies"] == ["Noch ein Beispiel?"]


def test_an_answer_without_a_letter_or_digit_is_left_empty() -> None:
    content = _invoke(FakeModel({**QUOTED_REPLY, "answer": " , "})).content

    assert content["answer"] == ""
    assert content["steps"] == QUOTED_STEPS


def test_a_short_text_with_a_digit_or_a_letter_is_kept() -> None:
    reply = {**QUOTED_REPLY, "steps": ["12", "x", "π", *QUOTED_STEPS], "answer": "7"}

    content = _invoke(FakeModel(reply)).content

    assert content["steps"] == ["12", "x", "π", *QUOTED_STEPS]
    assert content["answer"] == "7"


def test_a_reply_of_punctuation_only_is_malformed() -> None:
    reply = {**QUOTED_REPLY, "steps": [" , ", "…"], "answer": " , "}

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _invoke(FakeModel(reply))

    assert failure.value.category == "malformed_response"


def test_the_prompt_names_the_quotation_marks_to_use() -> None:
    prompt = ask_answer.SYSTEM_PROMPT
    assert "«…»" in prompt
    assert "„…“" in prompt
    assert "never a straight double quote" in prompt


def test_a_cut_answer_is_stored_and_published_without_the_stray_step(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stoa.services.ask_question import _store

    published: list[list[str]] = []
    record = _store.record_generation_progress

    def recording(*args: Any, **kwargs: Any) -> Any:
        published.append(list(kwargs["steps"]))
        return record(*args, **kwargs)

    monkeypatch.setattr(_store, "record_generation_progress", recording)
    model.outcomes = [CUT_REPLY]
    model.pieces = 7
    client = _client()

    response = _send(client, "key-1")

    assert response.status_code == 200, response.text
    assert published, "no step was published while streaming"
    assert published[-1] == WORDED_STEPS
    assert all(step.strip(" ,") for steps in published for step in steps)
    generation = _generation(client, "key-1")
    assert generation["steps"] == WORDED_STEPS
    assert "3.  , " not in response.text
