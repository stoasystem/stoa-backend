"""An Ask answer's knowledge points are picked from the student's star map (#142).

The model is shown every star on the student's map, in every subject, as fenced
data in the student's turn. A knowledge point it picks from that list carries
the star's unit id; anything it names that is not on the list - an id it made
up, a real unit id it was never shown - is free text. Free text is what the
knowledge base lacks, so each one is counted, with its subject, once for each
new question; a follow-up counts nothing.

These run the real routes, worker, prompt builder and repository against the
shared table double. Only the Bedrock provider, the Lambda invoke and the two
reads the map is made of (the catalog and the student's mastery) are replaced.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any, Callable

import pytest

from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import (
    curriculum_service,
    knowledge_mastery_service,
    star_map_candidates,
)
from test_async_generation_cutover import invokes as invokes  # noqa: F401 - the fixture
from test_async_generation_cutover import switched_on as switched_on  # noqa: F401
from test_conversation_token_finalization import _patch_allowance_table
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    QUESTION,
    _client,
    _events,
    _send,
)
from test_message_command_generation import _no_memory_personalisation  # noqa: F401
from test_message_command_generation import table as table  # noqa: F401 - the fixture
from test_token_allowances import AtomicAllowanceTable

_READ_THE_MAP = star_map_candidates.for_student

LOCALES = ("de", "en", "fr", "it")

# The catalog as `curriculum_service.list_catalog` builds it, one title per
# language. `ohne-lektion` has no active lesson, so the map does not draw it.
TITLES: dict[str, dict[str, str]] = {
    "brueche-kuerzen": {
        "de": "Brüche kürzen",
        "en": "Simplifying fractions",
        "fr": "Simplifier des fractions",
        "it": "Semplificare le frazioni",
    },
    "teiler-vielfache": {
        "de": "Teiler und Vielfache",
        "en": "Divisors and multiples",
        "fr": "Diviseurs et multiples",
        "it": "Divisori e multipli",
    },
    "kraefte": {
        "de": "Kräfte und Bewegung",
        "en": "Forces and motion",
        "fr": "Forces et mouvement",
        "it": "Forze e moto",
    },
    "ohne-lektion": {
        "de": "Noch ohne Lektion",
        "en": "No lesson yet",
        "fr": "Pas encore de leçon",
        "it": "Ancora senza lezione",
    },
}
STATES = {
    "brueche-kuerzen": knowledge_mastery_service.LearningState.LIT,
    "teiler-vielfache": knowledge_mastery_service.LearningState.IN_PROGRESS,
    "kraefte": knowledge_mastery_service.LearningState.READY,
    "ohne-lektion": knowledge_mastery_service.LearningState.READY,
}
SUBJECT_OF = {
    "brueche-kuerzen": ("math", "brueche"),
    "teiler-vielfache": ("math", "brueche"),
    "kraefte": ("physics", "mechanik"),
    "ohne-lektion": ("math", "brueche"),
}

TOPICS: dict[str, dict[str, str]] = {
    "brueche": {"de": "Brüche", "en": "Fractions", "fr": "Fractions", "it": "Frazioni"},
    "mechanik": {"de": "Mechanik", "en": "Mechanics", "fr": "Mécanique", "it": "Meccanica"},
}

# What the model writes on its own, in the language of the answer.
FREE: dict[str, str] = {
    "de": "Brüche im Alltag",
    "en": "Fractions in everyday life",
    "fr": "Les fractions au quotidien",
    "it": "Le frazioni nella vita quotidiana",
}


def _catalog(*, locale: str = "de", **_kwargs: Any) -> dict[str, Any]:
    return {
        "subjects": [{"id": "math", "order": 1}, {"id": "physics", "order": 2}],
        "topics": [
            {"id": "brueche", "subjectId": "math", "title": TOPICS["brueche"][locale], "order": 1},
            {"id": "mechanik", "subjectId": "physics", "title": TOPICS["mechanik"][locale], "order": 1},
        ],
        "units": [
            {
                "id": unit_id,
                "subjectId": SUBJECT_OF[unit_id][0],
                "topicId": SUBJECT_OF[unit_id][1],
                "title": titles[locale],
                "order": order,
            }
            for order, (unit_id, titles) in enumerate(TITLES.items(), start=1)
        ],
        "lessons": [],
    }


def _states(student_id: str, **_kwargs: Any) -> dict[str, knowledge_mastery_service.UnitMastery]:
    return {
        unit_id: knowledge_mastery_service.UnitMastery(
            unit_id=unit_id,
            topic_id=SUBJECT_OF[unit_id][1],
            subject_id=SUBJECT_OF[unit_id][0],
            state=state,
            progress=0.0,
            unmet_exercises=0,
            lesson_count=0 if unit_id == "ohne-lektion" else 1,
            lessons_done=0,
            next_lesson=None,
        )
        for unit_id, state in STATES.items()
    }


@pytest.fixture
def star_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """The map as its two reads would return it for this student."""
    monkeypatch.setattr(star_map_candidates, "for_student", _READ_THE_MAP)
    monkeypatch.setattr(curriculum_service, "list_catalog", _catalog)
    monkeypatch.setattr(knowledge_mastery_service, "unit_states", _states)


# ── The provider ─────────────────────────────────────────────────────────────


def _student_turn(body: dict[str, Any]) -> str:
    return str([turn for turn in body["messages"] if turn["role"] == "user"][-1]["content"])


def _shown_stars(body: dict[str, Any]) -> dict[str, str]:
    """The stars the model was shown, by name, as `ref` - read the way a model would."""
    turn = _student_turn(body)
    match = re.search(r"<(star_map-[0-9a-f]+)>\n(.*?)\n</\1>", turn, re.DOTALL)
    if match is None:
        return {}
    stars = {}
    for line in match.group(2).splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 3:
            stars[parts[1]] = parts[0]
    return stars


Answer = Callable[[dict[str, Any]], dict[str, Any]]


class _Bedrock:
    """The Bedrock runtime as boto3 hands it out; each answer is written from the request."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.answers: list[Answer] = []

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        return {"inputTokens": 90, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c"}}

    def _answer(self, body: str) -> str:
        request = json.loads(body)
        self.bodies.append(request)
        return json.dumps(self.answers.pop(0)(request), ensure_ascii=False)

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        payload = {
            "id": "msg_test_1",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": self._answer(body)}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return {"ResponseMetadata": {"RequestId": "r"}, "body": io.BytesIO(json.dumps(payload).encode())}

    def invoke_model_with_response_stream(self, *, modelId: str, body: str):  # noqa: N803
        text = self._answer(body)
        events = [
            {"type": "message_start", "message": {
                "id": "msg_test_1", "model": modelId, "usage": {"input_tokens": 70},
            }},
            {"type": "content_block_delta", "delta": {"text": text}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 25}},
        ]
        return {
            "ResponseMetadata": {"RequestId": "r"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }


@pytest.fixture
def bedrock(table, monkeypatch: pytest.MonkeyPatch) -> _Bedrock:
    provider = _Bedrock()
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    monkeypatch.setattr(conversations.ai_service.boto3, "client", lambda *_a, **_k: provider)
    return provider


def _answer(points: Callable[[dict[str, str]], list[Any]]) -> Answer:
    """A new question's answer, naming `points(stars shown)` as its knowledge points."""

    def write(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "steps": ["Zähler und Nenner durch den ggT teilen", "Das Ergebnis prüfen"],
            "answer": "So kürzt man einen Bruch.",
            "hints": ["Was ist der ggT von 6 und 8?"],
            "similar_exercises": ["Kürze 9/12."],
            "knowledge_points": points(_shown_stars(request)),
            "suggest_teacher": False,
        }

    return write


def _follow_up(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "steps": [],
        "answer": "Der ggT ist die grösste Zahl, die beide teilt.",
        "hints": [],
        "similar_exercises": [],
        "knowledge_points": [],
        "suggest_teacher": False,
    }


def _done(response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    [done] = [data for name, data in _events(response) if name == "message_done"]
    return done


def _read_back(client) -> list[dict[str, Any]]:
    response = client.get(f"/conversations/{CONV}")
    assert response.status_code == 200, response.text
    return [message for message in response.json()["messages"] if message["role"] == "assistant"]


def _gaps(table) -> dict[tuple[str, str], int]:
    """The free-text knowledge points recorded for the knowledge-base gap list."""
    return {
        (row["subject"], row["name"]): int(row["count"])
        for row in table.rows.values()
        if row.get("entity_type") == "knowledge_gap"
    }


# ── What the model is shown ──────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_the_model_is_shown_every_star_on_the_student_s_map(
    table, bedrock, star_map, locale
) -> None:
    bedrock.answers = [_answer(lambda _stars: [])]

    _done(_send(_client(), "key-1", language=locale))

    [body] = bedrock.bodies
    shown = _shown_stars(body)
    # Every drawn star, in every subject, named in the answer's language.
    assert set(shown) == {
        TITLES["brueche-kuerzen"][locale],
        TITLES["teiler-vielfache"][locale],
        TITLES["kraefte"][locale],
    }
    turn = _student_turn(body)
    assert f"{TITLES['brueche-kuerzen'][locale]} | lit" in turn
    assert f"{TITLES['teiler-vielfache'][locale]} | in_progress" in turn
    # Fenced data in the student's turn, never the system prompt.
    assert TITLES["kraefte"][locale] not in body["system"]
    # The model answers with the short ref, never with the unit id itself.
    assert "brueche-kuerzen" not in turn


@pytest.mark.parametrize("locale", LOCALES)
def test_each_topic_heads_its_stars(table, bedrock, star_map, locale) -> None:
    """The topics are shown too, for #124 to name one the student asks about."""
    bedrock.answers = [_answer(lambda _stars: [])]

    _done(_send(_client(), "key-1", language=locale))

    turn = _student_turn(bedrock.bodies[0])
    fractions = turn.index(f"| {TOPICS['brueche'][locale]}\n")
    mechanics = turn.index(f"| {TOPICS['mechanik'][locale]}\n")
    assert turn.count(f"| {TOPICS['brueche'][locale]}\n") == 1
    assert fractions < turn.index(TITLES["brueche-kuerzen"][locale]) < mechanics
    assert mechanics < turn.index(TITLES["kraefte"][locale])


def test_the_model_is_told_to_pick_from_the_map_before_writing_its_own(
    table, bedrock, star_map
) -> None:
    bedrock.answers = [_answer(lambda _stars: [])]

    _done(_send(_client(), "key-1", language="de"))

    system = bedrock.bodies[0]["system"]
    assert "star map" in system
    assert '{"id":"k1","name":"..."}' in system
    assert '{"id":null,"name":"..."}' in system


# ── Picked, forged and free ──────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_a_point_picked_from_the_map_carries_its_unit_id(
    table, bedrock, star_map, locale
) -> None:
    name = TITLES["kraefte"][locale]
    bedrock.answers = [
        _answer(lambda stars: [{"id": stars[name], "name": name}, {"id": None, "name": FREE[locale]}])
    ]
    client = _client()

    streamed = _done(_send(client, "key-1", language=locale))["structured"]["knowledgePoints"]

    expected = [{"name": name, "unitId": "kraefte"}, {"name": FREE[locale], "unitId": None}]
    assert streamed == expected
    [assistant] = _read_back(client)
    assert assistant["structured"]["knowledgePoints"] == expected


def test_the_star_s_own_name_is_kept_whatever_the_model_called_it(
    table, bedrock, star_map
) -> None:
    bedrock.answers = [
        _answer(lambda stars: [{"id": stars["Brüche kürzen"], "name": "Kürzen"}])
    ]

    points = _done(_send(_client(), "key-1", language="de"))["structured"]["knowledgePoints"]

    assert points == [{"name": "Brüche kürzen", "unitId": "brueche-kuerzen"}]


@pytest.mark.parametrize(
    "forged",
    [
        "k99",  # a ref the model was never shown
        "brueche-kuerzen",  # a real unit id, but the model is shown refs only
        "ohne-lektion",  # a unit the map does not draw
        7,  # not even text
    ],
)
def test_an_id_the_model_was_not_shown_is_free_text(table, bedrock, star_map, forged) -> None:
    bedrock.answers = [_answer(lambda _stars: [{"id": forged, "name": "Erfundener Punkt"}])]

    points = _done(_send(_client(), "key-1", language="de"))["structured"]["knowledgePoints"]

    assert points == [{"name": "Erfundener Punkt", "unitId": None}]
    assert _gaps(table) == {("math", "Erfundener Punkt"): 1}


def test_a_point_written_as_plain_text_is_free_text(table, bedrock, star_map) -> None:
    bedrock.answers = [_answer(lambda _stars: ["Brüche im Alltag"])]

    points = _done(_send(_client(), "key-1", language="de"))["structured"]["knowledgePoints"]

    assert points == [{"name": "Brüche im Alltag", "unitId": None}]


# ── What is recorded ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_free_text_is_recorded_with_its_subject_and_counted(
    table, bedrock, star_map, locale
) -> None:
    picked = TITLES["brueche-kuerzen"][locale]
    free = FREE[locale]
    bedrock.answers = [
        _answer(lambda stars: [{"id": stars[picked], "name": picked}, {"id": None, "name": free}]),
        # The same point, written a little differently, for the next question.
        _answer(lambda _stars: [{"id": None, "name": f"  {free.upper()} "}]),
    ]
    client = _client()

    _done(_send(client, "key-1", language=locale))
    assert _gaps(table) == {("math", free): 1}

    _done(_send(client, "key-2", language=locale, content="Und wie erweitere ich?"))
    # One record, counted twice, under the name it was first written as; the
    # point that was on the map is not a gap.
    assert _gaps(table) == {("math", free): 2}


def test_a_follow_up_records_nothing(table, bedrock, star_map) -> None:
    bedrock.answers = [_answer(lambda _stars: [{"id": None, "name": "Brüche im Alltag"}]), _follow_up]
    client = _client()
    _done(_send(client, "key-1", language="de"))

    done = _done(_send(client, "key-2", language="de", content="Was ist der ggT?"))

    assert done["structured"]["kind"] == "followUp"
    assert _gaps(table) == {("math", "Brüche im Alltag"): 1}


def test_a_question_about_a_step_records_nothing_even_if_the_model_names_points_again(
    table, bedrock, star_map
) -> None:
    """The "I don't get this step" follow-up: the model should answer in plain
    words, but one that repeats the earlier points must not count them twice."""
    repeated = _answer(lambda _stars: [{"id": None, "name": "Brüche im Alltag"}])
    bedrock.answers = [repeated, repeated]
    client = _client()
    first = _done(_send(client, "key-1", language="de"))

    response = client.post(
        f"/conversations/{CONV}/messages/stream",
        json={
            "content": "Diesen Schritt verstehe ich nicht.",
            "idempotencyKey": "key-2",
            "quote": {
                "text": "Zähler und Nenner durch den ggT teilen",
                "source": {
                    "kind": "message",
                    "id": first["messageId"],
                    "part": {"section": "steps", "index": 0},
                },
            },
        },
        headers={"Accept-Language": "de"},
    )

    _done(response)
    assert _gaps(table) == {("math", "Brüche im Alltag"): 1}


def test_the_same_question_sent_again_is_recorded_once(table, bedrock, star_map) -> None:
    bedrock.answers = [_answer(lambda _stars: [{"id": None, "name": "Brüche im Alltag"}])]
    client = _client()
    _done(_send(client, "key-1", language="de"))

    replayed = _done(_send(client, "key-1", language="de"))

    assert replayed["structured"]["knowledgePoints"] == [
        {"name": "Brüche im Alltag", "unitId": None}
    ]
    assert len(bedrock.bodies) == 1
    assert _gaps(table) == {("math", "Brüche im Alltag"): 1}


def test_the_worker_s_answer_after_a_202_is_checked_and_recorded_once(
    table, bedrock, star_map, invokes, switched_on
) -> None:
    bedrock.answers = [
        _answer(
            lambda stars: [
                {"id": stars["Teiler und Vielfache"], "name": "Teiler und Vielfache"},
                {"id": "k99", "name": "Brüche im Alltag"},
            ]
        )
    ]
    client = _client()
    assert _send(client, "key-1", language="de").status_code == 202

    assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "completed"}
    # Delivered again, the command is already answered and settles as it is.
    assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "settled"}

    [assistant] = _read_back(client)
    assert assistant["structured"]["knowledgePoints"] == [
        {"name": "Teiler und Vielfache", "unitId": "teiler-vielfache"},
        {"name": "Brüche im Alltag", "unitId": None},
    ]
    assert _gaps(table) == {("math", "Brüche im Alltag"): 1}


class _Killed(BaseException):
    """The Lambda stopped here: nothing after this line ran."""


def test_an_attempt_that_dies_before_storing_its_answer_counts_nothing(
    table, bedrock, star_map, invokes, switched_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer counts when it is stored, by the attempt that stores it."""
    bedrock.answers = [_answer(lambda _stars: [{"id": None, "name": "Brüche im Alltag"}])]
    client = _client()
    assert _send(client, "key-1", language="de").status_code == 202
    complete = conversations.attachment_repo.complete_message_command
    calls = {"complete": 0}

    def die_on_first_completion(**kwargs: Any) -> Any:
        calls["complete"] += 1
        if calls["complete"] == 1:
            raise _Killed()
        return complete(**kwargs)

    monkeypatch.setattr(
        conversations.attachment_repo, "complete_message_command", die_on_first_completion
    )
    with pytest.raises(_Killed):
        conversation_generation.handler(invokes.events[0], None)
    row = dict(table.rows[tuple(conversations.attachment_repo.message_command_key(CONV, "key-1").values())])
    row["expiresAt"] = 1
    table.seed(row)

    assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "completed"}

    # The kept answer was finished without asking the model again.
    assert len(bedrock.bodies) == 1
    assert _gaps(table) == {("math", "Brüche im Alltag"): 1}


def test_the_student_is_not_named_on_the_record(table, bedrock, star_map) -> None:
    bedrock.answers = [_answer(lambda _stars: [{"id": None, "name": "Brüche im Alltag"}])]

    _done(_send(_client(), "key-1", language="de"))

    [row] = [row for row in table.rows.values() if row.get("entity_type") == "knowledge_gap"]
    assert "student-1" not in json.dumps(row, default=str)
    assert QUESTION not in json.dumps(row, default=str)


def test_without_the_map_nothing_is_taken_for_a_gap(
    table, bedrock, star_map, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(curriculum_service, "list_catalog", unreadable)
    bedrock.answers = [_answer(lambda _stars: [{"id": "k1", "name": "Brüche kürzen"}])]

    done = _done(_send(_client(), "key-1", language="de"))

    assert _shown_stars(bedrock.bodies[0]) == {}
    # Nor is the model asked to pick from a map it was not shown.
    assert "star map" not in bedrock.bodies[0]["system"]
    assert done["structured"]["knowledgePoints"] == [{"name": "Brüche kürzen", "unitId": None}]
    # It may well be on the map: the model just could not see it.
    assert _gaps(table) == {}
