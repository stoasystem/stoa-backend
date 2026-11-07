"""Parent-student link rows, stored the way the link writer stores them (#208).

The relationship judge (`stoa.services.current_relationship`) reads only these
rows. A test that needs a relationship seeds one here, through the
`link_rows` fixture in `tests/conftest.py`, rather than stubbing the judge or
planting the retired binding rows.
"""

from __future__ import annotations

from typing import Any

from fakes.dynamodb import FakeTable
from stoa.db.repositories import parent_link_repo


LINKED_AT = "2026-11-01T09:00:00+00:00"


class LinkRows:
    """A table of link rows, plus profiles when a test wants them stored too."""

    def __init__(self, table: FakeTable | None = None) -> None:
        self.table = table or FakeTable()

    def link(
        self,
        parent_id: str,
        student_id: str,
        *,
        status: str = parent_link_repo.STATUS_ACTIVE,
        relationship: str = "child",
        stamp: str = LINKED_AT,
        student_side_status: str | None = None,
        student_side_stamp: str | None = None,
        only_parent_side: bool = False,
        initiator_role: str = parent_link_repo.INITIATOR_ADMIN,
        created_by: str = "admin-1",
    ) -> None:
        """Both sides of one link; the arguments make the sides disagree on purpose."""
        sides = [
            (parent_link_repo.parent_side_key(parent_id, student_id), status, stamp),
        ]
        if not only_parent_side:
            sides.append(
                (
                    parent_link_repo.student_side_key(student_id, parent_id),
                    student_side_status or status,
                    student_side_stamp or stamp,
                )
            )
        for key, side_status, side_stamp in sides:
            self.table.seed(
                {
                    **key,
                    "entity_type": parent_link_repo.ENTITY_TYPE,
                    "parent_id": parent_id,
                    "student_id": student_id,
                    "relationship": relationship,
                    "status": side_status,
                    "initiator_role": initiator_role,
                    "created_by": created_by,
                    "linked_at": LINKED_AT,
                    "updated_by": created_by,
                    "link_updated_at": side_stamp,
                }
            )

    def unlink(self, parent_id: str, student_id: str) -> None:
        """Remove both sides, as if the pair had never been linked."""
        for key in (
            parent_link_repo.parent_side_key(parent_id, student_id),
            parent_link_repo.student_side_key(student_id, parent_id),
        ):
            self.table.rows.pop((key["PK"], key["SK"]), None)

    def set_status(self, parent_id: str, student_id: str, status: str) -> None:
        """Move both sides to `status` in place, e.g. `rejected` for a revoked link."""
        for key in (
            parent_link_repo.parent_side_key(parent_id, student_id),
            parent_link_repo.student_side_key(student_id, parent_id),
        ):
            row = self.table.rows.get((key["PK"], key["SK"]))
            if row is not None:
                row["status"] = status

    def account(
        self, user_id: str, role: str, *, status: str = "active", **extra: Any
    ) -> None:
        self.table.seed(
            {
                "PK": f"USER#{user_id}",
                "SK": "PROFILE",
                "user_id": user_id,
                "role": role,
                "account_status": status,
                **extra,
            }
        )

    def side(self, pk: str, sk: str) -> dict[str, Any] | None:
        return self.table.rows.get((pk, sk))
