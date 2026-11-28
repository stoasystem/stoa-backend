"""The weekly report tells what the student solved alone from what they solved with Ask (#450).

The counts come from the answer receipts' "asked AI first" mark (#449): this
week's newly solved exercises, on the student's own and after asking, and the
stars lit this week, those lit mostly after asking named. The model is given
them and told how to write about them; the report STOA writes itself says the
same in the parent's language. A week without help from the AI says nothing
about the AI at all.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from string import Formatter
from typing import Any

import pytest

from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.services import (
    knowledge_mastery_service,
    locale_service,
    message_catalog,
    report_service,
    student_evidence,
)
from stoa.services.knowledge_mastery_service import LitFact, LitSource
from stoa.services.message_catalog import weekly_report as weekly_report_catalog

LOCALES = sorted(locale_service.SUPPORTED_LOCALES)
WEEK = "2026-06-01"
START = datetime(2026, 6, 1, tzinfo=UTC)
END = datetime(2026, 6, 8, tzinfo=UTC)
IN_WEEK = "2026-06-03T10:00:00+00:00"
BEFORE = "2026-05-20T10:00:00+00:00"
AFTER = "2026-06-09T10:00:00+00:00"

CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 0},
        {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "Erweitern", "order": 1},
        {"id": "u3", "subjectId": "math", "topicId": "t1", "title": "Teilen", "order": 2},
        {"id": "u4", "subjectId": "math", "topicId": "t1", "title": "Vergleichen", "order": 3},
    ],
    "lessons": [
        {"id": f"l{n}", "unitId": f"u{n}", "subjectId": "math", "topicId": "t1", "order": 0}
        for n in range(1, 5)
    ],
    "rolloutSubjects": ["math"],
}

# Mentions of the AI, in any of the four languages.
_AI_WORDS = re.compile(r"\b(AI|KI|IA)\b")


def _right(challenge: str, at: str = IN_WEEK, unit: str = "u1", **fields: Any) -> dict[str, Any]:
    return {"challenge_id": challenge, "correct": True, "unit_id": unit, "created_at": at, **fields}


# ── the counts ──────────────────────────────────────────────────────────────


def test_this_weeks_newly_solved_exercises_are_split_by_whether_the_student_asked_ai() -> None:
    evidence = fake_evidence.evidence(
        catalog=CATALOG,
        attempts=[
            _right("alone"),
            _right("helped", asked_ai=True),
            # Answered right both ways this week: shown on the student's own.
            _right("both", asked_ai=True),
            _right("both"),
            # Solved before the week: not new, however it was answered now.
            _right("old", at=BEFORE),
            _right("old", asked_ai=True),
            # After the week, or never checked, or wrong: none of them count.
            _right("later", at=AFTER),
            _right("reported", self_reported=True),
            {"challenge_id": "wrong", "correct": False, "unit_id": "u1", "created_at": IN_WEEK},
        ],
    )

    assert evidence.right_answers_between(START, END) == student_evidence.RightAnswers(
        independent=2, asked_ai=1
    )


def test_the_stars_lit_this_week_are_the_lightings_recorded_in_it_in_catalog_order() -> None:
    evidence = fake_evidence.evidence(
        catalog=CATALOG,
        ledger_open=True,
        lit=[
            LitFact(unit_id="u3", lit_at=IN_WEEK, source=LitSource.QUIZ),
            LitFact(unit_id="u1", lit_at=IN_WEEK, source=LitSource.OBSERVED),
            # The ledger opening is history, not a lighting this week.
            LitFact(unit_id="u2", lit_at=IN_WEEK, source=LitSource.BACKFILLED),
            LitFact(unit_id="u4", lit_at=BEFORE, source=LitSource.OBSERVED),
        ],
    )

    assert knowledge_mastery_service.lit_between(evidence, START, END) == ("u1", "u3")


# ── the payload the report is written from ──────────────────────────────────


def _install_week(monkeypatch: pytest.MonkeyPatch, *, locale: str, attempts, lit) -> None:
    fake_evidence.install(
        monkeypatch,
        fake_evidence.evidence(
            "student-1", catalog=CATALOG, attempts=attempts, lit=lit, ledger_open=True
        ),
    )
    monkeypatch.setattr(report_service.locale_service, "stored_locale", lambda _user_id: locale)
    monkeypatch.setattr(
        report_service.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {"user_id": user_id, "name": "Mia" if user_id == "student-1" else "P"},
    )
    monkeypatch.setattr(
        report_service,
        "_get_linked_student_profile",
        lambda _parent, student: {"user_id": student, "name": "Mia", "grade": 5},
    )
    # No sessions and no help requests: an empty table.
    db_table.install(FakeTable())
    monkeypatch.setattr(
        report_service.asked_knowledge_repo, "list_for_student", lambda *_args, **_kwargs: []
    )


def test_the_report_payload_carries_both_counts_and_the_stars_lit_mostly_with_ai(monkeypatch) -> None:
    _install_week(
        monkeypatch,
        locale="fr",
        attempts=[
            _right("a1", unit="u1"),
            _right("a2", unit="u1"),
            _right("h1", unit="u2", asked_ai=True),
            _right("h2", unit="u2", asked_ai=True),
            _right("h3", unit="u2"),
        ],
        lit=[
            LitFact(unit_id="u1", lit_at=IN_WEEK, source=LitSource.OBSERVED),
            LitFact(unit_id="u2", lit_at=IN_WEEK, source=LitSource.OBSERVED),
        ],
    )

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", WEEK)

    assert payload["locale"] == "fr"
    assert payload["answeredRight"] == {"onOwn": 3, "afterAskingAi": 2}
    # u2's right answers came two of three after asking: mostly with AI.
    assert payload["starsLit"] == {"onOwn": 1, "mostlyAfterAskingAi": ["Erweitern"]}

    model_input = report_service.build_bedrock_report_input(payload)
    assert model_input["language"] == "fr"
    assert model_input["answeredRight"] == {"onOwn": 3, "afterAskingAi": 2}
    assert model_input["starsLit"] == {"onOwn": 1, "mostlyAfterAskingAi": ["Erweitern"]}


def test_a_week_whose_lightings_cannot_be_read_still_has_its_report(monkeypatch) -> None:
    _install_week(monkeypatch, locale="de", attempts=[_right("a1")], lit=[])

    def unreadable(_evidence, _start, _end):
        raise RuntimeError("activity unavailable")

    monkeypatch.setattr(report_service.knowledge_mastery_service, "lit_between", unreadable)

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", WEEK)

    assert payload["answeredRight"] == {"onOwn": 1, "afterAskingAi": 0}
    assert payload["starsLit"] == {"onOwn": 0, "mostlyAfterAskingAi": []}


# ── what the model is asked ─────────────────────────────────────────────────


def _payload(locale: str, *, on_own: int, with_ai: int, stars_on_own: int = 0, stars_with_ai=()) -> dict:
    return {
        "locale": locale,
        "student": {"id": "student-1", "name": "Mia", "grade": 5},
        "week": {"start": "2026-06-01", "end": "2026-06-07"},
        "metrics": {
            "questionsAsked": 2,
            "aiResolved": 2,
            "teacherHelpRequests": 0,
            "practiceLessonsCompleted": 1,
            "mistakesLogged": 1,
        },
        "answeredRight": {"onOwn": on_own, "afterAskingAi": with_ai},
        "starsLit": {"onOwn": stars_on_own, "mostlyAfterAskingAi": list(stars_with_ai)},
        "weakTopics": [],
        "activities": [],
        "sourceCounts": {},
    }


def test_the_rules_are_the_same_for_every_student_and_only_the_input_varies() -> None:
    """Fixed rules first, the student's week after: a cacheable prefix (#442)."""
    one = report_service.weekly_report_request(_payload("de", on_own=1, with_ai=0))
    other = report_service.weekly_report_request(
        _payload("it", on_own=0, with_ai=3, stars_with_ai=["Kürzen"])
    )

    assert one["system"] == other["system"]
    assert one["tool"] == other["tool"]
    for rule in ("answeredRight", "afterAskingAi", "mostlyAfterAskingAi", "`language`"):
        assert rule in one["system"]
    sent = json.loads(other["messages"][0]["content"])
    assert sent["language"] == "it"
    assert sent["answeredRight"] == {"onOwn": 0, "afterAskingAi": 3}
    assert sent["starsLit"]["mostlyAfterAskingAi"] == ["Kürzen"]


def test_a_payload_in_no_known_language_is_written_in_the_default_one() -> None:
    payload = _payload("xx", on_own=1, with_ai=0)

    assert report_service.build_bedrock_report_input(payload)["language"] == "de"


# ── the report STOA writes itself ───────────────────────────────────────────


def _text(content: dict[str, Any]) -> str:
    return json.dumps(content, ensure_ascii=False)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_fallback_report_says_what_was_solved_alone_and_with_ai(locale) -> None:
    content = report_service.build_deterministic_report_fallback(
        _payload(locale, on_own=3, with_ai=2, stars_on_own=1, stars_with_ai=["Kürzen", "Teilen"])
    )

    def copy(key: str, **values: Any) -> str:
        return message_catalog.text(f"weekly_report.{key}", locale, **values)

    assert copy("summary.solved_split", student="Mia", total=5, on_own=3, with_ai=2) in content["summary"]
    assert copy("summary.stars_lit", count=3) in content["summary"]
    assert copy("summary.stars_mostly_with_ai", stars="Kürzen, Teilen") in content["summary"]
    assert copy("recommendation.retry_without_ai", student="Mia", stars="Kürzen, Teilen") in (
        content["recommendations"]
    )
    # The rest of the report is in the same language.
    assert content["strengths"][0] == copy("strength.questions")


def test_the_english_fallback_reads_as_a_sentence() -> None:
    content = report_service.build_deterministic_report_fallback(
        _payload("en", on_own=3, with_ai=2, stars_with_ai=["Kürzen"])
    )

    assert content["summary"] == (
        "This week (1 June 2026 to 7 June 2026), Mia asked 2 question(s), completed 1 practice "
        "lesson(s) and logged 1 mistake(s). Of 5 newly solved exercise(s), Mia solved 3 on their "
        "own and 2 with help from the AI. 1 new star(s) lit up on the star map. Lit mostly with "
        "help from the AI: Kürzen."
    )
    assert "Encourage Mia to practise Kürzen again without asking the AI." in content["recommendations"]


@pytest.mark.parametrize("locale", LOCALES)
def test_a_student_who_never_asked_ai_reads_nothing_about_it(locale) -> None:
    content = report_service.build_deterministic_report_fallback(
        _payload(locale, on_own=4, with_ai=0, stars_on_own=2)
    )

    assert not _AI_WORDS.search(_text(content)), content
    assert message_catalog.text(
        "weekly_report.summary.solved_on_own", locale, student="Mia", on_own=4
    ) in content["summary"]


@pytest.mark.parametrize("locale", LOCALES)
def test_a_week_with_nothing_solved_adds_no_sentence_about_it(locale) -> None:
    payload = _payload(locale, on_own=0, with_ai=0)

    content = report_service.build_deterministic_report_fallback(payload)

    assert content["summary"] == message_catalog.text(
        "weekly_report.summary.activity",
        locale,
        week=message_catalog.text(
            "email.weekly_report.week_range",
            locale,
            start=report_service.email_layout.format_date("2026-06-01", locale),
            end=report_service.email_layout.format_date("2026-06-07", locale),
        ),
        student="Mia",
        questions=2,
        lessons=1,
        mistakes=1,
    )


def test_exercises_solved_with_nothing_else_are_activity() -> None:
    payload = _payload("en", on_own=0, with_ai=2)
    payload["metrics"] = {key: 0 for key in payload["metrics"]}

    content = report_service.build_deterministic_report_fallback(payload)

    assert "Of 2 newly solved exercise(s), Mia solved 0 on their own and 2 with help" in content["summary"]


# ── the copy ────────────────────────────────────────────────────────────────


def _params(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


@pytest.mark.parametrize("key", sorted(weekly_report_catalog.TEXT))
def test_every_fallback_sentence_has_four_languages_with_the_same_params(key) -> None:
    variants = weekly_report_catalog.TEXT[key]

    assert set(variants) == set(LOCALES)
    assert all(variants[locale].strip() for locale in LOCALES)
    assert len({frozenset(_params(variants[locale])) for locale in LOCALES}) == 1, variants
    assert "ß" not in variants["de"]
    assert key in message_catalog.TEXT
