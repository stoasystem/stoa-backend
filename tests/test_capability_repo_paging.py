"""A user's capability rows are read to the last page, not only the first.

A query answers at most 1 MB and hands the rest back behind LastEvaluatedKey.
Reading one page authorized from part of a user's grants, and let the #84
baseline write a completed summary without the grants past it.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from stoa.db.repositories import capability_repo


class PagedTable:
    """Real grant writes through the transaction hook; reads one row per page."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {
            ("USER#admin-1", "ACCOUNT_FENCE"): {
                "PK": "USER#admin-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 1,
            }
        }
        self.queries: list[dict[str, Any]] = []

    def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:  # noqa: N803
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        rows = sorted(
            (item for item in self.items.values() if item["SK"].startswith("CAPABILITY")),
            key=lambda item: item["SK"],
        )
        start = kwargs.get("ExclusiveStartKey")
        if start is not None:
            rows = [row for row in rows if row["SK"] > start["SK"]]
        page = rows[:1]
        response: dict[str, Any] = {"Items": [dict(row) for row in page]}
        if len(rows) > 1:
            response["LastEvaluatedKey"] = {"PK": page[0]["PK"], "SK": page[0]["SK"]}
        return response

    def apply_capability_transaction(self, operations: list[dict[str, Any]]) -> None:
        pending = dict(self.items)
        for operation in operations:
            if operation["kind"] == "condition":
                current = pending.get((operation["key"]["PK"], operation["key"]["SK"]))
                if not current or any(
                    current.get(name) != value for name, value in operation["expected"].items()
                ):
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException"}},
                        "TransactWriteItems",
                    )
                continue
            item = operation["item"]
            key = (item["PK"], item["SK"])
            if operation["condition"] == "absent" and key in pending:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "TransactWriteItems"
                )
            pending[key] = dict(item)
        self.items = pending


def _grant(table: PagedTable, capability: str, grant_id: str) -> None:
    capability_repo.grant_capability(
        user_id="admin-1",
        command_id=f"command-{grant_id}",
        grant_id=grant_id,
        capability=capability,
        scope="global",
        grantor_id="admin-0",
        reason="approved change",
        effective_at="2026-09-30T12:00:00Z",
        expected_generation=0,
        table_factory=lambda: table,
    )


def _table_with_three_grants() -> PagedTable:
    table = PagedTable()
    for index, capability in enumerate(
        (
            capability_repo.STUDENT_SUPPORT_LOOKUP,
            capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER,
            capability_repo.PARENT_BINDING_REPAIRER,
        )
    ):
        _grant(table, capability, f"grant-{index}")
    return table


def test_current_grants_are_read_past_the_first_page() -> None:
    table = _table_with_three_grants()
    grants = capability_repo.get_current_grants("admin-1", table_factory=lambda: table)
    assert sorted(item["capability"] for item in grants) == sorted(
        [
            capability_repo.STUDENT_SUPPORT_LOOKUP,
            capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER,
            capability_repo.PARENT_BINDING_REPAIRER,
        ]
    )
    # Three grants are six rows (a revision and a pointer each), one per page.
    assert len(table.queries) == 6
    assert "ExclusiveStartKey" not in table.queries[0]
    assert all("ExclusiveStartKey" in query for query in table.queries[1:])


def test_every_revision_is_listed_past_the_first_page() -> None:
    table = _table_with_three_grants()
    revisions = capability_repo.list_grant_revisions("admin-1", table_factory=lambda: table)
    assert sorted(item["grant_id"] for item in revisions) == ["grant-0", "grant-1", "grant-2"]
    assert all(item["entity_type"] == "capability_grant_revision" for item in revisions)
