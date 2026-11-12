"""A first answer that failed on a broken reply, and the question sent again (#389).

In production a reply came back as JSON with an unescaped `"` inside a step
(German quotes the word "von" that way). The whole reply could not be parsed,
so the command failed `malformed_response`, but the steps already published
while it streamed were cut from that broken text - the first one starting
mid-sentence - and `/generation` kept returning them with `status: failed`.
The student then sent the question again with a new key, and the conversation
held the question twice, as did the teacher's help request.
"""

from __future__ import annotations

import pytest

from fakes.ask_question import (
    CONV,
    QUESTION,
    _client,
    _generation,
    _messages,
    _send,
)
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.services import ai_service, learning_session

# The shape of the reply that failed: an unescaped quote inside the first step.
BROKEN_REPLY = (
    '{"steps": ["Bei solchen Aufgaben bedeutet das Wort "von" eine Multiplikation. '
    'Also: 3/5 · 20.", "Rechne 20 : 5 = 4.", "Dann 3 · 4 = 12."], '
    '"answer": "12", "hints": []}'
)


# ── The steps cut from a partly received reply ───────────────────────────────


def test_a_step_with_an_unescaped_quote_is_never_cut_mid_sentence() -> None:
    steps = ai_service.completed_steps(BROKEN_REPLY)

    assert all(not step.startswith(" ") for step in steps)
    assert not any("eine Multiplikation" in step for step in steps)


def test_steps_stop_at_the_first_string_that_does_not_close_cleanly() -> None:
    reply = '{"steps": ["Erst kürzen.", "Das Wort "von" heisst mal.", "Dann teilen."]}'

    assert ai_service.completed_steps(reply) == ["Erst kürzen."]


@pytest.mark.parametrize(
    ("partial", "expected"),
    [
        ('{"steps": [', []),
        ('{"steps": ["Erst', []),
        ('{"steps": ["Erst kürzen."', []),
        ('{"steps": ["Erst kürzen.",', ["Erst kürzen."]),
        ('{"steps": ["Erst \\"so\\" kürzen.", "Dann', ['Erst "so" kürzen.']),
        ('{"steps": ["a", "b"], "answer": "c", "hints": ["d", "e"]}', ["a", "b"]),
        ('{"answer": "c"}', []),
    ],
)
def test_steps_are_reported_only_once_whole(partial: str, expected: list[str]) -> None:
    assert ai_service.completed_steps(partial) == expected


# ── What /generation reports for a failed answer ─────────────────────────────


def test_a_failed_answer_reports_no_steps(table, model) -> None:
    # Two whole steps arrive and are published, then the reply fails to parse.
    model.outcomes = [
        '{"steps": ["Kürze mit 2.", "Teile durch 3."], '
        '"answer": "Das Wort "von" heisst mal.", "hints": []}'
    ]
    client = _client()

    assert _send(client, "key-1").status_code == 409  # message_failed (#412)

    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "malformed_response"
    assert generation["steps"] == []


def test_a_failed_answer_reports_no_steps_without_a_key_either(table, model) -> None:
    model.outcomes = [
        '{"steps": ["Kürze mit 2.", "Teile durch 3."], '
        '"answer": "Das Wort "von" heisst mal.", "hints": []}'
    ]
    client = _client()
    assert _send(client, "key-1").status_code == 409  # message_failed (#412)

    assert _generation(client, None)["steps"] == []


# ── The question sent again ──────────────────────────────────────────────────


def _resend_after_a_failure(table, model) -> None:
    model.outcomes = [BROKEN_REPLY]
    client = _client()
    assert _send(client, "initial-1").status_code == 409  # message_failed (#412)
    assert _generation(client, "initial-1")["status"] == "failed"

    # "Erneut senden": the same question, under a new key.
    resent = _send(client, "resend-1")
    assert resent.status_code == 200, resent.text


def test_the_question_sent_again_reads_back_once(table, model) -> None:
    _resend_after_a_failure(table, model)

    history = learning_session.history(CONV)

    assert [(message.role, message.content) for message in history if message.role == "student"] == [
        ("student", QUESTION)
    ]
    assert [message.role for message in history] == ["student", "assistant"]
    read_back = _client().get(f"/conversations/{CONV}").json()["messages"]
    assert [message["role"] for message in read_back] == ["student", "assistant"]
    # Both rows stay as written; only the reading collapses them.
    assert len(_messages(table, "student")) == 2


def test_the_model_is_asked_the_question_sent_again_once(table, model) -> None:
    _resend_after_a_failure(table, model)

    turns = model.calls[-1]["messages"]
    assert len(turns) == 1
    assert turns[0]["content"].count(QUESTION) == 1


def test_a_different_question_after_a_failure_is_kept(table, model) -> None:
    model.outcomes = [BROKEN_REPLY]
    client = _client()
    assert _send(client, "initial-1").status_code == 409  # message_failed (#412)

    assert _send(client, "next-1", content="Und wie erweitere ich?").status_code == 200

    students = [m.content for m in learning_session.history(CONV) if m.role == "student"]
    assert students == [QUESTION, "Und wie erweitere ich?"]
    assert len(_messages(table, "student")) == 2


def test_the_same_question_asked_again_after_an_answer_is_kept(table, model) -> None:
    client = _client()
    assert _send(client, "key-1").status_code == 200

    assert _send(client, "key-2").status_code == 200

    roles = [message.role for message in learning_session.history(CONV)]
    assert roles == ["student", "assistant", "student", "assistant"]
