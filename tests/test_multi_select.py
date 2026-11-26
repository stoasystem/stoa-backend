"""Choose-several exercises: a set of options, picked in a list or in the figure (#593).

The two sample exercises (`fixtures/multi_select_samples_593.json`) go through a
real migration - dry run, apply, publish - into the practice partition of a
table double, and are answered there. Around them: what the student sends and
how it is judged, what authoring refuses, and that no read a student makes
before answering carries the key.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db.repositories import practice_repo, review_repo
from stoa.services import (
    answer_judging,
    answer_recording,
    curriculum_migration_service,
    curriculum_ops_service,
    curriculum_service,
    error_causes,
    exercise_localization,
    figure_svg,
    multi_select,
    practice_projection_service,
    review_service,
)
from stoa.services.curriculum_issues import Issue, IssueCode
from stoa.services.quiz import _exercise_preview as quiz_exercise_preview
from test_curriculum_publish_projection import install_seeded_table

SAMPLES = json.loads(
    (Path(__file__).parent / "fixtures" / "multi_select_samples_593.json").read_text(encoding="utf-8")
)
LESSON_ID = "multi-select-samples-593"
PRIMES = f"{LESSON_ID}-q01"
HOTSPOTS = f"{LESSON_ID}-q02"
OPERATOR = {
    "sub": "migration-operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    },
}
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """The samples migrated and published into a seeded table double."""
    table = install_seeded_table(monkeypatch)
    planned = curriculum_migration_service.dry_run(deepcopy(SAMPLES), OPERATOR)
    assert planned["publishReady"], planned["rows"][0]["validationIssues"]
    applied = curriculum_migration_service.apply_migration(
        planned["migrationId"], deepcopy(SAMPLES), planned["confirmationToken"], OPERATOR
    )
    assert applied["rows"][0]["status"] == "applied"
    assert applied["rows"][0]["pointer"]["publishedVersionId"] == applied["rows"][0]["versionId"]
    return table


def _challenge(exercise_id: str) -> dict[str, Any]:
    challenge = practice_repo.get_challenge(exercise_id)
    assert challenge is not None
    return challenge


# ── the samples, migrated and published ──────────────────────────────────────


def test_the_samples_are_published_with_their_key_and_hotspots(published: FakeTable) -> None:
    primes = _challenge(PRIMES)
    assert primes["type"] == "multi_select"
    assert [int(index) for index in primes["correct_options"]] == [0, 2, 4]
    # What a teacher's preview and the receipt show of the key.
    assert primes["correct_answer"] == "2; 11; 17"

    hotspots = _challenge(HOTSPOTS)
    assert figure_svg.hotspots(hotspots["figure"]) == ["A", "B", "C", "D", "E"]
    assert multi_select.correct_options(hotspots) == [0, 3]


@pytest.mark.parametrize(
    ("exercise_id", "picked", "right"),
    [
        (PRIMES, [0, 2, 4], True),
        (PRIMES, [4, 0, 2], True),  # in any order
        (PRIMES, [0, 2], False),  # one missing
        (PRIMES, [0, 1, 2, 4], False),  # one extra
        (PRIMES, [0, 2, 3], False),  # one wrong
        (HOTSPOTS, [3, 0], True),
        (HOTSPOTS, [0], False),
        (HOTSPOTS, [0, 3, 4], False),
    ],
)
def test_a_sample_is_right_only_for_exactly_its_set(
    published: FakeTable, exercise_id: str, picked: list[int], right: bool
) -> None:
    for locale in ("de", "en", "fr", "it"):
        judgement = answer_recording.judge(_challenge(exercise_id), picked, locale=locale)
        assert judgement.correct is right, locale


def test_answering_a_sample_records_the_picked_options_and_shows_the_key_after(
    published: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    published.seed_active_account("student-1")
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)

    result = answer_recording.answer_practice(
        "student-1", _challenge(PRIMES), [2, 0], locale="fr"
    )

    assert result.correct is False
    assert result.standard_answer == "2; 11; 17"
    assert result.correct_options == [0, 2, 4]
    [receipt] = [
        row for key, row in published.rows.items()
        if key[0] == "ATTEMPTS#student-1" and key[1].startswith("ATTEMPT#")
    ]
    assert receipt["submitted_answer"] == ["2", "11"]
    assert receipt["challenge_type"] == "multi_select"
    # No cause per option yet: the general line, never "check your calculation".
    assert receipt["error_cause"] == {"category": error_causes.UNCLASSIFIED}
    assert result.feedback == practice_projection_service.answer_feedback({}, "fr")[1]


# ── what is not an answer ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        [0, 0, 2],  # the same option twice
        [0, 5],  # no sixth option
        [-1],
        [],
        "2; 11; 17",
        ["0", "2"],
        [0.0, 2],
        [True],
        {"0": True},
        None,
    ],
)
def test_anything_but_distinct_option_numbers_is_refused(published: FakeTable, raw: object) -> None:
    with pytest.raises(answer_recording.AnswerInvalid):
        answer_recording.judge(_challenge(PRIMES), raw, locale="de")


def test_an_ordering_is_still_judged_in_order() -> None:
    # A list answer to any other exercise is compared in order, as before.
    assert answer_judging.judge(["1/2", "0,75"], ["1/2", "0.75"])
    assert not answer_judging.judge(["0,75", "1/2"], ["1/2", "0.75"])


# ── authoring ────────────────────────────────────────────────────────────────


def _exercise(**extra: Any) -> dict[str, Any]:
    exercise = deepcopy(SAMPLES["lessons"][0]["exercises"][1])
    exercise.update(extra)
    return exercise


def _issues(exercise: dict[str, Any]) -> list[tuple[str, Issue]]:
    [stored] = curriculum_ops_service._exercise_payloads(LESSON_ID, [exercise])  # noqa: SLF001
    return [
        (item["field"], Issue(IssueCode(item["code"]), tuple(sorted(item["params"].items()))))
        for item in curriculum_ops_service._validation_issues(  # noqa: SLF001
            {}, [stored], level="draft"
        )
        if item["field"].startswith("exercises[0]")
    ]


def test_the_samples_author_without_an_issue() -> None:
    for exercise in SAMPLES["lessons"][0]["exercises"]:
        assert _issues(deepcopy(exercise)) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        # Only `data-choice` is let through, nothing else new.
        (
            {"figure": _exercise()["figure"].replace('data-choice="E"', 'data-choice="E" data-x="1"')},
            ("exercises[0].figure", Issue.of(IssueCode.FIGURE_ATTRIBUTE_NOT_ALLOWED, attribute="data-x")),
        ),
        (
            {"figure": _exercise()["figure"].replace('data-choice="E"', 'data-choice="F"')},
            ("exercises[0].figure", Issue.of(IssueCode.HOTSPOT_NOT_AN_OPTION, choice="F")),
        ),
        (
            {"figure": _exercise()["figure"].replace('data-choice="E"', 'data-choice="D"')},
            ("exercises[0].figure", Issue.of(IssueCode.HOTSPOT_REPEATED, choice="D")),
        ),
        (
            {"translations": {**_exercise()["translations"], "it": {
                **_exercise()["translations"]["it"], "options": ["A", "B", "C", "D"]}}},
            ("exercises[0].translations.it", Issue.of(IssueCode.TRANSLATION_OPTIONS_MISMATCH)),
        ),
        (
            {"translations": {**_exercise()["translations"], "en": {
                **_exercise()["translations"]["en"],
                "figure": _exercise()["figure"].replace(' data-choice="E"', "")}}},
            ("exercises[0].translations.en.figure", Issue.of(IssueCode.TRANSLATION_HOTSPOTS_MISMATCH)),
        ),
        ({"correctOptions": [0, 0]}, ("exercises[0].correct_options", Issue.of(IssueCode.CORRECT_OPTIONS_INVALID))),
        ({"correctOptions": [5]}, ("exercises[0].correct_options", Issue.of(IssueCode.CORRECT_OPTIONS_INVALID))),
        ({"correctOptions": []}, ("exercises[0].correct_options", Issue.of(IssueCode.CORRECT_OPTIONS_INVALID))),
        ({"correctOptions": ["A"]}, ("exercises[0].correct_options", Issue.of(IssueCode.CORRECT_OPTIONS_INVALID))),
        (
            {"options": [chr(ord("A") + index) for index in range(13)], "translations": {}},
            ("exercises[0].options", Issue.of(IssueCode.TOO_MANY_OPTIONS, max_options=12)),
        ),
        ({"options": ["A"], "translations": {}}, ("exercises[0].options", Issue.of(IssueCode.TOO_FEW_OPTIONS))),
        # Hotspots and a set key belong to a choose-several exercise only.
        (
            {"type": "multiple_choice", "answerKey": "A", "correctOptions": None},
            ("exercises[0].figure", Issue.of(IssueCode.HOTSPOT_WITHOUT_MULTI_SELECT)),
        ),
        (
            {"type": "multiple_choice", "answerKey": "A"},
            ("exercises[0].correct_options", Issue.of(IssueCode.CORRECT_OPTIONS_WITHOUT_MULTI_SELECT)),
        ),
    ],
)
def test_authoring_refuses_a_bad_choose_several_exercise(
    change: dict[str, Any], expected: tuple[str, Issue]
) -> None:
    assert expected in _issues(_exercise(**change))


def test_a_bad_sample_fails_its_migration_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    install_seeded_table(monkeypatch)
    manifest = deepcopy(SAMPLES)
    manifest["lessons"][0]["exercises"][1]["figure"] = _exercise()["figure"].replace(
        'data-choice="E"', 'data-choice="Z"'
    )

    planned = curriculum_migration_service.dry_run(manifest, OPERATOR)

    assert planned["publishReady"] is False
    [issue] = planned["rows"][0]["validationIssues"]
    assert (issue["field"], issue["code"], issue["params"]) == (
        "exercises[1].figure", "hotspot_not_an_option", {"choice": "Z"}
    )


def test_the_shown_key_follows_the_readers_options() -> None:
    [stored] = curriculum_ops_service._exercise_payloads(  # noqa: SLF001
        LESSON_ID,
        [{**_exercise(), "translations": {"en": {"prompt": "Which?", "options": ["P", "Q", "R", "S", "T"]}}}],
    )
    assert stored["correct_answer"] == "A; D"
    assert exercise_localization.localized(stored, "en")["correct_answer"] == "P; S"
    assert exercise_localization.localized(stored, "it")["correct_answer"] == "A; D"


# ── nothing a student reads before answering carries the key ─────────────────


def _assert_answer_free(projection: object) -> None:
    text = json.dumps(projection, ensure_ascii=False)
    for leak in ("correct_options", "correctOptions", "correct_answer", "correctAnswer",
                 "answer_key", "answerKey", "standardAnswer", "2; 11; 17", "A; D", "explanation"):
        assert leak not in text, leak


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_no_pre_answer_projection_carries_the_key(
    published: FakeTable, monkeypatch: pytest.MonkeyPatch, locale: str
) -> None:
    hotspots = _challenge(HOTSPOTS)
    primes = _challenge(PRIMES)

    # Course preview: the curriculum lesson and its exercises.
    lesson = curriculum_service.get_lesson_detail(LESSON_ID, locale=locale)
    _assert_answer_free(lesson)
    shown = {item["id"]: item for item in lesson["exercises"]}
    assert shown[HOTSPOTS]["type"] == "multi_select"
    assert shown[HOTSPOTS]["figure"] == hotspots["figure"]
    assert shown[PRIMES]["choices"] == ["2", "9", "11", "15", "17"]

    # Practice: the challenge as a lesson hands it out.
    for challenge in (primes, hotspots):
        preview = practice_projection_service.build_challenge_preview(challenge, locale)
        _assert_answer_free(preview)
        assert preview["type"] == "multi_select"
        assert "data-choice" in practice_projection_service.build_challenge_preview(hotspots, locale)["figure"]

    # Quiz: the exercise asked now.
    asked = quiz_exercise_preview([HOTSPOTS], locale)
    _assert_answer_free(asked)
    assert asked["options"] == ["A", "B", "C", "D", "E"]

    # Review: the due card.
    published.seed_active_account("student-1")
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)
    review_service.record_answer(
        student_id="student-1", challenge=hotspots, correct=False, answered_at=NOW
    )
    due = review_service.due_review(
        student_id="student-1", now=NOW + timedelta(hours=1), locale=locale
    )
    _assert_answer_free(due)
    [card] = due["items"]
    assert card["type"] == "multi_select"
    assert card["options"] == ["A", "B", "C", "D", "E"]
    assert card["figure"] == hotspots["figure"]
