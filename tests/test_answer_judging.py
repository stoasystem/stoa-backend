"""Which submissions count as the key, and which still do not.

The seed prompts write numbers the Swiss way (`π ≈ 3,14`, `4,5 m`, `CHF 40.–`)
while the keys use a point, so an answer in the prompt's own notation was marked
wrong. Writing a value differently is forgiven; giving a different value is not -
a fraction the exercise asked to reduce stays wrong unreduced. Equivalent forms an
author wants to count are listed per exercise as `accepted_answers`; the cases at
the bottom are the ZAP fractions batch's own lists from #106.
"""

from __future__ import annotations

import pytest

from stoa.services import answer_judging, lesson_quiz_service


@pytest.mark.parametrize(
    ("submitted", "key"),
    [
        # geometrie-l2-c1: "Verwende π ≈ 3,14", key 31.4
        ("31,4", "31.4"),
        ("31.40", "31.4"),
        # textaufgaben-l1-c1: CHF amounts
        ("10.80", "10.8"),
        ("10,80", "10.8"),
        # prozentrechnung-l2-c1: "CHF 40.–"
        ("34.–", "34"),
        ("34.-", "34"),
        ("34.00", "34"),
        ("1'200", "1200"),
        ("1’200.50", "1200.5"),
        ("−5", "-5"),
        ("  27  ", "27"),
        ("18.", "18"),
        # gleichungen-l3-c1: spacing around operators
        ("x - 8 = 17", "x-8=17"),
        ("X-8 = 17", "x-8=17"),
        ("2 / 3", "2/3"),
        ("4 11/12", "4 11/12"),
        ("4  11 / 12", "4 11/12"),
        ("2x + 7 = 21", "2x+7=21"),
        ("Dreieck", "dreieck"),
    ],
)
def test_a_different_writing_of_the_key_is_right(submitted: str, key: str) -> None:
    assert answer_judging.judge(submitted, key)


@pytest.mark.parametrize(
    ("submitted", "key"),
    [
        # brueche-l1-c2: "Kürze den Bruch 12/18 so weit wie möglich"
        ("4/6", "2/3"),
        ("12/18", "2/3"),
        ("0.5", "1/2"),
        ("31.5", "31.4"),
        ("3.14", "31.4"),
        ("314", "31.4"),
        ("1,200", "1200"),
        ("411/12", "4 11/12"),
        ("x-8=71", "x-8=17"),
        ("", ""),
        ("  ", "0"),
    ],
)
def test_a_different_value_is_still_wrong(submitted: str, key: str) -> None:
    assert not answer_judging.judge(submitted, key)


def test_choices_and_list_answers_compare_item_by_item() -> None:
    assert answer_judging.judge(["1/2", "0,75"], ["1/2", "0.75"])
    assert not answer_judging.judge(["0,75", "1/2"], ["1/2", "0.75"])
    assert answer_judging.judge("Der Umfang verdoppelt sich", "der Umfang verdoppelt sich")


@pytest.mark.parametrize(
    ("key", "accepted", "right", "wrong"),
    [
        # EX-D0821-BUNG-2-A: "Kürze das Resultat vollständig"
        ("59/12", ["4 11/12"], ["59/12", "4 11/12", "4 11 / 12"], ["118/24", "4.916"]),
        # EX-D0821-BUNG-2-D lists the decimal too
        ("11/4", ["2 3/4", "2.75"], ["2,75", "2 3/4", "11/4"], ["22/8", "2.7"]),
        # EX-D0011-5: unit optional
        ("86.5", ["86.5 kg"], ["86,5", "86,5 kg", "86.5kg", "86,50 KG"], ["86,5 g", "865"]),
        # EX-D0005-3A: "Fr." as written in the source answer
        ("100", ["100 Fr.", "100 CHF"], ["100", "100 Fr", "100 fr.", "100 CHF"], ["10"]),
        # EX-D0070-8: unit required for full credit, so the bare number is not listed
        ("3120 km", ["3120000 m"], ["3120 km", "3'120 km", "3120000 m"], ["3120", "3120 m"]),
    ],
)
def test_listed_alternatives_count_and_nothing_else_does(
    key: str, accepted: list[str], right: list[str], wrong: list[str]
) -> None:
    challenge = {"correct_answer": key, "accepted_answers": accepted}
    for submitted in right:
        assert answer_judging.judge_challenge(submitted, challenge), submitted
    for submitted in wrong:
        assert not answer_judging.judge_challenge(submitted, challenge), submitted


def test_a_malformed_alternatives_field_counts_as_none() -> None:
    assert answer_judging.accepted_answers({"accepted_answers": "18"}) == []
    assert answer_judging.accepted_answers({"accepted_answers": [18, None, " ", "18"]}) == ["18"]
    assert not answer_judging.judge_challenge(
        "19", {"correct_answer": "18", "accepted_answers": "19"}
    )


def test_the_quiz_entry_point_judges_by_the_same_rules() -> None:
    assert lesson_quiz_service.judge_answer("31,4", "31.4")
    assert not lesson_quiz_service.judge_answer("4/6", "2/3")


def test_the_answer_route_records_a_listed_alternative_as_right(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from actor_helpers import install_actor_overrides
    from stoa.routers import practice
    from stoa.services import curriculum_analytics_service

    challenge = {
        "challenge_id": "exercise-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "brueche",
        "prompt": "Wie schwer ist die Kiste?",
        "correct_answer": "86.5",
        "accepted_answers": ["86.5 kg"],
        "explanation": "86,5 kg.",
    }
    recorded: list[bool] = []
    repo = curriculum_analytics_service.curriculum_analytics_repo
    monkeypatch.setattr(repo, "record_student_signal", lambda item, **_kwargs: None)
    monkeypatch.setattr(repo, "increment_metric", lambda item: None)
    monkeypatch.setattr(
        practice.practice_repo, "get_challenge", lambda challenge_id: dict(challenge)
    )
    monkeypatch.setattr(
        practice.practice_repo, "get_challenges", lambda lesson_id: [dict(challenge)]
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "put_attempt",
        lambda *args, **kwargs: (
            recorded.append(args[3])
            or {
                "attempt_id": f"attempt-{len(recorded)}",
                "student_id": args[0],
                "challenge_id": args[1],
                "student_answer": args[2],
                "correct": args[3],
                **kwargs,
            }
        ),
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    client = TestClient(app)

    for answer in ("86,5 kg", "86,50", "865"):
        response = client.post("/practice/challenges/exercise-1/answer", json={"answer": answer})
        assert response.status_code == 200

    assert recorded == [True, True, False]
