"""What a student asks about in Ask reaches the readers the old flow fed (#143).

The knowledge points of a new Ask question (#142) are recorded once, beside the
answer, and every reader the old 「交一道题」 flow fed reads them too: the
student's weak topics and summary, adaptive memory, the parent dashboard, the
weekly report and the prep a teacher reads on a help request. None of them
needs a question row: there is none here, as there will be none once #148
retires that flow.

Asking about a star does not move it: a star's state is earned in practice
alone. A parent reads the names and never the question, and only while the
relationship is current.

The Ask runs through the real route, generation and repository over the shared
table double (see test_conversation_knowledge_points.py); the parent's
relationship is judged by the real authorization facts over the same table.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import (
    asked_knowledge_repo,
    parent_link_repo,
    practice_repo,
    report_repo,
    user_repo,
)
from stoa.db.repositories import account_deletion_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.jobs import conversation_generation
from stoa.routers import adaptive, conversations, parents, students
from stoa.security.authorization import CurrentAuthorizationFactRepository
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import (
    account_deletion_service,
    adaptive_learning_service,
    curriculum_service,
    parent_link_service,
    report_service,
)
from test_async_generation_cutover import invokes as invokes  # noqa: F401 - the fixture
from test_async_generation_cutover import switched_on as switched_on  # noqa: F401
from test_conversation_knowledge_points import (
    FREE,
    LOCALES,
    TITLES,
    _answer,
    _catalog,
    _done,
    _follow_up,
    _student_turn,
)
from test_conversation_knowledge_points import bedrock as bedrock  # noqa: F401 - the fixture
from test_conversation_knowledge_points import star_map as star_map  # noqa: F401
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    QUESTION,
    STUDENT,
    _client,
    _no_memory_personalisation,
    _send,
)
from test_message_command_generation import table as table  # noqa: F401 - the fixture

# Read before the autouse stub replaces it for the Ask itself.
_REAL_MEMORY_SUMMARY = adaptive_learning_service.get_memory_summary

PARENT = "parent-143"
NOW = "2026-10-26T09:00:00+00:00"
WEEK = "2026-10-26"
# Every question here is asked in that week.
ASKED_AT = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
# What the student wrote, word for word; a parent must never read it. No
# listed word of any language (#172), so the answer follows the display
# language each test asks in.
ASKED = "Mein Geheimnis: 6/8 ganz genau?"


def _profile(user_id: str, role: str) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        "date_of_birth": "2000-01-01",
    }


@pytest.fixture
def world(table, monkeypatch: pytest.MonkeyPatch):
    """One table behind the Ask, the parent's link and every reader."""
    profiles = {STUDENT: _profile(STUDENT, "student"), PARENT: _profile(PARENT, "parent")}
    table.seed_active_account(PARENT)
    # Opened with the question, as the client opens one: the title is the
    # question's own words, and the student index lists the conversation.
    conversation = table.rows[(f"CONV#{CONV}", "CONV")]
    conversation["title"] = conversations._title_from_question(ASKED)
    conversation["created_at"] = conversation["updated_at"] = ASKED_AT.isoformat()
    for name, module in list(sys.modules.items()):
        if name.startswith("stoa.") and hasattr(module, "get_table"):
            monkeypatch.setattr(module, "get_table", lambda table=table: table)
    monkeypatch.setattr(
        user_repo, "get_user", lambda user_id, **_k: deepcopy(profiles.get(user_id))
    )
    for name in (
        "get_parent_student_binding",
        "get_student_parent_binding",
    ):
        monkeypatch.setattr(user_repo, name, lambda *_a, **_k: None)
    for name in ("list_parent_student_bindings", "list_student_parent_bindings"):
        monkeypatch.setattr(user_repo, name, lambda *_a, **_k: [])
    monkeypatch.setattr(user_repo, "list_children_by_parent_scan", lambda *_a, **_k: [])
    # No practice at all: every star keeps the state the map was drawn with.
    for name in ("get_mistakes", "get_progress"):
        monkeypatch.setattr(practice_repo, name, lambda *_a, **_k: [])
    parent_link_service.assign_link(
        parent_id=PARENT, student_id=STUDENT, actor_id="admin-1", now=NOW
    )
    return table


def _ask(locale: str, *, key: str = "key-1", content: str = ASKED) -> dict[str, Any]:
    """Send a new question, as asked in the report's week."""
    with time_machine.travel(ASKED_AT, tick=False):
        return _done(_send(_client(), key, language=locale, content=content))


def _points(locale: str):
    """An answer naming the star `kraefte` and one point the model wrote itself."""
    name = TITLES["kraefte"][locale]
    return _answer(
        lambda stars: [{"id": stars[name], "name": name}, {"id": None, "name": FREE[locale]}]
    )


def _student() -> TestClient:
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.include_router(adaptive.router, prefix="/adaptive")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    return TestClient(app, raise_server_exceptions=False)


def _parent() -> TestClient:
    actor = Actor(
        PARENT,
        "https://identity.test",
        f"{PARENT}-subject",
        CanonicalRole.PARENT,
        AccountStatus.ACTIVE,
        "parent",
    )
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_actor] = lambda: actor
    # The real facts: whether the parent may read is judged from the link rows.
    app.dependency_overrides[get_authorization_fact_repository] = (
        CurrentAuthorizationFactRepository
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=True)


def _ok(response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return response.json()


def _revoke() -> None:
    """What the admin's revocation does to an active link."""
    parent_link_repo.transition_link(
        parent_id=PARENT,
        student_id=STUDENT,
        expected_status=parent_link_repo.STATUS_ACTIVE,
        next_status=parent_link_repo.STATUS_REJECTED,
        updated_by="admin-1",
        link_updated_at="2026-10-27T09:00:00+00:00",
    )


# ── The student ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_what_was_asked_about_is_among_the_student_s_weak_topics(
    world, bedrock, star_map, locale
) -> None:
    bedrock.answers = [_points(locale)]

    _ask(locale)

    profile = _ok(_student().get(f"/students/{STUDENT}/learning-profile"))
    topics = {(topic["subject"], topic["label"]): topic["count"] for topic in profile["weakTopics"]}
    assert topics == {("math", TITLES["kraefte"][locale]): 1, ("math", FREE[locale]): 1}
    summary = _ok(_student().get(f"/students/{STUDENT}/summary"))
    assert set(summary["weak_knowledge_points"]) == {TITLES["kraefte"][locale], FREE[locale]}


def test_each_new_question_counts_and_a_follow_up_does_not(
    world, bedrock, star_map
) -> None:
    bedrock.answers = [_points("de"), _follow_up, _points("de")]

    _ask("de", key="key-1")
    _ask("de", key="key-2", content="Und warum?")
    _ask("de", key="key-3", content="Noch eine Frage zu Kräften.")

    profile = _ok(_student().get(f"/students/{STUDENT}/learning-profile"))
    counts = {topic["label"]: topic["count"] for topic in profile["weakTopics"]}
    assert counts == {TITLES["kraefte"]["de"]: 2, FREE["de"]: 2}


def test_a_question_about_a_step_counts_nothing_even_if_points_are_named_again(
    world, bedrock, star_map
) -> None:
    # Shown no map, the model can only write the names again.
    again = [{"id": None, "name": TITLES["kraefte"]["de"]}, {"id": None, "name": FREE["de"]}]
    bedrock.answers = [_points("de"), _answer(lambda _stars: again)]
    first = _ask("de")

    response = _client().post(
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

    profile = _ok(_student().get(f"/students/{STUDENT}/learning-profile"))
    assert {topic["count"] for topic in profile["weakTopics"]} == {1}


def test_adaptive_memory_remembers_what_was_asked_about(
    world, bedrock, star_map, monkeypatch: pytest.MonkeyPatch
) -> None:
    bedrock.answers = [_points("fr")]
    _ask("fr")
    monkeypatch.setattr(adaptive_learning_service, "get_memory_summary", _REAL_MEMORY_SUMMARY)

    memory = _ok(_student().get("/adaptive/students/me/memory"))

    assert {topic["label"] for topic in memory["weakTopics"]} == {
        TITLES["kraefte"]["fr"],
        FREE["fr"],
    }
    snapshots = {(row["subject"], row["topic_id"]) for row in memory["memorySnapshots"]}
    assert ("math", "forces-et-mouvement") in snapshots


def test_asking_about_a_star_does_not_change_its_state(world, bedrock, star_map) -> None:
    """A star is lit by practice alone: an Ask writes nothing practice is read from."""
    titles = [TITLES[unit]["de"] for unit in ("brueche-kuerzen", "teiler-vielfache", "kraefte")]
    bedrock.answers = [
        _answer(lambda stars: [{"id": stars[title], "name": title} for title in titles])
    ]
    before = set(world.rows)

    done = _ask("de")

    assert [point["unitId"] for point in done["structured"]["knowledgePoints"]] == [
        "brueche-kuerzen",
        "teiler-vielfache",
        "kraefte",
    ]
    written = set(world.rows) - before
    assert not any(pk.startswith(("PROGRESS#", "ATTEMPTS#")) for pk, _sk in written)
    # The next question is shown the map as it was.
    bedrock.answers = [_answer(lambda _stars: [])]
    _ask("de", key="key-2", content="Noch etwas.")
    turn = _student_turn(bedrock.bodies[-1])
    assert f"{TITLES['brueche-kuerzen']['de']} | lit" in turn
    assert f"{TITLES['teiler-vielfache']['de']} | in_progress" in turn
    assert f"{TITLES['kraefte']['de']} | ready" in turn


# ── The parent ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_the_parent_dashboard_names_what_was_asked_about_and_never_the_question(
    world, bedrock, star_map, locale
) -> None:
    bedrock.answers = [_points(locale)]
    _ask(locale)
    parent = _parent()

    summary = _ok(parent.get(f"/parents/me/children/{STUDENT}/summary"))
    profile = _ok(parent.get(f"/parents/me/children/{STUDENT}/learning-profile"))
    history = _ok(parent.get(f"/parents/me/children/{STUDENT}/history"))

    assert TITLES["kraefte"][locale] in summary["weakTopics"]
    assert FREE[locale] in summary["weakTopics"]
    assert {topic["label"] for topic in profile["weakTopics"]} == {
        TITLES["kraefte"][locale],
        FREE[locale],
    }
    for read in (summary, profile, history):
        assert "Geheimnis" not in str(read)
        assert "6/8" not in str(read)


def test_after_the_relationship_is_revoked_the_parent_reads_none_of_it(
    world, bedrock, star_map
) -> None:
    bedrock.answers = [_points("it")]
    _ask("it")
    parent = _parent()
    assert parent.get(f"/parents/me/children/{STUDENT}/summary").status_code == 200

    _revoke()

    for path in ("summary", "learning-profile", "history", f"reports/{WEEK}"):
        response = parent.get(f"/parents/me/children/{STUDENT}/{path}")
        assert response.status_code in {403, 404}, (path, response.status_code)
        assert TITLES["kraefte"]["it"] not in response.text
    with pytest.raises(ValueError):
        report_service.build_weekly_learning_payload(PARENT, STUDENT, WEEK)


# ── The weekly report ────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_the_weekly_report_names_what_was_asked_about_and_never_the_question(
    world, bedrock, star_map, locale
) -> None:
    bedrock.answers = [_points(locale)]
    _ask(locale)

    payload = report_service.build_weekly_learning_payload(PARENT, STUDENT, WEEK)
    content = report_service.build_deterministic_report_fallback(payload)
    record = report_service.build_weekly_report_record(payload, content)
    record["account_fence_generation"] = 1
    report_repo.put_report(record)

    report = _ok(_parent().get(f"/parents/me/children/{STUDENT}/reports/{WEEK}"))
    assert TITLES["kraefte"][locale] in report["report"]["weakKnowledgePoints"]
    assert FREE[locale] in report["report"]["weakKnowledgePoints"]
    # Nothing the model or the parent is given carries the question.
    for shown in (
        report_service.build_bedrock_report_input(payload),
        report_service.render_weekly_report_html(payload, content),
        report_service.build_weekly_report_json_artifact(payload, content, record),
        report,
    ):
        assert "Geheimnis" not in str(shown)
        assert "6/8" not in str(shown)


def test_the_weekly_report_counts_only_that_week_s_questions(
    world, bedrock, star_map
) -> None:
    bedrock.answers = [_points("de")]
    _ask("de")

    payload = report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-10-12")

    assert payload["weakTopics"] == []


# ── The record ───────────────────────────────────────────────────────────────


def test_the_record_holds_names_and_never_the_question(world, bedrock, star_map) -> None:
    bedrock.answers = [_points("en")]
    _ask("en")

    [record] = asked_knowledge_repo.list_for_student(STUDENT)

    assert record["subject"] == "math"
    assert record["knowledge_points"] == [TITLES["kraefte"]["en"], FREE["en"]]
    assert record["unit_ids"] == ["kraefte"]
    assert "Geheimnis" not in str(record)
    assert conversations._conv_pk(CONV) == record["PK"]


def test_the_worker_s_answer_after_a_202_is_recorded_once(
    world, bedrock, star_map, invokes, switched_on
) -> None:
    bedrock.answers = [_points("de")]

    with time_machine.travel(ASKED_AT, tick=False):
        assert _send(_client(), "key-1", language="de", content=ASKED).status_code == 202
        assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "completed"}
        # Delivered again, the command is already answered and records nothing more.
        assert conversation_generation.handler(invokes.events[0], None) == {"outcome": "settled"}

    profile = _ok(_student().get(f"/students/{STUDENT}/learning-profile"))
    counts = {topic["label"]: topic["count"] for topic in profile["weakTopics"]}
    assert counts == {TITLES["kraefte"]["de"]: 1, FREE["de"]: 1}


# ── What may be recorded ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "personal",
    [
        "Frag anna.muster@example.ch",  # an e-mail address
        "Ruf an: 079 123 45 67",  # a phone number
        "Mein Code 12345678",  # a long run of digits
    ],
)
def test_a_written_name_that_looks_like_personal_data_reaches_no_reader(
    world, bedrock, star_map, personal
) -> None:
    """The student can steer what the model writes; the parent must not read it."""
    star = TITLES["kraefte"]["de"]
    bedrock.answers = [
        _answer(
            lambda stars: [
                {"id": stars[star], "name": star},
                {"id": None, "name": personal},
                {"id": None, "name": FREE["de"]},
            ]
        )
    ]

    done = _ask("de")

    # The student still sees what the model wrote; only the record leaves it out.
    assert {"name": personal, "unitId": None} in done["structured"]["knowledgePoints"]
    summary = _ok(_parent().get(f"/parents/me/children/{STUDENT}/summary"))
    assert set(summary["weakTopics"]) == {star, FREE["de"]}
    profile = _ok(_student().get(f"/students/{STUDENT}/learning-profile"))
    assert personal not in str(profile)


def test_a_star_s_name_is_recorded_whatever_digits_it_holds(
    world, bedrock, star_map, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A star's name is the catalog's, not the model's, so nothing in it is withheld."""
    title = "Zahlen bis 10000000"

    def catalog(**kwargs: Any) -> dict[str, Any]:
        built = _catalog(**kwargs)
        built["units"][2]["title"] = title  # kraefte
        return built

    monkeypatch.setattr(curriculum_service, "list_catalog", catalog)
    bedrock.answers = [_answer(lambda stars: [{"id": stars[title], "name": title}])]

    _ask("de")

    summary = _ok(_parent().get(f"/parents/me/children/{STUDENT}/summary"))
    assert summary["weakTopics"] == [title]


def test_deleting_the_account_scrubs_the_record(world, bedrock, star_map) -> None:
    bedrock.answers = [_points("de")]
    done = _ask("de")
    key = tuple(asked_knowledge_repo.record_key(CONV, done["messageId"]).values())
    assert world.rows[key]["knowledge_points"]
    fence = world.rows[tuple(account_deletion_repo.account_fence_key(STUDENT).values())]
    fence["status"] = "deletion_pending"

    previous: dict[str, Any] = {}
    for _ in range(4):
        result = account_deletion_service._conversation_messages_branch(
            command={"user_id": STUDENT, "generation": 1}, previous=previous
        )
        previous = result.persisted(NOW)

    assert result.quiescent is True
    tombstone = world.rows[key]
    assert tombstone["status"] == "deleted"
    assert not {"knowledge_points", "unit_ids", "subject"} & set(tombstone)
    assert asked_knowledge_repo.list_for_student(STUDENT) == []
