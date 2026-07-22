from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from typing import Any, Callable

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa import deps
from stoa.db.repositories import account_deletion_repo
from stoa.routers import auth
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import account_deletion_service


USER_ID = "student-deleted-1"
ISSUER = "https://identity.example/pool"
SUBJECT = "subject-deleted-1"
ACCEPTED_AT = "2026-07-22T00:00:00+00:00"
COMPLETED_AT = "2026-07-22T00:05:00+00:00"


def _token(*, issuer: str = ISSUER, subject: str = SUBJECT) -> VerifiedAccessToken:
    return VerifiedAccessToken(
        issuer=issuer,
        subject=subject,
        client_id="student-client",
        groups=("students",),
    )


class _IdentityRepository:
    def __init__(self) -> None:
        self.active = True

    async def get_binding(self, _issuer: str, _subject: str) -> dict[str, str] | None:
        if not self.active:
            return None
        return {"status": "active", "user_id": USER_ID}


class _DeletionTable:
    def __init__(self) -> None:
        self.fence: dict[str, Any] = {
            "PK": f"USER#{USER_ID}",
            "SK": "ACCOUNT_FENCE",
            "entity_type": "account_fence",
            "schema_version": "account-fence.v1",
            "user_id": USER_ID,
            "status": "active",
            "generation": 3,
            "version": 1,
        }
        self.command: dict[str, Any] | None = None
        self.effects = {
            "branch_handlers": 0,
            "cleanup_calls": 0,
            "command_claims": 0,
            "command_writes": 0,
            "fence_writes": 0,
            "background_scheduled": 0,
            "background_runs": 0,
        }

    def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
        if Key["SK"] == "ACCOUNT_FENCE":
            return {"Item": deepcopy(self.fence)}
        if Key["SK"].startswith("DELETE_COMMAND#") and self.command:
            return {"Item": deepcopy(self.command)}
        return {}

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        values = kwargs["ExpressionAttributeValues"]
        if (
            self.command
            and self.command.get("issuer_hash") == values[":issuer"]
            and self.command.get("subject_hash") == values[":subject"]
        ):
            return {"Items": [deepcopy(self.command)]}
        return {"Items": []}

    def begin_account_deletion(
        self, fence: dict[str, Any], command: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        assert self.fence["status"] == "active"
        command = {
            **command,
            "accepted_at": ACCEPTED_AT,
            "created_at": ACCEPTED_AT,
            "updated_at": ACCEPTED_AT,
        }
        fence = {
            **fence,
            "deletion_accepted_at": ACCEPTED_AT,
            "updated_at": ACCEPTED_AT,
        }
        self.fence = deepcopy(fence)
        self.command = deepcopy(command)
        self.effects["fence_writes"] += 1
        self.effects["command_writes"] += 1
        return deepcopy(self.fence), deepcopy(self.command)

    def complete(self, command_id: str) -> None:
        assert self.command and self.command["command_id"] == command_id
        self.effects["command_claims"] += 1
        self.effects["branch_handlers"] += len(
            account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS
        )
        self.effects["cleanup_calls"] += 1
        terminal = {
            key: deepcopy(self.command[key])
            for key in (
                "PK",
                "SK",
                "entity_type",
                "command_id",
                "user_id",
                "generation",
                "accepted_at",
                "inventory_sha256",
                "issuer_hash",
                "subject_hash",
                "fingerprint",
                "method",
                "path",
                "request_body_sha256",
            )
        }
        terminal.update(
            {
                "schema_version": "account-deletion-command.v2",
                "status": "complete",
                "completed_at": COMPLETED_AT,
                "receipt": {
                    "command_id": command_id,
                    "status": "deleted",
                    "completed_at": COMPLETED_AT,
                },
            }
        )
        self.command = terminal
        self.fence = {
            **self.fence,
            "schema_version": "account-fence.v2",
            "status": "deleted",
            "deleted_at": COMPLETED_AT,
            "version": int(self.fence["version"]) + 1,
        }
        self.effects["command_writes"] += 1
        self.effects["fence_writes"] += 1

    def seed_terminal(self, token: VerifiedAccessToken) -> None:
        seal = account_deletion_service.load_private_store_seal()
        command_id = "delete-command-terminal"
        fingerprint = account_deletion_service.deletion_command_fingerprint(
            verified=token,
            user_id=USER_ID,
            method="DELETE",
            path="/auth/me",
            body=b"",
            generation=3,
        )
        self.command = {
            "PK": f"USER#{USER_ID}",
            "SK": f"DELETE_COMMAND#{command_id}",
            "entity_type": "account_deletion_command",
            "schema_version": "account-deletion-command.v2",
            "command_id": command_id,
            "user_id": USER_ID,
            "generation": 3,
            "status": "complete",
            "accepted_at": ACCEPTED_AT,
            "completed_at": COMPLETED_AT,
            "inventory_sha256": seal["inventory_sha256"],
            "issuer_hash": account_deletion_repo.normalized_identity_hash(ISSUER),
            "subject_hash": account_deletion_repo.normalized_identity_hash(SUBJECT),
            "fingerprint": fingerprint,
            "method": "DELETE",
            "path": "/auth/me",
            "request_body_sha256": sha256(b"").hexdigest(),
            "receipt": {
                "command_id": command_id,
                "status": "deleted",
                "completed_at": COMPLETED_AT,
            },
        }
        self.fence = {
            **self.fence,
            "schema_version": "account-fence.v2",
            "status": "deleted",
            "command_id": command_id,
            "version": 2,
            "deleted_at": COMPLETED_AT,
        }


def _client(
    *,
    table: _DeletionTable,
    identity: _IdentityRepository,
    monkeypatch: pytest.MonkeyPatch,
    token: VerifiedAccessToken | None = None,
    continuation: Callable[[str], None] | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[deps.get_verified_token] = lambda: token or _token()
    app.dependency_overrides[deps.get_identity_repository] = lambda: identity
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)

    def run(command_id: str) -> None:
        table.effects["background_runs"] += 1
        if continuation:
            continuation(command_id)

    monkeypatch.setattr(auth, "continue_deletion_command", run)
    original_add_task = BackgroundTasks.add_task

    def add_task(self: BackgroundTasks, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        table.effects["background_scheduled"] += 1
        original_add_task(self, func, *args, **kwargs)

    monkeypatch.setattr(BackgroundTasks, "add_task", add_task)
    return TestClient(app)


def test_completed_deletion_replays_stored_receipt_without_new_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _DeletionTable()
    identity = _IdentityRepository()

    def finalize_lost_response(command_id: str) -> None:
        table.complete(command_id)
        identity.active = False

    client = _client(
        table=table,
        identity=identity,
        monkeypatch=monkeypatch,
        continuation=finalize_lost_response,
    )
    lost_response = client.delete("/auth/me", headers={"Authorization": "Bearer token"})
    assert lost_response.status_code == 202
    assert lost_response.json()["status"] == "deletion_pending"
    assert "completedAt" not in lost_response.json()
    command_id = lost_response.json()["commandId"]
    del lost_response

    assert table.command is not None
    stored_command = deepcopy(table.command)
    stored_receipt = deepcopy(stored_command["receipt"])
    stored_public_receipt = {
        "commandId": stored_receipt["command_id"],
        "status": stored_receipt["status"],
        "acceptedAt": stored_command["accepted_at"],
        "completedAt": stored_receipt["completed_at"],
    }
    before_replay = deepcopy(table.effects)

    def fail_if_called(boundary: str) -> Callable[..., Any]:
        def fail(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail(f"terminal replay crossed {boundary} boundary")

        return fail

    # Identity recovery performs its one required read-only command lookup. Once the
    # compact terminal command is found, no destructive discovery, branch/provider
    # work, scheduling, or persistence boundary may reopen.
    monkeypatch.setattr(
        account_deletion_repo,
        "scan_owned_private_rows",
        fail_if_called("private-row discovery"),
    )
    monkeypatch.setattr(
        account_deletion_repo, "transact", fail_if_called("repository transaction")
    )
    monkeypatch.setattr(
        account_deletion_service.boto3,
        "client",
        fail_if_called("provider client"),
    )
    for branch_id in account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS:
        monkeypatch.setitem(
            account_deletion_service.BRANCH_HANDLERS,
            branch_id,
            fail_if_called(f"{branch_id} cleanup"),
        )
    monkeypatch.setattr(
        auth, "continue_deletion_command", fail_if_called("continuation scheduler")
    )
    monkeypatch.setattr(
        BackgroundTasks, "add_task", fail_if_called("background scheduler")
    )
    monkeypatch.setattr(
        table, "begin_account_deletion", fail_if_called("deletion write")
    )
    for method in ("put_item", "update_item", "delete_item", "transact_write_items"):
        monkeypatch.setattr(table, method, fail_if_called(method), raising=False)

    class ChangedReplayClock:
        values = iter(
            (
                "2037-01-01T01:00:00+00:00",
                "2041-06-15T12:30:00+00:00",
                "2099-12-31T23:59:59+00:00",
            )
        )
        calls = 0

        @classmethod
        def now(cls, _timezone: object) -> datetime:
            cls.calls += 1
            return datetime.fromisoformat(next(cls.values))

    monkeypatch.setattr(deps, "datetime", ChangedReplayClock)

    replays = [
        client.delete("/auth/me", headers={"Authorization": "Bearer token"})
        for _ in range(3)
    ]
    replay_bodies = [response.json() for response in replays]

    assert all(response.status_code == 202 for response in replays)
    assert replay_bodies == [stored_public_receipt] * 3
    assert [response.content for response in replays] == [replays[0].content] * 3
    assert stored_receipt == {
        "command_id": command_id,
        "status": "deleted",
        "completed_at": COMPLETED_AT,
    }
    assert {body["commandId"] for body in replay_bodies} == {command_id}
    assert {body["status"] for body in replay_bodies} == {"deleted"}
    assert {body["completedAt"] for body in replay_bodies} == {COMPLETED_AT}
    assert ChangedReplayClock.calls == len(replays)
    assert table.command == stored_command
    assert table.effects == before_replay

    public_keys = {"commandId", "status", "acceptedAt", "completedAt"}
    forbidden_fragments = (
        "PK",
        "SK",
        "USER#",
        "DELETE_COMMAND#",
        "provider",
        "token",
        "inventory",
        "fingerprint",
        "issuer",
        "subject",
        "diagnostic",
        "exception",
        "traceback",
    )
    for body in replay_bodies:
        assert set(body) == public_keys
        rendered = repr(body).lower()
        assert not any(fragment.lower() in rendered for fragment in forbidden_fragments)


def test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the Phase 475 checked-evidence selector bound to the stronger proof."""
    test_completed_deletion_replays_stored_receipt_without_new_effects(monkeypatch)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda command: command.pop("receipt"),
        lambda command: command["receipt"].update(command_id="different-command"),
        lambda command: command["receipt"].update(status="deletion_pending"),
        lambda command: command["receipt"].pop("completed_at"),
        lambda command: command["receipt"].update(completed_at="not-a-timestamp"),
        lambda command: command["receipt"].update(
            completed_at="2026-07-22T02:05:00+02:00"
        ),
    ],
)
def test_malformed_terminal_receipt_fails_closed_without_effects(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], Any],
) -> None:
    table = _DeletionTable()
    table.seed_terminal(_token())
    assert table.command
    mutate(table.command)
    identity = _IdentityRepository()
    identity.active = False
    client = _client(table=table, identity=identity, monkeypatch=monkeypatch)

    response = client.delete("/auth/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "identity_conflict"
    assert not any(table.effects.values())


@pytest.mark.parametrize("mismatch", ["fingerprint", "identity"])
def test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    table = _DeletionTable()
    table.seed_terminal(_token())
    identity = _IdentityRepository()
    identity.active = False
    token = _token()
    if mismatch == "fingerprint":
        assert table.command
        table.command["fingerprint"] = "0" * 64
    else:
        token = _token(subject="different-subject")
    client = _client(
        table=table,
        identity=identity,
        monkeypatch=monkeypatch,
        token=token,
    )

    response = client.delete("/auth/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "identity_conflict"
    assert not any(table.effects.values())


def test_pending_replay_schedules_one_continuation_per_accepted_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _DeletionTable()
    identity = _IdentityRepository()
    client = _client(table=table, identity=identity, monkeypatch=monkeypatch)

    first = client.delete("/auth/me", headers={"Authorization": "Bearer token"})
    second = client.delete("/auth/me", headers={"Authorization": "Bearer token"})

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert first.json()["status"] == "deletion_pending"
    assert "completedAt" not in first.json()
    assert table.effects["background_scheduled"] == 2
    assert table.effects["background_runs"] == 2
    assert table.effects["command_writes"] == 1
    assert table.effects["fence_writes"] == 1
