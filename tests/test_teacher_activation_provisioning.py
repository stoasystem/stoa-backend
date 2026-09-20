"""Card 010: teacher activation opens its account the way every other role does.

Read against the real repositories through the single-table double, because the
whole point of the card is that teacher activation stopped having a creation path
of its own. A stub of `open_account` would agree with anything.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
import pytest

from test_account_provisioning import FakeAccountTable

from stoa.db.repositories import (
    account_deletion_repo,
    account_email_claim_repo,
    account_invitation_repo,
    account_number_repo,
    identity_repo,
    security_audit_repo,
    teacher_application_repo,
    user_repo,
)
from stoa.services import (
    account_provisioning_service,
    notify_service,
    teacher_application_service,
)


MOMENT = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
CANDIDATE = "candidate@example.ch"
ISSUER = "https://identity.example/primary"

# Written out here rather than imported from the numbering service, so a wrong
# prefix there cannot agree with the assertion.
TEACHER_NUMBER = re.compile(r"^T\d{2}-\d{4}$")


def _key_conditions(expression: Any) -> dict[str, tuple[str, Any]]:
    """Flatten one boto3 key condition into `{attribute: (operator, value)}`."""
    parsed = expression.get_expression()
    operator = str(parsed["operator"])
    values = parsed["values"]
    if operator == "AND":
        merged: dict[str, tuple[str, Any]] = {}
        for part in values:
            merged.update(_key_conditions(part))
        return merged
    return {str(values[0].name): (operator, values[1])}


class TeacherTable(FakeAccountTable):
    """The shared double plus the main-table query the application rows are read by.

    Subclassed rather than reimplemented so the conditions, the transaction and the
    address index stay the ones every other account test is read against.
    """

    def query(self, *, IndexName: str | None = None, **kwargs: Any) -> dict[str, Any]:  # noqa: N803
        if IndexName is not None:
            return super().query(IndexName=IndexName, **kwargs)
        conditions = _key_conditions(kwargs["KeyConditionExpression"])
        partition = conditions["PK"][1]
        sort_operator, sort_value = conditions.get("SK", ("", ""))
        with self.lock:
            matches = [
                deepcopy(row)
                for key, row in sorted(self.rows.items())
                if key[0] == partition
                and (not sort_operator or key[1].startswith(str(sort_value)))
            ]
        return {"Items": matches}


class TeacherProvider:
    """Identity provider double with the teacher flow's method names."""

    def __init__(self, *, group_failures: int = 0) -> None:
        self.created: list[str] = []
        self.groups: list[dict[str, str]] = []
        self.group_failures = group_failures

    def create_teacher_account(self, *, email: str, password: str) -> str:
        del password
        self.created.append(email)
        return f"sub-{uuid4().hex[:12]}"

    def ensure_teacher_identity(self, *, email: str, user_id: str, group: str) -> None:
        if self.group_failures > 0:
            self.group_failures -= 1
            raise RuntimeError("group membership temporarily unavailable")
        self.groups.append({"email": email, "user_id": user_id, "group": group})


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> TeacherTable:
    fake = TeacherTable()
    for module in (
        account_deletion_repo,
        account_email_claim_repo,
        account_invitation_repo,
        account_number_repo,
        identity_repo,
        security_audit_repo,
        teacher_application_repo,
        user_repo,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    return fake


@pytest.fixture
def delivered(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def send(recipient: str, *, activation_token: str, expires_at: str, full_name: str = "") -> None:
        sent.append(
            {
                "recipient": recipient,
                "token": activation_token,
                "expires_at": expires_at,
                "full_name": full_name,
            }
        )

    monkeypatch.setattr(notify_service, "send_teacher_invitation_email", send)
    return sent


def _reviewer() -> dict[str, Any]:
    return {
        "user_id": "reviewer-1",
        "role": "admin",
        "account_status": "active",
        "current_grants": [
            {
                "capability": "teacher_identity_reviewer",
                "scope": "global",
                "status": "active",
                "version": 1,
            }
        ],
    }


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


def _moment(offset_seconds: int = 0) -> datetime:
    return MOMENT + timedelta(seconds=offset_seconds)


def _approve(delivered: list[dict[str, Any]], *, email: str = CANDIDATE) -> str:
    """Take one candidacy to an approved version and return the delivered token."""
    application = teacher_application_service.submit_application(
        {
            "email": email,
            "email_verified": True,
            "full_name": "Alex Muster",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=_moment,
    )
    teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=application["version"],
        decision="approved",
        reason="offline qualifications reviewed",
        invitation_expiry_seconds=3600,
        now=_moment,
    )
    assert delivered, "an approved application must deliver one invitation email"
    return str(delivered[-1]["token"])


def _activate(
    token: str,
    *,
    provider: TeacherProvider | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    return teacher_application_service.claim_and_activate(
        token=token,
        password="Startpass1",
        issuer=ISSUER,
        provider=provider or TeacherProvider(),
        now=lambda: at or _moment(60),
    )


def _profile(table: TeacherTable, user_id: str) -> dict[str, Any]:
    return table.rows[(f"USER#{user_id}", "PROFILE")]


def _invitation_row(table: TeacherTable) -> dict[str, Any]:
    rows = [
        row
        for key, row in table.rows.items()
        if key[0].startswith("TEACHER_INVITATION#") and key[1] == "META"
    ]
    assert len(rows) == 1
    return rows[0]


# ---------------------------------------------------------------------------
# 判据一：教师激活建出来的账号有 T 前缀的编号
# ---------------------------------------------------------------------------


def test_教师激活建出来的账号带着T前缀的编号(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The opening is the shared one, so the number comes with it rather than never.

    Read off the stored row, not the response: the response could carry a number the
    account does not hold, and it is the row a login and a deletion both go by.
    """
    activated = _activate(_approve(delivered))

    profile = _profile(table, activated["userId"])
    assert TEACHER_NUMBER.match(str(profile["account_number"]))
    assert profile["account_number"] == f"T{MOMENT.year % 100:02d}-0001"
    assert profile["role"] == "teacher"
    assert profile["account_status"] == "active"
    # The number claim is the only place the pairing is recorded, so an account number
    # on the profile with no claim behind it would be a number nothing reserved.
    claim = account_number_repo.get_account_number_claim(
        str(profile["account_number"]), table=table
    )
    assert claim is not None and claim["account_id"] == activated["userId"]


def test_教师账号跟着拿到强制改密标志与生日字段的处理(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The flags the shared opening writes reach the teacher row too.

    A teacher chooses their own password at claim time, so they owe no change - but
    the field has to be written and say so, because an absent flag is not an answer.
    The birthday is absent rather than empty: the application form never asks for one,
    and `""` would read as a stored answer the minor rule must not see.
    """
    activated = _activate(_approve(delivered))

    profile = _profile(table, activated["userId"])
    assert profile["must_change_password"] is False
    assert "date_of_birth" not in profile
    assert profile["activation_command_id"]


# ---------------------------------------------------------------------------
# 判据二：邀请行的 expires_at 是整数
# ---------------------------------------------------------------------------


def test_教师邀请行的过期时间是整数epoch(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """`expires_at` is the table's time-to-live attribute, and TTL only reads a number.

    An ISO string there is collected by nothing, so the row lives forever and the
    expiry is enforced by the read alone. The readable copy moves beside it.
    """
    _approve(delivered)

    invitation = _invitation_row(table)
    stored_expiry = invitation["expires_at"]
    assert not isinstance(stored_expiry, (str, bool))
    assert int(stored_expiry) == stored_expiry == int(_moment(3600).timestamp())
    assert invitation["expires_at_iso"] == _moment(3600).isoformat()
    assert delivered[-1]["expires_at"] == _moment(3600).isoformat()


def test_过期判断仍然拦得住过期的令牌(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """Negative control for the row above: the numeric spelling still expires tokens.

    A change that only moved the value would pass the type assertion and quietly stop
    refusing anything, so the refusal is read out separately.
    """
    token = _approve(delivered)

    with pytest.raises(HTTPException) as expired:
        _activate(token, at=_moment(3601))
    assert expired.value.detail == {"code": "invitation_expired"}
    assert table.rows.get(("USER#", "PROFILE")) is None
    assert not [key for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK]


def test_激活仍然认得只写了ISO过期时间的老邀请行(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """Rows issued before the epoch move still expire, rather than becoming unusable.

    Nothing migrates these, so a reader that only knows the new spelling would refuse
    every outstanding invitation the day it ships.
    """
    token = _approve(delivered)
    invitation = _invitation_row(table)
    key = (str(invitation["PK"]), str(invitation["SK"]))
    table.rows[key]["expires_at"] = _moment(3600).isoformat()
    del table.rows[key]["expires_at_iso"]

    with pytest.raises(HTTPException) as expired:
        _activate(token, at=_moment(3601))
    assert expired.value.detail == {"code": "invitation_expired"}

    activated = _activate(token, at=_moment(60))
    assert activated["status"] == "active"


# ---------------------------------------------------------------------------
# 判据三：两条建号路径共用同一个唯一性判定
# ---------------------------------------------------------------------------


def test_教师激活写的是通用占位行(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The key is the one the claim repository spells, not one assembled here."""
    activated = _activate(_approve(delivered))

    expected = account_email_claim_repo.claim_key(email=CANDIDATE, role="teacher")
    row = table.rows[(expected["PK"], expected["SK"])]
    assert row["account_id"] == activated["userId"]
    assert row["claimed_email"] == CANDIDATE and row["role"] == "teacher"
    # The placeholder stays out of GSI-Email, or uniqueness would start reading it as
    # a profile holding the address.
    assert "email" not in row


def test_管理员先开的教师账号挡住同地址的教师激活(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """One pair, one account, whichever path asked first."""
    account_provisioning_service.invite_account(
        actor=_admin(),
        role="teacher",
        email=CANDIDATE,
        full_name="Alex Muster",
        now=_moment,
    )
    token = _approve(delivered)

    with pytest.raises(HTTPException) as refused:
        _activate(token)
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "account_exists"}
    assert len([key for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK]) == 1


def test_教师激活挡住管理员再开同地址的教师账号(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The same refusal in the other direction, which a per-path rule would not give."""
    _activate(_approve(delivered))

    with pytest.raises(HTTPException) as refused:
        account_provisioning_service.invite_account(
            actor=_admin(),
            role="teacher",
            email=CANDIDATE,
            full_name="Alex Muster",
            now=lambda: _moment(120),
        )
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "account_exists"}


def test_同一地址仍然可以另开一个家长账号(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """Negative control for the two above: the key is the pair, not the address.

    A teacher whose own child studies here holds both accounts on one address, so a
    rule that refused this would be refusing something legitimate rather than a
    duplicate.
    """
    _activate(_approve(delivered))

    opened = account_provisioning_service.invite_account(
        actor=_admin(),
        role="parent",
        email=CANDIDATE,
        full_name="Alex Muster",
        now=lambda: _moment(120),
    )
    assert opened["accountNumber"].startswith("P")
    assert sorted(
        str(key[0]) for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK
    ) == [f"EMAIL#{CANDIDATE}#parent", f"EMAIL#{CANDIDATE}#teacher"]


# ---------------------------------------------------------------------------
# 判据四：阴性对照 —— 审核语义与令牌单次使用不变
# ---------------------------------------------------------------------------


def test_令牌仍然只能用一次且不会开出第二个账号(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    token = _approve(delivered)
    activated = _activate(token)

    with pytest.raises(HTTPException) as replay:
        _activate(token, at=_moment(120))
    assert replay.value.detail == {"code": "invitation_already_used"}
    assert [str(row["user_id"]) for row in table.profiles()] == [activated["userId"]]
    assert len([key for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK]) == 1
    assert len([key for key in table.rows if key[0].startswith("ACCOUNT_NUMBER#")]) == 1


def test_没有审核权限就批不了也开不出账号(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The review threshold is untouched: no capability, no approval, no invitation."""
    application = teacher_application_service.submit_application(
        {
            "email": CANDIDATE,
            "email_verified": True,
            "full_name": "Alex Muster",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=_moment,
    )
    stranger = {"user_id": "admin-2", "role": "admin", "account_status": "active"}

    with pytest.raises(HTTPException) as refused:
        teacher_application_service.review_application(
            actor=stranger,
            application_id=application["applicationId"],
            version=1,
            decision="approved",
            reason="no capability",
            now=_moment,
        )
    assert refused.value.status_code == 403
    assert delivered == []
    assert table.profiles() == []
    assert not [key for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK]


def test_供应商失败后重试续做同一个账号而不是开第二个(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """Resuming is still resuming, now that the opening is two commits rather than one.

    The row and its number land separately, so a retry has to finish the account it
    already opened - a second one would burn a second number and be refused by the
    claim it already holds.
    """
    token = _approve(delivered)
    provider = TeacherProvider(group_failures=1)

    with pytest.raises(HTTPException) as deferred:
        _activate(token, provider=provider)
    assert deferred.value.status_code == 503
    parked = table.profiles()
    assert len(parked) == 1 and parked[0]["account_status"] == "pending_review"
    assert TEACHER_NUMBER.match(str(parked[0]["account_number"]))

    resumed = teacher_application_service.activate_from_invitation(
        token=token,
        verified_email=CANDIDATE,
        issuer=ISSUER,
        subject="sub-resumed",
        provider=provider,
        now=lambda: _moment(120),
    )
    assert resumed["status"] == "active"
    assert [str(row["user_id"]) for row in table.profiles()] == [parked[0]["user_id"]]
    assert _profile(table, resumed["userId"])["account_number"] == parked[0]["account_number"]
    assert len([key for key in table.rows if key[0].startswith("ACCOUNT_NUMBER#")]) == 1


# ---------------------------------------------------------------------------
# 009 带出来的补充判据：删号必须把地址还回去
# ---------------------------------------------------------------------------


def test_删掉教师账号后地址还回去且同一对可以重开(
    table: TeacherTable, delivered: list[dict[str, Any]]
) -> None:
    """The release only fires for a profile shaped the way the deletion path expects.

    `_email_claim_release` reads `SK == "PROFILE"` and a matching `user_id`, so a
    teacher row with a shape of its own would leave the pair taken by an account that
    no longer exists - free to every read, refused by the store.
    """
    activated = _activate(_approve(delivered))
    user_id = activated["userId"]
    profile = dict(_profile(table, user_id))

    fence = table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")]
    fence["status"] = "deletion_pending"
    fence["generation"] = 1
    account_deletion_repo.replace_with_deletion_tombstone(
        profile, user_id=user_id, generation=1, now_iso=_moment(120).isoformat()
    )

    assert account_email_claim_repo.get_claim(email=CANDIDATE, role="teacher") is None
    assert not [key for key in table.rows if key[1] == account_email_claim_repo.CLAIM_SK]
    tombstone = table.rows[(f"USER#{user_id}", "PROFILE")]
    assert tombstone["status"] == "deleted" and "email" not in tombstone

    reopened = account_provisioning_service.invite_account(
        actor=_admin(),
        role="teacher",
        email=CANDIDATE,
        full_name="Alex Muster",
        now=lambda: _moment(180),
    )
    # A number is never recycled, an address always is.
    assert reopened["accountNumber"] == f"T{MOMENT.year % 100:02d}-0002"


# ---------------------------------------------------------------------------
# 010 独立审计的 A-2 / A-3 / B-3
# ---------------------------------------------------------------------------


def test_争用导致的编号失败要能续做而不是把命令钉死(
    table: TeacherTable, delivered: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing a race for a number answers 409, and it happens after the row lands.

    Deciding by status code puts that refusal in the same basket as "the pair belongs
    to somebody else", which is the one basket it must not be in: the account is
    already open and holding its address, the number is already burnt, and refusing
    to defer leaves the command sitting in `pending` with both entry points replying
    `invitation_already_used`. Nobody can finish it and nobody can start again.
    """
    token = _approve(delivered)
    attempts: list[str] = []
    real_attach = account_provisioning_service._attach_account_number

    def contended(*, account_id: str, role: str, now: datetime) -> str:
        attempts.append(account_id)
        if len(attempts) == 1:
            raise HTTPException(
                status_code=409, detail={"code": "account_number_already_assigned"}
            )
        return real_attach(account_id=account_id, role=role, now=now)

    monkeypatch.setattr(
        account_provisioning_service, "_attach_account_number", contended
    )

    with pytest.raises(HTTPException) as deferred:
        _activate(token)
    assert deferred.value.status_code == 503
    assert deferred.value.detail == {"code": "activation_temporarily_unavailable"}

    resumed = teacher_application_service.activate_from_invitation(
        token=token,
        verified_email=CANDIDATE,
        issuer=ISSUER,
        subject="sub-resumed",
        provider=TeacherProvider(),
        now=lambda: _moment(120),
    )
    assert resumed["status"] == "active"
    assert TEACHER_NUMBER.match(str(_profile(table, resumed["userId"])["account_number"]))


def test_一个地址已经属于别人时激活直接拒绝而不是停在可续做(
    table: TeacherTable, delivered: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the rule above: some refusals really are forever."""
    token = _approve(delivered)
    monkeypatch.setattr(
        account_provisioning_service,
        "_attach_account_number",
        lambda **_kwargs: (_ for _ in ()).throw(
            HTTPException(status_code=409, detail={"code": "account_exists"})
        ),
    )

    with pytest.raises(HTTPException) as refused:
        _activate(token)

    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "account_exists"}


def test_续做只续做本账号_地址对不上就拒绝(table: TeacherTable) -> None:
    """`open_account` resumes by id, and an id alone does not say whose row it is.

    Without the check a caller finishes an account it never opened - including one
    already replaced by a deletion tombstone, which carries no address at all.
    """
    account_provisioning_service.open_account(
        account_id="shared-id",
        role="teacher",
        email="first@example.ch",
        account_status="pending_review",
        created_by="test",
        now=lambda: MOMENT,
    )

    with pytest.raises(HTTPException) as refused:
        account_provisioning_service.open_account(
            account_id="shared-id",
            role="teacher",
            email="second@example.ch",
            account_status="pending_review",
            created_by="test",
            now=lambda: MOMENT,
        )

    assert refused.value.detail == {"code": "account_state_invalid"}


def test_调用方的附加字段改不动身份(table: TeacherTable) -> None:
    """`open_account` is a public entry point now, so what a caller may set is fenced."""
    account_provisioning_service.open_account(
        account_id="fenced-id",
        role="teacher",
        email="fenced@example.ch",
        account_status="pending_review",
        created_by="test",
        extra_fields={
            "role": "admin",
            "email": "attacker@example.ch",
            "account_status": "active",
            "account_number": "A26-9999",
            "activation_command_id": "kept",
        },
        now=lambda: MOMENT,
    )

    profile = _profile(table, "fenced-id")
    assert profile["role"] == "teacher"
    assert profile["email"] == "fenced@example.ch"
    assert profile["account_status"] == "pending_review"
    assert TEACHER_NUMBER.match(str(profile["account_number"]))
    assert profile["activation_command_id"] == "kept"
