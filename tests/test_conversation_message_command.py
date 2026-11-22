"""Lower-boundary contract for the durable conversation message command.

These tests intentionally drive repository clients and transaction responses.  They
do not replace the command executor or completion repository method with a mock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.ask_question import (
    CONV,
    STUDENT,
    AtomicAllowanceTable,
    _command_key,
    _commit,
    _patch_allowance_table,
    _submit,
)
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import _client as _question_client
from fakes.ask_question import _message_command as _command
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.services import learning_session
from stoa.services.ask_question import _answering
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services.ask_question.models import SendMessageRequest, message_request_fingerprint


def _actor() -> Actor:
    return Actor(
        "student-1",
        "https://identity.test",
        "student-1-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        "student",
        (),
    )


class _BatchReadTable:
    name = "private-table-canary"

    def __init__(self, *, permanently_unprocessed: bool = False) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.permanently_unprocessed = permanently_unprocessed

    def batch_get_item(self, *, RequestItems):  # noqa: N803
        keys = RequestItems[self.name]["Keys"]
        self.calls.append(keys)
        key = keys[0]
        attachment_id = key["PK"].removeprefix("ATTACHMENT#")
        if self.permanently_unprocessed or len(self.calls) == 1:
            return {
                "Responses": {self.name: []},
                "UnprocessedKeys": {self.name: {"Keys": keys}},
            }
        return {
            "Responses": {
                self.name: [
                    {
                        "PK": key["PK"],
                        "SK": key["SK"],
                        "attachment_id": attachment_id,
                        "owner_id": "student-1",
                        "status": "active",
                    }
                ]
            },
            "UnprocessedKeys": {},
        }


def test_batch_get_retries_unprocessed_keys_before_projecting_resume_state() -> None:
    table = _BatchReadTable()

    result = attachment_repo.get_attachments(["attachment-1"], table=table)

    assert list(result) == ["attachment-1"]
    assert len(table.calls) == 2


def test_batch_get_exhaustion_is_a_redacted_dependency_failure() -> None:
    table = _BatchReadTable(permanently_unprocessed=True)

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict) as captured:
        attachment_repo.get_attachments(["attachment-1"], table=table)

    assert captured.value.category == "dependency_failure"
    assert len(table.calls) == 3


def _route_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def test_create_conversation_routes_initial_message_through_shared_executor(
    table, model, monkeypatch
) -> None:
    """The first message is committed under the account fence generation the
    conversation was created under."""
    table.seed_active_account(STUDENT, generation=7)
    allowance = AtomicAllowanceTable()
    allowance.items[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["generation"] = 7
    _patch_allowance_table(monkeypatch, allowance)

    response = _question_client().post(
        "/conversations",
        json={
            "subject": "math",
            "grade": "Sek1",
            "initialMessage": "through-shared-command",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert [message["role"] for message in body["messages"]] == ["student", "assistant"]
    assert body["messages"][0]["content"] == "through-shared-command"
    command = table.rows[
        tuple(
            _command_key(body["id"], f"initial-{body['id']}").values()
        )
    ]
    assert command["account_fence_generation"] == 7
    assert table.rows[(f"CONV#{body['id']}", "CONV")]["account_fence_generation"] == 7


@pytest.mark.parametrize("suffix", ["/messages", "/messages/stream"])
def test_regular_and_sse_get_item_transport_faults_share_safe_retry(
    monkeypatch, suffix: str
) -> None:
    class FaultingTable:
        def get_item(self, **_kwargs):
            raise TimeoutError("get-item-provider-coordinate-private-canary")

    monkeypatch.setattr(
        learning_session,
        "read",
        lambda *_: {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "subject": "math",
            "grade": "Sek1",
        },
    )
    db_table.install(FaultingTable())
    response = _route_client().post(
        f"/conversations/conv-1{suffix}",
        json={"content": "content-private-canary", "idempotencyKey": "fault-key"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert "private-canary" not in response.text


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        ({"status": "rejected", "error_code": "upload_not_found"}, "upload_not_found"),
        ({"status": "terminal_failed"}, "message_failed"),
        ({"status": "expired"}, "message_command_expired"),
        (None, "message_command_not_found"),
        ({"status": "unknown"}, "upload_service_unavailable"),
    ],
)
def test_polling_projects_nonlive_states_without_in_progress(
    table, model, monkeypatch, ending: dict[str, Any] | None, expected: str
) -> None:
    """Waiting for another delivery, the command ends in a state that is not live."""
    _commit("message-key")
    key = tuple(_command_key(CONV, "message-key").values())
    held = dict(table.rows[key])
    held.update(
        status="ai_running",
        attempt=1,
        leaseOwner="another-delivery",
        expiresAt=int(datetime.now(timezone.utc).timestamp()) + 300,
    )
    table.seed(held)

    def the_other_delivery_ends_it(_seconds: float) -> None:
        if ending is None:
            table.rows.pop(key, None)
        else:
            table.seed({**held, **ending})

    monkeypatch.setattr(_answering.time, "sleep", the_other_delivery_ends_it)

    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("message-key")

    assert captured.value.code.value == expected
    assert captured.value.code.value != "message_in_progress"


@pytest.mark.parametrize("suffix", ["/messages", "/messages/stream"])
def test_regular_and_sse_replay_exact_durable_rejection(table, model, suffix: str) -> None:
    request = SendMessageRequest.model_validate(
        {"content": "same", "idempotencyKey": "message-key"}
    )
    command_id = str(uuid5(NAMESPACE_URL, f"stoa.conversation.send.v1:{CONV}:message-key"))
    student_message_id = str(uuid5(UUID(command_id), "student-message"))
    table.seed(
        {
            **_command_key(CONV, "message-key"),
            **_command(
                status="rejected",
                error_code="storage_quota_exceeded",
                conversation_id=CONV,
                fingerprint=message_request_fingerprint(request),
                command_id=command_id,
                student_message_id=student_message_id,
                assistant_message_id=str(uuid5(UUID(command_id), "assistant-message")),
                history_anchor_message_id=student_message_id,
                history_message_ids=[],
                history_fingerprint="0" * 64,
                attachment_count=1,
            ),
        }
    )

    response = _question_client().post(
        f"/conversations/{CONV}{suffix}",
        json={"content": "same", "idempotencyKey": "message-key"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "storage_quota_exceeded"
    assert "private" not in response.text
    assert model.calls == []
