"""Card 008: the account carries a birthday, and a minor cannot self-serve a link.

Two halves, deliberately in one file: what the account stores (a date of birth,
on both provisioning paths) and what that buys (`request_link` and `confirm_link`
refused when either side is a minor, `assign_link` untouched).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from test_account_provisioning import FakeAccountTable, RecordingProvider
from test_parent_student_links import FakeLinkTable

from stoa.config import Settings, get_settings
from stoa.db.repositories import (
    account_deletion_repo,
    account_invitation_repo,
    account_number_repo,
    identity_repo,
    parent_link_repo,
    security_audit_repo,
    user_repo,
)
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.models import user as user_model
from stoa.routers import students
from stoa.security.authorization import CurrentAuthorizationFactRepository
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import account_provisioning_service, parent_link_service


NOW = "2026-09-20T10:00:00+00:00"
MOMENT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

ADULT = "2000-01-01"
MINOR = "2012-05-06"
# Turns 18 on exactly the day the tests run their clock to.
TURNS_ADULT_TODAY = "2008-09-20"
# Turns 18 tomorrow.
ONE_DAY_SHORT = "2008-09-21"


# ---------------------------------------------------------------------------
# Half one: the birthday reaches the account row on both openings
# ---------------------------------------------------------------------------


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeAccountTable:
    fake = FakeAccountTable()
    for module in (
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        security_audit_repo,
        user_repo,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    return fake


def _admin() -> dict[str, Any]:
    return {
        "user_id": "admin-1",
        "role": "admin",
        "account_status": "active",
        "current_grants": [
            {
                "capability": "admin_identity_manager",
                "scope": "global",
                "status": "active",
                "version": 1,
            }
        ],
    }


def _invite(*, date_of_birth: str | None = None, email: str = "invitee@example.ch"):
    return account_provisioning_service.invite_account(
        actor=_admin(),
        role="student",
        email=email,
        full_name="Alex Muster",
        date_of_birth=date_of_birth,
        invitation_expiry_seconds=3600,
        now=lambda: MOMENT,
    )


def _claim(*, token: str, date_of_birth: str | None = None):
    return account_provisioning_service.claim_invitation(
        token=token,
        password="Startpass1",
        date_of_birth=date_of_birth,
        issuer="https://issuer.example",
        provider=RecordingProvider(),
        now=lambda: MOMENT,
    )


def _stored(table: FakeAccountTable, user_id: str) -> dict[str, Any]:
    return table.rows[(f"USER#{user_id}", "PROFILE")]


def test_邀请建号把生日落在账号行上(table: FakeAccountTable) -> None:
    issued = _invite(date_of_birth=MINOR)

    assert _stored(table, issued["userId"])["date_of_birth"] == MINOR


def test_直接分配建号把生日落在账号行上(table: FakeAccountTable) -> None:
    assigned = account_provisioning_service.assign_account(
        actor=_admin(),
        role="student",
        email="assigned@example.ch",
        full_name="Alex Muster",
        date_of_birth=MINOR,
        provider=RecordingProvider(),
        issuer="https://issuer.example",
        now=lambda: MOMENT,
    )

    assert _stored(table, assigned["userId"])["date_of_birth"] == MINOR


def test_不带生日建号时账号行上没有这个字段(table: FakeAccountTable) -> None:
    """"Not known" has to stay tellable from "known and empty"."""
    issued = _invite()

    assert "date_of_birth" not in _stored(table, issued["userId"])


def test_认领时补上邀请里没有带的生日(table: FakeAccountTable) -> None:
    issued = _invite()

    _claim(token=issued["activationToken"], date_of_birth=MINOR)

    assert _stored(table, issued["userId"])["date_of_birth"] == MINOR
    assert _stored(table, issued["userId"])["account_status"] == "active"


def test_管理员记下的生日不会被认领时申报的那个覆盖(table: FakeAccountTable) -> None:
    issued = _invite(date_of_birth=MINOR)

    _claim(token=issued["activationToken"], date_of_birth=ADULT)

    assert _stored(table, issued["userId"])["date_of_birth"] == MINOR


def test_生日不进邀请行也不进审计流(table: FakeAccountTable) -> None:
    """A birthday is personal data: only the account row is allowed to hold it."""
    _invite(date_of_birth=MINOR)

    for row in table.invitations():
        assert MINOR not in str(row)
    audit = [
        row
        for key, row in table.rows.items()
        if str(key[0]).startswith("SECURITY_AUDIT#")
    ]
    assert audit, "no audit rows were written, so this proves nothing"
    for row in audit:
        assert MINOR not in str(row)


@pytest.mark.parametrize(
    "bad",
    ["2008-2-30-CANARY", "not-a-date-CANARY", "2099-01-01", "20080101"],
)
def test_生日不合法按代码拒绝且原值不进错误也不进栈(
    table: FakeAccountTable, bad: str
) -> None:
    with pytest.raises(HTTPException) as refused:
        _invite(date_of_birth=bad)

    assert refused.value.status_code == 422
    assert refused.value.detail == {"code": "date_of_birth_invalid"}
    rendered = "".join(
        traceback.format_exception(
            type(refused.value), refused.value, refused.value.__traceback__
        )
    )
    assert bad not in rendered


def test_认领时的生日在令牌被烧掉之前就被拒(table: FakeAccountTable) -> None:
    """A malformed field must not cost the invitee their single-use token."""
    issued = _invite()

    with pytest.raises(HTTPException):
        _claim(token=issued["activationToken"], date_of_birth="nonsense")

    _claim(token=issued["activationToken"], date_of_birth=ADULT)
    assert _stored(table, issued["userId"])["date_of_birth"] == ADULT


# ---------------------------------------------------------------------------
# Half two: who may建立 a link without an administrator
# ---------------------------------------------------------------------------


class LinkWorld:
    """One in-memory link table plus the account rows the service reads."""

    def __init__(self, table: FakeLinkTable) -> None:
        self.table = table
        self.accounts: dict[str, dict[str, Any]] = {}

    def add(self, user_id: str, role: str, date_of_birth: str | None) -> str:
        row: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "account_status": "active",
            "email": f"{user_id}@stoa.test",
            "name": user_id,
        }
        if date_of_birth is not None:
            row["date_of_birth"] = date_of_birth
        self.accounts[user_id] = row
        return user_id

    def pending(self, *, parent_id: str, student_id: str, created_by: str) -> None:
        parent_link_repo.create_link(
            parent_id=parent_id,
            student_id=student_id,
            status=parent_link_service.STATUS_PENDING,
            initiator_role=(
                parent_link_service.INITIATOR_PARENT
                if created_by == parent_id
                else parent_link_service.INITIATOR_STUDENT
            ),
            created_by=created_by,
            linked_at=NOW,
        )

    def status(self, parent_id: str, student_id: str) -> str | None:
        row = self.table.items.get((f"PARENT#{parent_id}", f"CHILD#{student_id}"))
        return None if row is None else str(row.get("status"))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> LinkWorld:
    built = LinkWorld(FakeLinkTable())
    monkeypatch.setattr(parent_link_repo, "get_table", lambda: built.table)
    monkeypatch.setattr(
        user_repo, "get_user", lambda user_id: deepcopy(built.accounts.get(user_id))
    )
    monkeypatch.setattr(user_repo, "list_parent_student_bindings", lambda _p: [])
    monkeypatch.setattr(
        user_repo, "get_parent_student_binding", lambda _p, _s: None
    )
    monkeypatch.setattr(
        user_repo, "get_student_parent_binding", lambda _s, _p: None
    )
    return built


def _refusal(call) -> str:
    with pytest.raises(parent_link_service.ParentLinkError) as refused:
        call()
    return refused.value.code


def test_未成年学生自助发起关联被拒(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=NOW
        )
    )

    assert code == "link_requires_administrator"
    assert world.status("parent-a", "student-b") is None


def test_家长对未成年学生自助发起关联同样被拒(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="parent-a", counterpart_id="student-b", now=NOW
        )
    )

    assert code == "link_requires_administrator"
    assert world.status("parent-a", "student-b") is None


def test_家长侧是未成年时自助同样被拒(world: LinkWorld) -> None:
    """A minor parent row is a data error, and it is refused the same way."""
    world.add("parent-a", "parent", MINOR)
    world.add("student-b", "student", ADULT)

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=NOW
        )
    )

    assert code == "link_requires_administrator"
    assert world.status("parent-a", "student-b") is None


def test_未成年学生确认一条_pending_被拒(world: LinkWorld) -> None:
    """The birthday can be corrected after the request was raised."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)
    world.pending(parent_id="parent-a", student_id="student-b", created_by="parent-a")

    code = _refusal(
        lambda: parent_link_service.confirm_link(
            parent_id="parent-a",
            student_id="student-b",
            actor_id="student-b",
            now=NOW,
        )
    )

    assert code == "link_requires_administrator"
    assert world.status("parent-a", "student-b") == "pending"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_未成年学生仍然可以拒绝一条_pending(world: LinkWorld) -> None:
    """Refusing is not consenting, so the minor is not trapped under the request."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)
    world.pending(parent_id="parent-a", student_id="student-b", created_by="parent-a")

    parent_link_service.reject_link(
        parent_id="parent-a", student_id="student-b", actor_id="student-b", now=NOW
    )

    assert world.status("parent-a", "student-b") == "rejected"


def test_管理员分配对未成年照常成立(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)

    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1", now=NOW
    )

    assert world.status("parent-a", "student-b") == "active"
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_成年学生的自助发起与确认照常成立(world: LinkWorld) -> None:
    """Negative control: the gate must refuse minors and nothing else."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", ADULT)

    parent_link_service.request_link(
        requester_id="student-b", counterpart_id="parent-a", now=NOW
    )
    assert world.status("parent-a", "student-b") == "pending"

    parent_link_service.confirm_link(
        parent_id="parent-a", student_id="student-b", actor_id="parent-a", now=NOW
    )

    assert world.status("parent-a", "student-b") == "active"
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_生日恰好使人今天成年按成年处理(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", TURNS_ADULT_TODAY)

    parent_link_service.request_link(
        requester_id="student-b", counterpart_id="parent-a", now=NOW
    )

    assert world.status("parent-a", "student-b") == "pending"


def test_差一天成年按未成年处理(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", ONE_DAY_SHORT)

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=NOW
        )
    )

    assert code == "link_requires_administrator"
    assert world.status("parent-a", "student-b") is None


def test_生日未知按未成年处理(world: LinkWorld) -> None:
    """Fail closed: the rule exists to protect minors, so "unknown" is one."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", None)

    assert (
        _refusal(
            lambda: parent_link_service.request_link(
                requester_id="student-b", counterpart_id="parent-a", now=NOW
            )
        )
        == "link_requires_administrator"
    )

    world.pending(parent_id="parent-a", student_id="student-b", created_by="parent-a")
    assert (
        _refusal(
            lambda: parent_link_service.confirm_link(
                parent_id="parent-a",
                student_id="student-b",
                actor_id="student-b",
                now=NOW,
            )
        )
        == "link_requires_administrator"
    )
    assert world.status("parent-a", "student-b") == "pending"


def test_生日存的是日期不是年龄所以判定随时间推移而改变(world: LinkWorld) -> None:
    """The point of storing the date: the same row answers differently later."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", ONE_DAY_SHORT)

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=NOW
        )
    )
    assert code == "link_requires_administrator"

    parent_link_service.request_link(
        requester_id="student-b",
        counterpart_id="parent-a",
        now="2026-09-21T10:00:00+00:00",
    )
    assert world.status("parent-a", "student-b") == "pending"


# ---------------------------------------------------------------------------
# The threshold is configuration, not a number in the code
# ---------------------------------------------------------------------------


def test_成年阈值默认是十八岁() -> None:
    # 18 is written out by hand here. Asserting against the constant instead
    # would make this agree with whatever the constant happens to say.
    assert Settings().adult_age_years == 18
    assert get_settings().adult_age_years == 18


def test_成年阈值来自配置而不是写死在判定里(
    world: LinkWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sixteen-year-old is a minor at 18 and is not one where majority is 16."""
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", "2010-09-20")

    code = _refusal(
        lambda: parent_link_service.request_link(
            requester_id="student-b", counterpart_id="parent-a", now=NOW
        )
    )
    assert code == "link_requires_administrator"

    lowered = get_settings().model_copy(update={"adult_age_years": 16})
    monkeypatch.setattr(user_model, "get_settings", lambda: lowered)

    parent_link_service.request_link(
        requester_id="student-b", counterpart_id="parent-a", now=NOW
    )
    assert world.status("parent-a", "student-b") == "pending"


# ---------------------------------------------------------------------------
# The refusal reaches the caller as a 403, not as a 500 or a bare conflict
# ---------------------------------------------------------------------------


def _student_app(student_id: str) -> FastAPI:
    actor = Actor(
        student_id,
        "https://identity.test",
        f"{student_id}-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        "student",
    )
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = (
        CurrentAuthorizationFactRepository
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return app


def test_未成年学生在接口上确认关联收到_403(world: LinkWorld) -> None:
    world.add("parent-a", "parent", ADULT)
    world.add("student-b", "student", MINOR)
    world.pending(parent_id="parent-a", student_id="student-b", created_by="parent-a")

    response = TestClient(_student_app("student-b")).post(
        "/students/me/parent-requests/parent-a/confirm"
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "link_requires_administrator"
    assert world.status("parent-a", "student-b") == "pending"
