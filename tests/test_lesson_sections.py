"""A student reads a lesson's explanation cards before its exercises (#465).

The cards are the lesson's `sections`, written by curriculum authoring - the AI
lesson draft (#441, `scripts/ai_lesson_draft.py`) writes them as
`[{id, title, body, translations: {en|fr|it: {title, body}}}]`, with German
`title` and `body`. Both student lesson reads return them as `[{id, title, body}]`
in the student's language, falling back to German, in the stored order; the raw
`translations` stay on the server. A bad shape is a validation issue, so a
migration dry run reports it before anything is written.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from fakes import student_evidence as fake_evidence
from stoa.routers import practice
from stoa.services import (
    curriculum_ops_service,
    lesson_sections,
    practice_projection_service,
)
from stoa.services.curriculum_issues import IssueCode

# The shape `scripts/ai_lesson_draft.py` writes; `it` is left out of the second
# card so the fallback to German shows.
SECTIONS = [
    {
        "id": "card-1",
        "title": "Kraft",
        "body": "Eine Kraft $F$ wird in Newton gemessen: $1\\,\\mathrm{N}$.",
        "translations": {
            "en": {"title": "Force", "body": "A force $F$ is measured in newtons."},
            "fr": {"title": "Force", "body": "Une force $F$ se mesure en newtons."},
            "it": {"title": "Forza", "body": "Una forza $F$ si misura in newton."},
        },
    },
    {
        "id": "card-2",
        "title": "Gewicht",
        "body": "$F_G = m \\cdot g$",
        "translations": {
            "en": {"title": "Weight", "body": "$F_G = m \\cdot g$ (weight)"},
            "fr": {"title": "Poids", "body": "$F_G = m \\cdot g$ (poids)"},
        },
    },
]

LESSON = {
    "lesson_id": "lesson-forces-1",
    "unit_id": "unit-forces",
    "subject_id": "physics",
    "topic_id": "forces",
    "grade_level": "lower_secondary",
    "title": "Kraft und Gewicht",
    "objective": "Kräfte messen.",
    "status": "active",
    "order": 1,
    "sections": SECTIONS,
}

CHALLENGE = {
    "challenge_id": "challenge-forces-1",
    "lesson_id": "lesson-forces-1",
    "unit_id": "unit-forces",
    "subject_id": "physics",
    "topic_id": "forces",
    "prompt": "Wie schwer ist 1 kg?",
    "correct_answer": "9.81 N",
    "explanation": "F = m g",
    "status": "active",
    "order": 1,
}


# ── the projection ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        (
            "de",
            [
                {"id": "card-1", "title": "Kraft", "body": SECTIONS[0]["body"]},
                {"id": "card-2", "title": "Gewicht", "body": "$F_G = m \\cdot g$"},
            ],
        ),
        (
            "fr",
            [
                {"id": "card-1", "title": "Force", "body": "Une force $F$ se mesure en newtons."},
                {"id": "card-2", "title": "Poids", "body": "$F_G = m \\cdot g$ (poids)"},
            ],
        ),
        (
            "it",
            [
                {"id": "card-1", "title": "Forza", "body": "Una forza $F$ si misura in newton."},
                # No Italian for this card: the German original, in its place.
                {"id": "card-2", "title": "Gewicht", "body": "$F_G = m \\cdot g$"},
            ],
        ),
    ],
)
def test_sections_are_shown_in_the_reader_language_in_stored_order(locale, expected) -> None:
    practice_lesson = practice_projection_service.build_lesson_preview(LESSON, [], locale=locale)
    curriculum_lesson = practice_projection_service.build_curriculum_lesson_preview(
        LESSON, [], locale=locale
    )

    assert practice_lesson["sections"] == expected
    assert curriculum_lesson["sections"] == expected


def test_a_translation_missing_its_body_falls_back_whole_to_german() -> None:
    half = [{**SECTIONS[0], "translations": {"en": {"title": "Force", "body": " "}}}]

    assert lesson_sections.localized(half, "en") == [
        {"id": "card-1", "title": "Kraft", "body": SECTIONS[0]["body"]}
    ]


def test_a_lesson_without_sections_gets_an_empty_list_and_nothing_else_changes() -> None:
    bare = {key: value for key, value in LESSON.items() if key != "sections"}

    with_cards = practice_projection_service.build_lesson_preview(LESSON, [], locale="en")
    without = practice_projection_service.build_lesson_preview(bare, [], locale="en")
    curriculum = practice_projection_service.build_curriculum_lesson_preview(bare, [], locale="en")

    assert without["sections"] == []
    assert curriculum["sections"] == []
    assert {k: v for k, v in with_cards.items() if k != "sections"} == {
        k: v for k, v in without.items() if k != "sections"
    }


def test_a_malformed_stored_card_is_left_out_rather_than_failing_the_lesson() -> None:
    stored = [{"id": "card-0", "title": "", "body": "x"}, "not a card", SECTIONS[1]]

    assert [card["id"] for card in lesson_sections.localized(stored, "de")] == ["card-2"]


# ── the student routes ───────────────────────────────────────────────────────


def _student_client(monkeypatch, lesson: dict, locale: str) -> TestClient:
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda **_kwargs: [lesson])
    monkeypatch.setattr(practice.practice_repo, "get_lesson", lambda _id: lesson)
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda _id: [CHALLENGE])
    monkeypatch.setattr(
        practice.practice_repo,
        "get_all_challenges",
        lambda lesson_id=None, subject_id=None, topic_id=None: [CHALLENGE],
    )
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: locale)
    fake_evidence.install(monkeypatch, fake_evidence.evidence("student-1"))
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    return TestClient(app)


@pytest.mark.parametrize(
    "path", ["/practice/lessons/lesson-forces-1", "/practice/curriculum/lessons/lesson-forces-1"]
)
def test_both_student_lesson_reads_return_the_cards_without_raw_translations(
    monkeypatch, path: str
) -> None:
    client = _student_client(monkeypatch, LESSON, "fr")

    response = client.get(path)

    assert response.status_code == 200, response.text
    assert [card["title"] for card in response.json()["sections"]] == ["Force", "Poids"]
    assert "translations" not in response.text
    # The exercises stay answer-free beside the cards.
    assert "9.81 N" not in response.text


def test_a_draft_lesson_with_cards_stays_hidden_from_students(monkeypatch) -> None:
    client = _student_client(monkeypatch, {**LESSON, "status": "draft"}, "de")

    response = client.get("/practice/curriculum/lessons/lesson-forces-1")

    assert response.status_code == 404


def test_both_student_lesson_reads_declare_the_card_shape_in_openapi() -> None:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    schema = app.openapi()
    components = schema["components"]["schemas"]

    for path in ("/practice/lessons/{lesson_id}", "/practice/curriculum/lessons/{lesson_id}"):
        ok = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
        ref = ok["schema"]["$ref"].rsplit("/", 1)[-1]
        sections = components[ref]["properties"]["sections"]
        card = components[sections["items"]["$ref"].rsplit("/", 1)[-1]]
        assert set(card["properties"]) == {"id", "title", "body"}
        assert set(card["required"]) == {"id", "title", "body"}


# ── validation on write ──────────────────────────────────────────────────────


def _issues(sections: object) -> list[tuple[str, str]]:
    return [(field, issue.code.value) for field, issue in lesson_sections.issues(sections)]


def test_the_ai_draft_shape_and_no_sections_are_valid() -> None:
    assert _issues(SECTIONS) == []
    assert _issues(None) == []
    assert _issues([]) == []


@pytest.mark.parametrize(
    ("sections", "expected"),
    [
        ({"id": "card-1"}, [("sections", IssueCode.SECTIONS_NOT_A_LIST)]),
        (["card"], [("sections[0]", IssueCode.SECTION_FIELD_MISSING)]),
        ([{"id": "card-1", "title": "Kraft"}], [("sections[0]", IssueCode.SECTION_FIELD_MISSING)]),
        (
            [SECTIONS[0], {**SECTIONS[1], "id": "card-1"}],
            [("sections[1].id", IssueCode.SECTION_ID_REPEATED)],
        ),
        (
            [{**SECTIONS[0], "translations": ["en"]}],
            [("sections[0].translations", IssueCode.TRANSLATIONS_NOT_A_MAP)],
        ),
        (
            [{**SECTIONS[0], "translations": {"es": {"title": "Fuerza", "body": "..."}}}],
            [("sections[0].translations.es", IssueCode.TRANSLATION_LOCALE_UNSUPPORTED)],
        ),
        (
            [{**SECTIONS[0], "translations": {"en": {"title": "Force"}}}],
            [("sections[0].translations.en", IssueCode.SECTION_TRANSLATION_INCOMPLETE)],
        ),
    ],
)
def test_a_bad_sections_shape_is_an_issue(sections, expected) -> None:
    assert _issues(sections) == [(field, code.value) for field, code in expected]


def test_the_missing_card_fields_are_named() -> None:
    [(_, issue)] = lesson_sections.issues([{"id": "card-1", "title": " "}])

    assert issue.values == {"fields": "title, body"}


def test_a_migration_dry_run_reports_bad_sections(monkeypatch) -> None:
    from test_curriculum_migration import _install_curriculum_repo, _manifest
    from stoa.services import curriculum_migration_service

    _install_curriculum_repo(monkeypatch)
    operator = {
        "sub": "migration-operator-1",
        "role": "teacher",
        "capabilities": {curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted"},
    }
    good = _manifest()
    good["lessons"][0]["sections"] = SECTIONS
    bad = _manifest()
    bad["lessons"][0]["sections"] = [{"id": "card-1", "title": "Kraft"}]

    good_run = curriculum_migration_service.dry_run(good, operator)
    bad_run = curriculum_migration_service.dry_run(bad, operator)

    assert good_run["rows"][0]["validationIssues"] == []
    assert good_run["rows"][0]["lesson"]["sections"] == SECTIONS
    assert bad_run["publishReady"] is False
    assert bad_run["summary"]["errors"] == 1
    [issue] = bad_run["rows"][0]["validationIssues"]
    assert (issue["field"], issue["code"]) == ("sections[0]", "section_field_missing")


def test_a_lesson_drafted_with_cards_reaches_no_student_until_published(monkeypatch) -> None:
    # The AI draft writes its lessons with `publish: false`. Only publishing
    # projects a lesson into the practice partition the student routes read,
    # so its cards are stored but shown to no one.
    from test_curriculum_migration import _install_curriculum_repo, _manifest
    from stoa.services import curriculum_migration_service

    state = _install_curriculum_repo(monkeypatch)
    operator = {
        "sub": "migration-operator-1",
        "role": "teacher",
        "capabilities": {curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted"},
    }
    manifest = _manifest(publish=False)
    manifest["lessons"][0]["sections"] = SECTIONS
    planned = curriculum_migration_service.dry_run(manifest, operator)

    curriculum_migration_service.apply_migration(
        planned["migrationId"], manifest, planned["confirmationToken"], operator
    )

    [version] = state["versions"].values()
    assert version["lesson"]["sections"] == SECTIONS
    assert state["projections"] == []
