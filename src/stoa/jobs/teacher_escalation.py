"""Generation-fenced consumer for opaque teacher escalation messages."""

from __future__ import annotations

import json
from typing import Any

from stoa.db.repositories import account_deletion_repo, question_repo
from stoa.services import teacher_dispatch_service


def consume_message(
    message: dict[str, Any],
    *,
    delete: Any | None = None,
) -> str:
    """Drop legacy/private or fenced payloads before any dispatch effect."""
    try:
        body = json.loads(str(message.get("Body") or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return "legacy_debt"
    if not isinstance(body, dict) or set(body) != {
        "operation_id",
        "question_id",
        "generation",
    }:
        return "legacy_debt"
    if any(key in body for key in ("student_id", "subject", "content")):
        return "legacy_debt"
    question = question_repo.get_question(str(body["question_id"]))
    if not question:
        if callable(delete):
            delete(message)
        return "dropped"
    owner_id = str(question.get("student_id") or "")
    try:
        account_deletion_repo.require_active_account_fence(
            owner_id, int(body["generation"])
        )
    except (ValueError, TypeError, account_deletion_repo.AccountDeletionConflict):
        if callable(delete):
            delete(message)
        return "fenced"
    teacher_dispatch_service.dispatch_question(str(body["question_id"]), question=question)
    if callable(delete):
        delete(message)
    return "processed"


def handler(event: dict[str, Any], _context: Any) -> dict[str, int]:
    counts = {"processed": 0, "fenced": 0, "dropped": 0, "legacy_debt": 0}
    for record in event.get("Records") or []:
        result = consume_message(record)
        counts[result] += 1
    return counts

