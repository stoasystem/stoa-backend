"""A user's capability rows are read to the last page, not only the first.

A query answers at most 1 MB and hands the rest back behind LastEvaluatedKey.
Reading one page authorized from part of a user's grants, and let the #84
baseline write a completed summary without the grants past it.

The table is the shared double with one row per page, so the key condition is
judged as the real store judges it: another user's grants, planted beside these,
must not come back.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from boto3.dynamodb.types import TypeDeserializer
from fakes.dynamodb import FakeTable

from stoa.db.repositories import capability_repo


CAPABILITIES = (
    capability_repo.STUDENT_SUPPORT_LOOKUP,
    capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER,
    capability_repo.PARENT_BINDING_REPAIRER,
)


class CapabilityTable(FakeTable):
    """The shared double, named like a table so grants take the real serialized path.

    The capability store sends a low-level transaction, its values tagged with
    their types; the shared double judges resource-level values. This only
    decodes the tags and hands the same transaction to the shared double, whose
    conditions and effects are the ones every other test relies on.
    """

    name = "stoa-main"
    meta = SimpleNamespace(client=SimpleNamespace(meta=SimpleNamespace(region_name="eu-central-2")))

    def transact_write_items(self, operations=None, *, TransactItems=None):  # noqa: N803
        decode = TypeDeserializer().deserialize

        def plain(body: dict[str, Any]) -> dict[str, Any]:
            decoded = dict(body)
            for field in ("Item", "Key", "ExpressionAttributeValues"):
                if field in decoded:
                    decoded[field] = {k: decode(v) for k, v in decoded[field].items()}
            return decoded

        items = [
            {kind: plain(body) for kind, body in operation.items()}
            for operation in (TransactItems or [])
        ]
        return super().transact_write_items(operations, TransactItems=items or None)


def _grant(table: CapabilityTable, user_id: str, capability: str, grant_id: str) -> None:
    capability_repo.grant_capability(
        user_id=user_id,
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


def _table() -> CapabilityTable:
    table = CapabilityTable(page_item_cap=1)
    for user_id in ("admin-1", "admin-2"):
        table.seed(
            {"PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1}
        )
    for index, capability in enumerate(CAPABILITIES):
        _grant(table, "admin-1", capability, f"grant-{index}")
    # Another user's grants sit beside them; a query on the wrong partition finds these.
    _grant(table, "admin-2", capability_repo.ADMIN_IDENTITY_MANAGER, "grant-other")
    return table


def _queries(table: CapabilityTable) -> list[dict]:
    return [request for operation, request in table.requests if operation == "query"]


def test_current_grants_are_read_past_the_first_page() -> None:
    table = _table()
    table.requests.clear()
    grants = capability_repo.get_current_grants("admin-1", table_factory=lambda: table)
    assert sorted(item["capability"] for item in grants) == sorted(CAPABILITIES)
    assert {item["user_id"] for item in grants} == {"admin-1"}
    queries = _queries(table)
    # Three grants are six rows (a revision and a pointer each), one per page.
    assert len(queries) >= 6
    assert "ExclusiveStartKey" not in queries[0]
    assert all("ExclusiveStartKey" in query for query in queries[1:])


def test_every_revision_is_listed_past_the_first_page() -> None:
    table = _table()
    revisions = capability_repo.list_grant_revisions("admin-1", table_factory=lambda: table)
    assert sorted(item["grant_id"] for item in revisions) == ["grant-0", "grant-1", "grant-2"]
    assert all(item["entity_type"] == "capability_grant_revision" for item in revisions)


def test_another_users_grants_never_come_back() -> None:
    table = _table()
    revisions = capability_repo.list_grant_revisions("admin-2", table_factory=lambda: table)
    assert [item["grant_id"] for item in revisions] == ["grant-other"]
    grants = capability_repo.get_current_grants("admin-2", table_factory=lambda: table)
    assert [item["capability"] for item in grants] == [capability_repo.ADMIN_IDENTITY_MANAGER]
