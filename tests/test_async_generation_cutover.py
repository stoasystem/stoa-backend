"""The message route hands the answer to the worker (E21, #18).

With `CONVERSATION_GENERATION_FUNCTION_NAME` set, sending a message commits it
and invokes the generation worker asynchronously; the request returns 202 as
soon as the message is stored, and the answer is read from `/generation`. An
answer that takes longer than API Gateway's 29 seconds is no longer cut off.
Unset, the route generates in the request exactly as before (E19): the switch
is the rollback.

These run the real route, worker and repository against the shared table
double; the model call and the Lambda invoke are replaced.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import ai_service
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    QUESTION,
    _client,
    _command_row,
    _events,
    _generation,
    _messages,
    _send,
)
from test_message_command_generation import model as model  # noqa: F401 - the fixture
from test_message_command_generation import table as table  # noqa: F401 - the fixture

WORKER_ALIAS = "arn:aws:lambda:eu-central-2:111122223333:function:stoa-conversation-generation:production"


class _Invokes:
    """Stands in for the asynchronous Lambda invoke; records every event."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.failure: BaseException | None = None

    def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure


@pytest.fixture
def invokes(monkeypatch: pytest.MonkeyPatch) -> _Invokes:
    invokes = _Invokes()
    monkeypatch.setattr(conversations, "_invoke_generation_worker", invokes)
    return invokes


@pytest.fixture
def switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        conversations.settings, "conversation_generation_function_name", WORKER_ALIAS
    )


def _deliver(event: dict[str, Any]) -> dict[str, Any]:
    return conversation_generation.handler(event, None)


def test_the_request_returns_once_the_message_is_stored(
    table, model, invokes, switched_on
) -> None:
    response = _send(_client(), "key-1")

    assert response.status_code == 202, response.text
    body = response.json()
    row = _command_row(table, "key-1")
    assert body["commandId"] == row["command_id"]
    assert body["idempotencyKey"] == "key-1"
    assert body["status"] == "message_committed"
    assert body["studentMessage"]["content"] == QUESTION
    assert row["status"] == "message_committed"
    assert model.calls == []
    assert _messages(table, "assistant") == []
    assert invokes.events == [{"conversation_id": CONV, "idempotency_key": "key-1"}]


def test_the_worker_then_writes_the_answer_the_poll_reports(
    table, model, invokes, switched_on
) -> None:
    client = _client()
    _send(client, "key-1", language="fr")

    assert _deliver(invokes.events[0]) == {"outcome": "completed"}

    generation = _generation(client, "key-1")
    assert generation["status"] == "completed"
    assert len(_messages(table, "assistant")) == 1
    # The language the request asked in, carried on the command.
    assert model.calls[0]["language"] == "fr"


def test_a_lost_invoke_leaves_the_command_for_the_sweep(
    table, model, invokes, switched_on
) -> None:
    invokes.failure = RuntimeError("Lambda service unavailable")

    response = _send(_client(), "key-1")

    assert response.status_code == 202
    row = dict(_command_row(table, "key-1"))
    assert row["status"] == "message_committed"
    assert len(_messages(table, "student")) == 1
    # Committed long enough ago for the sweep to take it from the lost invoke.
    row["message_committed_at"] = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    table.seed(row)
    summary = _deliver({"source": "stoa.scheduler", "job": "conversation_generation_sweep"})
    assert summary["completed"] == 1
    assert _command_row(table, "key-1")["status"] == "completed"


def test_switched_off_the_answer_comes_back_on_the_request_as_before(
    table, model, invokes
) -> None:
    response = _send(_client(), "key-1")

    assert response.status_code == 200
    assert _events(response)[-1][0] == "message_done"
    assert len(model.calls) == 1
    assert invokes.events == []


def test_the_same_key_after_the_answer_replays_it_on_the_request(
    table, model, invokes, switched_on
) -> None:
    client = _client()
    _send(client, "key-1")
    _deliver(invokes.events[0])

    again = _send(client, "key-1")

    assert again.status_code == 200
    assert _events(again)[-1][0] == "message_done"
    assert len(invokes.events) == 1
    assert len(model.calls) == 1


def test_a_retry_of_a_failed_answer_reads_as_waiting_until_the_worker_answers(
    table, model, invokes, switched_on
) -> None:
    """The chat reads the command while the retry is on its way.

    If the command still read `failed` until the worker took it up, the chat
    would stop at that old failure, and a lost invoke would never be swept.
    """
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    _send(client, "key-1")
    assert _deliver(invokes.events[0]) == {"outcome": "failed"}
    assert _generation(client, "key-1")["retryable"] is True

    retried = _send(client, "key-1")

    assert retried.status_code == 202
    assert _generation(client, "key-1")["status"] == "message_committed"
    row = _command_row(table, "key-1")
    assert "failure_category" not in row
    retry_event = invokes.events[1]
    assert retry_event == {"conversation_id": CONV, "idempotency_key": "key-1"}
    assert _deliver(retry_event) == {"outcome": "completed"}
    assert _generation(client, "key-1")["attempt"] == 2
    # A late copy of either event finds the command settled.
    assert _deliver(retry_event) == {"outcome": "settled"}
    assert _deliver(invokes.events[0]) == {"outcome": "settled"}
    assert len(model.calls) == 2


def test_a_late_copy_of_a_retry_does_not_spend_another_attempt(
    table, model, invokes, switched_on
) -> None:
    client = _client()
    model.outcomes = [
        ai_service.AIInvocationFailure("deadline_exceeded"),
        ai_service.AIInvocationFailure("deadline_exceeded"),
    ]
    _send(client, "key-1")
    _deliver(invokes.events[0])
    _send(client, "key-1")
    retry_event = invokes.events[1]
    assert _deliver(retry_event) == {"outcome": "failed"}

    # The same event delivered again: only the student reopens a failure.
    assert _deliver(retry_event) == {"outcome": "settled"}
    assert len(model.calls) == 2
    assert _generation(client, "key-1")["attempt"] == 2


def test_a_retry_whose_invoke_is_lost_is_swept(table, model, invokes, switched_on) -> None:
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    _send(client, "key-1")
    _deliver(invokes.events[0])
    invokes.failure = RuntimeError("Lambda service unavailable")

    assert _send(client, "key-1").status_code == 202

    row = dict(_command_row(table, "key-1"))
    assert row["status"] == "message_committed"
    # Committed long enough ago for the sweep to take it from the lost invoke.
    row["message_committed_at"] = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    table.seed(row)
    summary = _deliver({"source": "stoa.scheduler", "job": "conversation_generation_sweep"})
    assert summary["completed"] == 1


def test_a_failure_that_may_not_be_retried_is_not_reopened(
    table, model, invokes, switched_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        conversations, "_message_allowance_metadata_from_failure", lambda *_a, **_k: {}
    )
    monkeypatch.setattr(conversations, "_observe_message_provider_usage", lambda **_k: True)
    monkeypatch.setattr(conversations, "_restore_message_allowance", lambda **_k: True)
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("incomplete_output")]
    _send(client, "key-1")
    _deliver(invokes.events[0])

    again = _send(client, "key-1")

    assert again.status_code == 409
    assert _command_row(table, "key-1")["status"] == "failed"
    assert len(invokes.events) == 1


def test_an_answer_longer_than_the_gateway_waits_no_longer_holds_the_request(
    table, model, invokes, switched_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audit's last latency contract: a 30-second answer and a 29-second gateway."""
    clock = {"now": 0.0}

    def thirty_second_answer(**kwargs: Any) -> Any:
        clock["now"] += 30.0
        return model(**kwargs)

    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", thirty_second_answer)

    response = _send(_client(), "key-1")

    assert response.status_code == 202
    assert clock["now"] < 29
    assert _deliver(invokes.events[0]) == {"outcome": "completed"}
    assert clock["now"] == 30.0


def test_the_first_message_of_a_new_conversation_is_handed_over_too(
    table, model, invokes, switched_on
) -> None:
    response = _client().post(
        "/conversations",
        json={"subject": "Mathematik", "grade": "Grade 6", "initialMessage": QUESTION},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert [message["role"] for message in body["messages"]] == ["student"]
    assert invokes.events == [
        {"conversation_id": body["id"], "idempotency_key": f"initial-{body['id']}"}
    ]
    assert model.calls == []


def test_the_invoke_is_asynchronous_and_names_the_worker_alias(
    monkeypatch: pytest.MonkeyPatch, switched_on
) -> None:
    calls: list[dict[str, Any]] = []

    class _Lambda:
        def invoke(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"StatusCode": 202}

    clients: list[dict[str, Any]] = []

    def client(service: str, **kwargs: Any) -> _Lambda:
        clients.append(kwargs)
        return _Lambda()

    monkeypatch.setattr(conversations.boto3, "client", client)

    conversations._invoke_generation_worker({"conversation_id": CONV, "idempotency_key": "k"})

    [call] = calls
    assert call["FunctionName"] == WORKER_ALIAS
    # Bounded well inside the request's 29 seconds; a slow invoke leaves the
    # command to the sweep rather than the student to a gateway timeout.
    config = clients[0]["config"]
    assert config.connect_timeout <= 2
    assert config.read_timeout <= 3
    assert config.retries["max_attempts"] <= 1
    assert call["InvocationType"] == "Event"
    assert json.loads(call["Payload"]) == {"conversation_id": CONV, "idempotency_key": "k"}
