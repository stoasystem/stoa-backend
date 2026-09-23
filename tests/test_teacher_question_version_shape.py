"""A question's version comes back as `Decimal`, and the reply path must know it.

The resource interface deserialises every stored number to `Decimal`, and
`isinstance(Decimal("3"), int)` is False. `_initialize_legacy_question_for_mutation`
asked exactly that, so a question that already carried a version was taken for
an unversioned legacy row and sent to `initialize_legacy_question_version` -
which asks the same thing correctly, finds the version, and raises "question
already has a positive version".

Every teacher reply to a versioned question went down that path. The suite never
saw it because its fixtures store versions as `int`, which no table returns.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from stoa.routers import teachers


def test_a_version_the_table_returned_is_recognised() -> None:
    question = {"question_id": "q-1", "version": Decimal("3")}

    assert (
        teachers._initialize_legacy_question_for_mutation(
            question, allowed_source_statuses=frozenset()
        )
        is question
    )


def test_a_plain_int_version_is_recognised_too() -> None:
    """The shape the fixtures use has to keep working alongside the real one."""
    question = {"question_id": "q-1", "version": 3}

    assert (
        teachers._initialize_legacy_question_for_mutation(
            question, allowed_source_statuses=frozenset()
        )
        is question
    )


@pytest.mark.parametrize(
    "version",
    [
        None,
        0,
        Decimal("0"),
        -1,
        Decimal("-2"),
        True,  # a bool is not a version, and `isinstance(True, int)` is True
        "3",
        Decimal("3.5"),
    ],
    ids=["absent", "zero", "decimal-zero", "negative", "decimal-negative", "bool", "text", "fractional"],
)
def test_anything_that_is_not_a_positive_whole_version_goes_to_initialisation(version) -> None:
    """Negative control: widening this must not accept a row with no version.

    A legacy row genuinely has none, and it still has to be sent to be
    initialised - otherwise the fix would simply stop initialising anything.
    """
    question = {"question_id": "q-1"}
    if version is not None:
        question["version"] = version

    sent: list[object] = []

    def initialise(q, *, allowed_source_statuses):
        sent.append(q)
        raise RuntimeError("reached initialisation")

    original = teachers.question_repo.initialize_legacy_question_version
    teachers.question_repo.initialize_legacy_question_version = initialise
    try:
        with pytest.raises(RuntimeError, match="reached initialisation"):
            teachers._initialize_legacy_question_for_mutation(
                question, allowed_source_statuses=frozenset()
            )
    finally:
        teachers.question_repo.initialize_legacy_question_version = original

    assert sent == [question]
