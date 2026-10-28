"""An Ask answer is kept in the sections the model wrote it in (#132).

The model answers with steps, an answer, hints, similar exercises, knowledge
points and whether the student should see a teacher. The joined text is still
stored as the fallback every text-only reader uses; beside it the assistant
message carries the sections as the model wrote them, the same on every path a
client reads an answer by: the streamed `message_done`, the plain send route,
the worker's answer after a 202, and `GET /conversations/{id}`.

A quote may also name one section of an earlier answer (a step, a hint), and
the model is told which one.

These run the real routes, worker and repository against the shared table
double; only the model call and the Lambda invoke are replaced.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import ai_service
from test_async_generation_cutover import invokes as invokes  # noqa: F401 - the fixture
from test_async_generation_cutover import switched_on as switched_on  # noqa: F401
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    QUESTION,
    STUDENT,
    _client,
    _events,
    _messages,
    _send,
)
from test_message_command_generation import _no_memory_personalisation  # noqa: F401
from test_message_command_generation import model as model  # noqa: F401 - the fixture
from test_message_command_generation import table as table  # noqa: F401 - the fixture

# One answer per language the platform speaks, as the model writes it, with
# the hint label the joined text puts in front of the first hint.
ANSWERS: dict[str, tuple[dict[str, Any], str]] = {
    "de": (
        {
            "steps": ["Zähler und Nenner durch den ggT teilen", "Das Ergebnis prüfen"],
            "answer": "So kürzt man einen Bruch.",
            "hints": ["Was ist der ggT von 6 und 8?", "Beide Zahlen sind gerade."],
            "similar_exercises": ["Kürze 9/12."],
            "knowledge_points": ["Brüche kürzen", "Grösster gemeinsamer Teiler"],
            "suggest_teacher": True,
        },
        "Hinweis",
    ),
    "en": (
        {
            "steps": ["Divide top and bottom by the GCD", "Check the result"],
            "answer": "That is how you simplify a fraction.",
            "hints": ["What is the GCD of 6 and 8?", "Both numbers are even."],
            "similar_exercises": ["Simplify 9/12."],
            "knowledge_points": ["Simplifying fractions", "Greatest common divisor"],
            "suggest_teacher": True,
        },
        "Hint",
    ),
    "fr": (
        {
            "steps": ["Diviser le numérateur et le dénominateur par le PGCD", "Vérifier"],
            "answer": "Voilà comment on simplifie une fraction.",
            "hints": ["Quel est le PGCD de 6 et 8 ?", "Les deux nombres sont pairs."],
            "similar_exercises": ["Simplifie 9/12."],
            "knowledge_points": ["Simplifier des fractions", "Plus grand commun diviseur"],
            "suggest_teacher": True,
        },
        "Indice",
    ),
    "it": (
        {
            "steps": ["Dividere numeratore e denominatore per il MCD", "Controllare"],
            "answer": "Così si semplifica una frazione.",
            "hints": ["Qual è il MCD di 6 e 8?", "Entrambi i numeri sono pari."],
            "similar_exercises": ["Semplifica 9/12."],
            "knowledge_points": ["Semplificare le frazioni", "Massimo comun divisore"],
            "suggest_teacher": True,
        },
        "Indizio",
    ),
}

LOCALES = sorted(ANSWERS)


def _expected(answer: dict[str, Any]) -> dict[str, Any]:
    """The sections as the API hands them on: the model's, under the API's names."""
    return {
        "kind": "answer",
        "steps": answer["steps"],
        "answer": answer["answer"],
        "hints": answer["hints"],
        "similarExercises": answer["similar_exercises"],
        "knowledgePoints": [
            {"name": name, "unitId": None} for name in answer["knowledge_points"]
        ],
        "suggestTeacher": answer["suggest_teacher"],
    }


def _done(response) -> dict[str, Any]:
    [done] = [data for name, data in _events(response) if name == "message_done"]
    return done


def _read_back(client) -> list[dict[str, Any]]:
    response = client.get(f"/conversations/{CONV}")
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def _assistant(messages: list[dict[str, Any]]) -> dict[str, Any]:
    [assistant] = [message for message in messages if message["role"] == "assistant"]
    return assistant


# ── Every path hands on the same sections, in every language ─────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_the_streamed_answer_ends_with_every_section(table, model, locale) -> None:
    answer, label = ANSWERS[locale]
    model.outcomes = [answer]

    response = _send(_client(), "key-1", language=locale)

    assert response.status_code == 200, response.text
    assert _done(response)["structured"] == _expected(answer)
    # The joined text is unchanged: steps, answer, the first hint and its label.
    streamed = "".join(data["delta"] for name, data in _events(response) if name == "message_delta")
    assert f"**{label}:** {answer['hints'][0]}" in streamed
    assert answer["hints"][1] not in streamed


@pytest.mark.parametrize("locale", LOCALES)
def test_the_answer_reads_back_with_the_sections_it_streamed(table, model, locale) -> None:
    answer, label = ANSWERS[locale]
    model.outcomes = [answer]
    client = _client()

    streamed = _done(_send(client, "key-1", language=locale))["structured"]

    assistant = _assistant(_read_back(client))
    assert assistant["structured"] == streamed == _expected(answer)
    assert f"**{label}:** {answer['hints'][0]}" in assistant["content"]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_plain_send_route_returns_the_sections(table, model, locale) -> None:
    answer, _label = ANSWERS[locale]
    model.outcomes = [answer]

    response = _client().post(
        f"/conversations/{CONV}/messages",
        json={"content": QUESTION, "idempotencyKey": "key-1"},
        headers={"Accept-Language": locale},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assistantMessage"]["structured"] == _expected(answer)
    assert body["studentMessage"]["structured"] is None


@pytest.mark.parametrize("locale", LOCALES)
def test_the_worker_s_answer_after_a_202_carries_the_same_sections(
    table, model, invokes, switched_on, locale
) -> None:
    answer, _label = ANSWERS[locale]
    model.outcomes = [answer]
    client = _client()
    assert _send(client, "key-1", language=locale).status_code == 202

    assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "completed"}

    assert _assistant(_read_back(client))["structured"] == _expected(answer)
    # The same key sent again replays the stored answer, sections and all.
    replayed = _send(client, "key-1", language=locale)
    assert replayed.status_code == 200
    assert _done(replayed)["structured"] == _expected(answer)
    assert len(model.calls) == 1


def test_an_answer_stored_before_sections_existed_reads_back_with_none(table, model) -> None:
    client = _client()
    _send(client, "key-1", language="de")
    # The row an answer was stored as before #132: the same, without sections.
    [stored] = _messages(table, "assistant")
    old = {key: value for key, value in stored.items() if key != "structured"}
    table.seed(old)

    assistant = _assistant(_read_back(client))

    assert assistant["structured"] is None
    assert assistant["content"] == old["content"]


# ── What the sections say ────────────────────────────────────────────────────


def test_an_answer_that_does_not_suggest_a_teacher_says_so(table, model) -> None:
    answer = dict(ANSWERS["de"][0])
    del answer["suggest_teacher"]
    model.outcomes = [answer]

    response = _send(_client(), "key-1", language="de")

    assert _done(response)["structured"]["suggestTeacher"] is False


def test_only_a_true_suggestion_counts_as_one(table, model) -> None:
    model.outcomes = [{**ANSWERS["de"][0], "suggest_teacher": "yes"}]

    response = _send(_client(), "key-1", language="de")

    assert _done(response)["structured"]["suggestTeacher"] is False


def test_a_follow_up_answered_in_plain_words_reads_as_a_follow_up(table, model) -> None:
    model.outcomes = [
        {
            "steps": [],
            "answer": "Der ggT ist die grösste Zahl, die beide teilt.",
            "hints": [],
            "similar_exercises": [],
            "knowledge_points": [],
            "suggest_teacher": True,
        }
    ]
    client = _client()

    response = _send(client, "key-1", language="de")

    structured = _done(response)["structured"]
    assert structured["kind"] == "followUp"
    assert structured["answer"] == "Der ggT ist die grösste Zahl, die beide teilt."
    assert structured["suggestTeacher"] is True
    assert _assistant(_read_back(client))["content"] == (
        "Der ggT ist die grösste Zahl, die beide teilt."
    )


def test_a_section_of_the_wrong_shape_is_left_out_not_failed(table, model) -> None:
    model.outcomes = [
        {
            **ANSWERS["de"][0],
            "similar_exercises": "Kürze 9/12.",
            "knowledge_points": [7, "Brüche kürzen", {"name": "x"}],
        }
    ]

    response = _send(_client(), "key-1", language="de")

    assert response.status_code == 200
    structured = _done(response)["structured"]
    assert structured["similarExercises"] == []
    assert structured["knowledgePoints"] == [{"name": "Brüche kürzen", "unitId": None}]


# ── A quote can name one section of an earlier answer ────────────────────────


def _quoted(part: dict[str, Any] | None, *, kind: str = "message") -> dict[str, Any]:
    source: dict[str, Any] = {"kind": kind, "id": "m-1"}
    if part is not None:
        source["part"] = part
    return {
        "content": "Diesen Schritt verstehe ich nicht.",
        "idempotencyKey": "key-q",
        "quote": {"text": "Durch den ggT", "source": source},
    }


def test_a_quote_naming_a_step_reaches_the_model_and_reads_back(table, model) -> None:
    client = _client()

    response = client.post(
        f"/conversations/{CONV}/messages/stream",
        json=_quoted({"section": "steps", "index": 1}),
        headers={"Accept-Language": "de"},
    )

    assert response.status_code == 200, response.text
    assert model.calls[0]["quote"]["source"]["part"] == {"section": "steps", "index": 1}
    [student] = [message for message in _read_back(client) if message["role"] == "student"]
    assert student["quote"]["source"]["part"] == {"section": "steps", "index": 1}


def test_a_quote_without_a_part_reaches_the_model_as_it_did(table, model) -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages/stream",
        json=_quoted(None),
        headers={"Accept-Language": "de"},
    )

    assert response.status_code == 200, response.text
    assert model.calls[0]["quote"] == {
        "text": "Durch den ggT",
        "source": {"kind": "message", "id": "m-1"},
    }


@pytest.mark.parametrize(
    "part",
    [
        {"section": "answer", "index": 0},
        {"section": "steps"},
        {"section": "hints", "index": -1},
        {"section": "summary", "index": 0},
        {"section": "steps", "index": 0, "text": "smuggled"},
    ],
)
def test_a_part_that_names_no_section_is_refused(table, model, part) -> None:
    response = _client().post(f"/conversations/{CONV}/messages/stream", json=_quoted(part))

    assert response.status_code == 422
    assert model.calls == []


def test_a_part_is_refused_on_a_quote_from_an_exercise(table, model) -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages/stream",
        json=_quoted({"section": "steps", "index": 0}, kind="challenge"),
    )

    assert response.status_code == 422
    assert model.calls == []


def test_the_whole_answer_can_be_quoted_as_a_part_without_an_index(table, model) -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages/stream", json=_quoted({"section": "answer"})
    )

    assert response.status_code == 200, response.text
    assert model.calls[0]["quote"]["source"]["part"] == {"section": "answer"}


def test_a_quote_without_a_part_keeps_its_exact_fingerprint() -> None:
    """Taken before parts existed, so a quoted command in flight over a deploy replays."""
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "warum?",
            "idempotencyKey": "compat-key-2",
            "quote": {"text": "Durch den ggT", "source": {"kind": "message", "id": "m-1"}},
        }
    )
    assert (
        conversations.message_request_fingerprint(body)
        == "cc7cd7e3f3dd51bdbeec2c1c238811a52153121c890d2c2f71e969bc3d85aba1"
    )


def test_the_fingerprint_tells_two_parts_apart() -> None:
    def fingerprint(part: dict[str, Any] | None) -> str:
        return conversations.message_request_fingerprint(
            conversations.SendMessageRequest.model_validate(_quoted(part))
        )

    assert len(
        {
            fingerprint(None),
            fingerprint({"section": "steps", "index": 0}),
            fingerprint({"section": "steps", "index": 1}),
            fingerprint({"section": "hints", "index": 0}),
            fingerprint({"section": "answer"}),
        }
    ) == 5


# ── What the model is told ───────────────────────────────────────────────────


class _CapturingBedrockClient:
    def __init__(self) -> None:
        self.request_body: dict | None = None

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        self.request_body = json.loads(body)
        payload = {
            "id": "msg_test_1",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": json.dumps(ANSWERS["de"][0])}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return {
            "ResponseMetadata": {"RequestId": "req-test-1"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }


def _sent(quote: dict[str, Any]) -> dict[str, Any]:
    client = _CapturingBedrockClient()
    ai_service.get_ai_answer(
        content="Diesen Schritt verstehe ich nicht.",
        subject="math",
        grade="Sek1",
        quote=quote,
        client=client,
        effect_id="effect-test-1",
    )
    assert client.request_body is not None
    return client.request_body


def _student_turn(body: dict[str, Any]) -> str:
    return str([turn for turn in body["messages"] if turn["role"] == "user"][-1]["content"])


@pytest.mark.parametrize(
    ("part", "named"),
    [
        ({"section": "steps", "index": 1}, 'part="step 2"'),
        ({"section": "hints", "index": 0}, 'part="hint 1"'),
        ({"section": "similarExercises", "index": 2}, 'part="similar exercise 3"'),
        ({"section": "knowledgePoints", "index": 0}, 'part="knowledge point 1"'),
        ({"section": "answer"}, 'part="answer"'),
    ],
)
def test_the_model_is_told_which_part_of_its_answer_is_quoted(part, named) -> None:
    body = _sent({"text": "Durch den ggT", "source": {"kind": "message", "id": "m-1", "part": part}})

    turn = _student_turn(body)
    assert named in turn
    assert named not in body["system"]


def test_a_quote_without_a_part_names_none() -> None:
    body = _sent({"text": "Durch den ggT", "source": {"kind": "message", "id": "m-1"}})

    assert "part=" not in _student_turn(body)


def test_the_model_is_told_a_follow_up_is_answered_in_plain_words() -> None:
    system = _sent({"text": "x", "source": {"kind": "message", "id": "m-1"}})["system"]

    assert "follows up on your earlier answer" in system
    assert "a new question" in system
