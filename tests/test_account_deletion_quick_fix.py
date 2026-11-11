"""The account deletion quick fix: no full-table cliffs on its path (stoasystem/stoa-backend#397).

A deletion read its own command by scanning the whole table, about 34 times a
round; its attachment branch read the whole table in one call; discovery walked
the table with a cursor and reached a command once in three runs; each run moved
every branch by a single page; and `DELETE /auth/me` ran a whole round before it
answered. At ~7k rows that is two days a deletion, and past 10k rows deletion
stops altogether. These tests hold the fix, which leaves the sealed inventory -
and with it every command already in flight - exactly as it was.
"""

from __future__ import annotations

import asyncio
from bisect import bisect_right
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

import test_chat_help_request_lifecycle as lifecycle
from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_message
from stoa import aws
from stoa.aws import Kind
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, account_email_claim_repo, identity_repo
from stoa.jobs import account_deletion as job
from stoa.services import account_deletion_service as service
from stoa.services import account_provisioning_service, attachment_service


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"
# Sealed into every deletion command and checked on every run: a command in
# flight stops with "seal drift" the moment these bytes change.
SEALED_INVENTORY_SHA256 = "8b4087165afbd6bff9a5e9efe59369ae6ed446a20765cca473227c87cc1480e4"

ISSUER = "https://cognito-idp.eu-central-2.amazonaws.com/pool-test"
SUBJECT = "subject-66"
EMAIL = "leaving.student@stoa.test"
ACCEPTED_AT = "2026-11-11T09:07:00+00:00"
PRIVATE = (
    "Probier jetzt 15 : 5.",
    "private student message",
    "private question",
    "Step 2 makes no sense to me.",
)


def test_the_sealed_inventory_bytes_are_unchanged() -> None:
    assert sha256(INVENTORY_PATH.read_bytes()).hexdigest() == SEALED_INVENTORY_SHA256
    assert service.load_private_store_seal()["inventory_sha256"] == SEALED_INVENTORY_SHA256


# ── doubles ────────────────────────────────────────────────────────────────


class _Provider:
    """Cognito, S3 or any other external client: records calls, answers empty."""

    class exceptions:
        class UserNotFoundException(Exception):
            pass

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def call(*_args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append((name, kwargs))
            return {}

        return call


def _complete(**_kwargs: Any) -> service.BranchResult:
    return service.BranchResult("complete", debt_counts={}, quiescent=True, epoch=2)


def _account_rows(user_id: str, *, role: str = "student") -> list[dict[str, Any]]:
    """What opening an account leaves under its own key: the fence and identity."""
    issuer_hash = identity_repo.issuer_hash(ISSUER)
    binding_pk = f"IDENTITY#{issuer_hash}#{SUBJECT}"
    return [
        {
            "PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
            "user_id": user_id, "status": "active", "generation": 1, "version": 1,
        },
        account_email_claim_repo.claim_item(
            email=EMAIL, role=role, account_id=user_id, created_at="2026-09-01T00:00:00+00:00"
        ),
        {
            "PK": binding_pk, "SK": "BINDING", "entity_type": "identity_binding",
            "issuer": ISSUER, "subject": SUBJECT, "user_id": user_id, "status": "active",
            "version": 1,
        },
        {
            "PK": f"USER#{user_id}", "SK": f"IDENTITY#{issuer_hash}#{SUBJECT}",
            "entity_type": "user_identity_inventory", "issuer": ISSUER, "subject": SUBJECT,
            "user_id": user_id, "binding_pk": binding_pk,
        },
    ]


def _accept(user_id: str) -> str:
    receipt = service.accept_account_deletion(
        user_id=user_id,
        initiator=service.OperatorInitiated(initiated_by="operator:test", reason="quick fix"),
        now_iso=ACCEPTED_AT,
    )
    return receipt.command_id


def _command(table: FakeTable, user_id: str, command_id: str) -> dict[str, Any]:
    return table.rows[(f"USER#{user_id}", f"DELETE_COMMAND#{command_id}")]


def _registered(table: FakeTable) -> set[str]:
    return {
        sk for (pk, sk) in table.rows if pk == account_deletion_repo.PENDING_REGISTRY_PK
    }


def _claim(command: dict[str, Any]) -> account_deletion_repo.DeletionCommandClaim:
    now = datetime.now(UTC)
    claim = account_deletion_repo.claim_deletion_command(
        command,
        lease_owner="worker-test",
        now_epoch=int(now.timestamp()),
        lease_expires_at=int(now.timestamp()) + 120,
        now_iso=now.isoformat(),
    )
    assert claim is not None
    return claim


@pytest.fixture
def small_table() -> FakeTable:
    table = FakeTable()
    db_table.install(table)
    table.seed(
        {
            "PK": "USER#student-small", "SK": "PROFILE", "user_id": "student-small",
            "role": "student", "account_status": "active", "version": 1,
        },
        {
            "PK": "USER#student-small", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
            "user_id": "student-small", "status": "active", "generation": 1, "version": 1,
        },
    )
    return table


# ── 1. the command is read by its key ──────────────────────────────────────


def test_acceptance_registers_the_command_in_the_same_commit(small_table: FakeTable) -> None:
    command_id = _accept("student-small")

    command = _command(small_table, "student-small", command_id)
    assert command["status"] == "pending"
    assert _registered(small_table) == {f"student-small#{command_id}"}
    row = small_table.rows[(account_deletion_repo.PENDING_REGISTRY_PK, f"student-small#{command_id}")]
    # Named under attributes of its own, so no deletion sweep takes it for the account's row.
    assert not account_deletion_repo._targets_user(row, "student-small")


@pytest.mark.parametrize("budgeted", [False, True])
def test_a_deletion_reads_its_command_by_key_and_never_scans_for_it(
    small_table: FakeTable, monkeypatch: pytest.MonkeyPatch, budgeted: bool
) -> None:
    command_id = _accept("student-small")
    claim = _claim(_command(small_table, "student-small", command_id))
    assert claim.user_id == "student-small"

    def no_scan(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the deletion command was looked up by a table scan")

    monkeypatch.setattr(account_deletion_repo, "get_command_by_id", no_scan)
    monkeypatch.setattr(account_deletion_repo, "_scan_commands", no_scan)
    worker = service.AccountDeletionService(
        branch_handlers={branch: _complete for branch in service.ACCOUNT_DELETION_BRANCH_IDS},
        remaining_seconds=(lambda: 500.0) if budgeted else None,
    )
    before = len(small_table.requests)

    worker.continue_command(claim)

    command = _command(small_table, "student-small", command_id)
    assert command["status"] == "complete"
    assert small_table.rows[("USER#student-small", "ACCOUNT_FENCE")]["status"] == "deleted"
    assert _registered(small_table) == set()  # dropped in the finalizing commit
    requests = small_table.requests[before:]
    assert not [operation for operation, _ in requests if operation == "scan"]
    assert (
        "get_item",
        {"Key": {"PK": "USER#student-small", "SK": f"DELETE_COMMAND#{command_id}"},
         "ConsistentRead": True},
    ) in requests


# ── 2. the attachment branch pages ─────────────────────────────────────────


class _BigTable:
    """A large table that pages cheaply: `Limit` rows, else a 1 MB page of 1000."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = sorted(rows, key=lambda row: (row["PK"], row["SK"]))
        self.keys = [(row["PK"], row["SK"]) for row in self.rows]
        self.scans: list[dict[str, Any]] = []

    def remove(self, key: tuple[str, str]) -> None:
        index = self.keys.index(key)
        del self.rows[index], self.keys[index]

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.scans.append(kwargs)
        resume = kwargs.get("ExclusiveStartKey")
        start = bisect_right(self.keys, (resume["PK"], resume["SK"])) if resume else 0
        limit = int(kwargs.get("Limit") or 1000)
        window = self.rows[start:start + limit]
        response: dict[str, Any] = {"Items": [dict(row) for row in window]}
        if start + limit < len(self.rows):
            response["LastEvaluatedKey"] = {"PK": window[-1]["PK"], "SK": window[-1]["SK"]}
        return response


def _unrelated(count: int) -> list[dict[str, Any]]:
    return [{"PK": f"ROW#{index:05d}", "SK": "DATA", "entity_type": "unrelated"} for index in range(count)]


OWNER = "student-big"
LATE_ATTACHMENT = {
    "PK": "ROW#11000", "SK": "ATTACHMENT", "entity_type": "attachment",
    "student_id": OWNER, "attachment_id": "att-late", "status": "active",
}


def test_the_owner_listing_reads_past_ten_thousand_rows() -> None:
    table = _BigTable([*_unrelated(12_000), LATE_ATTACHMENT])

    items = attachment_service.attachment_repo.list_owner_attachment_items(OWNER, table=table)

    assert [item["attachment_id"] for item in items] == ["att-late"]
    assert all(call["ConsistentRead"] is True for call in table.scans)
    assert "Limit" not in table.scans[0]  # whole 1 MB pages, not hundred-row ones


def _persist(result: service.BranchResult) -> dict[str, Any]:
    return result.persisted("2026-11-11T10:00:00+00:00", generation=1)


@pytest.mark.parametrize(
    "previous",
    [
        {},
        # A result written before the fix: one empty cursor per purge category.
        {
            "status": "retryable",
            "cursor": None,
            "debt_counts": dict.fromkeys(attachment_service.PURGE_CURSOR_CATEGORIES, 0),
            "epoch": 0,
        },
    ],
)
def test_the_attachment_branch_pages_past_ten_thousand_rows_and_purges_once(
    monkeypatch: pytest.MonkeyPatch, previous: dict[str, Any]
) -> None:
    table = _BigTable([*_unrelated(12_000), LATE_ATTACHMENT])
    db_table.install(table)
    purges: list[str] = []

    def purge(owner_id: str, **kwargs: Any) -> Any:
        purges.append(owner_id)
        assert kwargs["account_fence_generation"] == 1
        table.remove(("ROW#11000", "ATTACHMENT"))
        return attachment_service.AttachmentPurgeBranchResult(
            attachment_service.AttachmentPurgeBranchStatus.COMPLETE, quiescent=True, deleted=1
        )

    monkeypatch.setattr(attachment_service, "purge_student_attachments", purge)
    aws.install({Kind.S3: _Provider()})
    command = {"user_id": OWNER, "generation": 1}
    statuses: list[tuple[str, int]] = []
    state: dict[str, Any] = previous
    for _call in range(400):
        result = service._attachments_branch(command=command, previous=state)
        state = _persist(result)
        if result.cursor is None:
            statuses.append((result.status, result.epoch))
        if result.status == "complete":
            break

    assert purges == [OWNER]
    # A dirty pass, then two clean ones: the rule every other branch keeps.
    assert statuses == [("retryable", 0), ("retryable", 1), ("complete", 2)]
    assert state["quiescent"] is True and state["cursor"] is None and state["debt_counts"] == {}
    assert len(table.scans) > 300  # three passes of 121 strong pages each
    assert all(call["ConsistentRead"] is True and call["Limit"] == 100 for call in table.scans)


def test_a_purge_that_cannot_finish_keeps_the_branch_from_completing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _BigTable([*_unrelated(250), LATE_ATTACHMENT])
    db_table.install(table)
    monkeypatch.setattr(
        attachment_service,
        "purge_student_attachments",
        lambda *_a, **_k: attachment_service.AttachmentPurgeBranchResult(
            attachment_service.AttachmentPurgeBranchStatus.RETRYABLE
        ),
    )
    aws.install({Kind.S3: _Provider()})
    state: dict[str, Any] = {}
    for _call in range(30):
        result = service._attachments_branch(command={"user_id": OWNER, "generation": 1}, previous=state)
        state = _persist(result)
        assert result.status == "retryable"
    assert state["epoch"] == 0


# ── 3. discovery by the registry, with the scan kept for older commands ────


class _Worker:
    def __init__(self) -> None:
        self.continued: list[str] = []

    def continue_command(self, claim: account_deletion_repo.DeletionCommandClaim) -> None:
        self.continued.append(claim.command_id)


def _legacy_command(command_id: str, user: str) -> dict[str, Any]:
    return {
        "PK": f"USER#{user}", "SK": f"DELETE_COMMAND#{command_id}",
        "entity_type": "account_deletion_command", "command_id": command_id,
        "user_id": user, "generation": 1, "status": "running", "version": 131,
        "command_version": 131, "lease_owner": "an-earlier-run", "lease_expires_at": 1_000,
        "accepted_at": ACCEPTED_AT,
    }


def test_registered_commands_are_found_every_run_and_older_ones_by_the_scan(
    small_table: FakeTable,
) -> None:
    command_id = _accept("student-small")
    small_table.seed(
        *_unrelated(2_600),
        _legacy_command("legacy-command", "zz-legacy"),
        # A row left behind by a command that already finished.
        {
            **account_deletion_repo.pending_registry_key("gone", "finished"),
            "entity_type": "account_deletion_pending",
            "deletion_user_id": "gone", "deletion_command_id": "finished",
        },
    )
    worker = _Worker()

    first = job.run_pending_deletions(service_factory=lambda: worker)

    # The registered command is claimed although the scan's budget ends long
    # before its row; the older one is past that budget this run.
    assert worker.continued == [command_id]
    assert first.discovered == 1
    assert "gone#finished" not in _registered(small_table)

    job.run_pending_deletions(service_factory=lambda: worker)

    assert worker.continued == [command_id, "legacy-command"]
    # Found by the scan, and registered on the way: the next run's query finds it.
    assert {
        (entry.user_id, entry.command_id) for entry in account_deletion_repo.list_pending_deletions()
    } == {("student-small", command_id), ("zz-legacy", "legacy-command")}


@pytest.mark.parametrize("value", ["", "not-a-time", "2026-11-11T10:00:00", None])
def test_the_lease_release_refuses_an_invalid_time(small_table: FakeTable, value: Any) -> None:
    command_id = _accept("student-small")
    claim = _claim(_command(small_table, "student-small", command_id))
    before = dict(_command(small_table, "student-small", command_id))

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.release_deletion_command_claim(
            before, claim=claim, now_epoch=int(datetime.now(UTC).timestamp()), updated_at=value
        )

    assert _command(small_table, "student-small", command_id) == before


def test_only_the_lease_holder_can_release_it(small_table: FakeTable) -> None:
    command_id = _accept("student-small")
    claim = _claim(_command(small_table, "student-small", command_id))
    command = dict(_command(small_table, "student-small", command_id))
    stale = account_deletion_repo.DeletionCommandClaim(
        command_id=claim.command_id, generation=claim.generation, lease_owner="someone-else",
        lease_expires_at=claim.lease_expires_at, command_version=claim.command_version,
        branch_results_digest=claim.branch_results_digest, user_id=claim.user_id,
    )
    now = datetime.now(UTC)

    with pytest.raises(account_deletion_repo.DeletionCommandClaimLost):
        account_deletion_repo.release_deletion_command_claim(
            command, claim=stale, now_epoch=int(now.timestamp()), updated_at=now.isoformat()
        )
    released = account_deletion_repo.release_deletion_command_claim(
        command, claim=claim, now_epoch=int(now.timestamp()), updated_at=now.isoformat()
    )

    assert released.lease_expires_at < int(now.timestamp())
    stored = _command(small_table, "student-small", command_id)
    assert stored["status"] == "running" and stored["command_version"] == claim.command_version + 1


def test_the_registry_is_read_with_one_strong_query(small_table: FakeTable) -> None:
    _accept("student-small")
    before = len(small_table.requests)

    account_deletion_repo.list_pending_deletions()

    (request,) = small_table.requests[before:]
    assert request[0] == "query" and request[1]["ConsistentRead"] is True
    assert request[1]["ExpressionAttributeValues"] == {":pk": "ACCOUNT_DELETION_PENDING"}


# ── 4 and 5. a time-budgeted run, and the fast path first ──────────────────


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    table = lifecycle.table.__wrapped__(monkeypatch)
    lifecycle._dispatch_to(table, lifecycle.TEACHER)
    assert lifecycle._reply(lifecycle._client(), PRIVATE[0]).status_code in {200, 201}
    student = lifecycle.STUDENT
    seed_message(
        table, conversation_id=lifecycle.CONV, role="student", message_id="student-1",
        student_id=student, content=PRIVATE[1], created_at="2026-09-28T12:01:00+00:00",
    )
    table.seed(
        {
            "PK": "QUESTION#q-lane", "SK": "META", "entity_type": "question",
            "schema_version": "question.v1", "question_id": "q-lane", "student_id": student,
            "owner_id": student, "status": "resolved", "version": 3,
            "account_fence_generation": 1, "subject": "math", "content": PRIVATE[2],
            "created_at": "2026-09-27T10:00:00+00:00",
        },
        {"PK": f"PROGRESS#{student}", "SK": "LESSON#l1", "student_id": student, "completed": True},
        {"PK": f"USAGE_LEDGER#{student}", "SK": "EVENT#e1", "student_id": student, "action": "question"},
        *_unrelated(400),
        *_account_rows(student),
    )
    profile = dict(table.rows[(f"USER#{student}", "PROFILE")], email=EMAIL)
    table.seed(profile)
    return table


@pytest.fixture
def providers() -> dict[Kind, _Provider]:
    installed = {Kind.S3: _Provider(), Kind.COGNITO: _Provider()}
    aws.install(installed)
    return installed


def _private_left(table: FakeTable) -> list[tuple[str, str]]:
    return [
        key for key, row in table.rows.items()
        if any(text in json.dumps(row, default=str) for text in PRIVATE)
    ]


def test_one_scheduled_run_completes_a_deletion_within_its_budget(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)

    summary = job.run_pending_deletions(remaining_seconds=lambda: 500.0)

    assert summary.claimed == 1 and summary.continued == 1 and summary.retryable == 0
    command = _command(table, student, command_id)
    assert command["status"] == "complete", command.get("branch_results")
    assert command["inventory_sha256"] == SEALED_INVENTORY_SHA256
    assert table.rows[(f"USER#{student}", "ACCOUNT_FENCE")]["status"] == "deleted"
    assert _registered(table) == set()
    assert _private_left(table) == []


def test_a_run_out_of_budget_stops_cleanly_and_gives_its_lease_back(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)
    clock = {"calls": 0}

    def running_out() -> float:
        clock["calls"] += 1
        return 500.0 if clock["calls"] <= 8 else 30.0

    stopped = job.run_pending_deletions(remaining_seconds=running_out)

    command = _command(table, student, command_id)
    assert stopped.claimed == 1 and stopped.continued == 1
    assert command["status"] == "running"
    results = command["branch_results"]
    assert results and set(results) < set(service.ACCOUNT_DELETION_BRANCH_IDS)
    assert command["branch_results_digest"] == account_deletion_repo.branch_results_digest(results)
    # Released, not left to run out: the next run claims it at once.
    assert int(command["lease_expires_at"]) < int(datetime.now(UTC).timestamp())
    assert table.rows[(f"USER#{student}", "ACCOUNT_FENCE")]["status"] == "deletion_pending"

    finished = job.run_pending_deletions(remaining_seconds=lambda: 500.0)

    assert finished.claimed == 1
    assert _command(table, student, command_id)["status"] == "complete"
    assert _private_left(table) == []


def test_no_command_is_claimed_with_less_than_the_margin_left(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    command_id = _accept(lifecycle.STUDENT)
    before = dict(_command(table, lifecycle.STUDENT, command_id))

    summary = job.run_pending_deletions(remaining_seconds=lambda: 30.0)

    assert summary.claimed == 0 and summary.retryable >= 1
    assert _command(table, lifecycle.STUDENT, command_id) == before


def test_an_in_flight_command_from_before_the_fix_is_picked_up_and_completes(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    """The production command in flight at deploy: no registry row, an old-format
    attachment result, mid-run, an expired lease, accepted under the current seal."""
    student = lifecycle.STUDENT
    command_id = _accept(student)
    registry = account_deletion_repo.pending_registry_key(student, command_id)
    del table.rows[(registry["PK"], registry["SK"])]
    seal = service.load_private_store_seal()
    contract = seal["branch_contracts"]["attachments"]
    results = {
        "attachments": {
            "status": "retryable", "cursor": None,
            "debt_counts": dict.fromkeys(attachment_service.PURGE_CURSOR_CATEGORIES, 0),
            "quiescent": True, "epoch": 1, "legal_retention_blocked": 0,
            "external_receipts": [], "generation": 1,
            "handler_version": contract["handler_version"],
            "subfamilies": contract["subfamilies"], "updated_at": "2026-11-11T09:34:00+00:00",
            "result_version": 3,
        }
    }
    row = dict(_command(table, student, command_id))
    row.update(
        status="running", lease_owner="an-earlier-run", lease_expires_at=1_000,
        version=131, command_version=131, branch_results=results,
        branch_results_digest=account_deletion_repo.branch_results_digest(results),
    )
    table.seed(row)

    job.run_pending_deletions(remaining_seconds=lambda: 500.0)

    command = _command(table, student, command_id)
    assert command["status"] == "complete"
    assert command["inventory_sha256"] == SEALED_INVENTORY_SHA256
    assert _registered(table) == set()


def test_the_first_run_releases_the_email_and_revokes_the_provider_identity_at_once(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)
    command = _command(table, student, command_id)
    claim = _claim(command)
    worker = service.AccountDeletionService(
        # No branch gets anywhere: what changes is the fast path's doing alone.
        branch_handlers={
            branch: (lambda **_k: service.BranchResult("retryable", debt_counts={"dependency": 1}))
            for branch in service.ACCOUNT_DELETION_BRANCH_IDS
        },
        remaining_seconds=lambda: 500.0,
    )

    worker.continue_command(claim)

    profile = table.rows[(f"USER#{student}", "PROFILE")]
    assert account_deletion_repo.is_deletion_tombstone(profile) and "email" not in profile
    assert account_email_claim_repo.get_claim(email=EMAIL, role="student") is None
    # The same address may be invited again in the same role.
    assert account_provisioning_service.check_invitation(role="student", email=EMAIL)["holder"] is None
    revoke = table.rows[(f"USER#{student}", "PROVIDER_REVOKE#00000000000000000001")]
    assert revoke["status"] == "complete"
    cognito = [name for name, _ in providers[Kind.COGNITO].calls]
    assert cognito == ["admin_user_global_sign_out", "admin_delete_user"]
    assert providers[Kind.COGNITO].calls[1][1]["Username"] == SUBJECT
    binding_pk = f"IDENTITY#{identity_repo.issuer_hash(ISSUER)}#{SUBJECT}"
    assert table.rows[(binding_pk, "BINDING")]["entity_type"] == "identity_deletion_evidence"
    inventory = table.rows[(f"USER#{student}", f"IDENTITY#{identity_repo.issuer_hash(ISSUER)}#{SUBJECT}")]
    assert inventory["entity_type"] == "identity_deletion_evidence"
    # The scans still decide completion: nothing is complete yet.
    assert _command(table, student, command_id)["status"] == "running"


def test_the_fast_path_leaves_the_branches_a_clean_scan_and_a_valid_seal(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)
    asyncio.run(job.continue_deletion_command(command_id))
    assert account_email_claim_repo.get_claim(email=EMAIL, role="student") is None

    job.run_pending_deletions(remaining_seconds=lambda: 500.0)

    command = _command(table, student, command_id)
    assert command["status"] == "complete"
    # The identity branch replays the debt the fast path completed, and the
    # provider is not asked twice.
    assert [name for name, _ in providers[Kind.COGNITO].calls] == [
        "admin_user_global_sign_out", "admin_delete_user",
    ]


# ── 6. the request side ────────────────────────────────────────────────────


def test_the_request_side_releases_the_email_only_and_never_scans(
    table: FakeTable, providers: dict[Kind, _Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)

    def no_branch(**_kwargs: Any) -> service.BranchResult:
        raise AssertionError("the request ran a deletion branch")

    for branch in service.ACCOUNT_DELETION_BRANCH_IDS:
        monkeypatch.setitem(service.BRANCH_HANDLERS, branch, no_branch)
    before = len(table.requests)

    asyncio.run(job.continue_deletion_command(command_id))

    assert not [operation for operation, _ in table.requests[before:] if operation == "scan"]
    assert account_deletion_repo.is_deletion_tombstone(table.rows[(f"USER#{student}", "PROFILE")])
    assert account_email_claim_repo.get_claim(email=EMAIL, role="student") is None
    # The API function holds no Cognito admin rights: the provider revoke and
    # the identity rows wait for the deletion function's first run.
    assert providers[Kind.COGNITO].calls == []
    binding_pk = f"IDENTITY#{identity_repo.issuer_hash(ISSUER)}#{SUBJECT}"
    assert table.rows[(binding_pk, "BINDING")]["entity_type"] == "identity_binding"
    command = _command(table, student, command_id)
    assert command["status"] == "running"
    assert command.get("branch_results") in ({}, None)
    # Its lease is given back, so the schedule need not wait for it.
    assert int(command["lease_expires_at"]) < int(datetime.now(UTC).timestamp())


def test_the_request_side_leaves_a_command_without_a_registry_row_to_the_schedule(
    table: FakeTable, providers: dict[Kind, _Provider]
) -> None:
    student = lifecycle.STUDENT
    command_id = _accept(student)
    registry = account_deletion_repo.pending_registry_key(student, command_id)
    del table.rows[(registry["PK"], registry["SK"])]
    before = len(table.requests)

    asyncio.run(job.continue_deletion_command(command_id))

    assert not [operation for operation, _ in table.requests[before:] if operation == "scan"]
    assert _command(table, student, command_id)["status"] == "pending"
    assert not account_deletion_repo.is_deletion_tombstone(table.rows[(f"USER#{student}", "PROFILE")])


def test_the_delete_route_still_schedules_the_continuation_by_command_id() -> None:
    import inspect

    from stoa.routers import auth

    source = inspect.getsource(auth.delete_me)
    assert "background_tasks.add_task(continue_deletion_command, receipt.command_id)" in source
