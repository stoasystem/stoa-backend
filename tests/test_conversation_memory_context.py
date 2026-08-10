"""Integration tests for AI memory personalisation.

These drive the real `conversations._execute_message_command` code path and
capture the kwargs handed to `ai_service.get_ai_answer`, so they fail if the
memory-context wiring breaks — unlike a test that re-implements the logic.

Covers the regression where the extraction read snake_case keys that
`adaptive_learning_service._memory_response` never emits, which silently
disabled personalisation for every request.
"""
from __future__ import annotations

from typing import Any

import pytest

from stoa.db.repositories import attachment_repo
from stoa.routers import conversations
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import adaptive_learning_service


def _actor(role=CanonicalRole.STUDENT, user_id="student-1"):
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        (),
    )


def _run_message_command(monkeypatch, *, memory_summary: Any) -> dict[str, Any]:
    """Execute one full message command, returning the kwargs the AI received.

    `memory_summary` is returned by the patched adaptive-learning service; pass
    an Exception instance to make the lookup raise.
    """
    body = conversations.SendMessageRequest.model_validate(
        {"content": "how do I add fractions?", "idempotencyKey": "memory-test-key"}
    )
    command_state: dict[str, Any] = {}
    captured: dict[str, Any] = {}

    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free_trial")
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(conversations.boto3, "client", lambda *_a, **_k: object())
    monkeypatch.setattr(
        conversations.attachment_service, "prepare_message_attachments", lambda *_a, **_k: []
    )
    monkeypatch.setattr(
        conversations.attachment_service, "ensure_message_attachment_capacity", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        conversations.attachment_service, "bind_message_attachments", lambda **_k: []
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "extract_message_attachment_context",
        lambda *_a, **_k: conversations.attachment_service.AttachmentContextResult(
            conversations.attachment_service.AttachmentContextDisposition.READY
        ),
    )

    def claim(**kwargs):
        command_state.update(kwargs["command"])
        command_state["counter_value"] = 1
        return True, 1

    def claim_ai(**kwargs):
        command_state.update(status="ai_running", leaseOwner=kwargs["lease_owner"], attempt=1)
        return True, 1

    def complete(**kwargs):
        command_state.update(status="completed", result_json=kwargs["result_json"])
        return True

    monkeypatch.setattr(attachment_repo, "claim_message_command_and_quota", claim)
    monkeypatch.setattr(attachment_repo, "get_message_command", lambda *_a, **_k: dict(command_state) or None)
    monkeypatch.setattr(attachment_repo, "claim_message_ai_lease", claim_ai)
    monkeypatch.setattr(attachment_repo, "renew_message_ai_lease", lambda **_k: True)
    monkeypatch.setattr(attachment_repo, "complete_message_command", complete)

    def fake_memory_summary(**_kwargs):
        if isinstance(memory_summary, Exception):
            raise memory_summary
        return memory_summary

    monkeypatch.setattr(adaptive_learning_service, "get_memory_summary", fake_memory_summary)

    def fake_get_ai_answer(**kwargs):
        captured.update(kwargs)
        return {"steps": ["one"], "answer": "safe", "hints": []}

    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", fake_get_ai_answer)

    conversations._execute_message_command(
        conv_id="conv-1",
        student_id="student-1",
        subject="math",
        grade="Sek1",
        body=body,
        command_context={
            "actor": _actor(),
            "fingerprint": conversations.message_request_fingerprint(body),
            "existing": None,
        },
    )
    assert captured, "ai_service.get_ai_answer was never invoked"
    return captured


def _summary(weak_topics: list[dict[str, Any]]) -> dict[str, Any]:
    """A memory summary shaped like the real _memory_response output."""
    return {
        "studentId": "student-1",
        "roleView": "student",
        "weakTopics": weak_topics,
        "memorySnapshots": [],
        "recommendations": [],
    }


# ── The regression this suite exists for ─────────────────────────────────────

def test_weak_topics_reach_the_ai_prompt(monkeypatch):
    captured = _run_message_command(
        monkeypatch,
        memory_summary=_summary([
            {"subject": "math", "topicId": "fractions", "label": "Fractions", "count": 5},
            {"subject": "math", "topicId": "decimals", "label": "Decimals", "count": 2},
        ]),
    )
    context = captured["memory_context"]
    assert context is not None, "memory_context must be populated when weak topics exist"
    assert "Fractions" in context
    assert "Decimals" in context


def test_snake_case_summary_yields_no_context(monkeypatch):
    """Documents the exact shape that caused the silent regression."""
    captured = _run_message_command(
        monkeypatch,
        memory_summary={
            "snapshots": [{"weak_knowledge_points": [{"label": "Fractions"}]}],
            "weak_topics": [{"label": "Fractions"}],
        },
    )
    assert captured["memory_context"] is None


# ── Graceful degradation ─────────────────────────────────────────────────────

def test_no_weak_topics_sends_no_context(monkeypatch):
    captured = _run_message_command(monkeypatch, memory_summary=_summary([]))
    assert captured["memory_context"] is None


def test_memory_lookup_failure_does_not_block_the_answer(monkeypatch):
    """A broken memory service must degrade to an un-personalised answer."""
    captured = _run_message_command(
        monkeypatch, memory_summary=RuntimeError("dynamo unavailable")
    )
    assert captured["memory_context"] is None
    assert captured["content"] == "how do I add fractions?"


# ── Extraction details ───────────────────────────────────────────────────────

def test_topic_id_used_when_label_is_missing(monkeypatch):
    captured = _run_message_command(
        monkeypatch,
        memory_summary=_summary([{"subject": "math", "topicId": "long_division", "count": 3}]),
    )
    assert "long_division" in captured["memory_context"]


def test_context_is_capped_and_deduplicated(monkeypatch):
    topics = [{"subject": "math", "topicId": f"t{i}", "label": f"Topic{i}", "count": 1} for i in range(20)]
    topics.append({"subject": "math", "topicId": "t0", "label": "Topic0", "count": 1})
    captured = _run_message_command(monkeypatch, memory_summary=_summary(topics))
    context = captured["memory_context"]
    assert context.count(",") == 7, "Expected exactly 8 topics (7 separators)"
    assert context.count("Topic0") == 1


def test_malformed_topic_entries_are_skipped(monkeypatch):
    captured = _run_message_command(
        monkeypatch,
        memory_summary=_summary(["not-a-dict", None, {"label": "Fractions"}, {"label": "  "}]),
    )
    assert captured["memory_context"] == "Known weak topics for this student: Fractions."


# ── Response-shape contract the extraction depends on ────────────────────────

@pytest.mark.parametrize("key", ["weakTopics", "recommendations", "memorySnapshots"])
def test_memory_response_keeps_camel_case_keys(key):
    response = adaptive_learning_service._memory_response(
        student_id="student-1",
        user={"role": "student", "user_id": "student-1"},
        profile={"weakTopics": [{"subject": "math", "topicId": "fractions", "label": "Fractions", "count": 3}]},
        generated_snapshots=[],
        stored_snapshots=[],
        recommendations=[],
        assignments=[],
    )
    assert key in response
