"""The question's shared test setup (#204, decision 12).

Every test of the question path that runs the real route, entry points and
repository builds on this: the conversation table (the shared `FakeTable`,
reached everywhere the question reads it), the model (`FakeBedrock` behind the
real allowance client), and who answers a committed question (`invokes`
records what would reach the generation worker; without it the answer is
generated in the request). Only the model call and the entitlement read are
replaced.

Test modules import the fixtures by name, one per line, the way this repository
imports fixtures (`from fakes.ask_question import table as table  # noqa: F401`),
and never define a fixture of the same name.

The helpers further down were each imported by one test file from another;
they are collected here so no question-path test imports another test file.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.admission import seed_plan
from fakes.bedrock import FakeBedrock
from fakes.dynamodb import FakeTable
from fakes.learning_session import patch_session_table, seed_conversation
from stoa.db.repositories import allowance_repo, attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import (
    allowance_service,
    ask_question,
    attachment_service,
    curriculum_service,
    knowledge_mastery_service,
    locale_service,
    star_map_candidates,
    student_evidence,
)
from stoa.services.ask_question import _admission, _answering, _store, dispatch
from stoa.services.ask_question.models import SendMessageRequest, message_request_fingerprint
from stoa.services.document_extraction_service import (
    DocumentExtractionFailure,
    extract_attachment_text,
)
from stoa.services.document_parser_worker import ParserResult
from stoa.services.uploads import _store as upload_store
from test_token_allowances import AtomicAllowanceTable  # re-exported for the question tests

CONV = "conv-1"
STUDENT = "student-1"
QUESTION = "Wie kürze ich Brüche?"
ANSWER = {
    "steps": ["Zähler und Nenner teilen", "Durch den ggT"],
    "answer": "So kürzt man.",
    "hints": [],
}
WORKER_ALIAS = "arn:aws:lambda:eu-central-2:111122223333:function:stoa-conversation-generation:production"


# ── The student and the conversation ────────────────────────────────────────


def _actor(role=CanonicalRole.STUDENT, user_id=STUDENT, grants=()) -> Actor:
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        tuple(grants),
    )


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The prompt enrichment reads three tables; keep it out."""


class _Table(FakeTable):
    """The shared double."""


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """The student's conversation, on the table every read of the question reaches."""
    table = _Table()
    table.seed_active_account(STUDENT)
    seed_conversation(table, conversation_id=CONV, student_id=STUDENT)
    patch_session_table(monkeypatch, table)
    # These still reach the table themselves for rows that are not the session's.
    for module in (conversations, _answering, attachment_repo):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)
    monkeypatch.setattr(
        conversations.account_deletion_repo, "get_table", lambda: table, raising=False
    )
    seed_plan(monkeypatch)
    # The week a question is admitted against: on this table, until a test
    # points the allowance at its own.
    monkeypatch.setattr(allowance_repo, "get_table", lambda table=table: table)
    monkeypatch.setattr(conversations.user_repo, "get_user", lambda *_a, **_k: {})
    # Answered in the request unless a test hands the answer to the worker.
    monkeypatch.setattr(dispatch.settings, "conversation_generation_function_name", "")
    return table


def _command_key(conversation_id: str, key: str) -> dict[str, str]:
    """Where the question's command row for `key` is kept."""
    return _store.message_command_key(conversation_id, key)


def _command_row(table: FakeTable, key: str, conversation_id: str = CONV) -> dict[str, Any]:
    return table.rows[tuple(_command_key(conversation_id, key).values())]


def _messages(table: FakeTable, role: str) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == f"CONV#{CONV}" and sk.startswith("MSG#") and row.get("role") == role
    ]


# ── The model ────────────────────────────────────────────────────────────────

# When the allowance figures below were taken.
NOW = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)

# Taken before any test replaces them, so a test may point them at a second table.
_ALLOWANCE = (
    allowance_service.reserve_token_allowance,
    allowance_service.record_provider_usage,
    allowance_service.finalize_token_allowance,
    allowance_service.restore_user_allowance,
    allowance_service.week_exhausted,
)


def _patch_allowance_table(
    monkeypatch: pytest.MonkeyPatch,
    table: AtomicAllowanceTable,
) -> None:
    """Have the token allowance the answer is admitted by read and write `table`."""
    reserve, observe, finalize, restore, exhausted = _ALLOWANCE
    monkeypatch.setattr(
        allowance_service,
        "reserve_token_allowance",
        lambda **kwargs: reserve(**kwargs, table=table),
    )
    monkeypatch.setattr(
        allowance_service,
        "record_provider_usage",
        lambda **kwargs: observe(**kwargs, table=table),
    )
    monkeypatch.setattr(
        allowance_service,
        "finalize_token_allowance",
        lambda **kwargs: finalize(**kwargs, table=table),
    )
    monkeypatch.setattr(
        allowance_service,
        "restore_user_allowance",
        lambda **kwargs: restore(**kwargs, table=table),
    )
    monkeypatch.setattr(
        allowance_service,
        "week_exhausted",
        lambda **kwargs: exhausted(**kwargs, table=table),
    )



def charge_failures_as_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Have every failed answer count as a reply the provider charged for.

    Its evidence is observed and the reservation restored without touching the
    ledger, as `_admission`'s meter does with a real one.
    """
    paid = _admission.UsageEvidence(
        effect_id="0" * 64,
        evidence_id="paid-failure",
        request_id_digest="1" * 64,
        model_id_digest="2" * 64,
        input_tokens=1,
        output_tokens=1,
    )
    monkeypatch.setattr(
        _admission.UsageEvidence,
        "from_failure",
        classmethod(lambda _cls, *_a, **_k: paid),
    )
    monkeypatch.setattr(_admission.Meter, "observe", lambda _self, _evidence: None)
    monkeypatch.setattr(_admission.Meter, "restore", lambda _self, _evidence: None)

@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeBedrock:
    """The Bedrock runtime the answer is asked of, behind the real allowance client."""
    model = FakeBedrock(answer=ANSWER)
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    monkeypatch.setattr(_answering.ai_service.boto3, "client", lambda *_a, **_k: model)
    return model


def default_language(model: FakeBedrock, index: int = -1) -> str:
    """The language the model was told to fall back on, as its code."""
    match = re.search(r"DEFAULT LANGUAGE: \w+ \((\w+)\)", model.system(index))
    assert match is not None
    return match.group(1)


# ── The routes ───────────────────────────────────────────────────────────────


def _client(actor: Actor | None = None) -> TestClient:
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
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
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


# ── Who answers a committed question ─────────────────────────────────────────


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
    """The generation worker answers: what would reach it is recorded, not sent."""
    invokes = _Invokes()
    monkeypatch.setattr(dispatch, "override", dispatch.LambdaWorker(invoke=invokes))
    return invokes


def _request(key: str, *, content: str = QUESTION, **fields: Any) -> SendMessageRequest:
    return SendMessageRequest.model_validate(
        {"content": content, "idempotencyKey": key, **fields}
    )


def _submit(
    key: str,
    *,
    content: str = QUESTION,
    conversation: dict[str, Any] | None = None,
    **fields: Any,
) -> ask_question.Answered | ask_question.Accepted:
    """`ask_question.submit` as the message route calls it for the student."""
    body = _request(key, content=content, **fields)
    return ask_question.submit(
        _actor(),
        conversation or {"subject": "Mathematik", "grade": "Grade 6"},
        body,
        message_request_fingerprint(body),
        conversation_id=CONV,
        student_id=STUDENT,
    )


def _commit(key: str, *, content: str = QUESTION, **fields: Any) -> ask_question.Accepted:
    """Store the student's message and its command, and leave the answer to the worker."""
    previous = dispatch.override
    dispatch.override = dispatch.LambdaWorker(invoke=lambda _event: None)
    try:
        accepted = _submit(key, content=content, **fields)
    finally:
        dispatch.override = previous
    assert isinstance(accepted, ask_question.Accepted)
    return accepted


# ── The worker ───────────────────────────────────────────────────────────────


class _Killed(BaseException):
    """The Lambda stopped here: nothing after this line ran."""


def _deliver(key: str) -> dict[str, Any]:
    return conversation_generation.handler(
        {"conversation_id": CONV, "idempotency_key": key}, None
    )


def _expire_lease(table, key: str) -> None:
    row = dict(_command_row(table, key))
    assert row["status"] == "ai_running"
    row["expiresAt"] = 1
    table.seed(row)


def _running(table, key: str, *, attempt: int, claimed_minutes_ago: float) -> None:
    """An attempt that died: claimed then, its five-minute lease run out since."""
    now = datetime.now(UTC)
    row = dict(_command_row(table, key))
    claimed = now - timedelta(minutes=claimed_minutes_ago)
    row.update(
        status="ai_running",
        attempt=attempt,
        leaseOwner="died",
        claimedAt=int(claimed.timestamp()),
        expiresAt=int((claimed + timedelta(minutes=5)).timestamp()),
    )
    table.seed(row)


def _called(then: Any = None) -> Any:
    """The model was asked (the allowance client recorded the call) and then did `then`."""
    return ANSWER if then is None else then


def _minutes_ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _last_attempt_kept_its_answer(
    table, model, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """The answer was stored, then the Lambda died; that attempt was the last."""
    _commit(key)
    model.outcomes = [_called()]
    renew = _store.renew_message_ai_lease

    def die(**_: Any) -> bool:
        raise _Killed()

    monkeypatch.setattr(_store, "renew_message_ai_lease", die)
    with pytest.raises(_Killed):
        _deliver(key)
    monkeypatch.setattr(_store, "renew_message_ai_lease", renew)
    row = dict(_command_row(table, key))
    assert row["provider_result_json"]
    row.update(attempt=3, provider_invoked_attempt=3, provider_result_attempt=3)
    table.seed(row)


# ── The question's own rows, reached by the tests outside its store's (#220) ──
#
# Only `tests/test_ask_question_store.py` imports `ask_question._store`. Every
# other test that injects a fault into it, wraps one of its functions or builds
# one of its results goes through these.

CommandResult = _store.MessageCommandResult
Disposition = _store.MessageCommandDisposition


def store_call(name: str) -> Callable[..., Any]:
    """The store's function `name` as it is now, for a test that wraps it."""
    return getattr(_store, name)


def patch_store(monkeypatch: pytest.MonkeyPatch, name: str, replacement: Any) -> None:
    """The store's function `name` is `replacement` for the rest of the test."""
    store_call(name)  # a name the store does not have is a typo, not a patch
    monkeypatch.setattr(_store, name, replacement)


def fail_store(
    monkeypatch: pytest.MonkeyPatch, name: str, failure: BaseException, *, from_call: int = 1
) -> None:
    """The store's function `name` runs as it does until its `from_call`-th call,
    which raises `failure`, as does every call after it."""
    real = store_call(name)
    calls = {"count": 0}

    def failing(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] >= from_call:
            raise failure
        return real(*args, **kwargs)

    patch_store(monkeypatch, name, failing)


# ── Rows the store's tests share with the tests they were moved from (#220) ──


def _message_command(**overrides: Any) -> dict[str, Any]:
    """A message command as the table stores it, claimed and not yet committed."""
    value: dict[str, Any] = {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": "command-1",
        "conversation_id": "conv-1",
        "owner_id": "student-1",
        "idempotency_key": "message-key",
        "fingerprint": "f" * 64,
        "status": "claimed",
        "student_message_id": "student-message-1",
        "assistant_message_id": "assistant-message-1",
        "deterministic_attachment_ids": ["attachment-1"],
        "requested_attachments": [
            {"kind": "upload", "id": "upload-1", "attachment_id": "attachment-1"}
        ],
        "quota_period": "2026-07-17",
        "usage_action": "chat_message",
        "usage_resource_id": "student-message-1",
        "usage_idempotency_key": "chat_message:student-message-1",
        "usage_event_id": (
            "student-1:chat_message:2026-07-17:chat_message:student-message-1"
        ),
        "history_anchor_message_id": "student-message-1",
        "history_anchor_created_at": "2026-07-17T23:59:59+00:00",
        "attempt": 0,
        "created_at": "2026-07-17T23:59:59+00:00",
        "expires_at": 1784505599,
    }
    value.update(overrides)
    return value


# The account and conversation of the conversation deletion tests.
DELETED_STUDENT = "student-conversation-delete"
PRIVATE_CONVERSATION = "conversation-private"
DELETION_NOW = "2026-07-18T01:00:00+00:00"


def _private_message(sk: str = "MSG#student", **overrides: Any) -> dict[str, Any]:
    """A private row of `PRIVATE_CONVERSATION`, by default its student's message."""
    item = {
        "PK": f"CONV#{PRIVATE_CONVERSATION}",
        "SK": sk,
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": sk.split("#", 1)[-1],
        "conversation_id": PRIVATE_CONVERSATION,
        "student_id": DELETED_STUDENT,
        "owner_id": DELETED_STUDENT,
        "account_fence_generation": 7,
        "role": "student",
        "content": "private message canary",
        "attachment_ids": ["attachment-private"],
        "subject": "private subject",
        "grade": "private grade",
        "created_at": DELETION_NOW,
    }
    item.update(overrides)
    return item


# ── A provider answering with fixed text, for the allowance tests ───────────


class _ResponseBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.closed = False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


def _command() -> dict[str, object]:
    """One message command in the shape the table hands it back."""
    command: dict[str, object] = {
        "command_id": "message-command-1",
        "conversation_id": "conversation-1",
        "student_id": "student-1",
        "owner_id": "student-1",
        "assistant_message_id": "assistant-message-1",
        "account_fence_generation": Decimal(1),
        "created_at": NOW.isoformat(),
    }
    command.update(
        _admission.allowance_identity(
            command,
            {
                "effectivePlan": "free_trial",
                "source": "free_trial_activation",
                "grantId": "free-trial-grant-1",
                "allowanceVersion": Decimal(7),
            },
        )
    )
    command["allowance_version"] = Decimal(str(command["allowance_version"]))
    return command


_COMPLETE = json.dumps(
    {
        "steps": ["Schritt eins", "Schritt zwei"],
        "answer": "Die vollständige Antwort",
        "hints": ["Ein Hinweis"],
        "similar_exercises": [],
        "knowledge_points": ["Brüche"],
        "suggest_teacher": False,
    },
    ensure_ascii=False,
)


class _Provider:
    """CountTokens plus both InvokeModel shapes, replying with fixed text."""

    def __init__(self, *, text: str, stop_reason: str) -> None:
        self.text = text
        self.stop_reason = stop_reason
        self.invoke_calls: list[dict[str, object]] = []

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        return {
            "inputTokens": 90,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "count-request-1"},
        }

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": self.stop_reason,
                    "usage": {"input_tokens": 70, "output_tokens": 2048},
                    "content": [{"text": self.text}],
                }
            ),
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "invoke-request-1"},
        }

    def invoke_model_with_response_stream(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        events: list[dict[str, Any]] = [
            {
                "type": "message_start",
                "message": {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "usage": {"input_tokens": 70},
                },
            },
            *(
                {"type": "content_block_delta", "delta": {"text": self.text[i : i + 16]}}
                for i in range(0, len(self.text), 16)
            ),
            {
                "type": "message_delta",
                "delta": {"stop_reason": self.stop_reason},
                "usage": {"output_tokens": 2048},
            },
        ]
        return {
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "invoke-request-1"},
        }


def _run_message_command(
    monkeypatch: pytest.MonkeyPatch, *, text: str, stop_reason: str, key: str = "truncation-key"
) -> tuple[AtomicAllowanceTable, Any]:
    """Submit one question answered in the request by a provider replying `text`.

    Needs the `table` fixture. The answer goes through the real AI service and
    the real allowance client; the allowance is kept on the table returned.
    Returns that table and what `submit` returned or raised.
    """
    allowance = AtomicAllowanceTable()
    provider = _Provider(text=text, stop_reason=stop_reason)
    _patch_allowance_table(monkeypatch, allowance)
    monkeypatch.setattr(_answering.ai_service.boto3, "client", lambda *_a, **_k: provider)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)
    try:
        outcome: Any = _submit(key)
    except Exception as exc:
        outcome = exc
    return allowance, outcome


# ── What the model is shown and writes (#132, #142) ─────────────────────────


def _student_turn(body: dict[str, Any]) -> str:
    return str([turn for turn in body["messages"] if turn["role"] == "user"][-1]["content"])


def _done(response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    [done] = [data for name, data in _events(response) if name == "message_done"]
    return done


def _read_back(client) -> list[dict[str, Any]]:
    response = client.get(f"/conversations/{CONV}")
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def _assistant(messages: list[dict[str, Any]]) -> dict[str, Any]:
    [assistant] = [message for message in messages if message["role"] == "assistant"]
    return assistant



# One answer per language, for the sections tests (#132).
ANSWERS: dict[str, tuple[dict[str, Any], str]] = {
    "de": (
        {
            "steps": ["Zähler und Nenner durch den ggT teilen", "Das Ergebnis prüfen"],
            "answer": "So kürzt man einen Bruch.",
            "hints": ["Was ist der ggT von 6 und 8?", "Beide Zahlen sind gerade."],
            "similar_exercises": ["Kürze 9/12."],
            "knowledge_points": ["Brüche kürzen", "Grösster gemeinsamer Teiler"],
            "suggest_teacher": True,
        },
        "Hinweis",
    ),
    "en": (
        {
            "steps": ["Divide top and bottom by the GCD", "Check the result"],
            "answer": "That is how you simplify a fraction.",
            "hints": ["What is the GCD of 6 and 8?", "Both numbers are even."],
            "similar_exercises": ["Simplify 9/12."],
            "knowledge_points": ["Simplifying fractions", "Greatest common divisor"],
            "suggest_teacher": True,
        },
        "Hint",
    ),
    "fr": (
        {
            "steps": ["Diviser le numérateur et le dénominateur par le PGCD", "Vérifier"],
            "answer": "Voilà comment on simplifie une fraction.",
            "hints": ["Quel est le PGCD de 6 et 8 ?", "Les deux nombres sont pairs."],
            "similar_exercises": ["Simplifie 9/12."],
            "knowledge_points": ["Simplifier des fractions", "Plus grand commun diviseur"],
            "suggest_teacher": True,
        },
        "Indice",
    ),
    "it": (
        {
            "steps": ["Dividere numeratore e denominatore per il MCD", "Controllare"],
            "answer": "Così si semplifica una frazione.",
            "hints": ["Qual è il MCD di 6 e 8?", "Entrambi i numeri sono pari."],
            "similar_exercises": ["Semplifica 9/12."],
            "knowledge_points": ["Semplificare le frazioni", "Massimo comun divisore"],
            "suggest_teacher": True,
        },
        "Indizio",
    ),
}



class _CapturingBedrockClient:
    """The Bedrock runtime as boto3 hands it out: counts, answers, streams.

    Records the body it was sent and answers with `answer` as the model's
    JSON. Nothing else of the provider is stood in for.
    """

    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.request_body: dict | None = None
        self.answer = answer or ANSWERS["de"][0]

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        return {
            "inputTokens": 90,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "count-1"},
        }

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        self.request_body = json.loads(body)
        payload = {
            "id": "msg_test_1",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": json.dumps(self.answer)}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return {
            "ResponseMetadata": {"RequestId": "req-test-1"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }

    def invoke_model_with_response_stream(self, *, modelId: str, body: str):  # noqa: N803
        self.request_body = json.loads(body)
        text = json.dumps(self.answer, ensure_ascii=False)
        events = [
            {"type": "message_start", "message": {
                "id": "msg_test_1", "model": modelId, "usage": {"input_tokens": 70},
            }},
            # Cut in two, so the steps are found in a partly received answer.
            {"type": "content_block_delta", "delta": {"text": text[: len(text) // 2]}},
            {"type": "content_block_delta", "delta": {"text": text[len(text) // 2 :]}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 25}},
        ]
        return {
            "ResponseMetadata": {"RequestId": "req-test-1"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }



# ── The student's star map, as the model is shown it (#142) ──────────────────

_READ_THE_MAP = star_map_candidates.for_student

LOCALES = ("de", "en", "fr", "it")

# The catalog as `curriculum_service.list_catalog` builds it, one title per
# language. `ohne-lektion` has no active lesson, so the map does not draw it.
TITLES: dict[str, dict[str, str]] = {
    "brueche-kuerzen": {
        "de": "Brüche kürzen",
        "en": "Simplifying fractions",
        "fr": "Simplifier des fractions",
        "it": "Semplificare le frazioni",
    },
    "teiler-vielfache": {
        "de": "Teiler und Vielfache",
        "en": "Divisors and multiples",
        "fr": "Diviseurs et multiples",
        "it": "Divisori e multipli",
    },
    "kraefte": {
        "de": "Kräfte und Bewegung",
        "en": "Forces and motion",
        "fr": "Forces et mouvement",
        "it": "Forze e moto",
    },
    "ohne-lektion": {
        "de": "Noch ohne Lektion",
        "en": "No lesson yet",
        "fr": "Pas encore de leçon",
        "it": "Ancora senza lezione",
    },
}
STATES = {
    "brueche-kuerzen": knowledge_mastery_service.LearningState.LIT,
    "teiler-vielfache": knowledge_mastery_service.LearningState.IN_PROGRESS,
    "kraefte": knowledge_mastery_service.LearningState.READY,
    "ohne-lektion": knowledge_mastery_service.LearningState.READY,
}
SUBJECT_OF = {
    "brueche-kuerzen": ("math", "brueche"),
    "teiler-vielfache": ("math", "brueche"),
    "kraefte": ("physics", "mechanik"),
    "ohne-lektion": ("math", "brueche"),
}

TOPICS: dict[str, dict[str, str]] = {
    "brueche": {"de": "Brüche", "en": "Fractions", "fr": "Fractions", "it": "Frazioni"},
    "mechanik": {"de": "Mechanik", "en": "Mechanics", "fr": "Mécanique", "it": "Meccanica"},
}

# What the model writes on its own, in the language of the answer.
FREE: dict[str, str] = {
    "de": "Brüche im Alltag",
    "en": "Fractions in everyday life",
    "fr": "Les fractions au quotidien",
    "it": "Le frazioni nella vita quotidiana",
}


def _catalog(*, locale: str = "de", **_kwargs: Any) -> dict[str, Any]:
    return {
        "subjects": [{"id": "math", "order": 1}, {"id": "physics", "order": 2}],
        "topics": [
            {"id": "brueche", "subjectId": "math", "title": TOPICS["brueche"][locale], "order": 1},
            {"id": "mechanik", "subjectId": "physics", "title": TOPICS["mechanik"][locale], "order": 1},
        ],
        "units": [
            {
                "id": unit_id,
                "subjectId": SUBJECT_OF[unit_id][0],
                "topicId": SUBJECT_OF[unit_id][1],
                "title": titles[locale],
                "order": order,
            }
            for order, (unit_id, titles) in enumerate(TITLES.items(), start=1)
        ],
        "lessons": [],
    }


def _states(student_id: str, **_kwargs: Any) -> dict[str, knowledge_mastery_service.UnitMastery]:
    return {
        unit_id: knowledge_mastery_service.UnitMastery(
            unit_id=unit_id,
            topic_id=SUBJECT_OF[unit_id][1],
            subject_id=SUBJECT_OF[unit_id][0],
            state=state,
            progress=0.0,
            unmet_exercises=0,
            lesson_count=0 if unit_id == "ohne-lektion" else 1,
            lessons_done=0,
            next_lesson=None,
        )
        for unit_id, state in STATES.items()
    }


class _Reads:
    """How often each read the map is made of was made."""

    def __init__(self) -> None:
        self.catalog = 0
        self.states = 0


@pytest.fixture
def star_map(monkeypatch: pytest.MonkeyPatch) -> _Reads:
    """The map as its reads would return it for this student, counted."""
    reads = _Reads()

    def catalog(**kwargs: Any) -> dict[str, Any]:
        reads.catalog += 1
        return _catalog(**kwargs)

    def states(evidence: Any) -> dict[str, knowledge_mastery_service.UnitMastery]:
        reads.states += 1
        return _states(evidence.student_id)

    monkeypatch.setattr(star_map_candidates, "for_student", _READ_THE_MAP)
    monkeypatch.setattr(star_map_candidates, "_content", {})
    monkeypatch.setattr(curriculum_service, "list_catalog", catalog)
    monkeypatch.setattr(student_evidence, "indexed_lessons", lambda: {})
    monkeypatch.setattr(knowledge_mastery_service, "unit_states", states)
    return reads


# ── A provider that answers from the stars it was shown ─────────────────────


def _shown_stars(body: dict[str, Any]) -> dict[str, str]:
    """The stars the model was shown, by name, as `ref` - read the way a model would."""
    turn = _student_turn(body)
    match = re.search(r"<(star_map-[0-9a-f]+)>\n(.*?)\n</\1>", turn, re.DOTALL)
    if match is None:
        return {}
    stars = {}
    for line in match.group(2).splitlines():
        if line.startswith("#"):
            continue  # a subject or topic heading
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 3:
            stars[parts[1]] = parts[0]
    return stars


Answer = Callable[[dict[str, Any]], dict[str, Any]]


class _Bedrock:
    """The Bedrock runtime as boto3 hands it out; each answer is written from the request."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.answers: list[Answer] = []

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        return {"inputTokens": 90, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c"}}

    def _answer(self, body: str) -> str:
        request = json.loads(body)
        self.bodies.append(request)
        return json.dumps(self.answers.pop(0)(request), ensure_ascii=False)

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        payload = {
            "id": "msg_test_1",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": self._answer(body)}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return {"ResponseMetadata": {"RequestId": "r"}, "body": io.BytesIO(json.dumps(payload).encode())}

    def invoke_model_with_response_stream(self, *, modelId: str, body: str):  # noqa: N803
        text = self._answer(body)
        events = [
            {"type": "message_start", "message": {
                "id": "msg_test_1", "model": modelId, "usage": {"input_tokens": 70},
            }},
            {"type": "content_block_delta", "delta": {"text": text}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 25}},
        ]
        return {
            "ResponseMetadata": {"RequestId": "r"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }


@pytest.fixture
def bedrock(table, monkeypatch: pytest.MonkeyPatch) -> _Bedrock:
    provider = _Bedrock()
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    monkeypatch.setattr(_answering.ai_service.boto3, "client", lambda *_a, **_k: provider)
    return provider


def _answer(points: Callable[[dict[str, str]], list[Any]]) -> Answer:
    """A new question's answer, naming `points(stars shown)` as its knowledge points."""

    def write(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "steps": ["Zähler und Nenner durch den ggT teilen", "Das Ergebnis prüfen"],
            "answer": "So kürzt man einen Bruch.",
            "hints": ["Was ist der ggT von 6 und 8?"],
            "similar_exercises": ["Kürze 9/12."],
            "knowledge_points": points(_shown_stars(request)),
            "suggest_teacher": False,
        }

    return write


def _follow_up(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "steps": [],
        "answer": "Der ggT ist die grösste Zahl, die beide teilt.",
        "hints": [],
        "similar_exercises": [],
        "knowledge_points": [],
        "suggest_teacher": False,
    }


# ── Attachments: the private bucket and the parser ───────────────────────────


class _Body:
    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


class _Bucket:
    """The private bucket, holding each upload's exact immutable version."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, key: str, version: str, data: bytes) -> None:
        self.objects[(key, version)] = data

    def get_object(self, *, Bucket: str, Key: str, VersionId: str):  # noqa: N803 - boto3 casing
        data = self.objects[(Key, VersionId)]
        return {
            "Body": _Body(data),
            "ETag": f"etag-{Key}",
            "ContentLength": len(data),
        }


@pytest.fixture
def bucket(model: FakeBedrock, monkeypatch: pytest.MonkeyPatch) -> _Bucket:
    """The private bucket uploads are read from; the model is still `model`."""
    bucket = _Bucket()
    clients = {"s3": bucket, "bedrock-runtime": model}
    monkeypatch.setattr(_answering.boto3, "client", lambda name, *_a, **_k: clients[name])
    return bucket


def _parse_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The extraction the parser process runs, without the process.

    The process sets rlimits, which only exist on POSIX; on Windows it always
    answers `service_unavailable`. What it extracts is the same either way.
    """

    def parse(data: Any, media_type: str, **_kwargs: Any) -> ParserResult:
        data.seek(0)
        try:
            return ParserResult(text=extract_attachment_text(data.read(), media_type))
        except DocumentExtractionFailure as error:
            return ParserResult(category=error.category)

    monkeypatch.setattr(attachment_service, "parse_document_isolated", parse)


@pytest.fixture(autouse=True)
def _parser_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_parse_in_process` for every test of a module that imports this."""
    _parse_in_process(monkeypatch)


def _upload(
    table: FakeTable,
    bucket: _Bucket,
    upload_id: str,
    data: bytes,
    *,
    filename: str,
    media_type: str,
    declared_length: int | None = None,
) -> None:
    key = f"objects/private/{upload_id}"
    bucket.put(key, "immutable-version", data)
    table.seed(
        {
            **upload_store.upload_key(upload_id),
            "upload_id": upload_id,
            "owner_id": STUDENT,
            "immutable_object_key": key,
            "immutable_version_id": "immutable-version",
            "immutable_etag": f"etag-{key}",
            "content_sha256": hashlib.sha256(data).hexdigest(),
            "original_filename": filename,
            "detected_type": media_type,
            "content_length": len(data) if declared_length is None else declared_length,
            "status": "validated",
            "expected_kind": "conversation_attachment",
            "version": 3,
            "expires_at": 4_000_000_000,
        }
    )
