"""An Ask answer can name the star the student wants to go to (#124).

A student who says "I want to keep practising derivatives" in Ask gets a text
answer as usual; beside it the assistant message names the one unit on their
star map they meant, and the star map offers to fly there. The model picks it
from the stars it was shown (#142) by their short ref; the backend keeps it
only when it is one of them. When the student names a whole topic the backend
picks the star in it the way the map recommends one. Anything else, a concept
question, an open-ended wish or a ref that is not on the list, leaves the
target empty.

The target is kept on the message, so every path a client reads an answer by
hands it on: the streamed `message_done`, the plain send route, the worker's
answer after a 202 and `GET /conversations/{id}`.

These run the real routes, worker and repository against the shared table
double; the model call, the Lambda invoke and the two reads the map is made of
(the catalog and the student's mastery) are replaced.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import curriculum_service, knowledge_mastery_service, star_map_candidates
from test_async_generation_cutover import invokes as invokes  # noqa: F401 - the fixture
from test_async_generation_cutover import switched_on as switched_on  # noqa: F401
from test_conversation_structured_answers import (
    ANSWERS,
    _assistant,
    _CapturingBedrockClient,
    _done,
    _read_back,
    _student_turn,
)
from test_conversation_token_finalization import _patch_allowance_table
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    STUDENT,
    _client,
    _messages,
    _send,
)
from test_message_command_generation import _no_memory_personalisation  # noqa: F401
from test_message_command_generation import model as model  # noqa: F401 - the fixture
from test_message_command_generation import table as table  # noqa: F401 - the fixture
from test_phase475_question_effect_recovery import EffectRecoveryTable
from test_phase475_question_effect_recovery import _client as _question_client
from test_phase475_question_effect_recovery import _request as _question
from test_question_token_finalization import MockBedrockProvider, _patch_allowance_runtime
from test_token_allowances import AtomicAllowanceTable

_READ_THE_MAP = star_map_candidates.for_student
_State = knowledge_mastery_service.LearningState

WANT_TO_PRACTISE = "我想继续练导数"

# The student's sky across two subjects. Physics is a subject they are not
# enrolled in, drawn dimmed; its stars are still theirs to name.
TOPICS = {
    "brueche": ("mathematics", "Brüche", 1),
    "funktionen": ("mathematics", "Funktionen", 2),
    "zahlen": ("mathematics", "Zahlen", 3),
    "optik": ("physics", "Optik", 1),
}
STARS = {
    "brueche-kuerzen": ("brueche", "Brüche kürzen", _State.LIT),
    "brueche-addieren": ("brueche", "Brüche addieren", _State.READY),
    "brueche-dividieren": ("brueche", "Brüche dividieren", _State.IN_PROGRESS),
    "funktionen-linear": ("funktionen", "Lineare Funktionen", _State.LOCKED),
    "funktionen-ableitung": ("funktionen", "Ableitungen", _State.READY),
    "funktionen-quadratisch": ("funktionen", "Quadratische Funktionen", _State.READY),
    "zahlen-teilbarkeit": ("zahlen", "Teilbarkeit", _State.LIT),
    "optik-licht": ("optik", "Licht und Schatten", _State.READY),
}


def _catalog(**_kwargs: Any) -> dict[str, Any]:
    return {
        "subjects": [{"id": "mathematics", "order": 1}, {"id": "physics", "order": 2}],
        "topics": [
            {"id": topic_id, "subjectId": subject, "title": title, "order": order}
            for topic_id, (subject, title, order) in TOPICS.items()
        ],
        "units": [
            {
                "id": unit_id,
                "subjectId": TOPICS[topic_id][0],
                "topicId": topic_id,
                "title": title,
                "order": order,
            }
            for order, (unit_id, (topic_id, title, _state)) in enumerate(STARS.items(), start=1)
        ],
        "lessons": [],
    }


def _states(student_id: str, **_kwargs: Any) -> dict[str, knowledge_mastery_service.UnitMastery]:
    return {
        unit_id: knowledge_mastery_service.UnitMastery(
            unit_id=unit_id,
            topic_id=topic_id,
            subject_id=TOPICS[topic_id][0],
            state=state,
            progress=0.0,
            unmet_exercises=0,
            lesson_count=1,
            lessons_done=0,
            next_lesson=None,
        )
        for unit_id, (topic_id, _title, state) in STARS.items()
    }


@pytest.fixture(autouse=True)
def sky(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The student's map as its two reads return it; records whose map was read."""
    asked: list[str] = []

    def states(student_id: str, **kwargs: Any) -> dict[str, Any]:
        asked.append(student_id)
        return _states(student_id, **kwargs)

    monkeypatch.setattr(star_map_candidates, "for_student", _READ_THE_MAP)
    # The catalog is cached per language; a cache left by another test is not this map.
    monkeypatch.setattr(star_map_candidates, "_content", {})
    monkeypatch.setattr(curriculum_service, "list_catalog", _catalog)
    monkeypatch.setattr(knowledge_mastery_service, "indexed_lessons", lambda: {})
    monkeypatch.setattr(knowledge_mastery_service, "unit_states", states)
    return asked


def _shown() -> list[star_map_candidates.Candidate]:
    return star_map_candidates.from_catalog(_catalog(), _states(STUDENT))


def _ref(unit_id: str) -> str:
    """The ref the model is shown a star under."""
    [ref] = [star["ref"] for star in _shown() if star["unitId"] == unit_id]
    return ref


def _topic_ref(topic_id: str) -> str:
    return star_map_candidates.topic_refs(_shown())[topic_id]


def _answer(target: object = None, **changes: Any) -> dict[str, Any]:
    """A short reply in plain words, with the target the model named."""
    answer: dict[str, Any] = {
        "steps": [],
        "answer": "Gute Idee, die Ableitungen warten auf dich.",
        "hints": [],
        "similar_exercises": [],
        "knowledge_points": [],
        "suggest_teacher": False,
        **changes,
    }
    if target is not None:
        answer["target_unit_id"] = target
    return answer


def _target(response) -> object:
    return _done(response)["targetUnit"]


# ── Which target is kept ─────────────────────────────────────────────────────


def test_a_star_on_the_student_s_map_is_kept_and_reads_back(table, model) -> None:
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]
    client = _client()

    response = _send(client, "key-1", language="de", content=WANT_TO_PRACTISE)

    assert response.status_code == 200, response.text
    assert _target(response) == {"unitId": "funktionen-ableitung"}
    assert _assistant(_read_back(client))["targetUnit"] == {"unitId": "funktionen-ableitung"}
    # It was named out of the list the model was shown.
    assert model.calls[0]["star_map"] == _shown()


@pytest.mark.parametrize(
    "named",
    [
        "k99",
        "t99",
        # A real unit id names nothing: the model was shown refs, never ids.
        "funktionen-ableitung",
        "",
        7,
        {"id": "k5"},
    ],
)
def test_a_target_that_is_not_on_the_list_is_dropped(table, model, named) -> None:
    model.outcomes = [_answer(named)]
    client = _client()

    response = _send(client, "key-1", language="de", content=WANT_TO_PRACTISE)

    assert response.status_code == 200, response.text
    assert _target(response) is None
    assert _assistant(_read_back(client))["targetUnit"] is None
    # The answer itself is untouched.
    assert _done(response)["structured"]["answer"] == _answer()["answer"]


def test_an_answer_that_names_no_target_has_none(table, model) -> None:
    model.outcomes = [_answer()]
    client = _client()

    response = _send(client, "key-1", language="de", content="Was ist eine Ableitung?")

    assert _target(response) is None
    assert _assistant(_read_back(client))["targetUnit"] is None


def test_a_concept_question_answered_with_a_null_target_has_none(table, model) -> None:
    model.outcomes = [{**ANSWERS["de"][0], "target_unit_id": None}]

    response = _send(_client(), "key-1", language="de", content="Was ist eine Ableitung?")

    assert response.status_code == 200, response.text
    assert _target(response) is None


def test_a_lit_star_is_still_a_target(table, model) -> None:
    """"I want to review fractions": going back to a lit star is going somewhere."""
    model.outcomes = [_answer(_ref("brueche-kuerzen"))]

    assert _target(_send(_client(), "key-1", language="de")) == {"unitId": "brueche-kuerzen"}


def test_a_star_of_another_subject_is_a_target(table, model) -> None:
    """Named in a maths conversation, the physics star is still on the student's map."""
    model.outcomes = [_answer(_ref("optik-licht"))]

    assert _target(_send(_client(), "key-1", language="de")) == {"unitId": "optik-licht"}


# ── A topic is narrowed to one of its stars ──────────────────────────────────


def test_a_topic_goes_to_the_star_the_student_has_begun(table, model) -> None:
    """In progress beats a star not yet begun, even one earlier in the course."""
    model.outcomes = [_answer(_topic_ref("brueche"))]

    assert _target(_send(_client(), "key-1", language="de")) == {"unitId": "brueche-dividieren"}


def test_a_topic_with_nothing_begun_goes_to_its_first_reachable_star(table, model) -> None:
    """The first star in course order whose prerequisites are lit, not a locked one."""
    model.outcomes = [_answer(_topic_ref("funktionen"))]

    assert _target(_send(_client(), "key-1", language="de")) == {"unitId": "funktionen-ableitung"}


def test_a_topic_that_is_all_lit_has_no_target(table, model) -> None:
    model.outcomes = [_answer(_topic_ref("zahlen"))]

    assert _target(_send(_client(), "key-1", language="de")) is None


# ── Every read path hands it on ──────────────────────────────────────────────


def test_the_plain_send_route_returns_the_target(table, model) -> None:
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]

    response = _client().post(
        f"/conversations/{CONV}/messages",
        json={"content": WANT_TO_PRACTISE, "idempotencyKey": "key-1"},
        headers={"Accept-Language": "de"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assistantMessage"]["targetUnit"] == {"unitId": "funktionen-ableitung"}
    assert body["studentMessage"]["targetUnit"] is None


def test_the_worker_s_answer_after_a_202_carries_the_target(
    table, model, invokes, switched_on, sky
) -> None:
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]
    client = _client()
    assert _send(client, "key-1", language="de", content=WANT_TO_PRACTISE).status_code == 202

    assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "completed"}

    assert _assistant(_read_back(client))["targetUnit"] == {"unitId": "funktionen-ableitung"}
    # The same key sent again replays the stored answer, target and all.
    replayed = _send(client, "key-1", language="de", content=WANT_TO_PRACTISE)
    assert replayed.status_code == 200
    assert _target(replayed) == {"unitId": "funktionen-ableitung"}
    assert len(model.calls) == 1
    # The map read was the student's own.
    assert sky and set(sky) == {STUDENT}


def test_an_answer_stored_before_targets_existed_reads_back_with_none(table, model) -> None:
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]
    client = _client()
    _send(client, "key-1", language="de")
    [stored] = _messages(table, "assistant")
    table.seed({key: value for key, value in stored.items() if key != "target_unit_id"})

    assert _assistant(_read_back(client))["targetUnit"] is None


def test_an_unreadable_map_still_answers_without_a_target(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("table unavailable")

    monkeypatch.setattr(curriculum_service, "list_catalog", unreadable)
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]

    response = _send(_client(), "key-1", language="de", content=WANT_TO_PRACTISE)

    assert response.status_code == 200, response.text
    assert _target(response) is None
    assert _done(response)["structured"]["answer"] == _answer()["answer"]


# ── The production path, with only the provider stood in for ─────────────────


def test_the_target_comes_through_the_real_model_path(
    table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model is told the rule, and a Chinese wish reaches it beside the map."""
    provider = _CapturingBedrockClient(_answer(_ref("funktionen-ableitung")))
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    monkeypatch.setattr(conversations.ai_service.boto3, "client", lambda *_a, **_k: provider)
    client = _client()

    response = _send(client, "key-1", language="de", content=WANT_TO_PRACTISE)

    assert response.status_code == 200, response.text
    assert _target(response) == {"unitId": "funktionen-ableitung"}
    assert _assistant(_read_back(client))["targetUnit"] == {"unitId": "funktionen-ableitung"}
    assert provider.request_body is not None
    system = provider.request_body["system"]
    assert "Set it only when the student clearly wants" in system
    assert "for a question about a concept" in system
    assert "when the wish fits several" in system
    assert '"target_unit_id"' in system
    turn = _student_turn(provider.request_body)
    assert WANT_TO_PRACTISE in turn
    # The topic the model may name whole is shown under the ref it is checked by.
    assert f"## {_topic_ref('funktionen')} | Funktionen" in turn
    assert f"{_ref('funktionen-ableitung')} | Ableitungen | ready" in turn


# ── Where there is no map, there is no target ────────────────────────────────


def test_a_follow_up_on_an_earlier_answer_is_shown_no_map_and_has_no_target(
    table, model
) -> None:
    """A question about one step of an answer is not a wish to go anywhere."""
    client = _client()
    model.outcomes = [ANSWERS["de"][0]]
    assert _send(client, "key-a", language="de").status_code == 200
    answer_id = _assistant(_read_back(client))["id"]
    model.outcomes = [_answer(_ref("funktionen-ableitung"))]

    response = client.post(
        f"/conversations/{CONV}/messages/stream",
        json={
            "content": "Diesen Schritt verstehe ich nicht.",
            "idempotencyKey": "key-q",
            "quote": {
                "text": "Durch den ggT",
                "source": {"kind": "message", "id": answer_id, "part": {"section": "steps", "index": 0}},
            },
        },
        headers={"Accept-Language": "de"},
    )

    assert response.status_code == 200, response.text
    assert model.calls[1]["star_map"] is None
    assert _target(response) is None


class _QuestionProviderNamingATarget(MockBedrockProvider):
    """Answers the old question route with a target it was never asked for."""

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        response = super().invoke_model(**kwargs)
        payload = json.loads(response["body"].read())
        content = json.loads(payload["content"][0]["text"])
        content["target_unit_id"] = "k1"
        payload["content"][0]["text"] = json.dumps(content)
        response["body"] = type(response["body"])(payload)
        return response


def test_the_question_route_is_not_asked_for_a_target_and_survives_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old "submit a question" route shares the prompt but shows no map."""
    provider = _QuestionProviderNamingATarget()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=EffectRecoveryTable(),
        allowance_table=AtomicAllowanceTable(),
        provider=provider,
    )

    response = _question_client().post("/questions", json=_question())

    assert response.status_code == 201, response.text
    assert "target_unit_id" not in response.json()["ai_response"]
    [call] = provider.invoke_calls
    assert "target_unit_id" not in json.loads(str(call["body"]))["system"]
