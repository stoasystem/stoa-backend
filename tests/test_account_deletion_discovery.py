"""Whose rows an account deletion takes, case by case (Plan 475, #588, #642)."""

from __future__ import annotations

import pytest

from stoa.db import data_catalog
from stoa.services import account_deletion_flow as flow


IDENTITY = "identity-1"


def _row(entity_type: str, **fields: object) -> dict[str, object]:
    return {
        "PK": f"ROW#{entity_type}",
        "SK": "META",
        "entity_type": entity_type,
        **fields,
    }


@pytest.mark.parametrize(
    ("candidate", "selected"),
    [
        pytest.param(
            _row("parent_student_link", parent_id=IDENTITY, student_id="student-1"),
            True,
            id="parent-link-parent-id",
        ),
        pytest.param(
            _row("question", student_id="student-1", teacher_id=IDENTITY),
            True,
            id="teacher-question-teacher-id",
        ),
        pytest.param(
            _row("teacher_session", student_id="student-1", teacher_id=IDENTITY),
            True,
            id="teacher-session-teacher-id",
        ),
        pytest.param(
            _row("notification_event", owner_id="student-1", actor_id=IDENTITY),
            True,
            id="notification-actor-id",
        ),
        pytest.param(
            _row(
                "notification_event",
                owner_id="student-1",
                metadata={"teacher_id": IDENTITY},
            ),
            True,
            id="notification-metadata-teacher-id",
        ),
        pytest.param(
            _row(
                "notification_event",
                owner_id="student-1",
                metadata={"owner_id": IDENTITY},
            ),
            True,
            id="notification-metadata-owner-id",
        ),
        pytest.param(
            _row(
                "notification_event",
                owner_id="student-1",
                metadata={"student_id": IDENTITY},
            ),
            True,
            id="notification-metadata-student-id",
        ),
        pytest.param(
            _row("parent_student_binding", parent_id=f"prefix-{IDENTITY}"),
            False,
            id="scalar-substring",
        ),
        pytest.param(
            _row("question", student_id="student-1", content=f"mentions {IDENTITY}"),
            False,
            id="unrelated-free-text",
        ),
        pytest.param(
            _row("question", student_id="student-1", payload={"teacher_id": IDENTITY}),
            False,
            id="unregistered-question-payload",
        ),
        # The accounts the notification family scrubs out of a notification
        # are taken here as well (#574).
        pytest.param(
            _row("notification_event", owner_id="student-1", metadata={"actor_id": IDENTITY}),
            True,
            id="notification-metadata-actor-id",
        ),
        pytest.param(
            _row("notification_event", owner_id="student-1", metadata={"parent_id": IDENTITY}),
            True,
            id="notification-metadata-parent-id",
        ),
        pytest.param(
            _row("notification_event", owner_id="student-1", metadata={"recipient_id": IDENTITY}),
            False,
            id="unregistered-notification-metadata",
        ),
        pytest.param(
            _row("unreviewed_record", teacher_id=IDENTITY),
            False,
            id="field-on-unregistered-entity",
        ),
    ],
)
def test_an_account_deletion_takes_the_rows_the_catalog_says_name_it(
    candidate: dict[str, object],
    selected: bool,
) -> None:
    """Which rows a deletion acts on is the catalog's answer alone (#588, #642).

    The table of cases the old base-table scan was held to, now asked of the
    catalog and of the flow that reads it: a pointer the catalog declares is
    taken, a substring, free text or an undeclared field is not.
    """
    assert data_catalog.names(candidate, IDENTITY) is selected
    assert (flow.action_for(candidate, IDENTITY) is not None) is selected
