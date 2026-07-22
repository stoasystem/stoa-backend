from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


IDENTITY = "identity-1"
NOW = "2026-07-22T08:00:00+00:00"
CURSOR = {"PK": "CURSOR#1", "SK": "META"}


def _row(entity_type: str, **fields: object) -> dict[str, object]:
    return {
        "PK": f"ROW#{entity_type}",
        "SK": "META",
        "entity_type": entity_type,
        **fields,
    }


class _PagedTable:
    def __init__(self, candidate: dict[str, object]) -> None:
        self.calls: list[dict[str, object]] = []
        self.pages = [
            {"Items": [_row("unrelated", owner_id="someone-else")], "LastEvaluatedKey": CURSOR},
            {"Items": [candidate]},
        ]

    def scan(self, **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        assert kwargs.get("Limit") == 1
        assert "IndexName" not in kwargs
        if self.calls:
            assert kwargs.get("ExclusiveStartKey") == CURSOR
        else:
            assert "ExclusiveStartKey" not in kwargs
        self.calls.append(dict(kwargs))
        return deepcopy(self.pages[len(self.calls) - 1])


class _RepeatingCursorTable:
    def scan(self, **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        return {"Items": [], "LastEvaluatedKey": CURSOR}


@pytest.mark.parametrize(
    ("candidate", "selected"),
    [
        pytest.param(
            _row("parent_student_binding", parent_id=IDENTITY, student_id="student-1"),
            True,
            id="formal-parent-binding-parent-id",
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
        pytest.param(
            _row("notification_event", owner_id="student-1", metadata={"actor_id": IDENTITY}),
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
def test_cross_account_identity_registry_and_two_clean_epochs(
    monkeypatch: pytest.MonkeyPatch,
    candidate: dict[str, object],
    selected: bool,
) -> None:
    table = _PagedTable(candidate)
    page = account_deletion_repo.scan_owned_private_rows(
        f" {IDENTITY} ", table=table, maximum_pages=2, page_limit=1
    )

    assert page.cursor is None
    assert len(table.calls) == 2
    assert [item["PK"] for item in page.items] == (
        [candidate["PK"]] if selected else []
    )

    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match="repeating"):
        account_deletion_repo.scan_owned_private_rows(
            IDENTITY,
            table=_RepeatingCursorTable(),
            maximum_pages=2,
            page_limit=1,
        )

    late_row = _row("question", student_id="student-1", teacher_id=IDENTITY)
    pages = [
        account_deletion_repo.OwnedPrivatePage((), None),
        account_deletion_repo.OwnedPrivatePage((late_row,), None),
        account_deletion_repo.OwnedPrivatePage((), None),
        account_deletion_repo.OwnedPrivatePage((), None),
    ]
    monkeypatch.setattr(
        account_deletion_repo,
        "scan_owned_private_rows",
        lambda *_args, **_kwargs: pages.pop(0),
    )
    previous: dict[str, Any] = {}
    results = []
    mutated: list[str] = []
    for _ in range(4):
        result = account_deletion_service._run_base_branch(
            command={"user_id": IDENTITY, "generation": 7},
            previous=previous,
            predicate=lambda item: item.get("entity_type") == "question",
            mutate=lambda item: mutated.append(str(item["PK"])),
        )
        results.append(result)
        previous = result.persisted(NOW)

    assert [result.epoch for result in results] == [1, 0, 1, 2]
    assert [result.status for result in results] == [
        "retryable",
        "retryable",
        "retryable",
        "complete",
    ]
    assert results[-1].quiescent is True
    assert mutated == [late_row["PK"]]
