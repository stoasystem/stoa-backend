"""错因: why a wrong answer was wrong, tagged on distractors when authored (#452).

Each wrong option of a choice exercise may carry an error cause - one of four
categories and the misconception it stands for, one sentence in each locale.
The exercise data and the curriculum migration manifest accept it, and the
dry run refuses an unknown category. A student who picks a tagged distractor
gets that cause on their receipt; any other wrong answer is "unclassified".
The student's evidence tallies the recent causes. No model is called for any
of it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable

from stoa.services import (
    answer_recording,
    curriculum_migration_service,
    curriculum_ops_service,
    error_causes,
    student_evidence,
)
from test_answer_recording import _Writes
from test_curriculum_publish_projection import install_seeded_table
from test_editorial_batch_to_migration import OPERATOR

DENOMINATORS = {
    "de": "Addiert auch die Nenner.",
    "en": "Adds the denominators too.",
    "fr": "Additionne aussi les dénominateurs.",
    "it": "Somma anche i denominatori.",
}
SIGN = {
    "de": "Verliert das Vorzeichen.",
    "en": "Drops the sign.",
    "fr": "Oublie le signe.",
    "it": "Dimentica il segno.",
}
ADDS_DENOMINATORS = {"category": "structural", "misconception": DENOMINATORS}

CHOICE: dict[str, Any] = {
    "challenge_id": "exercise-1",
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "brueche",
    "unit_id": "brueche-u1",
    "type": "multiple_choice",
    "prompt": "Berechne 1/5 + 1/5.",
    "options": ["2/5", "2/10", "1/5"],
    "correct_answer": "2/5",
    "explanation": "Gleiche Nenner: nur die Zähler addieren.",
    "option_error_causes": [None, ADDS_DENOMINATORS, None],
    "translations": {
        "fr": {
            "prompt": "Calcule 1/5 + 1/5.",
            "options": ["2/5", "deux dixièmes", "un cinquième"],
            "correct_answer": "2/5",
        }
    },
}


# ── authoring ────────────────────────────────────────────────────────────────


def _authored(**extra: Any) -> dict[str, Any]:
    return {
        "exerciseId": "lesson-1-q01",
        "type": "multiple_choice",
        "prompt": "Berechne 1/5 + 1/5.",
        "options": ["2/5", "2/10", "1/5"],
        "answerKey": "2/5",
        "explanation": "Gleiche Nenner: nur die Zähler addieren.",
        "difficulty": "practice",
        **extra,
    }


def _issues(exercise: dict[str, Any]) -> list[tuple[str, str]]:
    [stored] = curriculum_ops_service._exercise_payloads("lesson-1", [exercise])  # noqa: SLF001
    return [
        (issue["field"], issue["code"])
        for issue in curriculum_ops_service._validation_issues(  # noqa: SLF001
            {}, [stored], level="draft"
        )
        if issue["field"].startswith("exercises[0].option_error_causes")
    ]


def test_an_authored_cause_is_stored_beside_its_option() -> None:
    [stored] = curriculum_ops_service._exercise_payloads(  # noqa: SLF001
        "lesson-1",
        [_authored(optionErrorCauses=[None, {"category": " Structural ", "misconception": DENOMINATORS}, {}])],
    )

    assert stored["option_error_causes"] == [None, ADDS_DENOMINATORS, None]
    assert _issues(_authored(optionErrorCauses=[None, ADDS_DENOMINATORS, None])) == []


def test_an_exercise_without_causes_stores_none() -> None:
    [stored] = curriculum_ops_service._exercise_payloads("lesson-1", [_authored()])  # noqa: SLF001
    [blank] = curriculum_ops_service._exercise_payloads(  # noqa: SLF001
        "lesson-1", [_authored(optionErrorCauses=[None, None, {}])]
    )

    assert "option_error_causes" not in stored
    assert "option_error_causes" not in blank


@pytest.mark.parametrize(
    ("causes", "code"),
    [
        ([None, {"category": "careless", "misconception": DENOMINATORS}, None], "error_cause_category_unknown"),
        ([None, {"category": "structural"}, None], "error_cause_misconception_missing"),
        (
            [None, {"category": "deviation", "misconception": {"de": "Nur Deutsch."}}, None],
            "error_cause_misconception_missing",
        ),
        ([None, ADDS_DENOMINATORS], "option_error_causes_mismatch"),
        ([ADDS_DENOMINATORS, None, None], "error_cause_on_answer"),
        ("structural", "option_error_causes_mismatch"),
    ],
    ids=["unknown category", "no misconception", "one locale only", "one short", "on the key", "not a list"],
)
def test_a_cause_the_vocabulary_does_not_allow_is_reported(causes: Any, code: str) -> None:
    assert [found for _field, found in _issues(_authored(optionErrorCauses=causes))] == [code]


def test_a_typed_answer_exercise_carries_no_causes() -> None:
    typed = _authored(type="text_input", options=[], optionErrorCauses=[ADDS_DENOMINATORS])

    assert [code for _field, code in _issues(typed)] == ["option_error_causes_mismatch"]


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def _manifest(causes: Any) -> dict[str, Any]:
    return {
        "source": {"sourceId": "zap1", "sourceVersion": "2026-11", "sourceType": "manifest"},
        "lessons": [
            {
                "publicLessonId": "zap1-error-cause-001",
                "title": "Brüche addieren",
                "objective": "Gleichnamige Brüche addieren.",
                "subjectId": "math",
                "topicId": "brueche",
                "unitId": "brueche-u2",
                "gradeLevel": "grade_6_primary",
                "exercises": [
                    _authored(
                        exerciseId="zap1-error-cause-001-q01",
                        skills=["brueche-addieren"],
                        optionErrorCauses=causes,
                    )
                ],
            }
        ],
    }


def test_the_migration_dry_run_carries_a_known_cause(table: FakeTable) -> None:
    preview = curriculum_migration_service.dry_run(
        _manifest([None, ADDS_DENOMINATORS, None]), OPERATOR
    )

    [row] = preview["rows"]
    assert row["action"] == "create", row["validationIssues"]
    assert row["exercises"][0]["option_error_causes"] == [None, ADDS_DENOMINATORS, None]


def test_the_migration_dry_run_refuses_an_unknown_category(table: FakeTable) -> None:
    preview = curriculum_migration_service.dry_run(
        _manifest([None, {"category": "careless", "misconception": DENOMINATORS}, None]), OPERATOR
    )

    [row] = preview["rows"]
    assert row["action"] == "error"
    assert [(issue["field"], issue["code"]) for issue in row["validationIssues"]] == [
        ("exercises[0].option_error_causes[1].category", "error_cause_category_unknown")
    ]
    assert preview["summary"]["errors"] == 1


# ── recording ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("answer", "locale"),
    [("2/10", "de"), (" 2/10 ", "de"), ("deux dixièmes", "fr"), ("2/10", "fr")],
    ids=["as shown", "spaced", "translated", "stored language after switching"],
)
def test_picking_a_tagged_distractor_records_its_cause(
    monkeypatch: pytest.MonkeyPatch, answer: str, locale: str
) -> None:
    recorded = _Writes(monkeypatch, [CHOICE])

    result = answer_recording.answer_practice("student-1", CHOICE, answer, locale=locale)

    [receipt] = recorded.by_kind["receipt"]
    assert result.correct is False
    assert receipt["error_cause"] == ADDS_DENOMINATORS


@pytest.mark.parametrize(
    "exercise",
    [
        CHOICE,
        {**CHOICE, "option_error_causes": None},
        {**CHOICE, "type": "text_input", "options": None, "option_error_causes": None},
    ],
    ids=["untagged distractor", "no causes at all", "typed answer"],
)
def test_any_other_wrong_answer_is_unclassified(
    monkeypatch: pytest.MonkeyPatch, exercise: dict[str, Any]
) -> None:
    recorded = _Writes(monkeypatch, [exercise])

    answer_recording.answer_practice("student-1", exercise, "1/5", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["error_cause"] == {"category": "unclassified"}


def test_a_right_answer_has_no_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [CHOICE])

    answer_recording.answer_practice("student-1", CHOICE, "2/5", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt.get("error_cause") is None


def test_a_cause_stored_wrong_is_recorded_as_unclassified(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row written before validation, or edited by hand, never breaks an answer."""
    broken = {**CHOICE, "option_error_causes": [None, {"category": "careless"}, None]}
    recorded = _Writes(monkeypatch, [broken])

    answer_recording.answer_practice("student-1", broken, "2/10", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["error_cause"] == {"category": "unclassified"}


def test_the_stored_exercise_is_not_changed_by_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    before = copy.deepcopy(CHOICE)
    _Writes(monkeypatch, [CHOICE])

    answer_recording.answer_practice("student-1", CHOICE, "2/10", locale="fr")

    assert CHOICE == before


# ── the evidence ─────────────────────────────────────────────────────────────


def _wrong(n: int, cause: dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    row = {
        "challenge_id": f"c{n}",
        "attempt_id": f"a{n:02d}",
        "correct": False,
        "unit_id": "u1",
        "created_at": f"2026-11-{n:02d}T10:00:00+00:00",
        **fields,
    }
    if cause is not None:
        row["error_cause"] = cause
    return row


SIGN_CAUSE = {"category": "deviation", "misconception": SIGN}


def test_the_evidence_tallies_the_recent_causes_most_common_first() -> None:
    evidence = fake_evidence.evidence(
        attempts=[
            _wrong(1, SIGN_CAUSE),
            _wrong(2, ADDS_DENOMINATORS),
            _wrong(3, ADDS_DENOMINATORS),
            _wrong(4, {"category": "unclassified"}),
            # A receipt written before causes were recorded.
            _wrong(5),
            _wrong(6, SIGN_CAUSE),
            _wrong(7, ADDS_DENOMINATORS),
            # Right, or never checked, is no mistake to explain.
            {**_wrong(8, SIGN_CAUSE), "correct": True},
            _wrong(9, SIGN_CAUSE, self_reported=True),
        ]
    )

    tally = evidence.recent_error_causes

    assert [(item.category, item.misconception_in("en"), item.count) for item in tally] == [
        ("structural", DENOMINATORS["en"], 3),
        ("deviation", SIGN["en"], 2),
        ("unclassified", "", 2),
    ]
    assert evidence.most_common_error_cause == tally[0]
    assert tally[0].misconception_in("it") == DENOMINATORS["it"]


def test_only_the_most_recent_mistakes_are_tallied() -> None:
    old = [_wrong(n, SIGN_CAUSE) for n in range(1, 6)]
    recent = [
        _wrong(n, ADDS_DENOMINATORS)
        for n in range(6, 6 + student_evidence.RECENT_ERROR_CAUSE_ANSWERS)
    ]

    evidence = fake_evidence.evidence(attempts=[*old, *recent])

    assert [(item.category, item.count) for item in evidence.recent_error_causes] == [
        ("structural", student_evidence.RECENT_ERROR_CAUSE_ANSWERS)
    ]


def test_a_tie_goes_to_the_cause_seen_last() -> None:
    evidence = fake_evidence.evidence(
        attempts=[_wrong(1, SIGN_CAUSE), _wrong(2, ADDS_DENOMINATORS)]
    )

    assert [item.category for item in evidence.recent_error_causes] == ["structural", "deviation"]


def test_unclassified_mistakes_alone_name_no_common_cause() -> None:
    evidence = fake_evidence.evidence(attempts=[_wrong(1), _wrong(2, {"category": "unclassified"})])

    assert [(item.category, item.count) for item in evidence.recent_error_causes] == [
        ("unclassified", 2)
    ]
    assert evidence.most_common_error_cause is None


def test_the_tally_reads_the_answers_once() -> None:
    evidence = fake_evidence.evidence(attempts=[_wrong(1, ADDS_DENOMINATORS)])

    assert evidence.recent_error_causes is evidence.recent_error_causes
    assert evidence.mistakes
    assert evidence.source.reads == ["attempts"]


def test_the_vocabulary_is_four_categories() -> None:
    assert error_causes.CATEGORIES == ("structural", "deviation", "application", "metacognitive")
    assert error_causes.UNCLASSIFIED not in error_causes.CATEGORIES
