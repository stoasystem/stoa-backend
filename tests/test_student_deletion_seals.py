"""A student's account deletion runs to a valid seal: stoasystem/stoa-backend#78.

Every deletion branch was tested on its own mocked or synthetic data, and no
test ran them together, so four independent faults each kept a real deletion
from ever sealing: the conversation and practice branches re-found their own
tombstones, the identity branch refused to replay its own revoke debt, and
the attachments branch declared itself complete one clean pass early and was
then never run again. No deletion command exists in production yet.

This drives every branch the way `continue_command` does, over the shared
table double with production-shaped rows, stubbing only external clients
(Cognito, S3), until `validate_deletion_seal` accepts the command.
"""

from __future__ import annotations

import json

import pytest

import test_chat_help_request_lifecycle as lifecycle
from stoa.services import account_deletion_service as service

COMMAND_ID = "cmd-e2e"
NOW = "2026-09-28T23:59:00+00:00"
PRIVATE = ("Probier jetzt 15 : 5.", "private student message", "private question")


class _ExternalClient:
    """Any external client call answers an empty success."""

    class exceptions:
        class UserNotFoundException(Exception):
            pass

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: {}


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.table.__wrapped__(monkeypatch)
    lifecycle._dispatch_to(table, lifecycle.TEACHER)
    assert lifecycle._reply(lifecycle._client(), PRIVATE[0]).status_code in {200, 201}
    student = lifecycle.STUDENT
    table.seed(
        {
            "PK": f"CONV#{lifecycle.CONV}", "SK": "MSG#student-1", "entity_type": "conversation_message",
            "schema_version": "conversation-message.v1", "message_id": "student-1",
            "conversation_id": lifecycle.CONV, "student_id": student, "owner_id": student,
            "account_fence_generation": 1, "role": "student", "content": PRIVATE[1],
            "created_at": "2026-09-28T12:01:00+00:00",
        },
        {
            "PK": "QUESTION#q-lane", "SK": "META", "entity_type": "question", "schema_version": "question.v1",
            "question_id": "q-lane", "student_id": student, "owner_id": student, "status": "resolved",
            "version": 3, "account_fence_generation": 1, "subject": "math", "content": PRIVATE[2],
            "created_at": "2026-09-27T10:00:00+00:00",
        },
        # Practice progress and the usage ledger: every student who asked a
        # question or practised has rows like these.
        {"PK": f"PROGRESS#{student}", "SK": "LESSON#l1", "student_id": student, "completed": True},
        {"PK": f"USAGE_LEDGER#{student}", "SK": "EVENT#e1", "student_id": student, "action": "question"},
    )
    table.rows[(f"USER#{student}", "ACCOUNT_FENCE")].update(
        {"status": "deletion_pending", "command_id": COMMAND_ID, "entity_type": "account_fence",
         "user_id": student, "version": 2}
    )
    return table


def test_a_student_with_a_conversation_and_practice_can_be_deleted(table, monkeypatch):
    monkeypatch.setattr(service.boto3, "client", lambda *_args, **_kwargs: _ExternalClient())
    seal = service.load_private_store_seal()
    results: dict = {}
    command = {"user_id": lifecycle.STUDENT, "generation": 1, "command_id": COMMAND_ID, "branch_results": results}
    history: dict = {branch: [] for branch in service.ACCOUNT_DELETION_BRANCH_IDS}

    for _run in range(8):
        for branch_id in service.ACCOUNT_DELETION_BRANCH_IDS:
            previous = results.get(branch_id) or {}
            if previous.get("status") == "complete" and previous.get("quiescent") is True:
                continue
            try:
                result = service.BRANCH_HANDLERS[branch_id](command=command, previous=previous)
            except Exception as exc:  # as continue_command records it
                history[branch_id].append(f"raised {type(exc).__name__}")
                result = service.BranchResult("retryable", debt_counts={"dependency": 1})
            contract = seal["branch_contracts"][branch_id]
            results[branch_id] = result.persisted(
                NOW, generation=1, handler_version=contract["handler_version"],
                subfamilies=contract["subfamilies"],
            )
            history[branch_id].append(f"{result.status}/{result.epoch}")

    full_command = {
        "status": "running", "command_id": COMMAND_ID, "generation": 1,
        "inventory_sha256": seal["inventory_sha256"],
        "branch_ids": list(service.ACCOUNT_DELETION_BRANCH_IDS),
        "branch_contracts": seal["branch_contracts"], "branch_results": results,
    }
    fence = dict(table.rows[(f"USER#{lifecycle.STUDENT}", "ACCOUNT_FENCE")], generation=1)

    assert service.validate_deletion_seal(command=full_command, fence=fence, seal=seal), history
    left = [key for key, row in table.rows.items() if any(text in json.dumps(row, default=str) for text in PRIVATE)]
    assert left == [], left
