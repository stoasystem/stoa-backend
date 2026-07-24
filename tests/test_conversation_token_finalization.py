"""Conversation token finalization at the durable message replay boundary."""

from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timezone

import pytest

from stoa.db.repositories import allowance_repo
from stoa.routers import conversations
from stoa.services import ai_service, allowance_service
from tests.test_token_allowances import AtomicAllowanceTable


NOW = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)


class _ResponseBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.closed = False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


class MockBedrockProvider:
    """CountTokens plus InvokeModel fake; no network/provider access."""

    def __init__(
        self,
        *,
        input_tokens: object = 90,
        actual_input_tokens: int = 70,
        actual_output_tokens: int = 25,
        invoke_error: Exception | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.actual_input_tokens = actual_input_tokens
        self.actual_output_tokens = actual_output_tokens
        self.invoke_error = invoke_error
        self.count_calls: list[dict[str, object]] = []
        self.invoke_calls: list[dict[str, object]] = []

    def count_tokens(self, **kwargs: object) -> dict[str, object]:
        self.count_calls.append(copy.deepcopy(kwargs))
        return {
            "inputTokens": self.input_tokens,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "count-request-1",
            },
        }

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        if self.invoke_error is not None:
            raise self.invoke_error
        content = {
            "answer": "The durable conversation answer",
            "steps": ["First durable step"],
            "hints": ["The same durable hint"],
            "similar_exercises": [],
            "knowledge_points": ["fractions"],
        }
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": self.actual_input_tokens,
                        "output_tokens": self.actual_output_tokens,
                    },
                    "content": [{"text": json.dumps(content)}],
                }
            ),
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "invoke-request-1",
            },
        }


def _command() -> dict[str, object]:
    command: dict[str, object] = {
        "command_id": "message-command-1",
        "conversation_id": "conversation-1",
        "student_id": "student-1",
        "owner_id": "student-1",
        "assistant_message_id": "assistant-message-1",
        "account_fence_generation": 1,
        "created_at": NOW.isoformat(),
    }
    command.update(
        conversations._conversation_allowance_command_fields(
            command,
            {
                "effectivePlan": "free_trial",
                "source": "free_trial_activation",
                "grantId": "free-trial-grant-1",
                "allowanceVersion": 7,
            },
        )
    )
    return command


def _patch_allowance_table(
    monkeypatch: pytest.MonkeyPatch,
    table: AtomicAllowanceTable,
) -> None:
    reserve = allowance_service.reserve_token_allowance
    observe = allowance_service.record_provider_usage
    finalize = allowance_service.finalize_token_allowance
    restore = allowance_service.restore_user_allowance
    monkeypatch.setattr(
        conversations.allowance_service,
        "reserve_token_allowance",
        lambda **kwargs: reserve(**kwargs, table=table),
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "record_provider_usage",
        lambda **kwargs: observe(**kwargs, table=table),
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "finalize_token_allowance",
        lambda **kwargs: finalize(**kwargs, table=table),
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "restore_user_allowance",
        lambda **kwargs: restore(**kwargs, table=table),
    )


def _provider_result(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: AtomicAllowanceTable,
    provider: MockBedrockProvider,
) -> tuple[
    dict[str, object],
    ai_service.AIProviderResult[dict[str, object]],
]:
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(
        conversations.ai_service.boto3,
        "client",
        lambda *_args, **_kwargs: provider,
    )
    command = _command()
    client = conversations._ConversationAllowanceBedrockClient(command)
    result = ai_service.get_ai_answer(
        content="private-message-canary",
        subject="math",
        grade="Sek1",
        correlation_id="transport-correlation-that-must-not-own-the-effect",
        effect_id=client.allowance_effect_id,
        client=client,
        observed_at=NOW,
    )
    return command, result


def _metadata(
    result: ai_service.AIProviderResult[dict[str, object]],
    command: dict[str, object],
) -> dict[str, object]:
    return conversations._message_allowance_metadata_from_provider(
        result,
        allowance_effect_id=str(command["allowance_effect_id"]),
    )


def test_count_failure_never_reserves_or_invokes(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider(input_tokens="not-an-exact-count")
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(
        conversations.ai_service.boto3,
        "client",
        lambda *_args, **_kwargs: provider,
    )
    client = conversations._ConversationAllowanceBedrockClient(_command())

    with pytest.raises(conversations._ConversationAllowanceFailure) as captured:
        ai_service.get_ai_answer(
            content="message",
            subject="math",
            grade="Sek1",
            effect_id=client.allowance_effect_id,
            client=client,
        )

    assert captured.value.code == "provider_token_count_unavailable"
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []
    assert not any(
        item.get("entity_type") == "allowance_effect"
        for item in table.items.values()
    )


def test_allowance_denial_never_invokes_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(
        conversations.ai_service.boto3,
        "client",
        lambda *_args, **_kwargs: provider,
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: allowance_repo.ReservationResult(
            allowance_repo.ReservationDisposition.LIMIT_EXCEEDED
        ),
    )
    client = conversations._ConversationAllowanceBedrockClient(_command())

    with pytest.raises(conversations._ConversationAllowanceFailure) as captured:
        ai_service.get_ai_answer(
            content="message",
            subject="math",
            grade="Sek1",
            effect_id=client.allowance_effect_id,
            client=client,
        )

    assert captured.value.code == "allowance_exhausted"
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []


def test_provider_timeout_after_reserve_remains_reserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider(invoke_error=TimeoutError("timeout-canary"))
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(
        conversations.ai_service.boto3,
        "client",
        lambda *_args, **_kwargs: provider,
    )
    client = conversations._ConversationAllowanceBedrockClient(_command())

    with pytest.raises(TimeoutError):
        ai_service.get_ai_answer(
            content="message",
            subject="math",
            grade="Sek1",
            effect_id=client.allowance_effect_id,
            client=client,
        )

    effect = next(
        item
        for item in table.items.values()
        if item.get("entity_type") == "allowance_effect"
    )
    assert effect["state"] == "reserved"
    assert table.counter()["finalized_input_tokens"] == 0
    assert len(provider.invoke_calls) == 1


def test_store_ambiguity_keeps_observed_reservation_without_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, result = _provider_result(
        monkeypatch,
        table=table,
        provider=MockBedrockProvider(),
    )
    metadata = _metadata(result, command)

    assert conversations._observe_message_provider_usage(
        beneficiary_id="student-1",
        metadata=metadata,
    )

    effect = next(
        item
        for item in table.items.values()
        if item.get("entity_type") == "allowance_effect"
    )
    assert effect["state"] == "observed"
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 90
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70


def test_regular_sse_and_hint_replay_finalize_one_exact_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    command, result = _provider_result(
        monkeypatch,
        table=table,
        provider=provider,
    )
    metadata = _metadata(result, command)
    assert conversations._observe_message_provider_usage(
        beneficiary_id="student-1",
        metadata=metadata,
    )
    response = conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id="student-message-1",
            conversationId="conversation-1",
            role="student",
            content="private-message-canary",
            createdAt=NOW.isoformat(),
        ),
        assistantMessage=conversations.ChatMessage(
            id="assistant-message-1",
            conversationId="conversation-1",
            role="assistant",
            content=(
                "1. First durable step\n\nThe durable conversation answer"
                "\n\n**Hinweis:** The same durable hint"
            ),
            createdAt=NOW.isoformat(),
        ),
    )
    durable = {
        **command,
        "status": "completed",
        "student_message_id": "student-message-1",
        "result_json": conversations._message_result_json(response, metadata),
    }

    regular = conversations._result_response(
        allowance_repo_message_result(durable)
    )
    sse = conversations._result_response(
        allowance_repo_message_result(durable)
    )

    assert regular == sse == response
    assert len(provider.invoke_calls) == 1
    assert "The same durable hint" in regular.assistantMessage.content
    counter = table.counter()
    assert counter["finalized_input_tokens"] == 70
    assert counter["finalized_output_tokens"] == 25
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 25
    assert len(table.evidence()) == 1


def test_finalize_timeout_repairs_from_the_same_durable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, result = _provider_result(
        monkeypatch,
        table=table,
        provider=MockBedrockProvider(),
    )
    metadata = _metadata(result, command)
    assert conversations._observe_message_provider_usage(
        beneficiary_id="student-1",
        metadata=metadata,
    )
    response = conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id="student-message-1",
            conversationId="conversation-1",
            role="student",
            content="message",
            createdAt=NOW.isoformat(),
        ),
        assistantMessage=conversations.ChatMessage(
            id="assistant-message-1",
            conversationId="conversation-1",
            role="assistant",
            content="answer",
            createdAt=NOW.isoformat(),
        ),
    )
    durable = {
        **command,
        "status": "completed",
        "student_message_id": "student-message-1",
        "result_json": conversations._message_result_json(response, metadata),
    }
    real_finalize = conversations.allowance_service.finalize_token_allowance
    calls = 0

    def retry_once(**kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 1:
            return allowance_repo.FinalizationResult(
                allowance_repo.FinalizationDisposition.RETRYABLE
            )
        return real_finalize(**kwargs)

    monkeypatch.setattr(
        conversations.allowance_service,
        "finalize_token_allowance",
        retry_once,
    )

    with pytest.raises(conversations._ConversationAllowanceFailure):
        conversations._result_response(allowance_repo_message_result(durable))
    replay = conversations._result_response(allowance_repo_message_result(durable))

    assert replay == response
    assert table.counter()["finalized_input_tokens"] == 70
    assert table.counter()["finalized_output_tokens"] == 25


def allowance_repo_message_result(
    command: dict[str, object],
):
    from stoa.db.repositories import attachment_repo

    return attachment_repo.MessageCommandResult(
        attachment_repo.MessageCommandDisposition.COMPLETED,
        command=command,
    )


def test_terminal_validation_restores_user_and_retains_provider_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    command, result = _provider_result(
        monkeypatch,
        table=table,
        provider=provider,
    )
    metadata = _metadata(result, command)
    assert conversations._observe_message_provider_usage(
        beneficiary_id="student-1",
        metadata=metadata,
    )

    assert conversations._restore_message_allowance(
        beneficiary_id="student-1",
        metadata=metadata,
    )

    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 25
    assert len(table.evidence()) == 1


def test_durable_payload_is_private_and_content_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, result = _provider_result(
        monkeypatch,
        table=table,
        provider=MockBedrockProvider(),
    )
    metadata = _metadata(result, command)
    response = conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id="student-message-1",
            conversationId="conversation-1",
            role="student",
            content="private-message-canary",
            createdAt=NOW.isoformat(),
        ),
        assistantMessage=conversations.ChatMessage(
            id="assistant-message-1",
            conversationId="conversation-1",
            role="assistant",
            content="private-answer-canary",
            createdAt=NOW.isoformat(),
        ),
    )
    durable_json = conversations._message_result_json(response, metadata)
    public = conversations._completed_command_response(
        {
            **command,
            "status": "completed",
            "student_message_id": "student-message-1",
            "result_json": durable_json,
        }
    )

    assert public == response
    assert "allowance_effect_id" not in public.model_dump_json()
    assert "provider_usage_evidence_id" not in public.model_dump_json()
    evidence_json = json.dumps(table.evidence(), default=str)
    assert "private-message-canary" not in evidence_json
    assert "private-answer-canary" not in evidence_json


def test_title_generation_is_explicit_provider_cost_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TitleProvider:
        def invoke_model(self, **_kwargs: object) -> dict[str, object]:
            return {
                "body": _ResponseBody(
                    {"content": [{"text": "A Safe Title"}]}
                )
            }

    monkeypatch.setattr(
        conversations.boto3,
        "client",
        lambda *_args, **_kwargs: TitleProvider(),
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: pytest.fail("title reserved student allowance"),
    )
    monkeypatch.setattr(
        conversations.allowance_service,
        "finalize_token_allowance",
        lambda **_kwargs: pytest.fail("title finalized student allowance"),
    )

    assert conversations._generate_title("message", "math") == "A Safe Title"
    source = inspect.getsource(conversations._generate_title)
    assert "AIInvocationClass.PROVIDER_COST_ONLY" in source


def test_source_binds_durable_message_effect_before_invoke_and_finalize() -> None:
    source = inspect.getsource(conversations)
    reserve_at = source.index("reserve_token_allowance")
    invoke_at = source.index("invoke_model", reserve_at)
    assert reserve_at < invoke_at
    assert "allowance_effect_id" in source
    assert "record_provider_usage" in source
    assert "finalize_token_allowance" in source
    assert "restore_user_allowance" in source
    assert "_execute_message_command" in inspect.getsource(conversations.send_message)
    assert "_execute_message_command" in inspect.getsource(conversations.stream_message)
