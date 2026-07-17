"""Plan 473-29 contracts for deny-first, resumable account deletion."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import attachment_repo, question_repo, user_repo
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import AccountStatus, resolve_actor
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import notify_service


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

    async def get_current_grants(self, _user_id: str) -> list[dict[str, Any]]:
        self.reads.append("grants")
        return []


class _AccountTable:
    """High-level fake that preserves conditional command semantics."""

    def __init__(self, *, profile: dict[str, Any] | None = None) -> None:
        self.profile = profile
        self.fence: dict[str, Any] | None = None
        self.command: dict[str, Any] | None = None
        self.branch_results: dict[str, Any] = {}
        self.pending: list[dict[str, Any]] = []

    def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
        if Key["SK"] == "PROFILE":
            return {"Item": dict(self.profile)} if self.profile else {}
        if Key["SK"] == "ACCOUNT_FENCE":
            return {"Item": dict(self.fence)} if self.fence else {}
        if Key["SK"].startswith("DELETE_COMMAND#"):
            return {"Item": dict(self.command)} if self.command else {}
        return {}

    def backfill_account_fence(self, item: dict[str, Any]) -> dict[str, Any]:
        if self.fence is None:
            self.fence = dict(item)
        return dict(self.fence)

    def begin_account_deletion(
        self, fence: dict[str, Any], command: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.fence is None:
            raise RuntimeError("missing fence")
        if self.fence["status"] == "active":
            self.fence = {**fence, "status": "deletion_pending", "version": 2}
            self.command = dict(command)
        elif not self.command or self.command["fingerprint"] != command["fingerprint"]:
            raise RuntimeError("command conflict")
        return dict(self.fence), dict(self.command)

    def scan_pending_deletion_commands(
        self, *, limit: int, exclusive_start_key: dict[str, str] | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
        del exclusive_start_key
        return [dict(item) for item in self.pending[:limit]], None

    def claim_deletion_command(self, command_id: str, generation: int, **_kwargs: Any):
        match = next(
            (
                item
                for item in self.pending
                if item["command_id"] == command_id and item["generation"] == generation
            ),
            None,
        )
        return dict(match) if match else None


def test_account_status_and_registry_are_closed_before_later_branches() -> None:
    repository, service, _job = _deletion_modules()

    assert AccountStatus.DELETION_PENDING.value == "deletion_pending"
    assert repository.account_fence_key(STUDENT_ID) == {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "ACCOUNT_FENCE",
    }
    assert service.PRIMARY_BRANCH_IDS == {
        "account_profile",
        "identity_cross_account",
        "capability_scope",
        "question_ocr_session",
        "attachments",
    }
    assert len(service.ACCOUNT_DELETION_BRANCH_IDS) == 17
    assert service.can_finalize_account_deletion(service.PRIMARY_BRANCH_IDS) is False


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
    assert set(asdict(replay)) == {"command_id", "status", "accepted_at"}
    assert "actor" not in asdict(replay)

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


def test_every_primary_writer_uses_the_same_active_fence_and_exact_generation() -> None:
    repository, _service, _job = _deletion_modules()
    expected_key = repository.account_fence_key(STUDENT_ID)

    profile_ops = user_repo.build_profile_update_transaction(
        STUDENT_ID,
        update_expression="SET grade=:grade",
        expression_attribute_values={":grade": "9"},
        expected_generation=4,
    )
    question_ops = question_repo.build_question_update_transaction(
        {"question_id": "q-1", "student_id": STUDENT_ID},
        status="resolved",
        expected_generation=4,
    )
    attachment_checks = attachment_repo._retention_fence_checks(
        STUDENT_ID, "question", "q-1", account_fence_generation=4
    )
    for operations in (profile_ops, question_ops, attachment_checks):
        checks = [
            operation.item.get("ConditionCheck", {})
            if hasattr(operation, "item")
            else operation.get("ConditionCheck", {})
            for operation in operations
        ]
        fence = next(check for check in checks if check.get("Key") == expected_key)
        assert "#status=:active" in fence["ConditionExpression"]
        assert "generation=:generation" in fence["ConditionExpression"]
        assert fence["ExpressionAttributeValues"][":generation"] == 4

    updates = [
        operation.get("Update", {})
        for operation in profile_ops + question_ops
        if operation.get("Update")
    ]
    assert all("attribute_exists(PK)" in item["ConditionExpression"] for item in updates)


def test_upload_intent_is_fenced_before_any_provider_creation() -> None:
    source = inspect.getsource(
        importlib.import_module("stoa.services.attachment_service").create_upload_intent
    )
    persist = source.index("prepare(item)")
    provider = source.index("create_multipart_upload")
    assert persist < provider
    assert "account_fence_generation" in source
    assert "require_active_account_fence" in source


class _PagedPrivateTable:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.pages = [
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


def test_base_table_discovery_finds_owner_only_intents_and_late_pages() -> None:
    repository, _service, _job = _deletion_modules()
    table = _PagedPrivateTable()
    page = repository.scan_owned_private_rows(STUDENT_ID, table=table, maximum_pages=4)
    assert {item["entity_type"] for item in page.items} == {"upload_intent", "question"}
    assert len(table.calls) == 2
    with pytest.raises(AssertionError):
        table.query(IndexName="GSI-StudentId", ConsistentRead=True)


def test_question_and_session_scrub_allowlists_exclude_all_private_learning_fields() -> None:
    repository, service, _job = _deletion_modules()
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
    assert private <= repository.PRIVATE_QUESTION_SESSION_FIELDS
    assert private.isdisjoint(repository.QUESTION_TOMBSTONE_ALLOWLIST)
    assert private.isdisjoint(repository.SESSION_TOMBSTONE_ALLOWLIST)
    assert service.PRIMARY_BRANCH_IDS <= set(service.BRANCH_HANDLERS)


def test_teacher_queue_payload_is_opaque_and_generation_fenced(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []

    class _Sqs:
        def send_message(self, **kwargs: Any) -> None:
            sent.append(kwargs)

    monkeypatch.setattr(notify_service.boto3, "client", lambda *_args, **_kwargs: _Sqs())
    monkeypatch.setattr(
        notify_service,
        "require_active_account_fence",
        lambda _owner, generation: generation == 7,
    )
    notify_service.enqueue_teacher_request(
        question_id="question-1",
        operation_id="teacher-intent-1",
        generation=7,
    )
    payload = json.loads(sent[0]["MessageBody"])
    assert payload == {
        "operation_id": "teacher-intent-1",
        "question_id": "question-1",
        "generation": 7,
    }
    rendered = repr(sent[0]).lower()
    assert STUDENT_ID.lower() not in rendered
    assert "subject" not in rendered


def test_scheduled_discovery_recovers_lost_route_trigger_and_reconstructs_service() -> None:
    _repository, service, job = _deletion_modules()
    table = _AccountTable()
    table.pending.append(
        {
            "PK": f"USER#{STUDENT_ID}",
            "SK": "DELETE_COMMAND#delete-command-1",
            "entity_type": "account_deletion_command",
            "command_id": "delete-command-1",
            "user_id": STUDENT_ID,
            "generation": 1,
            "status": "pending",
        }
    )
    calls: list[str] = []
    result = job.run_pending_deletions(
        repository=table,
        service_factory=lambda: type(
            "Worker",
            (),
            {"continue_command": lambda self, command_id: calls.append(command_id)},
        )(),
        limit=10,
    )
    assert calls == ["delete-command-1"]
    assert result.discovered == 1 and result.claimed == 1
    assert result.retryable == 0
    assert service.can_finalize_account_deletion(service.PRIMARY_BRANCH_IDS) is False


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


@pytest.mark.parametrize(
    "cursor",
    [
        {"PK": "only-pk"},
        {"PK": "", "SK": "META"},
        {"PK": "CURSOR#1", "SK": 7},
    ],
)
def test_private_scan_rejects_malformed_progress(cursor: dict[str, Any]) -> None:
    repository, _service, _job = _deletion_modules()

    class _Malformed:
        def scan(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Items": [], "LastEvaluatedKey": cursor}

    with pytest.raises(repository.AccountDeletionConflict):
        repository.scan_owned_private_rows(STUDENT_ID, table=_Malformed())


def test_private_scan_accepts_last_item_cursor_but_rejects_repeated_page_cursor() -> None:
    repository, _service, _job = _deletion_modules()

    class _Repeating:
        calls = 0

        def scan(self, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            cursor = {"PK": "QUESTION#1", "SK": "META"}
            return {
                "Items": [
                    {
                        **cursor,
                        "entity_type": "question",
                        "student_id": STUDENT_ID,
                    }
                ],
                "LastEvaluatedKey": cursor,
            }

    with pytest.raises(repository.AccountDeletionConflict, match="repeating"):
        repository.scan_owned_private_rows(
            STUDENT_ID, table=_Repeating(), maximum_pages=3
        )


def test_command_lookup_crosses_filtered_empty_pages_with_strong_base_reads() -> None:
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

    command = repository.get_command_by_id("command-late", table=_Commands())
    assert command and command["command_id"] == "command-late"
    assert len(calls) == 2
    assert all(call.get("ConsistentRead") is True for call in calls)
    assert calls[1]["ExclusiveStartKey"] == {"PK": "OTHER#1", "SK": "META"}


def test_primary_branch_persists_cursor_and_requires_two_clean_epochs(monkeypatch) -> None:
    repository, service, _job = _deletion_modules()
    pages = [
        repository.OwnedPrivatePage(
            (
                {
                    "PK": "QUESTION#1",
                    "SK": "META",
                    "entity_type": "question",
                    "student_id": STUDENT_ID,
                },
            ),
            {"PK": "QUESTION#1", "SK": "META"},
        ),
        repository.OwnedPrivatePage((), None),
        repository.OwnedPrivatePage((), None),
        repository.OwnedPrivatePage((), None),
    ]
    monkeypatch.setattr(repository, "scan_owned_private_rows", lambda *_args, **_kwargs: pages.pop(0))
    mutated: list[str] = []
    command = {"user_id": STUDENT_ID, "generation": 1}
    previous: dict[str, Any] = {}
    results = []
    for _ in range(4):
        result = service._run_base_branch(
            command=command,
            previous=previous,
            predicate=lambda item: item.get("entity_type") == "question",
            mutate=lambda item: mutated.append(str(item["PK"])),
        )
        results.append(result)
        previous = result.persisted(NOW)
    assert results[0].cursor == {"PK": "QUESTION#1", "SK": "META"}
    assert [result.epoch for result in results] == [0, 0, 1, 2]
    assert results[-1].status == "complete" and results[-1].quiescent is True
    assert mutated == ["QUESTION#1"]


def test_tombstone_replacement_retains_only_declared_noncontent_keys() -> None:
    repository, _service, _job = _deletion_modules()
    captured: list[dict[str, Any]] = []

    class _Tombstones:
        def replace_with_deletion_tombstone(
            self,
            _item: dict[str, Any],
            tombstone: dict[str, Any],
            _user_id: str,
            _generation: int,
        ) -> None:
            captured.append(tombstone)

    repository.replace_with_deletion_tombstone(
        {
            "PK": "QUESTION#private",
            "SK": "META",
            "entity_type": "question",
            "question_id": "private",
            "student_id": STUDENT_ID,
            "content": "secret",
            "subject": "private learning context",
            "ocr_metadata": {"raw": "private"},
            "teacher_response_rich": {"text": "private"},
            "created_at": NOW,
        },
        user_id=STUDENT_ID,
        generation=3,
        now_iso=NOW,
        table=_Tombstones(),
    )
    assert set(captured[0]) <= repository.QUESTION_TOMBSTONE_ALLOWLIST
    assert repository.PRIVATE_QUESTION_SESSION_FIELDS.isdisjoint(captured[0])


def test_base_scan_discovers_embedded_parent_profile_child_summary() -> None:
    repository, _service, _job = _deletion_modules()

    class _ParentProfile:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["ConsistentRead"] is True
            return {
                "Items": [
                    {
                        "PK": "USER#parent-1",
                        "SK": "PROFILE",
                        "entity_type": "user_profile",
                        "user_id": "parent-1",
                        "child_summaries": [
                            {"student_id": STUDENT_ID, "name": "private child name"}
                        ],
                    }
                ]
            }

    page = repository.scan_owned_private_rows(STUDENT_ID, table=_ParentProfile())
    assert [(item["PK"], item["SK"]) for item in page.items] == [
        ("USER#parent-1", "PROFILE")
    ]
