"""A subject the student ticked on their profile is a subject they take (#321).

The star map draws and recommends only in subjects the student takes (#164).
Those used to be the subjects with progress rows, which a lesson writes when it
is finished - so a student who has finished nothing took nothing, and the start
by year group (#310) never reached them. Ticking a subject on the profile
(`primary_subjects`, stoa-frontend#591) now counts as taking it, beside the
progress rows, never instead of them.

Through `knowledge_map` over a student's evidence, as the route calls it.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes import student_evidence as fake_evidence
from stoa.services import knowledge_map_service as km
from stoa.services import learning_profile_service

CATALOG = {
    "subjects": [
        {"id": "math", "name": "Mathematik", "order": 0},
        {"id": "physics", "name": "Physik", "order": 1},
    ],
    "topics": [
        {"id": "t6", "subjectId": "math", "title": "t6", "order": 0, "gradeLevel": "grade_6_primary"},
        {"id": "t9", "subjectId": "math", "title": "t9", "order": 1, "gradeLevel": "grade_9_secondary"},
        {"id": "p9", "subjectId": "physics", "title": "p9", "order": 0, "gradeLevel": "grade_9_secondary"},
    ],
    "units": [
        {"id": "t6-s1", "subjectId": "math", "topicId": "t6", "title": "t6-s1", "order": 0},
        {"id": "t9-s1", "subjectId": "math", "topicId": "t9", "title": "t9-s1", "order": 1},
        {"id": "p9-s1", "subjectId": "physics", "topicId": "p9", "title": "p9-s1", "order": 0},
    ],
    "lessons": [
        {"id": "l6", "unitId": "t6-s1", "subjectId": "math", "topicId": "t6"},
        {"id": "l9", "unitId": "t9-s1", "subjectId": "math", "topicId": "t9"},
        {"id": "lp", "unitId": "p9-s1", "subjectId": "physics", "topicId": "p9"},
    ],
}


def sky(
    profile: dict[str, Any],
    *,
    progress_in: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The sky for a student with this profile and progress rows in `progress_in`.

    A progress row of a lesson started, not finished: the subject is taken, no
    star is lit, so the recommendation falls through to rule 3.
    """
    evidence = fake_evidence.evidence(
        catalog=CATALOG,
        progress=[{"lesson_id": f"started-{s}", "subject_id": s} for s in progress_in],
        ledger_open=True,
    )
    return km.knowledge_map(
        evidence,
        subject_id="math",
        student_grade=profile.get("grade"),
        chosen_subject_ids=learning_profile_service.chosen_subjects(profile),
    )


def enrolled(result: dict[str, Any]) -> dict[str, bool]:
    return {galaxy["subjectId"]: galaxy["enrolled"] for galaxy in result["galaxies"]}


def recommendations(result: dict[str, Any]) -> dict[str, tuple[str, str]]:
    subject_of = {item["topicId"]: item["subjectId"] for item in result["nebulae"]}
    return {
        subject_of[star["nebulaId"]]: (star["unitId"], star["recommendation"]["reason"])
        for star in result["stars"]
        if star["recommendation"]
    }


def test_a_new_student_who_ticked_maths_starts_at_the_first_star_of_their_year() -> None:
    result = sky({"grade": "grade_9_secondary", "primary_subjects": ["math"]})

    assert enrolled(result) == {"math": True, "physics": False}
    assert recommendations(result) == {"math": ("t9-s1", "grade")}


def test_a_new_student_who_ticked_nothing_gets_no_recommendation_as_before() -> None:
    for profile in (
        {"grade": "grade_9_secondary"},
        {"grade": "grade_9_secondary", "primary_subjects": []},
        {"grade": "grade_9_secondary", "primary_subjects": None},
    ):
        result = sky(profile)

        assert enrolled(result) == {"math": False, "physics": False}, profile
        assert recommendations(result) == {}, profile


@pytest.mark.parametrize("ticked", ["mathematics", "Math", " MATHEMATICS "])
def test_a_subject_ticked_under_its_other_name_is_taken(ticked: str) -> None:
    result = sky({"grade": "grade_9_secondary", "primary_subjects": [ticked]})

    assert enrolled(result)["math"] is True
    assert recommendations(result) == {"math": ("t9-s1", "grade")}


def test_a_catalog_saying_mathematics_is_matched_by_a_profile_saying_math() -> None:
    renamed = {
        **CATALOG,
        "subjects": [{"id": "mathematics", "name": "Mathematik", "order": 0}],
        "topics": [{**t, "subjectId": "mathematics"} for t in CATALOG["topics"][:2]],
        "units": [{**u, "subjectId": "mathematics"} for u in CATALOG["units"][:2]],
        "lessons": [{**item, "subjectId": "mathematics"} for item in CATALOG["lessons"][:2]],
    }
    evidence = fake_evidence.evidence(catalog=renamed, ledger_open=True)

    result = km.knowledge_map(evidence, chosen_subject_ids=("math",))

    assert enrolled(result) == {"mathematics": True}


def test_a_subject_with_progress_is_taken_though_it_is_not_ticked() -> None:
    result = sky(
        {"grade": "grade_9_secondary", "primary_subjects": ["math"]},
        progress_in=("physics",),
    )

    assert enrolled(result) == {"math": True, "physics": True}
    assert recommendations(result) == {"math": ("t9-s1", "grade"), "physics": ("p9-s1", "grade")}


def test_the_older_subjects_field_is_read_when_primary_subjects_is_absent() -> None:
    result = sky({"grade": "grade_9_secondary", "subjects": ["math"]})

    assert enrolled(result)["math"] is True


def test_primary_subjects_wins_over_the_older_field_as_in_the_profile_response() -> None:
    result = sky({"grade": "grade_9_secondary", "primary_subjects": [], "subjects": ["math"]})

    assert enrolled(result)["math"] is False


def test_what_the_profile_holds_that_names_no_subject_is_passed_over() -> None:
    result = sky(
        {"grade": "grade_9_secondary", "primary_subjects": ["astrology", "", 7, None, "math"]},
    )

    assert enrolled(result) == {"math": True, "physics": False}


@pytest.mark.parametrize("stored", ["math", {"math": True}, 7])
def test_a_profile_value_that_is_not_a_list_is_no_subjects(stored: object) -> None:
    assert learning_profile_service.chosen_subjects({"primary_subjects": stored}) == ()
