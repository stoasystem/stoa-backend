"""Card 002-F: many-to-many parent links, confirmation, and the visibility they grant."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import (
    account_deletion_repo,
    account_number_repo,
    parent_link_repo,
    user_repo,
)
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import parents, students
from stoa.security.authorization import CurrentAuthorizationFactRepository
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import parent_link_service


NOW = "2026-09-19T10:00:00+00:00"


def _condition_terms(expression: Any) -> dict[tuple[str, str], str]:
    terms: dict[tuple[str, str], str] = {}
    pending = [expression]
    while pending:
        node = pending.pop()
        built = node.get_expression()
        if built["operator"] == "AND":
            pending.extend(built["values"])
            continue
        terms[(built["values"][0].name, built["operator"])] = built["values"][1]
    return terms


class FakeLinkTable:
    """In-memory table with all-or-nothing transacts, mirroring TransactWriteItems."""

    def __init__(self, *, refuse_prefix: str | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.refuse_prefix = refuse_prefix
        self.transactions: list[list[dict[str, Any]]] = []

    def get_item(self, *, Key, ConsistentRead=False):  # noqa: N803
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def query(self, **kwargs):
        terms = _condition_terms(kwargs["KeyConditionExpression"])
        partition = terms[("PK", "=")]
        prefix = terms[("SK", "begins_with")]
        return {
            "Items": [
                deepcopy(item)
                for (pk, sk), item in self.items.items()
                if pk == partition and sk.startswith(prefix)
            ]
        }

    def put_item(self, *, Item, ConditionExpression=None, **kwargs):  # noqa: N803
        key = (Item["PK"], Item["SK"])
        self._refuse_guard(key)
        self.items[key] = deepcopy(Item)

    def seed_account_fence(
        self, user_id: str, *, status: str = "active", generation: int = 1
    ) -> None:
        """An account fence row, storing the generation as the real table does."""
        self.items[(f"USER#{user_id}", "ACCOUNT_FENCE")] = {
            "PK": f"USER#{user_id}",
            "SK": "ACCOUNT_FENCE",
            "entity_type": "account_fence",
            "status": status,
            "generation": Decimal(generation),
        }

    def _check_condition(self, check, staged) -> None:
        key = (check["Key"]["PK"], check["Key"]["SK"])
        item = staged.get(key)
        expression = check.get("ConditionExpression") or ""
        values = check.get("ExpressionAttributeValues") or {}
        if item is None:
            raise account_deletion_repo.AccountDeletionConflict("condition row missing")
        if "#status=:active" in expression and item.get("status") != values[":active"]:
            raise account_deletion_repo.AccountDeletionConflict("condition status")
        if "generation=:generation" in expression and item.get("generation") != values[
            ":generation"
        ]:
            raise account_deletion_repo.AccountDeletionConflict("condition generation")

    def transact_account_deletion(self, operations):
        copied = deepcopy(operations)
        self.transactions.append(copied)
        staged = deepcopy(self.items)
        for operation in copied:
            if "ConditionCheck" in operation:
                self._check_condition(operation["ConditionCheck"], staged)
                continue
            put = operation["Put"]
            item = put["Item"]
            key = (item["PK"], item["SK"])
            self._refuse_guard(key)
            condition = put.get("ConditionExpression") or ""
            existing = staged.get(key)
            if "attribute_not_exists(PK)" in condition and existing is not None:
                raise account_deletion_repo.AccountDeletionConflict("exists")
            if "attribute_exists(PK)" in condition:
                if existing is None:
                    raise account_deletion_repo.AccountDeletionConflict("missing")
                if "#status = :expected_status" in condition:
                    expected = put["ExpressionAttributeValues"][":expected_status"]
                    if existing.get("status") != expected:
                        raise account_deletion_repo.AccountDeletionConflict("status")
                if "link_updated_at = :expected_link_updated_at" in condition:
                    expected_stamp = put["ExpressionAttributeValues"][
                        ":expected_link_updated_at"
                    ]
                    if existing.get("link_updated_at") != expected_stamp:
                        raise account_deletion_repo.AccountDeletionConflict("stale")
            staged[key] = item
        self.items = staged

    def update_item(self, *, Key, **kwargs):  # noqa: N803
        """Only the link-request quota counter uses this; one attempt per call."""
        key = (Key["PK"], Key["SK"])
        item = self.items.setdefault(key, {"PK": Key["PK"], "SK": Key["SK"], "attempts": 0})
        item["attempts"] = int(item.get("attempts") or 0) + 1
        return {"Attributes": {"attempts": item["attempts"]}}

    def _refuse_guard(self, key: tuple[str, str]) -> None:
        if self.refuse_prefix and key[0].startswith(self.refuse_prefix):
            raise account_deletion_repo.AccountDeletionConflict("injected write failure")


# Card 008: self-service needs both sides to be adults, and an account with no
# recorded birthday reads as a minor. Every account here is an adult unless a
# test says otherwise.
ADULT_BIRTHDAY = "2000-01-01"


def _profile(
    user_id: str, role: str, date_of_birth: str | None = ADULT_BIRTHDAY
) -> dict[str, Any]:
    profile = {
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@stoa.test",
        "name": user_id,
    }
    if date_of_birth is not None:
        profile["date_of_birth"] = date_of_birth
    return profile


ACCOUNTS = {
    "parent-a": _profile("parent-a", "parent"),
    "parent-b": _profile("parent-b", "parent"),
    "student-b": _profile("student-b", "student"),
    "student-c": _profile("student-c", "student"),
}


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeLinkTable:
    fake = FakeLinkTable()
    for user_id in ACCOUNTS:
        fake.seed_account_fence(user_id)
    monkeypatch.setattr(parent_link_repo, "get_table", lambda: fake)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(ACCOUNTS.get(user_id)))
    monkeypatch.setattr(user_repo, "list_parent_student_bindings", lambda _parent_id: [])
    monkeypatch.setattr(
        user_repo, "get_parent_student_binding", lambda _parent_id, _student_id: None
    )
    monkeypatch.setattr(
        user_repo, "get_student_parent_binding", lambda _student_id, _parent_id: None
    )
    return fake


def _parent_app(parent_id: str) -> FastAPI:
    actor = Actor(
        parent_id,
        "https://identity.test",
        f"{parent_id}-subject",
        CanonicalRole.PARENT,
        AccountStatus.ACTIVE,
        "parent",
    )

    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_actor] = lambda: actor
    # The production fact loader, not a stub: the link table has to be visible
    # through the one repository every router shares, not through a local wrapper.
    app.dependency_overrides[get_authorization_fact_repository] = (
        CurrentAuthorizationFactRepository
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return app


@pytest.fixture
def quiet_learning_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda *_a, **_k: {"Items": []})
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", lambda *_a, **_k: [])


def test_admin_assignment_writes_both_directions_active(table: FakeLinkTable) -> None:
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
    )

    forward = table.items[("PARENT#parent-a", "CHILD#student-b")]
    reverse = table.items[("STUDENT#student-b", "PARENT#parent-a")]
    assert forward["status"] == "active"
    assert reverse["status"] == "active"
    assert forward["initiator_role"] == "admin"
    assert forward["created_by"] == "admin-1"


def test_self_service_request_stops_at_pending(table: FakeLinkTable) -> None:
    link = parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )

    assert link["status"] == "pending"
    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "pending"
    assert table.items[("STUDENT#student-b", "PARENT#parent-a")]["status"] == "pending"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_many_to_many_in_both_directions(table: FakeLinkTable) -> None:
    for parent_id, student_id in (
        ("parent-a", "student-b"),
        ("parent-a", "student-c"),
        ("parent-b", "student-b"),
    ):
        parent_link_service.assign_link(
            parent_id=parent_id, student_id=student_id, actor_id="admin-1", now=NOW
        )

    children = {link["student_id"] for link in parent_link_service.active_children("parent-a")}
    assert children == {"student-b", "student-c"}
    parents_of_b = {
        link["parent_id"]
        for link in parent_link_repo.list_links_for_student("student-b")
    }
    assert parents_of_b == {"parent-a", "parent-b"}


def test_only_the_counterpart_can_confirm(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )

    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        parent_link_service.confirm_link(
            parent_id="parent-a", student_id="student-b", actor_id="parent-a", now=NOW
        )
    assert refused.value.code == "link_confirmation_not_allowed"
    assert parent_link_service.active_link("parent-a", "student-b") is None

    parent_link_service.confirm_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=NOW
    )
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_rejected_request_never_becomes_visible(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="student-b", counterpart_id="parent-a", now=NOW
    )
    parent_link_service.reject_link(
        parent_id="parent-a", student_id="student-b", actor_id="parent-a", now=NOW
    )

    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "rejected"
    assert parent_link_service.active_link("parent-a", "student-b") is None
    assert parent_link_service.active_children("parent-a") == []


def test_pending_link_denies_the_child_data_route(
    table: FakeLinkTable, quiet_learning_reads: None
) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )

    client = TestClient(_parent_app("parent-a"))
    response = client.get("/parents/me/children/student-b/learning-profile")

    assert response.status_code == 403


def test_confirmed_link_allows_the_same_route(
    table: FakeLinkTable, quiet_learning_reads: None
) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )
    client = TestClient(_parent_app("parent-a"))
    assert client.get("/parents/me/children/student-b/learning-profile").status_code == 403

    parent_link_service.confirm_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=NOW
    )
    allowed = client.get("/parents/me/children/student-b/learning-profile")

    assert allowed.status_code == 200
    assert allowed.json()["studentId"] == "student-b"


def test_unrelated_student_stays_denied(
    table: FakeLinkTable, quiet_learning_reads: None
) -> None:
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
    )

    client = TestClient(_parent_app("parent-a"))
    # No link at all keeps the existing existence hiding: the route must not
    # confirm that student-c is an account.
    assert client.get("/parents/me/children/student-c/learning-profile").status_code == 404


def test_child_list_holds_exactly_the_active_links(table: FakeLinkTable) -> None:
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
    )
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-c", now=NOW
    )

    client = TestClient(_parent_app("parent-a"))
    response = client.get("/parents/me/children")

    assert response.status_code == 200
    listed = [child["userId"] for child in response.json()["items"]]
    assert listed == ["student-b"]


def test_failed_second_write_leaves_no_half_link(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLinkTable(refuse_prefix="STUDENT#")
    for user_id in ACCOUNTS:
        fake.seed_account_fence(user_id)
    monkeypatch.setattr(parent_link_repo, "get_table", lambda: fake)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(ACCOUNTS.get(user_id)))

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.assign_link(
            parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
        )

    assert ("PARENT#parent-a", "CHILD#student-b") not in fake.items
    assert not [key for key in fake.items if key[1] != "ACCOUNT_FENCE"]


def test_failed_second_write_leaves_no_half_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLinkTable()
    for user_id in ACCOUNTS:
        fake.seed_account_fence(user_id)
    monkeypatch.setattr(parent_link_repo, "get_table", lambda: fake)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(ACCOUNTS.get(user_id)))
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )
    fake.refuse_prefix = "STUDENT#"

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.confirm_link(
            parent_id="parent-a", student_id="student-b", actor_id="student-b", now=NOW
        )

    assert fake.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "pending"
    assert fake.items[("STUDENT#student-b", "PARENT#parent-a")]["status"] == "pending"


def test_account_number_lookup_is_wired_through_one_narrow_hook(
    table: FakeLinkTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parent_link_service, "_account_number_resolver", None)
    with pytest.raises(parent_link_service.ParentLinkError) as missing:
        parent_link_service.request_link(requester_id="parent-a", counterpart_number="S26-0001")
    assert missing.value.code == "account_number_lookup_unavailable"

    monkeypatch.setattr(
        parent_link_service,
        "_account_number_resolver",
        lambda number: "student-b" if number == "S26-0001" else None,
    )
    link = parent_link_service.request_link(
        requester_id="parent-a", counterpart_number="S26-0001", now=NOW
    )
    assert link["student_id"] == "student-b"
    assert link["status"] == "pending"


def test_链接行不带_GSI_StudentId_的排序键():
    """链接行不能进「按学生列题目」那个索引。

    GSI-StudentId 的键是 (student_id, created_at)。链接行本来就带 student_id，
    再带上 created_at 就会被投影进去，而读那个索引的消费方里有几个不做过滤，
    会把行里的 parent_id 和 created_by 当成题目字段发出去。
    """
    row = parent_link_repo._link_body(
        parent_id="parent-a",
        student_id="student-b",
        status=parent_link_repo.STATUS_ACTIVE,
        relationship="guardian",
        initiator_role="admin",
        created_by="admin-1",
        linked_at="2026-09-19T10:00:00+00:00",
        updated_by="admin-1",
        link_updated_at="2026-09-19T10:00:00+00:00",
    )

    assert "student_id" in row
    assert "created_at" not in row, "带上 created_at 就会落进 GSI-StudentId"


def _link_rows():
    body = parent_link_repo._link_body(
        parent_id="parent-a",
        student_id="student-b",
        status=parent_link_repo.STATUS_ACTIVE,
        relationship="guardian",
        initiator_role="admin",
        created_by="admin-1",
        linked_at="2026-09-19T10:00:00+00:00",
        updated_by="admin-1",
        link_updated_at="2026-09-19T10:00:00+00:00",
    )
    forward = {**body, "PK": "PARENT#parent-a", "SK": "CHILD#student-b"}
    reverse = {**body, "PK": "STUDENT#student-b", "SK": "PARENT#parent-a"}
    return forward, reverse


def test_注销任一方都能扫到链接的两行():
    """删除扫描靠 _targets_user 一个谓词，而复核用的是同一个谓词。

    正向行的 PK 才带家长，SK 和字段都只指向学生，所以家长不在注册表里时
    这一行会活过它自己家长的注销，留下反向已墓碑、正向仍 active 的半截链接。
    """
    from stoa.db.repositories import account_deletion_repo

    forward, reverse = _link_rows()

    for row_name, row in (("forward", forward), ("reverse", reverse)):
        for user in ("parent-a", "student-b"):
            assert account_deletion_repo._targets_user(row, user), f"{row_name} 漏掉了 {user}"


def test_注销管理员不会扫走他签发的链接():
    """created_by 通常是管理员，链接不属于他。"""
    from stoa.db.repositories import account_deletion_repo

    forward, _ = _link_rows()

    assert not account_deletion_repo._targets_user(forward, "admin-1")


def test_只有单侧行时可见性不成立(table: FakeLinkTable, quiet_learning_reads: None) -> None:
    """两行是靠事务一起写的，但读侧不能因此假定它们总是成对存在。

    半截链接可以由别的途径留下（手工写库、注销扫描只墓碑了一侧、
    将来某条新写路径漏了一行），而放行只需要一次误判。
    """
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
    )
    del table.items[("STUDENT#student-b", "PARENT#parent-a")]

    assert parent_link_service.active_link("parent-a", "student-b") is None

    client = TestClient(_parent_app("parent-a"))
    response = client.get("/parents/me/children/student-b/learning-profile")

    assert response.status_code != 200


def test_预读之后状态被改掉则拒绝迁移(table: FakeLinkTable) -> None:
    """transition_link 先读后写，两者之间的窗口只能靠条件写兜住。"""
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=NOW
    )

    original = table.transact_account_deletion

    def racing_transact(operations):
        for key in (
            ("PARENT#parent-a", "CHILD#student-b"),
            ("STUDENT#student-b", "PARENT#parent-a"),
        ):
            table.items[key]["status"] = "rejected"
        table.transact_account_deletion = original
        return original(operations)

    table.transact_account_deletion = racing_transact

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.confirm_link(
            parent_id="parent-a", student_id="student-b", actor_id="student-b", now=NOW
        )

    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "rejected"


def test_发起方自己不能确认哪怕_initiator_role_被写反(table: FakeLinkTable) -> None:
    """_confirmer_side 全信 initiator_role；created_by 这道闸不信它。

    字段写反时第一条闸会把发起方认成应确认方，只剩这一条拦得住自确认。
    """
    body = parent_link_repo._link_body(
        parent_id="parent-a",
        student_id="student-b",
        status=parent_link_repo.STATUS_PENDING,
        relationship="child",
        initiator_role=parent_link_repo.INITIATOR_STUDENT,
        created_by="parent-a",
        linked_at=NOW,
        updated_by="parent-a",
        link_updated_at=NOW,
    )
    table.items[("PARENT#parent-a", "CHILD#student-b")] = {
        **body,
        "PK": "PARENT#parent-a",
        "SK": "CHILD#student-b",
    }
    table.items[("STUDENT#student-b", "PARENT#parent-a")] = {
        **body,
        "PK": "STUDENT#student-b",
        "SK": "PARENT#parent-a",
    }

    with pytest.raises(parent_link_service.ParentLinkError):
        parent_link_service.confirm_link(
            parent_id="parent-a", student_id="student-b", actor_id="parent-a", now=NOW
        )

    assert parent_link_service.active_link("parent-a", "student-b") is None


# ---------------------------------------------------------------------------
# Card 005: a refusal or an unanswered request must not seal the pair forever
# ---------------------------------------------------------------------------

BASE = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def _at(days: float) -> str:
    """An injected moment, so every boundary below is asserted, not waited for."""
    return (BASE + timedelta(days=days)).isoformat()


def _reject_at(table: FakeLinkTable, moment: str) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )
    parent_link_service.reject_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=moment
    )


def test_被拒后不满七天重新发起会被拒且带上还要等多久(table: FakeLinkTable) -> None:
    _reject_at(table, _at(0))

    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        parent_link_service.request_link(
            requester_id="parent-a", counterpart_id="student-b", now=_at(6.5)
        )

    assert refused.value.code == "link_rejected_cooldown"
    # 前端要说清「还要等多久」，所以剩余时间必须在错误里，不能只有一个码。
    assert refused.value.details["retryAfterSeconds"] == int(0.5 * 86400)
    assert refused.value.details["retryAt"] == _at(7)
    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "rejected"


def test_被拒满七天后重新发起成立且只到_pending(table: FakeLinkTable) -> None:
    _reject_at(table, _at(0))

    link = parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(7)
    )

    assert link["status"] == "pending"
    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["status"] == "pending"
    assert table.items[("STUDENT#student-b", "PARENT#parent-a")]["status"] == "pending"
    # 冷却期结束不等于关联成立：重新发起的仍然要对方确认。
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_未满十四天的_pending_仍然占着这一对(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=_at(13.9)
        )

    assert refused.value.code == "link_request_pending"
    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["created_by"] == "parent-a"


def test_满十四天的_pending_释放键位(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    link = parent_link_service.request_link(
        requester_id="student-b", counterpart_id="parent-a", now=_at(14)
    )

    assert link["status"] == "pending"
    assert link["initiator_role"] == "student"
    stored = table.items[("PARENT#parent-a", "CHILD#student-b")]
    assert stored["created_by"] == "student-b"
    assert stored["link_updated_at"] == _at(14)


def test_过期的_pending_不能再被确认(table: FakeLinkTable) -> None:
    """阴性方向：释放键位不许顺带把一条放了半年的请求变成可见性。"""
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        parent_link_service.confirm_link(
            parent_id="parent-a", student_id="student-b", actor_id="student-b", now=_at(14)
        )

    assert refused.value.code == "link_request_expired"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_过期的_pending_不再出现在待办列表里(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    assert parent_link_service.pending_requests_for_student("student-b", now=_at(13)) != []
    assert parent_link_service.pending_requests_for_student("student-b", now=_at(14)) == []
    assert parent_link_service.pending_requests_for_parent("parent-a", now=_at(14)) == []


def test_管理员分配不被拒绝挡住也不受冷却期约束(table: FakeLinkTable) -> None:
    _reject_at(table, _at(0))

    link = parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=_at(0.01)
    )

    assert link["status"] == "active"
    assert link["initiator_role"] == "admin"
    assert parent_link_service.active_link("parent-a", "student-b") is not None
    assert table.items[("STUDENT#student-b", "PARENT#parent-a")]["status"] == "active"


def test_管理员分配也能覆写一条过期的_pending(table: FakeLinkTable) -> None:
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    link = parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=_at(14)
    )

    assert link["status"] == "active"


def test_管理员分配仍然拒绝一条已经成立的关联(table: FakeLinkTable) -> None:
    """阴性对照：覆写路径只对没成立的状态开口，不是万能的重写。"""
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=_at(0)
    )

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.assign_link(
            parent_id="parent-a", student_id="student-b", actor_id="admin-2", now=_at(400)
        )


def test_已成立的关联不会因为时间流逝而失效(table: FakeLinkTable) -> None:
    """阴性对照：过期只针对无人应答的请求，不针对已经确认的关联。"""
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )
    parent_link_service.confirm_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=_at(1)
    )

    assert parent_link_service.active_link("parent-a", "student-b") is not None
    assert parent_link_service.active_children("parent-a") != []
    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        parent_link_service.request_link(
            requester_id="parent-a", counterpart_id="student-b", now=_at(3650)
        )
    assert refused.value.code == "link_already_active"
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_两个请求同时抢一个空键位只有一个成功(table: FakeLinkTable) -> None:
    """create_link 的 attribute_not_exists 是并发下唯一的仲裁者。

    两个发起方都是从「这一对没有行」出发算出要写什么的，表是最后一道闸。
    """
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_repo.create_link(
            parent_id="parent-a",
            student_id="student-b",
            status=parent_link_repo.STATUS_PENDING,
            initiator_role=parent_link_repo.INITIATOR_STUDENT,
            created_by="student-b",
            linked_at=_at(0),
        )

    assert table.items[("PARENT#parent-a", "CHILD#student-b")]["created_by"] == "parent-a"
    assert table.items[("STUDENT#student-b", "PARENT#parent-a")]["created_by"] == "parent-a"


def test_两个请求同时抢一个刚释放的键位只有一个成功(table: FakeLinkTable) -> None:
    """键位是被迁移回去的，不是被腾空的，所以这里承力的是状态加时间戳的栅栏。"""
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )

    original = table.transact_account_deletion

    def racing_transact(operations):
        table.transact_account_deletion = original
        parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=_at(14.5)
        )
        return original(operations)

    table.transact_account_deletion = racing_transact

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.request_link(
            requester_id="parent-a", counterpart_id="student-b", now=_at(14)
        )

    stored = table.items[("PARENT#parent-a", "CHILD#student-b")]
    assert stored["created_by"] == "student-b"
    assert stored["link_updated_at"] == _at(14.5)


def test_重建不走放松的创建条件(table: FakeLinkTable) -> None:
    """键位重用必须是条件迁移；create_link 的条件一个字都不许少。"""
    _reject_at(table, _at(0))
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(7)
    )

    creates = [
        operation["Put"]["ConditionExpression"]
        for transaction in table.transactions
        for operation in transaction
        if "Put" in operation
        and "attribute_not_exists" in operation["Put"].get("ConditionExpression", "")
    ]
    assert creates, "首次创建仍然要走 attribute_not_exists"
    assert all(
        term == "attribute_not_exists(PK) AND attribute_not_exists(SK)" for term in creates
    )
    reclaims = [
        operation["Put"]["ConditionExpression"]
        for transaction in table.transactions
        for operation in transaction
        if "Put" in operation
        and "link_updated_at = :expected_link_updated_at"
        in operation["Put"].get("ConditionExpression", "")
    ]
    assert len(reclaims) == 2


def test_链接行不带_expires_at(table: FakeLinkTable) -> None:
    """TTL 删行不是事务性的，删掉一侧就又是一对堵死的键位。

    过期改由 link_updated_at 判定，链接行因此不带 TTL 属性。
    """
    parent_link_service.request_link(
        requester_id="parent-a", counterpart_id="student-b", now=_at(0)
    )
    parent_link_service.reject_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=_at(1)
    )

    for row in table.items.values():
        assert "expires_at" not in row


# --- 端到端：002-D 没能构造出来的那个场景 -----------------------------------

ACCOUNT_NUMBERS = {"S26-0001": "student-b", "P26-0001": "parent-a"}


@pytest.fixture
def wired_table(table: FakeLinkTable, monkeypatch: pytest.MonkeyPatch) -> FakeLinkTable:
    """账号号码的认领行也要在表里，否则 studentNumber 根本解析不出来。"""
    monkeypatch.setattr(account_number_repo, "get_table", lambda: table)
    monkeypatch.setattr(parents, "get_table", lambda: table)
    for number, account_id in ACCOUNT_NUMBERS.items():
        table.items[(f"ACCOUNT_NUMBER#{number}", "ACCOUNT_NUMBER")] = {
            "PK": f"ACCOUNT_NUMBER#{number}",
            "SK": "ACCOUNT_NUMBER",
            "account_id": account_id,
        }
    return table


def _linked_app(user_id: str, role: CanonicalRole) -> TestClient:
    actor = Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = (
        CurrentAuthorizationFactRepository
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def test_端到端_点错一次拒绝之后仍有出路(wired_table: FakeLinkTable) -> None:
    parent = _linked_app("parent-a", CanonicalRole.PARENT)
    student = _linked_app("student-b", CanonicalRole.STUDENT)

    created = parent.post("/parents/me/children/requests", json={"studentNumber": "S26-0001"})
    assert created.status_code == 200, created.text
    rejected = student.post("/students/me/parent-requests/parent-a/reject")
    assert rejected.status_code == 200, rejected.text

    blocked = parent.post("/parents/me/children/requests", json={"studentNumber": "S26-0001"})
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "link_rejected_cooldown"
    assert detail["retryAfterSeconds"] > 0
    assert detail["retryAt"]

    # 冷却期一过，同一个端点就能再来一次。
    reopened = parent_link_service.request_link(
        requester_id="parent-a",
        counterpart_number="S26-0001",
        now=(datetime.now(UTC) + timedelta(days=7, seconds=1)).isoformat(),
    )
    assert reopened["status"] == "pending"
    listed = student.get("/students/me/parent-requests")
    assert listed.status_code == 200, listed.text
    assert [item["parentId"] for item in listed.json()["items"]] == ["parent-a"]


def test_没有时间戳的旧行不走重用路径(table: FakeLinkTable) -> None:
    """重用的栅栏就是那个时间戳；没有它就没法拦住并发的第二个人，宁可退回冲突。"""
    for key in (
        ("PARENT#parent-a", "CHILD#student-b"),
        ("STUDENT#student-b", "PARENT#parent-a"),
    ):
        table.items[key] = {
            "PK": key[0],
            "SK": key[1],
            "entity_type": parent_link_repo.ENTITY_TYPE,
            "parent_id": "parent-a",
            "student_id": "student-b",
            "relationship": "child",
            "status": parent_link_repo.STATUS_REJECTED,
            "initiator_role": parent_link_repo.INITIATOR_PARENT,
            "created_by": "parent-a",
            "linked_at": _at(0),
        }

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.request_link(
            requester_id="parent-a", counterpart_id="student-b", now=_at(400)
        )
