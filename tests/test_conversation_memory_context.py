"""Contract tests for the memory-context string built in conversations.py.

The AI personalisation step reads `weakTopics` off the adaptive-learning
memory summary.  These tests pin that contract so a rename in
adaptive_learning_service cannot silently degrade personalisation back to
an empty context.
"""
from __future__ import annotations

from collections.abc import Mapping

from stoa.services import adaptive_learning_service


def build_memory_context(memory_summary: Mapping[str, object]) -> str | None:
    """Mirror of the extraction logic in conversations.send_message."""
    labels: list[str] = []
    for topic in memory_summary.get("weakTopics", []):
        if not isinstance(topic, Mapping):
            continue
        label = str(topic.get("label") or topic.get("topicId") or "").strip()
        if label:
            labels.append(label)
    if not labels:
        return None
    unique_topics = list(dict.fromkeys(labels))[:8]
    return "Known weak topics for this student: " + ", ".join(unique_topics) + "."


# ── Contract: the response key the extraction depends on ─────────────────────

def test_memory_response_exposes_weak_topics_key():
    """_memory_response must keep emitting `weakTopics` (camelCase)."""
    response = adaptive_learning_service._memory_response(
        student_id="student-1",
        user={"role": "student", "user_id": "student-1"},
        profile={"weakTopics": [{"subject": "math", "topicId": "fractions", "label": "Fractions", "count": 3}]},
        generated_snapshots=[],
        stored_snapshots=[],
        recommendations=[],
        assignments=[],
    )
    assert "weakTopics" in response
    assert response["weakTopics"][0]["label"] == "Fractions"


def test_memory_response_exposes_recommendations_key():
    response = adaptive_learning_service._memory_response(
        student_id="student-1",
        user={"role": "student", "user_id": "student-1"},
        profile={"weakTopics": []},
        generated_snapshots=[],
        stored_snapshots=[],
        recommendations=[{"candidateId": "c1", "label": "Practice fractions", "confidence": "high"}],
        assignments=[],
    )
    assert "recommendations" in response
    assert response["recommendations"][0]["candidateId"] == "c1"


# ── Extraction behaviour ─────────────────────────────────────────────────────

def test_context_built_from_weak_topic_labels():
    context = build_memory_context(
        {"weakTopics": [
            {"subject": "math", "topicId": "fractions", "label": "Fractions"},
            {"subject": "math", "topicId": "decimals", "label": "Decimals"},
        ]}
    )
    assert context is not None
    assert "Fractions" in context
    assert "Decimals" in context


def test_context_falls_back_to_topic_id_when_label_missing():
    context = build_memory_context({"weakTopics": [{"subject": "math", "topicId": "long_division"}]})
    assert context is not None
    assert "long_division" in context


def test_context_is_none_when_no_weak_topics():
    assert build_memory_context({"weakTopics": []}) is None
    assert build_memory_context({}) is None


def test_context_deduplicates_and_caps_at_eight_topics():
    topics = [{"label": f"Topic{i}"} for i in range(20)]
    topics.append({"label": "Topic0"})  # duplicate
    context = build_memory_context({"weakTopics": topics})
    assert context is not None
    assert context.count(",") == 7, "Expected exactly 8 topics (7 separators)"
    assert context.count("Topic0") == 1, "Duplicate labels must be collapsed"


def test_context_skips_malformed_entries():
    context = build_memory_context(
        {"weakTopics": ["not-a-dict", None, {"label": "Fractions"}, {"label": "   "}]}
    )
    assert context == "Known weak topics for this student: Fractions."
