"""Readers are named by one rule (#662, part of #637).

- A reader interface's `subject` is the canonical id (`math`, ...), or null for
  a request or a row with none the platform teaches; the client names it.
- A subject name the backend writes itself is the message catalog's
  `subject.<id>` in the reader's language, never the name a row stores.
- A live answer is in the language of whoever asks (`reader_locale`); what is
  kept for somebody else - the weekly report - in the language they stored.
- A lesson or a knowledge point is called by the name `curriculum_names` gives
  it in that language; one it does not know is called by the level above, or
  by nothing.

The last part is the gate: the parent's, the teacher's and the student's
answers, and what the weekly report carries, show no stored id (`mathematics`,
a topic, unit or lesson id) and neither "General" nor "Practice".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import time_machine

import test_curriculum_reads as reads
from fakes import activity_students as typical
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_conversation
from stoa.db import table as db_table
from stoa.db.repositories import practice_repo, user_repo
from stoa.main import RequestLocaleMiddleware
from stoa.services import (
    curriculum_service,
    learning_profile_service,
    message_catalog,
    practice_projection_service,
    report_service,
    student_activity,
)
from test_chat_help_request_lifecycle import REQUEST, TEACHER, _dispatch_to, _help
from test_chat_help_request_lifecycle import _client as teacher_client
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture
from test_curriculum_names_unchanged import fixture_lesson as fixture_lesson  # noqa: F401 - the fixture
from test_student_activity import parent_client as parent_client  # noqa: F401 - the fixture
from test_weekly_report_activity import report_for as report_for  # noqa: F401 - the fixture

LOCALES = ("de", "en", "fr", "it")
SUBJECT_IDS = set(curriculum_service.SUPPORTED_SUBJECTS)
STUDENT = "student-662"

#: A curriculum of one topic, one unit and one lesson, as a German reader's catalog.
CATALOG = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "brueche", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "brueche-u2", "subjectId": "math", "topicId": "brueche", "title": "Brüche rechnen", "order": 0}
    ],
    "lessons": [
        {
            "id": "brueche-l3",
            "unitId": "brueche-u2",
            "topicId": "brueche",
            "subjectId": "math",
            "title": "Brüche addieren",
        }
    ],
}


def _finished(lesson_id: str, day: int, **stored: Any) -> dict[str, Any]:
    return {
        "lesson_id": lesson_id,
        "subject_id": "mathematics",
        "status": "completed",
        "completed_at": f"2026-11-{day:02d}T10:00:00+00:00",
        **stored,
    }


def _recent(evidence: Any, locale: str = "de") -> dict[str, student_activity.Activity]:
    entries = student_activity.recent(STUDENT, limit=50, evidence=evidence, locale=locale)
    return {entry.id: entry for entry in entries}


# ── 1. The subject of an entry ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("mathematics", "math"),
        ("Mathematik", "math"),
        ("math", "math"),
        (" PHYSIK ", "physics"),
        ("chemistry", None),
        ("General", None),
        ("", None),
    ],
)
def test_an_entry_s_subject_is_the_canonical_id_or_none(
    fake_table: FakeTable, stored: str, shown: str | None
) -> None:
    seed_conversation(
        fake_table,
        conversation_id="conv-662",
        student_id=STUDENT,
        subject=stored,
        now="2026-11-20T09:00:00+00:00",
    )
    evidence = fake_evidence.evidence(
        STUDENT,
        catalog=CATALOG,
        progress=[_finished("brueche-l3", 21, subject_id=stored)],
        attempts=[
            {
                "challenge_id": "wrong-1",
                "correct": False,
                "subject_id": stored,
                "topic_id": "brueche",
                "created_at": "2026-11-22T10:00:00+00:00",
            }
        ],
        now=typical.NOW,
    )

    entries = _recent(evidence)

    assert {entry.type: entry.subject for entry in entries.values()} == {
        "conversation": shown,
        "practice": shown,
        "practice_mistake": shown,
    }


# ── 2. What a finished lesson is called ──────────────────────────────────────


def test_a_finished_lesson_is_called_by_its_name_then_by_the_level_above(
    fake_table: FakeTable,
) -> None:
    evidence = fake_evidence.evidence(
        STUDENT,
        catalog=CATALOG,
        progress=[
            # The curriculum's name, not the title the progress row kept.
            _finished("brueche-l3", 1, unit_id="brueche-u2", topic_id="brueche", lesson_title="Alter Titel"),
            # A lesson the curriculum no longer has: its unit, then its topic.
            _finished("retired-1", 2, unit_id="brueche-u2", topic_id="brueche"),
            _finished("retired-2", 3, unit_id="retired-unit", topic_id="brueche"),
            # Nothing of it is known: the title its row kept, else nothing.
            _finished("retired-3", 4, topic_id="retired-topic", lesson_title="Alte Lektion"),
            _finished("retired-4", 5, unit_id="retired-unit", topic_id="retired-topic"),
        ],
        now=typical.NOW,
    )

    entries = _recent(evidence)

    assert {lesson_id: entry.summary for lesson_id, entry in entries.items()} == {
        "brueche-l3": "Brüche addieren",
        "retired-1": "Brüche rechnen",
        "retired-2": "Brüche",
        "retired-3": "Alte Lektion",
        "retired-4": "",
    }


@pytest.mark.parametrize(
    ("locale", "name"), [("de", "Kreis"), ("en", "Circle"), ("fr", "Cercle"), ("it", "Cerchio")]
)
def test_a_finished_lesson_is_named_in_the_reader_s_language(
    fake_table: FakeTable, locale: str, name: str
) -> None:
    """A lesson's row carries its name in each language (#661)."""
    row = {
        "lesson_id": "kreis-l1",
        "title": "Kreis",
        "titles": {"de": "Kreis", "en": "Circle", "fr": "Cercle", "it": "Cerchio"},
    }
    evidence = fake_evidence.evidence(
        STUDENT,
        catalog=CATALOG,
        named_rows=[row],
        locale=locale,
        progress=[_finished("kreis-l1", 1, lesson_title="Kreis (damals)")],
        now=typical.NOW,
    )

    assert _recent(evidence, locale)["kreis-l1"].summary == name


# ── 3. A subject name the backend writes ─────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_the_catalog_names_a_subject_from_the_message_catalog(
    monkeypatch: pytest.MonkeyPatch, locale: str
) -> None:
    stored = {
        "subject_id": "mathematics",
        "name": "Rechnen (stored)",
        "order": 0,
        "rollout_state": "active",
    }
    monkeypatch.setattr(practice_repo, "get_subjects", lambda: [stored])
    monkeypatch.setattr(practice_repo, "get_topics", lambda *_a, **_k: [])
    monkeypatch.setattr(practice_repo, "get_all_units", lambda: [])

    catalog = curriculum_service.list_catalog(locale=locale, lesson_rows=[])

    assert [(subject["id"], subject["name"]) for subject in catalog["subjects"]] == [
        ("math", message_catalog.text("subject.math", locale))
    ]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_learning_profile_labels_a_subject_in_the_reader_s_language(
    fake_table: FakeTable, locale: str
) -> None:
    profile = learning_profile_service.build_learning_profile(
        student_id=STUDENT,
        questions=[],
        evidence=fake_evidence.evidence(STUDENT, catalog=CATALOG, locale=locale, now=typical.NOW),
        locale=locale,
    )

    expected = {
        subject_id: message_catalog.text(f"subject.{subject_id}", locale)
        for subject_id in curriculum_service.SUPPORTED_SUBJECTS
    }
    assert {item["id"]: item["label"] for item in profile["subjects"]} == expected
    assert {item["subject"]: item["label"] for item in profile["subjectActivity"]} == expected


def test_the_model_s_prompt_keeps_its_own_english_label() -> None:
    """`SUPPORTED_SUBJECTS`' `label` is for the prompt, whatever the reader's language."""
    assert "Subject label: Mathematics." in learning_profile_service.subject_prompt_context("math")


# ── 4. Whose language ────────────────────────────────────────────────────────


def test_a_parent_who_names_no_language_reads_in_the_one_they_stored(
    parent_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = parent_client(typical.NOAH)
    profile = user_repo.get_user

    def stored(user_id: str, **kwargs: Any) -> dict[str, Any]:
        row = dict(profile(user_id, **kwargs))
        if user_id == "parent-693":
            row["preferred_locale"] = "fr"
        return row

    monkeypatch.setattr(user_repo, "get_user", stored)

    summary = client.get(f"/parents/me/children/{typical.NOAH.id}/summary").json()
    history = client.get(f"/parents/me/children/{typical.NOAH.id}/history").json()
    asked = client.get(
        f"/parents/me/children/{typical.NOAH.id}/history", headers={"Accept-Language": "it"}
    ).json()

    lesson = message_catalog.text("activity.practice_lesson_completed", "fr")
    assert lesson in [item["title"] for item in summary["recentActivity"]]
    assert lesson in [item["title"] for item in history["items"]]
    # What the request asks for still wins over what is stored.
    assert message_catalog.text("activity.practice_lesson_completed", "it") in [
        item["title"] for item in asked["items"]
    ]


# ── 5. The gate ──────────────────────────────────────────────────────────────

#: Keys whose string values a reader is shown as a name.
NAME_KEYS = frozenset({"title", "summary", "label", "name", "topic", "topicName", "unitTitle"})
#: Keys that carry a subject id.
SUBJECT_KEYS = frozenset({"subject", "subjectId"})
HARDCODED = frozenset({"General", "Practice"})

#: name -> (who asks, path): the reader interfaces the fixture's student shows up in.
READER_ROUTES: dict[str, tuple[str, str]] = {
    "parent_summary": reads.ROUTES["parent_summary"],
    "parent_history": reads.ROUTES["parent_history"],
    "parent_learning_profile": reads.ROUTES["parent_learning_profile"],
    "learning_profile": reads.ROUTES["learning_profile"],
    "student_mistakes": ("student", "/practice/mistakes"),
}


def _shown(value: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    """Every (key, value) a response carries under a name or a subject key."""
    if isinstance(value, dict):
        for inner, item in value.items():
            yield from _shown(item, inner)
    elif isinstance(value, list):
        for item in value:
            yield from _shown(item, key)
    elif key in NAME_KEYS | SUBJECT_KEYS or key == "weakTopics":
        yield key, value


def _stored_ids() -> set[str]:
    """Every id the fixture's curriculum stores: subjects as seeded, topics, units, lessons."""
    ids = {"mathematics"}
    for (pk, _sk), row in db_table.table().rows.items():
        if pk == "PRACTICE":
            ids.update(
                str(row[key])
                for key in ("subject_id", "topic_id", "unit_id", "lesson_id")
                if row.get(key)
            )
    return ids - SUBJECT_IDS


def _assert_named(shown: list[tuple[str, Any]], stored_ids: set[str], where: str) -> None:
    for key, value in shown:
        if key in SUBJECT_KEYS:
            assert value in SUBJECT_IDS | {None, ""}, f"{where}: {key}={value!r}"
        else:
            assert value not in stored_ids, f"{where}: {key} shows the stored id {value!r}"
            assert value not in HARDCODED, f"{where}: {key}={value!r}"


def _read(name: str, locale: str) -> Any:
    who, path = READER_ROUTES[name]
    client = reads._client(who)
    client.app.add_middleware(RequestLocaleMiddleware)
    response = client.get(path, headers={"Accept-Language": locale})
    assert response.status_code == 200, f"{name} {locale}: {response.status_code} {response.text}"
    return response.json()


@pytest.mark.parametrize("locale", LOCALES)
def test_no_reader_route_shows_a_stored_id_or_a_made_up_name(
    fixture_lesson: dict[str, Any], locale: str
) -> None:
    stored_ids = _stored_ids()
    assert {"brueche", "brueche-u1", "brueche-l1"} <= stored_ids

    with time_machine.travel(reads.READ_AT, tick=False):
        answers = {name: _read(name, locale) for name in READER_ROUTES}

    for name, answer in answers.items():
        shown = list(_shown(answer))
        assert shown, name
        _assert_named(shown, stored_ids, f"{name} {locale}")

    # The fixture does exercise it: practice rows that store `mathematics`
    # and a topic id, shown as `math` and by name.
    history = answers["parent_history"]["items"]
    assert {item["subject"] for item in history if item["type"].startswith("practice")} == {"math"}
    finished = {item["id"]: item["summary"] for item in history if item["type"] == "practice"}
    titles = next(
        row["titles"]
        for (pk, _sk), row in db_table.table().rows.items()
        if pk == "PRACTICE" and row.get("lesson_id") == "brueche-l1" and row.get("titles")
    )
    assert finished["brueche-l1"] == titles[locale]
    mistakes = answers["student_mistakes"]["items"]
    assert mistakes and {item["subjectId"] for item in mistakes} == {"math"}
    # A knowledge point the curriculum knows is named; one it does not is not.
    assert any(item["topic"] for item in mistakes)
    assert "Freies Thema" not in {item["topic"] for item in mistakes}


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize(
    ("stored", "shown"),
    [("mathematics", "math"), ("Physik", "physics"), ("General", None), ("chemistry", None), (None, None)],
)
def test_a_teacher_reads_the_subject_as_its_id_or_null(
    table: FakeTable,  # noqa: F811 - the fixture
    locale: str,
    stored: str | None,
    shown: str | None,
) -> None:
    _dispatch_to(table, TEACHER)
    if stored is None:
        _help(table).pop("subject")
    else:
        _help(table)["subject"] = stored
    teacher = teacher_client()
    headers = {"Accept-Language": locale}

    [listed] = teacher.get("/teachers/me/help-requests", headers=headers).json()["items"]
    detail = teacher.get(f"/teachers/me/help-requests/{REQUEST}", headers=headers)

    assert detail.status_code == 200, detail.text
    assert "subject" in listed and "subject" in detail.json()
    assert (listed["subject"], detail.json()["subject"]) == (shown, shown)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_weekly_report_carries_no_stored_id_and_no_other_language(
    report_for: Any,  # noqa: F811 - the fixture
    locale: str,
) -> None:
    payload = report_for(typical.LENA, locale=locale)

    titles = {entry["type"]: entry["title"] for entry in payload["activities"]}
    assert titles == {
        "conversation": message_catalog.text("activity.ai_conversation", locale),
        "practice": message_catalog.text("activity.practice_lesson_completed", locale),
        "practice_mistake": message_catalog.text("activity.practice_mistake_logged", locale),
    }
    assert {entry["subject"] for entry in payload["activities"]} == {"math"}
    # What the row stored is nowhere in the entries that are kept, sent to the
    # model or written without it: not the subject's stored id, not the
    # topic's. The weak topics are `weak_topics`' own (#673): a point the
    # curriculum does not know is shown there as it was written, which for a
    # wrong answer is what its row stored.
    entries = {**payload, "weakTopics": []}
    written = json.dumps(
        [
            payload["activities"],
            payload["starsLit"],
            report_service.build_bedrock_report_input(entries),
            report_service.build_deterministic_report_fallback(entries),
        ],
        ensure_ascii=False,
    )
    for stored in ("mathematics", "kopfrechnen-raw-id", '"General"', '"Practice"'):
        assert stored not in written, stored


def test_a_german_parent_s_report_has_no_english_activity_title(report_for: Any) -> None:  # noqa: F811
    payload = report_for(typical.LENA, locale="de")

    english = {
        message_catalog.text(key, "en")
        for key in (
            "activity.ai_conversation",
            "activity.teacher_help_requested",
            "activity.practice_lesson_completed",
            "activity.practice_mistake_logged",
        )
    }
    assert not english & {entry["title"] for entry in payload["activities"]}


def test_a_mistake_projected_without_names_shows_no_topic() -> None:
    stored = {
        "challenge_id": "challenge-1",
        "attempt_id": "attempt-1",
        "subject_id": "mathematics",
        "topic_id": "brueche",
        "submitted_answer": "1",
        "created_at": "2026-11-20T10:00:00+00:00",
    }

    mistake = practice_projection_service.build_mistake_projection(stored)

    assert (mistake.subject_id, mistake.topic) == ("math", "")
