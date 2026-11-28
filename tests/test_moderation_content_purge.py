"""Plan 473-30 contracts for moderation-derived private content deletion."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fakes.dynamodb import as_stored as _as_stored, from_wire

from stoa.db import table as db_table
from stoa.db.repositories import moderation_repo
from stoa.models.moderation import (
    ModerationCaseNoteRequest,
    ModerationReportRequest,
    ModerationSeverity,
    ModerationSurface,
    ModerationReason,
)
from stoa.services import moderation_service


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
    return _as_stored(item)


def _help_request() -> dict[str, Any]:
    """The help request a report is made from: what the report route resolves (#189)."""
    return _as_stored(
        {
            "PK": f"CONV#{QUESTION_ID}",
            "SK": "HELP",
            "entity_type": "help_request",
            "conversation_id": QUESTION_ID,
            "escalation_request_id": QUESTION_ID,
            "student_id": STUDENT_ID,
            "account_fence_generation": 7,
            "subject": "private-math",
            "escalation_status": "pending",
            "escalation_message": "private question canary",
        }
    )


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
    return _as_stored(item)


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
    return _as_stored(item)


def test_moderation_source_registry_closes_rows_fields_and_writers() -> None:
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


def test_moderation_create_binds_authoritative_owner_generation_and_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, Any] = {}
    handoff: dict[str, Any] = {}
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
        moderation_service.notifications,
        "happened",
        lambda happening: handoff.update(vars(happening)),
    )

    created = moderation_service.create_case(
        QUESTION_ID,
        ModerationReportRequest(
            surface=ModerationSurface.QUESTION,
            reason=ModerationReason.UNSAFE_CONTENT,
            severity=ModerationSeverity.HIGH,
            note="private report note canary",
        ),
        {"sub": STUDENT_ID, "role": "student"},
        request=_help_request(),
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
                        "generation": Decimal(7),
                    }
                }
            if Key["SK"] == "SUMMARY":
                return {"Item": _summary()}
            return {}

        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            operations = from_wire(TransactItems)
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
        moderation_service.notifications,
        "happened",
        lambda happening: handoff.update(vars(happening)),
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


def test_moderation_tombstones_are_not_returned_as_active_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tombstone = {
        "PK": f"MODERATION#{CASE_ID}",
        "SK": "SUMMARY",
        "entity_type": "moderation_case",
        "case_id": CASE_ID,
        "privacy_deleted": True,
        "privacy_generation": Decimal(7),
    }
    active = _summary(case_id="active-case", PK="MODERATION#active-case")

    class _Table:
        def get_item(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Item": dict(tombstone)}

        def scan(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Items": [dict(tombstone), dict(active)]}

        def query(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "Items": [
                    {**_event("deleted"), "privacy_deleted": True},
                    _event("active"),
                ]
            }

    table = _Table()
    db_table.install(table)
    assert moderation_repo.get_case(CASE_ID, table=table) is None
    assert [item["case_id"] for item in moderation_repo.list_cases()] == [
        "active-case"
    ]
    assert [item["event_id"] for item in moderation_repo.list_case_events(CASE_ID)] == [
        "active"
    ]


