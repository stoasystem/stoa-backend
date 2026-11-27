"""Content names read the same in all four languages after `curriculum_names` (#660).

`curriculum_names` took over naming topics, units, lessons and skill points
from `curriculum_translations.translated_title` / `skill_title` and
`learning_profile_service.TopicNames`, without changing a single response. The
routes that show those names - the catalog, the star map, the practice route,
a lesson, the learning history, the learning profile and the parent pages -
and the skill list were answered by origin/main `1e0d4d3b` for every language
on the same fixture (`tests/test_curriculum_reads.py`, plus wrong answers and
a finished lesson that carries its own title). The fixture keeps, per route and
language, every name the response carries and a digest of the whole response;
both must be what main gave. The two learning profiles were recorded again when
their weak topics began to come from `weak_topics` (#673): the same names, in
the new order, each topic with its `score`.

To record it again (on main, before a change to names):
`STOA_RECORD_CURRICULUM_NAMES=1 pytest tests/test_curriculum_names_unchanged.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import time_machine

import test_curriculum_reads as reads
from stoa.main import RequestLocaleMiddleware
from stoa.services import curriculum_service, locale_service

GOLDEN = Path(__file__).parent / "fixtures" / "curriculum_names_660.json"
LOCALES = ("de", "en", "fr", "it")
RECORD = bool(os.environ.get("STOA_RECORD_CURRICULUM_NAMES"))

#: name -> (who asks, path); `{lesson}` / `{topic}` as in test_curriculum_reads.
ROUTES: dict[str, tuple[str, str]] = {
    **{
        name: reads.ROUTES[name]
        for name in (
            "star_map",
            "stars_around",
            "catalog",
            "lesson",
            "roadmap",
            "learning_history",
            "learning_profile",
            "parent_summary",
            "parent_learning_profile",
            "parent_history",
        )
    },
    "curriculum_lesson": ("student", "/practice/curriculum/lessons/{lesson}"),
}

#: Keys whose string values are names a reader sees.
NAME_KEYS = frozenset(
    {"title", "name", "summary", "label", "topic", "topicName", "subject", "unitTitle"}
)


def _wrong_answers(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrong answers spelling their knowledge point each way a row may (#390)."""
    spellings = [
        # The unit and lesson the answer was given in.
        {"topic_id": lesson["topic_id"], "unit_id": lesson["unit_id"], "lesson_id": lesson["lesson_id"]},
        # A bare topic id, as every practice mistake stores it.
        {"topic_id": "brueche"},
        # A unit's title in another language, and a skill id.
        {"topic_id": "Equations"},
        {"topic_id": "brueche-kuerzen"},
        # A lesson the curriculum no longer has, under a known topic.
        {"topic_id": "gleichungen", "lesson_id": "retired-lesson"},
        # A name the curriculum does not know at all.
        {"topic_id": "Freies Thema"},
    ]
    return [
        {
            "PK": f"ATTEMPTS#{reads.STUDENT}",
            "SK": f"ATTEMPT#wrong-{index}",
            "attempt_id": f"wrong-{index}",
            "student_id": reads.STUDENT,
            "challenge_id": f"challenge-{index}",
            "subject_id": "mathematics",
            "correct": False,
            "answer": "1",
            "created_at": f"2026-11-1{index}T09:00:00+00:00",
            **spelling,
        }
        for index, spelling in enumerate(spellings)
    ]


@pytest.fixture
def fixture_lesson(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    table, lesson = reads._table(monkeypatch, reads.SMALL)
    table.seed(*_wrong_answers(lesson))
    # A finished lesson whose progress row carries the title it had then.
    table.seed(
        {
            "PK": f"PROGRESS#{reads.STUDENT}",
            "SK": "LESSON#brueche-l1",
            "entity_type": "practice_progress",
            "student_id": reads.STUDENT,
            "lesson_id": "brueche-l1",
            "subject_id": "mathematics",
            "topic_id": "brueche",
            "unit_id": "brueche-u1",
            "title": "Brüche kürzen (damals)",
            "status": "completed",
            "completed_at": "2026-11-20T10:00:00+00:00",
        }
    )
    table.reset_reads()
    yield lesson
    locale_service.set_request_locale(None)


def _get(name: str, lesson: dict[str, Any], locale: str) -> Any:
    who, template = ROUTES[name]
    client = reads._client(who)
    client.app.add_middleware(RequestLocaleMiddleware)
    path = template.format(lesson=lesson["lesson_id"], topic=lesson["topic_id"])
    response = client.get(path, headers={"Accept-Language": locale})
    assert response.status_code == 200, f"{name} {locale}: {response.status_code} {response.text}"
    return response.json()


def _names(value: Any, path: str = "") -> list[str]:
    """`path=value` for every name in a response, in the order it carries them."""
    found: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            item = value[key]
            if key in NAME_KEYS and isinstance(item, str):
                found.append(f"{path}.{key}={item}")
            else:
                found.extend(_names(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_names(item, f"{path}[{index}]"))
    return found


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _answers(lesson: dict[str, Any]) -> dict[str, dict[str, Any]]:
    answers: dict[str, dict[str, Any]] = {}
    with time_machine.travel(reads.READ_AT, tick=False):
        for name in ROUTES:
            for locale in LOCALES:
                response = _get(name, lesson, locale)
                answers.setdefault(name, {})[locale] = {
                    "digest": _digest(response),
                    "names": _names(response),
                }
    for locale in LOCALES:
        skills = curriculum_service.list_skills(locale=locale)
        answers.setdefault("skills", {})[locale] = {
            "digest": _digest(skills),
            "names": _names(skills),
        }
    return answers


def test_every_name_reads_as_main_gave_it(fixture_lesson: dict[str, Any]) -> None:
    answers = _answers(fixture_lesson)
    if RECORD:
        GOLDEN.write_text(
            json.dumps(answers, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert set(answers) == set(recorded)
    for name, by_locale in recorded.items():
        for locale, expected in by_locale.items():
            got = answers[name][locale]
            assert got["names"] == expected["names"], f"{name} {locale}"
            assert got["digest"] == expected["digest"], f"{name} {locale}"


def test_the_fixture_names_content_in_each_language() -> None:
    """The recorded routes do carry translated names: a language reached each of them."""
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for name in ("catalog", "star_map", "roadmap", "parent_history", "parent_summary", "skills"):
        by_locale = {locale: recorded[name][locale]["names"] for locale in LOCALES}
        assert len({tuple(names) for names in by_locale.values()}) == len(LOCALES), name
    # The wrong answers were named: by the curriculum where it knows the
    # spelling, as written where it does not.
    history = "\n".join(recorded["parent_history"]["en"]["names"])
    assert "Freies Thema" in history
    assert "Equations" in history
