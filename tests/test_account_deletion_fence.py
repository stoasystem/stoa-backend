"""Plan 473-29 contracts for deny-first, resumable account deletion."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Mapping

import pytest

from stoa.db import data_catalog
from stoa.db import table as db_table
from stoa.db.repositories import (
    account_deletion_repo,
    attachment_repo,
    user_repo,
)
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import AccountStatus, resolve_actor
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import help_requests, learning_session, owner_registry_sweep
from fakes.dynamodb import FakeTable, from_wire
from stoa.services import account_deletion_flow as flow


STUDENT_ID = "student-delete-1"
ISSUER = "https://identity.example/pool"
SUBJECT = "subject-delete-1"
NOW = "2026-07-17T20:45:16+00:00"


def _deletion_modules():
    return (
        importlib.import_module("stoa.db.repositories.account_deletion_repo"),
        importlib.import_module("stoa.services.account_deletion_service"),
        importlib.import_module("stoa.jobs.account_deletion"),
    )


def _token(*, issuer: str = ISSUER, subject: str = SUBJECT) -> VerifiedAccessToken:
    return VerifiedAccessToken(
        issuer=issuer,
        subject=subject,
        client_id="student-client",
        groups=("students",),
    )


class _IdentityFacts:
    def __init__(self, fence: dict[str, Any] | None) -> None:
        self.fence = fence
        self.reads: list[str] = []

    async def get_session_revocation(self, _issuer, _subject, _origin_jti):
        """No sign-in of this fixture was ever signed out."""
        return None

    async def get_binding(self, _issuer: str, _subject: str) -> dict[str, Any]:
        self.reads.append("binding")
        return {"status": "active", "user_id": STUDENT_ID}

    async def get_account_fence(self, _user_id: str) -> dict[str, Any] | None:
        self.reads.append("fence")
        return self.fence

    async def get_account(self, _user_id: str) -> dict[str, Any]:
        self.reads.append("account")
        return {
            "user_id": STUDENT_ID,
            "role": "student",
            "account_status": "active",
        }

    async def get_current_grants(
        self, _user_id: str
    ) -> list[Mapping[str, object]]:
        self.reads.append("grants")
        return []


class _AccountTable(FakeTable):
    """The shared table double, with the account's own rows at hand."""

    def __init__(self, *, profile: dict[str, Any] | None = None) -> None:
        super().__init__()
        # A clean daily registry sweep, as a new deletion requires (#641).
        self.seed({**owner_registry_sweep.RUN_MARKER_KEY, "complete": True,
                   "missing_registrations": 0, "completed_at": datetime.now(UTC).isoformat()})
        if profile is not None:
            self.seed(profile)

    @property
    def profile(self) -> dict[str, Any] | None:
        return self.rows.get((f"USER#{STUDENT_ID}", "PROFILE"))

    @property
    def fence(self) -> dict[str, Any] | None:
        return self.rows.get((f"USER#{STUDENT_ID}", "ACCOUNT_FENCE"))

    @fence.setter
    def fence(self, value: None) -> None:
        assert value is None
        self.rows.pop((f"USER#{STUDENT_ID}", "ACCOUNT_FENCE"), None)

    @property
    def command(self) -> dict[str, Any] | None:
        return next(
            (row for (pk, sk), row in self.rows.items()
             if pk == f"USER#{STUDENT_ID}" and sk.startswith("DELETE_COMMAND#")),
            None,
        )


def test_deletion_is_the_account_fences_lifecycle_not_a_profile_status() -> None:
    repository, _service, _job = _deletion_modules()

    # Deletion is the account fence's lifecycle, not a profile status (#289).
    assert "deletion_pending" not in {status.value for status in AccountStatus}
    assert repository.account_fence_key(STUDENT_ID) == {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "ACCOUNT_FENCE",
    }


@pytest.mark.asyncio
async def test_resolve_actor_checks_permanent_fence_before_profile_or_grants() -> None:
    active = _IdentityFacts(
        {
            "PK": f"USER#{STUDENT_ID}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": 1,
        }
    )
    actor = await resolve_actor(_token(), active)
    assert actor.user_id == STUDENT_ID
    assert active.reads == ["binding", "fence", "account", "grants"]

    closing = _IdentityFacts(
        {
            "PK": f"USER#{STUDENT_ID}",
            "SK": "ACCOUNT_FENCE",
            "status": "deletion_pending",
            "generation": 1,
        }
    )
    with pytest.raises(SecurityDecisionError):
        await resolve_actor(_token(), closing)
    assert closing.reads == ["binding", "fence"]


def test_legacy_backfill_requires_one_existing_active_canonical_profile() -> None:
    repository, _service, _job = _deletion_modules()
    table = _AccountTable(
        profile={
            "PK": f"USER#{STUDENT_ID}",
            "SK": "PROFILE",
            "user_id": STUDENT_ID,
            "role": "student",
            "account_status": "active",
        }
    )
    fence = repository.ensure_active_account_fence(STUDENT_ID, table=table, now_iso=NOW)
    assert fence["status"] == "active"
    assert fence["generation"] == 1

    assert table.profile is not None
    table.profile["account_status"] = "deleted"
    table.fence = None
    with pytest.raises(repository.AccountDeletionConflict):
        repository.ensure_active_account_fence(STUDENT_ID, table=table, now_iso=NOW)


def test_exact_verified_subject_command_replays_without_actor_authority() -> None:
    repository, service, _job = _deletion_modules()
    table = _AccountTable(
        profile={
            "PK": f"USER#{STUDENT_ID}",
            "SK": "PROFILE",
            "user_id": STUDENT_ID,
            "role": "student",
            "account_status": "active",
        }
    )
    repository.ensure_active_account_fence(STUDENT_ID, table=table, now_iso=NOW)
    first = service.begin_or_replay_deletion(
        verified=_token(),
        user_id=STUDENT_ID,
        method="DELETE",
        path="/auth/me",
        body=b"",
        table=table,
        now_iso=NOW,
        command_id="delete-command-1",
    )
    replay = service.begin_or_replay_deletion(
        verified=_token(),
        user_id=STUDENT_ID,
        method="DELETE",
        path="/auth/me",
        body=b"",
        table=table,
        now_iso=NOW,
        command_id="ignored-on-replay",
    )
    assert replay == first
    assert set(asdict(replay)) == {
        "command_id",
        "status",
        "accepted_at",
        "completed_at",
    }
    assert replay.completed_at is None
    assert replay.is_terminal is False
    assert "actor" not in asdict(replay)
    assert table.command is not None
    # Sealed with the catalog's hash for its three steps (#641), not an inventory.
    assert table.command["flow"] == "catalog.v1"
    assert table.command["catalog_sha256"] == data_catalog.catalog_sha256()
    assert "inventory_sha256" not in table.command and "branch_ids" not in table.command

    for values in (
        {"verified": _token(subject="other")},
        {"verified": _token(issuer="https://other.example")},
        {"user_id": "other-user"},
        {"path": "/auth/other"},
        {"body": b"changed"},
    ):
        arguments = {
            "verified": _token(),
            "user_id": STUDENT_ID,
            "method": "DELETE",
            "path": "/auth/me",
            "body": b"",
            "table": table,
            "now_iso": NOW,
            "command_id": "delete-command-1",
            **values,
        }
        with pytest.raises(repository.AccountDeletionConflict):
            service.begin_or_replay_deletion(**arguments)


def test_every_primary_writer_uses_the_same_active_fence_and_exact_generation(monkeypatch) -> None:
    repository, _service, _job = _deletion_modules()
    expected_key = repository.account_fence_key(STUDENT_ID)

    profile_ops: list[dict[str, Any]] = []

    class _ProfileTable:
        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:  # noqa: N803
            if Key["SK"] == "ACCOUNT_FENCE":
                return {"Item": {**Key, "status": "active", "generation": 4}}
            return {"Item": {**Key, "user_id": STUDENT_ID, "version": 1}}

        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            profile_ops.extend(from_wire(TransactItems))

    db_table.install(_ProfileTable())
    user_repo.update_profile_fields_versioned(
        STUDENT_ID,
        update_expression="SET grade=:grade",
        expression_attribute_values={":grade": "9"},
    )
    # No question row is written any more; a help request is (#189), and a
    # write that puts rows in the student's conversation carries their fence.
    help_ops: list[dict[str, Any]] = []

    class _CapturingTable:
        def get_item(self, **_kwargs: Any) -> dict[str, Any]:
            # The student's fence, which the reply's rows are stamped from.
            return {"Item": {"status": "active", "generation": 4}}

        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            operations = from_wire(TransactItems)
            help_ops.extend(operations)

    monkeypatch.setattr(help_requests.notifications, "happened", lambda _happening: None)
    help_requests.reply(
        {
            "conversation_id": "c-1",
            "student_id": STUDENT_ID,
            "account_fence_generation": 4,
            "teacher_id": "teacher-1",
            "escalation_status": "in_progress",
            "version": 1,
        },
        teacher_id="teacher-1",
        author_name="Teacher One",
        content="Subtract 5 from both sides.",
        rich={"version": 1, "blocks": []},
        format="stoa_teacher_reply_v1",
        images=(),
        now=NOW,
        table=_CapturingTable(),
    )
    # The question attachment writer this checked went with #148; a
    # conversation write is the learning session's writer now (#226), sent
    # behind the fence by the table gateway (#297).
    attachment_checks: list[dict[str, Any]] = []

    class _ConversationTable:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            attachment_checks.extend(from_wire(TransactItems))

    learning_session._store.create_conversation_record(
        {"PK": "CONV#c-1", "SK": "CONV", "conversation_id": "c-1"},
        owner_id=STUDENT_ID,
        generation=4,
        table=_ConversationTable(),
    )
    def payload(operation: object) -> dict[str, Any]:
        if isinstance(operation, attachment_repo.TransactionOperation):
            if not isinstance(operation.item, Mapping):
                raise AssertionError("transaction operation has malformed payload")
            return dict(operation.item)
        if isinstance(operation, Mapping):
            return dict(operation)
        raise AssertionError("unexpected transaction operation")

    for operations in (profile_ops, help_ops, attachment_checks):
        checks: list[dict[str, Any]] = []
        for operation in operations:
            condition_check = payload(operation).get("ConditionCheck")
            if isinstance(condition_check, Mapping):
                checks.append(dict(condition_check))
        fence = next(check for check in checks if check.get("Key") == expected_key)
        assert "#status=:active" in fence["ConditionExpression"]
        assert "generation=:generation" in fence["ConditionExpression"]
        assert fence["ExpressionAttributeValues"][":generation"] == 4

    updates = [
        update
        for operation in [*profile_ops, *help_ops]
        if isinstance((update := payload(operation).get("Update")), Mapping)
    ]
    assert all("attribute_exists(PK)" in item["ConditionExpression"] for item in updates)


def test_upload_intent_is_fenced_before_any_provider_creation() -> None:
    source = inspect.getsource(
        importlib.import_module("stoa.services.uploads._lifecycle").create_upload_intent
    )
    persist = source.index("prepare_staging_issuance(item)")
    provider = source.index("create_multipart_upload")
    assert persist < provider
    assert "account_fence_generation" in source
    assert "require_active_account_fence" in source


class _PagedPrivateTable:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.pages: list[dict[str, Any]] = [
            {
                "Items": [
                    {
                        "PK": "UPLOAD#owner-only",
                        "SK": "META",
                        "entity_type": "upload_intent",
                        "owner_id": STUDENT_ID,
                        "status": "pending_upload",
                    }
                ],
                "LastEvaluatedKey": {"PK": "CURSOR#1", "SK": "META"},
            },
            {
                "Items": [
                    {
                        "PK": "QUESTION#late",
                        "SK": "META",
                        "entity_type": "question",
                        "student_id": STUDENT_ID,
                        "content": "private content",
                    }
                ]
            },
        ]

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        assert "IndexName" not in kwargs
        assert kwargs.get("ConsistentRead") is True
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]

    def query(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("IndexName") and kwargs.get("ConsistentRead"):
            raise AssertionError("DynamoDB forbids strong GSI reads")
        return {"Items": []}


def test_question_and_session_tombstones_keep_no_private_learning_field() -> None:
    """What a question's or a session's tombstone keeps is the catalog's (#642)."""
    private = {
        "content",
        "original_content",
        "corrected_text",
        "attachment_id",
        "attachment_source_identity",
        "image_s3_key",
        "ocr_text",
        "ocr_metadata",
        "ai_response",
        "teacher_response",
        "teacher_response_text",
        "teacher_response_rich",
        "teacher_response_format",
        "student_feedback",
        "knowledge_points",
        "topic_seeds",
        "subject",
        "student_id",
        "teacher_id",
        "notes",
        "resolution_note",
    }
    for name in ("question", "teacher_session", "teacher_escalation_intent", "user_profile"):
        assert private.isdisjoint(data_catalog.DELETIONS[name].owner.keeps), name


def test_scheduled_discovery_recovers_lost_route_trigger_and_reconstructs_service(
    monkeypatch,
) -> None:
    # The real repository against the shared table double. The command is
    # found through its row in the pending registry (#397, #611).
    from fakes.dynamodb import FakeTable

    _repository, service, job = _deletion_modules()
    table = FakeTable()
    db_table.install(table)
    table.seed(
        {
            "PK": f"USER#{STUDENT_ID}",
            "SK": "DELETE_COMMAND#delete-command-1",
            "entity_type": "account_deletion_command",
            "command_id": "delete-command-1",
            "user_id": STUDENT_ID,
            "generation": 1,
            "status": "pending",
            "version": 1,
            "flow": "catalog.v1",
        },
        {
            **account_deletion_repo.pending_registry_key(STUDENT_ID, "delete-command-1"),
            "entity_type": "account_deletion_pending",
            "deletion_user_id": STUDENT_ID,
            "deletion_command_id": "delete-command-1",
        },
    )
    calls: list[account_deletion_repo.DeletionCommandClaim] = []
    result = job.run_pending_deletions(
        service_factory=lambda: type(
            "Worker",
            (),
            {"continue_command": lambda self, command_id: calls.append(command_id)},
        )(),
        limit=10,
    )
    assert [claim.command_id for claim in calls] == ["delete-command-1"]
    assert calls[0].lease_owner
    assert result.discovered == 1 and result.claimed == 1
    assert result.retryable == 0


def test_delete_route_is_explicit_and_depends_on_verified_token_not_actor() -> None:
    auth = importlib.import_module("stoa.routers.auth")
    route = next(
        route
        for route in auth.router.routes
        if route.path == "/me" and "DELETE" in route.methods
    )
    call_names = {
        dependency.call.__name__
        for dependency in route.dependant.dependencies
        if getattr(dependency.call, "__name__", None)
    }
    assert "get_deletion_command" in call_names
    source = inspect.getsource(importlib.import_module("stoa.deps").get_deletion_command)
    assert "get_verified_token" in source
    assert "get_actor" not in source
    assert "get_current_user" not in source
    assert getattr(route.endpoint, "__route_auth_classification__", None)


def test_lost_trigger_coroutine_is_safe_to_run_after_response_commit() -> None:
    _repository, _service, job = _deletion_modules()
    function = getattr(job, "continue_deletion_command")
    assert asyncio.run(function("missing-command", service=None)) is None


def test_command_lookup_crosses_filtered_empty_pages_with_strong_base_reads() -> None:
    """The one command lookup still by scan: a replay after the binding is gone."""
    repository, _service, _job = _deletion_modules()
    calls: list[dict[str, Any]] = []

    class _Commands:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            if len(calls) == 1:
                return {
                    "Items": [],
                    "LastEvaluatedKey": {"PK": "OTHER#1", "SK": "META"},
                }
            return {
                "Items": [
                    {
                        "PK": f"USER#{STUDENT_ID}",
                        "SK": "DELETE_COMMAND#command-late",
                        "command_id": "command-late",
                    }
                ]
            }

    command = repository.find_deletion_command_for_identity(
        "issuer-hash", "subject-hash", table=_Commands()
    )
    assert command and command["command_id"] == "command-late"
    assert len(calls) == 2
    assert all(call.get("ConsistentRead") is True for call in calls)
    assert calls[1]["ExclusiveStartKey"] == {"PK": "OTHER#1", "SK": "META"}


def test_the_profile_tombstone_retains_only_the_catalogs_noncontent_keys(fake_table) -> None:
    repository, _service, _job = _deletion_modules()
    profile = {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "PROFILE",
        "user_id": STUDENT_ID,
        "role": "student",
        "email": "private@example.ch",
        "full_name": "Private Name",
        "subject": "private learning context",
        "created_at": NOW,
    }
    fake_table.seed(
        profile,
        {**repository.account_fence_key(STUDENT_ID), "status": "deletion_pending",
         "generation": 3},
    )

    repository.replace_with_deletion_tombstone(
        profile, user_id=STUDENT_ID, generation=3, now_iso=NOW
    )

    tombstone = fake_table.rows[(f"USER#{STUDENT_ID}", "PROFILE")]
    assert set(tombstone) <= data_catalog.DELETIONS["user_profile"].owner.keeps
    assert not {"email", "full_name", "subject", "user_id", "role"} & set(tombstone)
    assert repository.is_deletion_tombstone(tombstone)


def test_a_child_named_in_a_parents_profile_summary_is_taken_out_of_it() -> None:
    parent = {
        "PK": "USER#parent-1",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": "parent-1",
        "child_summaries": [{"student_id": STUDENT_ID, "name": "private child name"}],
    }

    assert data_catalog.role_of(parent, STUDENT_ID) == data_catalog.REFERENCE
    found = flow.action_for(parent, STUDENT_ID)
    assert found is not None and isinstance(found[1], data_catalog.Scrub)


def test_分支摘要对存储回来的数与写进去的数算出同一个值():
    """The digest is written from `int` and checked against what the table gives back.

    DynamoDB gives back `Decimal`, `json.dumps` refuses it outright, and the
    refusal was wrapped as "invalid deletion branch results". So on a real
    table the check could never pass: every continuation raised, and no
    deletion advanced past the single pass the request itself made. The stored
    digests were computed from ints, so a whole Decimal has to render as one.
    """
    from decimal import Decimal

    repository, _service, _job = _deletion_modules()

    written = repository.branch_results_digest(
        {"account_profile": {"epoch": 2, "processed": 0, "status": "complete"}}
    )
    read_back = repository.branch_results_digest(
        {
            "account_profile": {
                "epoch": Decimal("2"),
                "processed": Decimal("0"),
                "status": "complete",
            }
        }
    )

    assert written == read_back


def test_分支摘要仍然拒绝它不认识的东西():
    """The negative control: a serializer that accepts anything checks nothing."""
    repository, _service, _job = _deletion_modules()

    with pytest.raises(repository.AccountDeletionConflict):
        repository.branch_results_digest({"account_profile": {"when": object()}})


def test_练习分支不碰账号自己的生命周期行():
    """Carrying the student's id does not make a row practice data.

    The profile carries `user_id`, and an ownership attribute alone was enough
    for the old practice branch, so it reached the profile and wrote a practice
    tombstone over it. That tombstone does not give the address back -- only the
    profile's own writer does -- so after a real deletion the pair stayed claimed
    and could never be opened again. Since #641 the catalog says what a row is;
    the account's lifecycle rows are never one of the practice kinds.
    """
    owner = "student-1"
    lifecycle_rows = [
        {"PK": f"USER#{owner}", "SK": "PROFILE", "user_id": owner, "email": "a@b.ch"},
        {"PK": f"USER#{owner}", "SK": "ACCOUNT_FENCE", "user_id": owner},
        {"PK": f"USER#{owner}", "SK": "DELETE_COMMAND#c1", "user_id": owner},
        {"PK": f"USER#{owner}", "SK": "IDENTITY#issuer#subject", "user_id": owner},
    ]
    for row in lifecycle_rows:
        kind = data_catalog.data_type_of(row)
        assert kind is None or "practice" not in kind.name, row["SK"]
    assert data_catalog.data_type_of(lifecycle_rows[0]).name == "user_profile"

    # The negative control: the practice rows are still the student's.
    practice_rows = [
        {"PK": f"PROGRESS#{owner}", "SK": "TOPIC#x"},
        {"PK": f"ATTEMPTS#{owner}", "SK": "ATTEMPT#1"},
        {"PK": f"USAGE#{owner}", "SK": "DAY#2026-09-21"},
        {"PK": "PRACTICE_ATTEMPT#a1", "SK": "META", "student_id": owner},
    ]
    for row in practice_rows:
        assert data_catalog.owns(row, owner), row["PK"]
