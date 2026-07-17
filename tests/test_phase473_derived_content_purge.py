"""Plan 473-30 contracts for moderation-derived private content deletion."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import moderation_repo
from stoa.models.moderation import (
    ModerationCaseNoteRequest,
    ModerationReportRequest,
    ModerationSeverity,
    ModerationSurface,
    ModerationReason,
)
from stoa.services import account_deletion_service, moderation_service


STUDENT_ID = "student-moderation-delete"
CASE_ID = "moderation-private-case"
QUESTION_ID = "moderation-private-question"
NOW = "2026-07-17T23:00:25+00:00"


def _require_contract(name: str) -> Any:
    value = getattr(moderation_repo, name, None)
    if value is None:
        pytest.fail(f"moderation repository contract {name} is not implemented")
    return value


def _question(**overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"QUESTION#{QUESTION_ID}",
        "SK": "META",
        "entity_type": "question",
        "question_id": QUESTION_ID,
        "student_id": STUDENT_ID,
        "account_fence_generation": 7,
        "subject": "private-math",
        "content": "private question canary",
        "status": "ai_answered",
        "ai_response": {"answer": "private answer canary"},
    }
    item.update(overrides)
    return item


def _summary(**overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"MODERATION#{CASE_ID}",
        "SK": "SUMMARY",
        "entity_type": "moderation_case",
        "case_id": CASE_ID,
        "question_id": QUESTION_ID,
        "student_id": STUDENT_ID,
        "privacy_generation": 7,
        "status": "open",
        "reason": "unsafe_content",
        "severity": "high",
        "surface": "ai_answer",
        "reporter_id": STUDENT_ID,
        "reporter_role": "student",
        "assigned_admin_id": "admin-private",
        "question_context": {"content_preview": "private question canary"},
        "report_note": "private report note canary",
        "resolution_note": "private resolution canary",
        "history": [{"note": "private inline history canary"}],
        "created_at": NOW,
        "updated_at": NOW,
    }
    item.update(overrides)
    return item


def _event(event_id: str = "event-private", **overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"MODERATION#{CASE_ID}",
        "SK": f"EVENT#{event_id}",
        "entity_type": "moderation_event",
        "event_id": event_id,
        "case_id": CASE_ID,
        "question_id": QUESTION_ID,
        "student_id": STUDENT_ID,
        "privacy_generation": 7,
        "event_type": "updated",
        "actor_id": "admin-private",
        "actor_role": "admin",
        "reason": "private reason canary",
        "status": "actioned",
        "severity": "high",
        "changes": {"before": "private-before", "after": "private-after"},
        "note": "private event note canary",
        "created_at": NOW,
    }
    item.update(overrides)
    return item


def test_moderation_source_registry_closes_rows_fields_writers_and_branch() -> None:
    row_registry = _require_contract("MODERATION_ROW_REGISTRY")
    private_fields = _require_contract("MODERATION_PRIVATE_FIELDS")
    writers = _require_contract("MODERATION_WRITER_REGISTRY")

    assert row_registry == {
        "summary": ("MODERATION#", "SUMMARY"),
        "event": ("MODERATION#", "EVENT#"),
    }
    assert {
        "question_context",
        "report_note",
        "resolution_note",
        "history",
        "note",
        "changes",
        "reason",
        "actor_id",
        "actor_role",
        "reporter_id",
        "reporter_role",
        "assigned_admin_id",
    } <= private_fields
    assert writers == {"put_case", "update_case", "put_event"}
    assert "moderation_support" in account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS


def test_moderation_create_binds_authoritative_owner_generation_and_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, Any] = {}
    handoff: dict[str, Any] = {}
    monkeypatch.setattr(
        moderation_service.question_repo,
        "get_question",
        lambda _question_id: _question(),
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "put_case",
        lambda item, *args, **kwargs: stored.update(item) or dict(item),
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "put_event",
        lambda *_args, **_kwargs: pytest.fail("initial case/event must be atomic"),
    )
    monkeypatch.setattr(
        moderation_service.notification_service,
        "emit_moderation_created",
        lambda **kwargs: handoff.update(kwargs),
    )

    created = moderation_service.create_case(
        QUESTION_ID,
        ModerationReportRequest(
            surface=ModerationSurface.AI_ANSWER,
            reason=ModerationReason.UNSAFE_CONTENT,
            severity=ModerationSeverity.HIGH,
            note="private report note canary",
        ),
        {"sub": STUDENT_ID, "role": "student"},
    )

    assert stored["student_id"] == STUDENT_ID
    assert stored["privacy_generation"] == 7
    assert created["privacy_generation"] == 7
    assert handoff["owner_id"] == STUDENT_ID
    assert handoff["privacy_generation"] == 7


def test_moderation_repository_case_and_event_writes_share_exact_fence() -> None:
    transactions: list[list[dict[str, Any]]] = []

    class _Table:
        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
            if Key["SK"] == "ACCOUNT_FENCE":
                return {
                    "Item": {
                        **Key,
                        "status": "active",
                        "generation": 7,
                    }
                }
            if Key["SK"] == "SUMMARY":
                return {"Item": _summary()}
            return {}

        def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
            transactions.append(operations)

    table = _Table()
    _require_contract("put_case")(_summary(), _event("initial"), table=table)
    _require_contract("put_event")(
        CASE_ID,
        {
            "event_id": "later",
            "event_type": "note_added",
            "note": "private later note",
            "created_at": NOW,
        },
        table=table,
    )
    updated = _require_contract("update_case")(
        CASE_ID,
        {"resolution_note": "private resolution"},
        table=table,
    )

    assert len(transactions) == 3
    for operations in transactions:
        fence = operations[0]["ConditionCheck"]
        assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
        assert fence["ExpressionAttributeValues"][":generation"] == 7
    later_item = transactions[1][1]["Put"]["Item"]
    assert later_item["student_id"] == STUDENT_ID
    assert later_item["privacy_generation"] == 7
    assert transactions[2][1]["Update"]["ConditionExpression"].startswith(
        "attribute_exists(PK) AND attribute_exists(SK)"
    )
    assert updated is not None


def test_moderation_service_updates_inherit_case_owner_not_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, Any]] = []
    handoff: dict[str, Any] = {}
    summary = _summary()
    monkeypatch.setattr(moderation_service.moderation_repo, "get_case", lambda *_: dict(summary))
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "update_case",
        lambda _case_id, attrs, **_kwargs: {**summary, **attrs},
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "put_event",
        lambda _case_id, event, **_kwargs: events.append(dict(event)),
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "list_case_events",
        lambda *_args, **_kwargs: list(events),
    )
    monkeypatch.setattr(
        moderation_service.notification_service,
        "emit_moderation_update",
        lambda **kwargs: handoff.update(kwargs),
    )

    moderation_service.add_note(
        CASE_ID,
        ModerationCaseNoteRequest(note="private operator note"),
        {"sub": "admin-attacker-shaped-id", "role": "admin"},
    )

    assert events[0]["student_id"] == STUDENT_ID
    assert events[0]["privacy_generation"] == 7
    assert handoff["owner_id"] == STUDENT_ID
    assert handoff["privacy_generation"] == 7


def test_moderation_scrub_removes_all_content_and_private_linkage() -> None:
    scrub = _require_contract("scrub_moderation_row")
    captured: list[dict[str, Any]] = []

    class _Table:
        def scrub_moderation_row(
            self,
            _original: dict[str, Any],
            tombstone: dict[str, Any],
            _user_id: str,
            _generation: int,
        ) -> None:
            captured.append(dict(tombstone))

    for row in (_summary(), _event(), _event("legacy", student_id=None, privacy_generation=None)):
        scrub(row, user_id=STUDENT_ID, generation=7, now_iso=NOW, table=_Table())

    allowlist = _require_contract("MODERATION_TOMBSTONE_ALLOWLIST")
    private_fields = _require_contract("MODERATION_PRIVATE_FIELDS")
    assert len(captured) == 3
    assert all(set(row) <= allowlist for row in captured)
    assert all(private_fields.isdisjoint(row) for row in captured)
    serialized = repr(captured)
    for canary in (
        "private question canary",
        "private report note canary",
        "private event note canary",
        "private-before",
        "admin-private",
    ):
        assert canary not in serialized


def test_moderation_discovery_resolves_legacy_event_owner_and_pages() -> None:
    scan = _require_contract("scan_moderation_private_rows")
    calls: list[dict[str, Any]] = []
    pages = [
        {
            "Items": [_summary()],
            "LastEvaluatedKey": {"PK": f"MODERATION#{CASE_ID}", "SK": "SUMMARY"},
        },
        {
            "Items": [_event("legacy", student_id=None, privacy_generation=None)],
        },
    ]

    class _Table:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return pages.pop(0)

        def get_item(self, *, Key: dict[str, str], **kwargs: Any) -> dict[str, Any]:
            assert kwargs.get("ConsistentRead") is True
            if Key["PK"].startswith("MODERATION#"):
                return {"Item": _summary()}
            if Key["PK"].startswith("QUESTION#"):
                return {"Item": _question()}
            return {}

    first = scan(STUDENT_ID, table=_Table(), maximum_pages=1)
    assert first.cursor == {"PK": f"MODERATION#{CASE_ID}", "SK": "SUMMARY"}
    second = scan(STUDENT_ID, table=_Table(), cursor=first.cursor, maximum_pages=1)
    assert [row["SK"] for row in second.items] == ["EVENT#legacy"]
    assert second.items[0]["student_id"] == STUDENT_ID
    assert second.items[0]["privacy_generation"] == 7
    assert all(call.get("ConsistentRead") is True and "IndexName" not in call for call in calls)


def test_moderation_discovery_rejects_malformed_or_repeating_cursor() -> None:
    scan = _require_contract("scan_moderation_private_rows")

    class _Malformed:
        def scan(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Items": [], "LastEvaluatedKey": {"PK": "missing-sk"}}

    with pytest.raises(Exception):
        scan(STUDENT_ID, table=_Malformed(), maximum_pages=1)

    class _Repeating:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            return {"Items": [], "LastEvaluatedKey": kwargs["ExclusiveStartKey"]}

    with pytest.raises(Exception):
        scan(
            STUDENT_ID,
            table=_Repeating(),
            cursor={"PK": "MODERATION#repeat", "SK": "SUMMARY"},
            maximum_pages=1,
        )


def test_moderation_unavailable_authoritative_question_remains_debt() -> None:
    scan = _require_contract("scan_moderation_private_rows")

    class _Unavailable:
        def scan(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Items": [_summary()]}

        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
            if Key["PK"].startswith("MODERATION#"):
                return {"Item": _summary()}
            return {}

    page = scan(STUDENT_ID, table=_Unavailable(), maximum_pages=1)
    assert page.items == ()
    assert page.unresolved == 1


def test_moderation_branch_persists_restart_progress_and_later_zero_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch = getattr(account_deletion_service, "_moderation_support_branch", None)
    if branch is None:
        pytest.fail("moderation deletion branch is not implemented")
    page_type = _require_contract("ModerationPrivatePage")
    pages = [
        page_type((_summary(),), {"PK": f"MODERATION#{CASE_ID}", "SK": "SUMMARY"}, 0),
        page_type((_event("late"),), None, 0),
        page_type((), None, 0),
        page_type((), None, 0),
    ]
    scrubbed: list[str] = []
    monkeypatch.setattr(
        moderation_repo,
        "scan_moderation_private_rows",
        lambda *_args, **_kwargs: pages.pop(0),
    )
    monkeypatch.setattr(
        moderation_repo,
        "scrub_moderation_row",
        lambda row, **_kwargs: scrubbed.append(str(row["SK"])),
    )
    command = {"user_id": STUDENT_ID, "generation": 7}
    previous: dict[str, Any] = {}
    results = []
    for _ in range(4):
        result = branch(command=command, previous=previous)
        results.append(result)
        previous = result.persisted(NOW)

    assert results[0].cursor is not None
    assert [result.epoch for result in results] == [0, 0, 1, 2]
    assert results[-1].status == "complete"
    assert results[-1].quiescent is True
    assert scrubbed == ["SUMMARY", "EVENT#late"]
    assert asdict(results[-1])["debt_counts"] == {}
