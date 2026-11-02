"""Integration tests for AI memory personalisation.

These submit a real question through `ask_question.submit`, answered in the
request against the shared table double, and read the system prompt the
Bedrock double is sent, so they fail if the memory-context wiring breaks —
unlike a test that re-implements the logic.

Covers the regression where the extraction read snake_case keys that
`adaptive_learning_service._memory_response` never emits, which silently
disabled personalisation for every request.
"""
from __future__ import annotations

from typing import Any

import pytest

from fakes.ask_question import _submit
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.services import adaptive_learning_service, star_map_candidates
from stoa.services.ask_question import dispatch


def _run_message_command(model, monkeypatch, *, memory_summary: Any) -> dict[str, Any]:
    """Submit one question, returning what the model was sent.

    `memory_summary` is returned by the patched adaptive-learning service; pass
    an Exception instance to make the lookup raise.
    """

    def fake_memory_summary(**_kwargs):
        if isinstance(memory_summary, Exception):
            raise memory_summary
        return memory_summary

    monkeypatch.setattr(adaptive_learning_service, "get_memory_summary", fake_memory_summary)
    monkeypatch.setattr(star_map_candidates, "for_student", lambda *_a, **_k: None)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)

    _submit("memory-test-key", content="how do I add fractions?")

    assert model.requests, "the model was never asked"
    return {"content": model.student_turn(), "memory_context": _memory_context(model.system())}


def _memory_context(system: str) -> str | None:
    """The weak-topic summary the system prompt carries, if it carries one."""
    marker = "Student learning context (use this to tailor your explanation):\n"
    if marker not in system:
        return None
    return system.split(marker, 1)[1].split("\n", 1)[0]


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

def test_weak_topics_reach_the_ai_prompt(table, model, monkeypatch):
    captured = _run_message_command(
        model,
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


def test_snake_case_summary_yields_no_context(table, model, monkeypatch):
    """Documents the exact shape that caused the silent regression."""
    captured = _run_message_command(
        model,
        monkeypatch,
        memory_summary={
            "snapshots": [{"weak_knowledge_points": [{"label": "Fractions"}]}],
            "weak_topics": [{"label": "Fractions"}],
        },
    )
    assert captured["memory_context"] is None


# ── Graceful degradation ─────────────────────────────────────────────────────

def test_no_weak_topics_sends_no_context(table, model, monkeypatch):
    captured = _run_message_command(model, monkeypatch, memory_summary=_summary([]))
    assert captured["memory_context"] is None


def test_memory_lookup_failure_does_not_block_the_answer(table, model, monkeypatch):
    """A broken memory service must degrade to an un-personalised answer."""
    captured = _run_message_command(
        model,
        monkeypatch, memory_summary=RuntimeError("dynamo unavailable")
    )
    assert captured["memory_context"] is None
    assert captured["content"] == "how do I add fractions?"


# ── Extraction details ───────────────────────────────────────────────────────

def test_topic_id_used_when_label_is_missing(table, model, monkeypatch):
    captured = _run_message_command(
        model,
        monkeypatch,
        memory_summary=_summary([{"subject": "math", "topicId": "long_division", "count": 3}]),
    )
    assert "long_division" in captured["memory_context"]


def test_context_is_capped_and_deduplicated(table, model, monkeypatch):
    topics = [{"subject": "math", "topicId": f"t{i}", "label": f"Topic{i}", "count": 1} for i in range(20)]
    topics.append({"subject": "math", "topicId": "t0", "label": "Topic0", "count": 1})
    captured = _run_message_command(model, monkeypatch, memory_summary=_summary(topics))
    context = captured["memory_context"]
    assert context.count(",") == 7, "Expected exactly 8 topics (7 separators)"
    assert context.count("Topic0") == 1


def test_malformed_topic_entries_are_skipped(table, model, monkeypatch):
    captured = _run_message_command(
        model,
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
