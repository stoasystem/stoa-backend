"""A parent reads a child's weak topics as the curriculum names them (#390).

Production held three spellings of the same knowledge point: the English slug
an old answer wrote (`calculating-with-fractions`), the unit id a newer record
carries (`brueche-u2`) and the bare topic id a practice mistake stores
(`brueche`). The learning profile counted each separately and labelled each
with whatever text the row held, so a parent reading in German was shown
"Calculating with fractions", "Brüche rechnen" and "brueche" as three weak
topics. Each is now folded into the current unit, and its label is the
catalog's title in the language the request asked for.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes import student_evidence as fake_evidence
from stoa.db.repositories import user_repo
from stoa.main import RequestLocaleMiddleware
from stoa.routers import parents
from stoa.services import learning_profile_service, locale_service, student_evidence

CHILD = "child-390"

UNIT_TITLES = {
    "brueche-u1": {"de": "Brüche verstehen und kürzen", "en": "Understanding and reducing fractions"},
    "brueche-u2": {"de": "Brüche rechnen", "en": "Calculating with fractions"},
    "gleichungen-u1": {"de": "Einfache Gleichungen lösen", "en": "Solving simple equations"},
}
TOPIC_TITLES = {
    "brueche": {"de": "Brüche", "en": "Fractions"},
    "gleichungen": {"de": "Gleichungen", "en": "Equations"},
}


def _catalog(locale: str) -> dict[str, Any]:
    """The student catalog as `curriculum_service.list_catalog` projects it."""
    return {
        "subjects": [{"id": "math", "order": 1}],
        "topics": [
            {"id": topic_id, "subjectId": "math", "title": titles[locale], "order": order}
            for order, (topic_id, titles) in enumerate(TOPIC_TITLES.items(), start=1)
        ],
        "units": [
            {
                "id": unit_id,
                "subjectId": "math",
                "topicId": unit_id.rsplit("-u", 1)[0],
                "title": titles[locale],
                "order": order,
            }
            for order, (unit_id, titles) in enumerate(UNIT_TITLES.items(), start=1)
        ],
        "lessons": [
            {"id": "brueche-l3", "unitId": "brueche-u2", "topicId": "brueche", "subjectId": "math"},
        ],
    }


# What production held for one child, each row as stored.
QUESTIONS = [
    {
        "question_id": "q-1",
        "subject": "math",
        "knowledge_points": [
            "Calculating with fractions",
            "Solving simple equations",
            "Understanding and reducing fractions",
        ],
        "created_at": "2026-11-02T09:00:00+00:00",
    },
    {
        "question_id": "q-2",
        "subject": "math",
        "topic_seeds": [
            {
                "subject": "math",
                "topic_id": "brueche-u2",
                "label": "Brüche rechnen",
                "evidence_question_ids": ["q-2"],
                "last_seen_at": "2026-11-03T09:00:00+00:00",
            }
        ],
        "created_at": "2026-11-03T09:00:00+00:00",
    },
]
MISTAKES = [
    # A current attempt row: it names its unit.
    {
        "subject_id": "mathematics",
        "topic_id": "brueche",
        "unit_id": "brueche-u2",
        "lesson_id": "brueche-l3",
        "created_at": "2026-11-04T09:00:00+00:00",
    },
    # An older one names only its lesson.
    {
        "subject_id": "mathematics",
        "topic_id": "brueche",
        "lesson_id": "brueche-l3",
        "created_at": "2026-11-05T09:00:00+00:00",
    },
]


def _profile(locale: str, **overrides: Any) -> dict[str, Any]:
    return learning_profile_service.build_learning_profile(
        student_id=CHILD,
        questions=overrides.get("questions", QUESTIONS),
        mistakes=overrides.get("mistakes", MISTAKES),
        asked=overrides.get("asked", []),
        catalog=_catalog(locale),
        locale=locale,
    )


def _topics(profile: dict[str, Any]) -> dict[tuple[str, str], int]:
    return {(topic["topicId"], topic["label"]): topic["count"] for topic in profile["weakTopics"]}


def test_every_spelling_of_one_unit_is_one_weak_topic_named_in_german() -> None:
    assert _topics(_profile("de")) == {
        ("brueche-u2", "Brüche rechnen"): 4,
        ("brueche-u1", "Brüche verstehen und kürzen"): 1,
        ("gleichungen-u1", "Einfache Gleichungen lösen"): 1,
    }


def test_the_same_rows_read_in_english_carry_the_english_titles() -> None:
    assert _topics(_profile("en")) == {
        ("brueche-u2", "Calculating with fractions"): 4,
        ("brueche-u1", "Understanding and reducing fractions"): 1,
        ("gleichungen-u1", "Solving simple equations"): 1,
    }


def test_a_merged_topic_keeps_every_piece_of_its_evidence() -> None:
    merged = next(t for t in _profile("de")["weakTopics"] if t["topicId"] == "brueche-u2")

    assert merged["evidenceQuestionIds"] == ["q-1", "q-2"]
    assert merged["latestEvidenceAt"] == "2026-11-05T09:00:00+00:00"
    assert merged["subject"] == "math"


def test_a_bare_topic_id_is_named_by_its_topic_never_shown_as_the_id() -> None:
    profile = _profile("de", questions=[], mistakes=[{"subject_id": "mathematics", "topic_id": "brueche"}])

    assert _topics(profile) == {("brueche", "Brüche"): 1}


def test_a_topic_with_one_unit_folds_into_that_unit() -> None:
    profile = _profile(
        "de", questions=[], mistakes=[{"subject_id": "mathematics", "topic_id": "gleichungen"}]
    )

    assert _topics(profile) == {("gleichungen-u1", "Einfache Gleichungen lösen"): 1}


def test_a_name_the_curriculum_does_not_know_is_kept_as_written() -> None:
    asked = [{"subject": "math", "knowledge_points": ["Kopfrechnen mit Zehnerpotenzen"], "created_at": "x"}]

    profile = _profile("de", questions=[], mistakes=[], asked=asked)

    assert _topics(profile) == {("kopfrechnen-mit-zehnerpotenzen", "Kopfrechnen mit Zehnerpotenzen"): 1}


# ── Through the parent's route ──────────────────────────────────────────────


@pytest.fixture
def parent_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_k: {"user_id": user_id, "role": "student", "account_status": "active"},
    )
    monkeypatch.setattr(
        parents.question_repo,
        "list_questions_by_student",
        lambda _student_id, limit=500, **_k: {"Items": [dict(row, PK="Q", SK="META") for row in QUESTIONS]},
    )
    monkeypatch.setattr(parents.question_repo, "is_question_record", lambda _row: True)
    monkeypatch.setattr(parents.asked_knowledge_repo, "list_for_student", lambda *_a, **_k: [])
    asked_locales: list[str] = []

    def client(locale: str) -> TestClient:
        fake_evidence.install(
            monkeypatch,
            fake_evidence.evidence(
                CHILD, catalog=_catalog(locale), locale=locale, attempts=MISTAKES
            ),
        )
        installed = student_evidence.for_student

        def for_student(student_id: str, *, locale: str = "de", **kwargs: Any):
            # The catalog the evidence reads is the one in the request's language.
            asked_locales.append(locale)
            return installed(student_id, locale=locale, **kwargs)

        monkeypatch.setattr(student_evidence, "for_student", for_student)
        app = FastAPI()
        app.include_router(parents.router, prefix="/parents")
        app.add_middleware(RequestLocaleMiddleware)
        install_actor_overrides(app, {"sub": "parent-390", "role": "parent"})
        return TestClient(app)

    client.locales = asked_locales  # type: ignore[attr-defined]
    yield client
    locale_service.set_request_locale(None)


@pytest.mark.parametrize("locale", ["de", "en"])
def test_the_parent_reads_one_weak_topic_per_unit_in_the_requested_language(
    parent_client, locale: str
) -> None:
    response = parent_client(locale).get(
        f"/parents/me/children/{CHILD}/learning-profile", headers={"Accept-Language": locale}
    )

    assert response.status_code == 200, response.text
    assert parent_client.locales == [locale]
    topics = {(t["topicId"], t["label"]) for t in response.json()["weakTopics"]}
    assert topics == {
        (unit_id, UNIT_TITLES[unit_id][locale])
        for unit_id in ("brueche-u2", "brueche-u1", "gleichungen-u1")
    }


def test_the_parent_dashboard_names_weak_topics_as_the_curriculum_does(parent_client) -> None:
    response = parent_client("de").get(
        f"/parents/me/children/{CHILD}/summary", headers={"Accept-Language": "de"}
    )

    assert response.status_code == 200, response.text
    named = response.json()["weakTopics"]
    assert "Brüche rechnen" in named
    for raw in ("brueche", "brueche-u2", "Calculating with fractions", "calculating-with-fractions"):
        assert raw not in named


@pytest.mark.parametrize("locale", ["de", "en"])
def test_a_mistake_in_the_history_names_its_unit_never_the_topic_id(parent_client, locale: str) -> None:
    response = parent_client(locale).get(
        f"/parents/me/children/{CHILD}/history", headers={"Accept-Language": locale}
    )

    assert response.status_code == 200, response.text
    assert parent_client.locales == [locale]
    mistakes = [e for e in response.json()["items"] if e["type"] == "practice_mistake"]
    assert [e["summary"] for e in mistakes] == [UNIT_TITLES["brueche-u2"][locale]] * 2
