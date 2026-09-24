"""The message command in two halves: commit it, then generate its answer (E19, #18).

Committing writes the student's message, the quota claim and the command, and
stores on the command what the request resolved for the answer - the language,
the subject, the grade, the student's weak topics. Generating reads only the
command, so it can later run somewhere without the request. Both halves still
run inside one request here, so the student sees what they saw before; what is
new is that the command ends in an explicit terminal state that
`GET /conversations/{id}/generation?idempotencyKey=` reports.

These run the real route and the real repository against the shared table
double. Only the model call and the entitlement lookup are replaced.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import FakeTable
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.services import ai_service, locale_service
from test_conversations import _actor

CONV = "conv-1"
STUDENT = "student-1"
QUESTION = "Wie kürze ich Brüche?"
ANSWER = {
    "steps": ["Zähler und Nenner teilen", "Durch den ggT"],
    "answer": "So kürzt man.",
    "hints": [],
}


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The prompt enrichment reads three tables; keep it out."""


class _Model:
    """Stands in for `ai_service.get_ai_answer`; records what each call was given."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[Any] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else ANSWER
        if isinstance(outcome, BaseException):
            raise outcome
        if not isinstance(outcome, dict):
            return outcome
        for index, step in enumerate(outcome.get("steps", [])):
            kwargs["on_step"](index, step)
        return dict(outcome)


class _Table(FakeTable):
    """The shared double, reached the way `attachment_repo.transact` calls it."""

    def transact_write_items(self, operations=None, *, TransactItems=None) -> None:
        super().transact_write_items(TransactItems if TransactItems is not None else operations)


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    table = _Table()
    table.seed_active_account(STUDENT)
    table.seed(
        {
            "PK": f"CONV#{CONV}",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": CONV,
            "student_id": STUDENT,
            "owner_id": STUDENT,
            "account_fence_generation": 1,
            "subject": "Mathematik",
            "grade": "Grade 6",
            "title": "Mathematik · Grade 6",
            "updated_at": "2026-09-24T08:00:00+00:00",
        }
    )
    for module in (conversations, attachment_repo):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)
    monkeypatch.setattr(
        conversations.account_deletion_repo, "get_table", lambda: table, raising=False
    )
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 50)
    monkeypatch.setattr(
        conversations.entitlement_service,
        "resolve_student_entitlement",
        lambda *_a, **_k: {"effectivePlan": "free_trial", "allowanceVersion": 1},
    )
    monkeypatch.setattr(conversations.user_repo, "get_user", lambda *_a, **_k: {})
    return table


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> _Model:
    model = _Model()
    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", model)
    return model


def _client() -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def bind_locale(request, call_next):
        locale_service.set_request_locale(
            locale_service.locale_from_accept_language(
                request.headers.get("accept-language")
            )
        )
        return await call_next(request)

    app.include_router(conversations.router, prefix="/conversations")
    app.dependency_overrides[get_actor] = lambda: _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def _send(client: TestClient, key: str, *, language: str = "fr", content: str = QUESTION):
    return client.post(
        f"/conversations/{CONV}/messages/stream",
        json={"content": content, "idempotencyKey": key},
        headers={"Accept-Language": language},
    )


def _events(response) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _generation(client: TestClient, key: str | None) -> dict[str, Any]:
    suffix = f"?idempotencyKey={key}" if key is not None else ""
    response = client.get(f"/conversations/{CONV}/generation{suffix}")
    assert response.status_code == 200, response.text
    return response.json()


def _command_row(table: FakeTable, key: str) -> dict[str, Any]:
    return table.rows[tuple(attachment_repo.message_command_key(CONV, key).values())]


def _messages(table: FakeTable, role: str) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == f"CONV#{CONV}" and sk.startswith("MSG#") and row.get("role") == role
    ]


def test_a_committed_and_generated_answer_still_streams_as_before(table, model) -> None:
    client = _client()

    response = _send(client, "key-1")

    assert response.status_code == 200, response.text
    events = _events(response)
    assert [name for name, _ in events[:2]] == ["student_message", "message_start"]
    assert events[-1][0] == "message_done"
    streamed = "".join(data["delta"] for name, data in events if name == "message_delta")
    assert "So kürzt man." in streamed
    assert len(_messages(table, "assistant")) == 1
    assert len(_messages(table, "student")) == 1


def test_the_generation_endpoint_reports_the_completed_command(table, model) -> None:
    client = _client()
    _send(client, "key-1")

    generation = _generation(client, "key-1")

    [assistant] = _messages(table, "assistant")
    assert generation["status"] == "completed"
    assert generation["attempt"] == 1
    assert generation["assistantMessageId"] == assistant["message_id"]
    assert generation["failureCategory"] is None
    assert generation["commandId"] == _command_row(table, "key-1")["command_id"]
    assert generation["steps"] == ANSWER["steps"]
    assert generation["updatedAt"]


def test_the_command_carries_what_the_request_resolved_for_the_answer(table, model) -> None:
    _send(_client(), "key-1", language="fr")

    context = _command_row(table, "key-1")["generation_context"]
    assert context["locale"] == "fr"
    assert context["subject"] == "math"
    assert context["grade"] == "Grade 6"
    assert "memory_context" in context
    assert model.calls[0]["language"] == "fr"


def _commit(key: str) -> Any:
    body = conversations.SendMessageRequest.model_validate(
        {"content": QUESTION, "idempotencyKey": key}
    )
    return conversations.commit_message_command(
        conv_id=CONV,
        student_id=STUDENT,
        subject="Mathematik",
        grade="Grade 6",
        body=body,
        command_context={
            "actor": _actor(),
            "fingerprint": conversations.message_request_fingerprint(body),
            "existing": None,
        },
    )


def test_generating_takes_the_language_from_the_command_not_the_request(
    table, model
) -> None:
    locale_service.set_request_locale("fr")
    committed = _commit("key-1")
    assert _command_row(table, "key-1")["status"] == "message_committed"

    # Whatever request is around when the answer is generated no longer counts.
    locale_service.set_request_locale("en")
    result = conversations.generate_for_command(committed)

    assert isinstance(result, conversations.SendMessageResponse)
    assert model.calls[-1]["language"] == "fr"
    assert _command_row(table, "key-1")["status"] == "completed"


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (ai_service.AIInvocationFailure("incomplete_output"), "incomplete_output"),
        (ai_service.AIInvocationFailure("malformed_response"), "malformed_response"),
        (ai_service.AIInvocationFailure("deadline_exceeded"), "deadline_exceeded"),
        (RuntimeError("provider went away"), "provider_error"),
    ],
)
def test_a_failed_answer_leaves_the_command_failed_with_its_category(
    table, model, failure, category
) -> None:
    client = _client()
    model.outcomes = [failure]

    response = _send(client, "key-1")

    assert response.status_code == 503
    assert _messages(table, "assistant") == []
    row = _command_row(table, "key-1")
    assert row["status"] == "failed"
    assert row["failure_category"] == category
    assert "leaseOwner" not in row
    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == category
    assert generation["retryable"] is True
    assert generation["assistantMessageId"] is None


def test_a_retry_with_the_same_key_resumes_the_same_command_after_an_unpaid_failure(
    table, model
) -> None:
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    assert _send(client, "key-1").status_code == 503

    retried = _send(client, "key-1")

    assert retried.status_code == 200, retried.text
    assert len(_messages(table, "student")) == 1
    assert len(_messages(table, "assistant")) == 1
    generation = _generation(client, "key-1")
    assert generation["status"] == "completed"
    assert generation["attempt"] == 2
    assert "failure_category" not in _command_row(table, "key-1")


def test_an_answer_refused_over_its_usage_evidence_is_not_generated_again(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model answered; only the accounting of it failed. Not a retry."""

    def refuse(*_a, **_k):
        raise conversations._allowance_recoverable_failure()

    monkeypatch.setattr(conversations, "_message_allowance_metadata_from_provider", refuse)
    model.outcomes = [ai_service.AIProviderResult.__new__(ai_service.AIProviderResult)]
    client = _client()

    assert _send(client, "key-1").status_code == 503

    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "allowance_finalization_recoverable"
    assert generation["retryable"] is False


def test_a_failure_the_provider_charged_for_is_not_generated_again(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paid answer that could not be used is a known result, not a retry."""
    monkeypatch.setattr(
        conversations, "_message_allowance_metadata_from_failure", lambda *_a, **_k: {}
    )
    monkeypatch.setattr(conversations, "_observe_message_provider_usage", lambda **_k: True)
    monkeypatch.setattr(conversations, "_restore_message_allowance", lambda **_k: True)
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("incomplete_output")]
    assert _send(client, "key-1").status_code == 503
    assert _generation(client, "key-1")["retryable"] is False

    retried = _send(client, "key-1")

    assert retried.status_code == 409, retried.text
    assert retried.json()["detail"]["code"] == "message_failed"
    assert len(model.calls) == 1
    assert _generation(client, "key-1")["status"] == "failed"


def test_steps_are_reported_only_for_the_command_that_wrote_them(table, model) -> None:
    client = _client()
    _send(client, "key-1")
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    _send(client, "key-2", content="Und wie erweitere ich?")

    assert _generation(client, "key-2")["steps"] == []
    assert _generation(client, "key-1")["steps"] == ANSWER["steps"]


def test_without_a_key_the_endpoint_answers_in_its_old_shape(table, model) -> None:
    client = _client()
    _send(client, "key-1")

    generation = _generation(client, None)

    assert generation["conversationId"] == CONV
    assert generation["steps"] == ANSWER["steps"]
    assert generation["updatedAt"]
    assert generation["status"] is None


def test_an_unknown_key_is_reported_as_an_unavailable_message(table, model) -> None:
    response = _client().get(f"/conversations/{CONV}/generation?idempotencyKey=nope")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "message_command_not_found"


def test_a_command_written_before_the_split_still_reads_and_resumes(
    table, model
) -> None:
    """In-flight commands of the previous version carry no generation context."""
    locale_service.set_request_locale("de")
    _commit("key-1")
    key = tuple(attachment_repo.message_command_key(CONV, "key-1").values())
    legacy = dict(table.rows[key])
    legacy.pop("generation_context")
    table.seed(legacy)
    client = _client()
    assert _generation(client, "key-1")["status"] == "message_committed"

    resumed = _send(client, "key-1", language="it")

    assert resumed.status_code == 200, resumed.text
    assert model.calls[-1]["language"] == "it"
    assert _generation(client, "key-1")["status"] == "completed"
    assert len(_messages(table, "student")) == 1


def test_an_old_running_command_reads_as_running(table, model) -> None:
    locale_service.set_request_locale("de")
    _commit("key-1")
    key = tuple(attachment_repo.message_command_key(CONV, "key-1").values())
    legacy = dict(table.rows[key])
    legacy.pop("generation_context")
    legacy.update(status="ai_running", attempt=1, leaseOwner="old", expiresAt=1)
    table.seed(legacy)

    generation = _generation(_client(), "key-1")

    assert generation["status"] == "ai_running"
    assert generation["attempt"] == 1


def test_the_same_key_after_success_replays_the_stored_answer(table, model) -> None:
    client = _client()
    first = _events(_send(client, "key-1"))

    second = _events(_send(client, "key-1"))

    assert first[1][1]["messageId"] == second[1][1]["messageId"]
    assert len(model.calls) == 1
    assert len(_messages(table, "assistant")) == 1
