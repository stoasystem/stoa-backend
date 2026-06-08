"""Learning expansion taxonomy, prompt context, and profile seed aggregation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


SUPPORTED_SUBJECTS: dict[str, dict[str, str]] = {
    "math": {
        "label": "Mathematics",
        "rollout_state": "active",
        "prompt_focus": "Use step-by-step mathematical reasoning and keep the student doing the thinking.",
    },
    "physics": {
        "label": "Physics",
        "rollout_state": "foundation",
        "prompt_focus": "Explain concepts with simple physical intuition, units, and step-by-step reasoning.",
    },
    "german": {
        "label": "German",
        "rollout_state": "foundation",
        "prompt_focus": "Treat this as language learning: correct, explain grammar or wording, and give examples.",
    },
    "english": {
        "label": "English",
        "rollout_state": "foundation",
        "prompt_focus": "Treat this as language learning: correct, explain grammar or wording, and give examples.",
    },
}


def supported_subject_ids() -> set[str]:
    return set(SUPPORTED_SUBJECTS)


def subject_metadata(subject: str) -> dict[str, str]:
    normalized = normalize_subject(subject)
    return {"id": normalized, **SUPPORTED_SUBJECTS[normalized]}


def normalize_subject(subject: str | None) -> str:
    value = (subject or "math").strip().lower()
    aliases = {
        "mathematics": "math",
        "mathematik": "math",
        "deutsch": "german",
        "englisch": "english",
    }
    value = aliases.get(value, value)
    if value not in SUPPORTED_SUBJECTS:
        raise ValueError(f"Unsupported subject: {subject}")
    return value


def subject_prompt_context(subject: str) -> str:
    meta = subject_metadata(subject)
    return (
        f"Subject label: {meta['label']}. "
        f"Rollout state: {meta['rollout_state']}. "
        f"Subject behavior: {meta['prompt_focus']} "
        "This foundation milestone does not imply full curriculum coverage or automatic exercise generation."
    )


def topic_seeds_from_ai_response(
    *,
    subject: str,
    response: dict[str, Any],
    question_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Extract normalized topic seed records from a structured AI response."""
    values: list[Any] = []
    for key in ("knowledge_points", "topics", "weak_topics", "weakTopics"):
        raw = response.get(key)
        if isinstance(raw, list):
            values.extend(raw)

    seeds = []
    seen: set[str] = set()
    for raw in values:
        label = _topic_label(raw)
        if not label:
            continue
        topic_id = normalize_topic_id(label)
        if topic_id in seen:
            continue
        seen.add(topic_id)
        seeds.append(
            {
                "subject": normalize_subject(subject),
                "topic_id": topic_id,
                "label": label,
                "source": "ai_response",
                "confidence": 0.7,
                "evidence_question_ids": [question_id],
                "first_seen_at": timestamp,
                "last_seen_at": timestamp,
            }
        )
    return seeds


def build_learning_profile(
    *,
    student_id: str,
    questions: list[dict[str, Any]],
    mistakes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build subject activity and weak-topic seed aggregates from existing records."""
    mistakes = mistakes or []
    activity: dict[str, dict[str, Any]] = {}
    feedback_totals: dict[str, list[int]] = defaultdict(list)
    topic_counter: Counter[tuple[str, str, str]] = Counter()
    topic_latest: dict[tuple[str, str, str], str] = {}
    topic_evidence: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for subject_id in SUPPORTED_SUBJECTS:
        activity[subject_id] = _empty_subject_activity(subject_id)

    for question in questions:
        subject_id = _safe_subject(question.get("subject"))
        item = activity.setdefault(subject_id, _empty_subject_activity(subject_id))
        item["questionCount"] += 1
        if question.get("status") == "ai_answered":
            item["aiResolvedCount"] += 1
        if question.get("status") in {"escalated", "teacher_requested", "teacher_active", "resolved"} or question.get(
            "teacher_help_requested"
        ):
            item["teacherEscalationCount"] += 1
        feedback = question.get("student_feedback")
        if isinstance(feedback, int):
            feedback_totals[subject_id].append(feedback)

        for seed in _question_topic_entries(question, subject_id):
            key = (seed["subject"], seed["topic_id"], seed["label"])
            topic_counter[key] += 1
            latest = seed.get("last_seen_at") or question.get("created_at") or ""
            if latest and latest > topic_latest.get(key, ""):
                topic_latest[key] = latest
            for evidence_id in seed.get("evidence_question_ids") or [question.get("question_id")]:
                if evidence_id:
                    topic_evidence[key].add(str(evidence_id))

    for mistake in mistakes:
        subject_id = _safe_subject(mistake.get("subject_id") or mistake.get("subject"))
        raw_topic = mistake.get("topic_id")
        if not raw_topic:
            continue
        label = str(raw_topic)
        key = (subject_id, normalize_topic_id(label), label)
        topic_counter[key] += 1
        latest = mistake.get("created_at") or ""
        if latest and latest > topic_latest.get(key, ""):
            topic_latest[key] = latest

    for subject_id, values in feedback_totals.items():
        activity.setdefault(subject_id, _empty_subject_activity(subject_id))["feedbackAverage"] = round(
            sum(values) / len(values), 2
        )

    weak_topics = [
        {
            "subject": subject_id,
            "topicId": topic_id,
            "label": label,
            "count": count,
            "latestEvidenceAt": topic_latest.get((subject_id, topic_id, label)),
            "evidenceQuestionIds": sorted(topic_evidence.get((subject_id, topic_id, label), set())),
        }
        for (subject_id, topic_id, label), count in topic_counter.items()
    ]
    weak_topics.sort(key=lambda item: (-int(item["count"]), item["subject"], item["label"]))

    return {
        "studentId": student_id,
        "subjects": [
            {
                "id": subject_id,
                "label": meta["label"],
                "rolloutState": meta["rollout_state"],
            }
            for subject_id, meta in SUPPORTED_SUBJECTS.items()
        ],
        "subjectActivity": list(activity.values()),
        "weakTopics": weak_topics[:10],
        "strengthTopics": [],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _empty_subject_activity(subject_id: str) -> dict[str, Any]:
    meta = subject_metadata(subject_id)
    return {
        "subject": subject_id,
        "label": meta["label"],
        "rolloutState": meta["rollout_state"],
        "questionCount": 0,
        "aiResolvedCount": 0,
        "teacherEscalationCount": 0,
        "feedbackAverage": None,
    }


def _question_topic_entries(question: dict[str, Any], subject_id: str) -> list[dict[str, Any]]:
    entries = question.get("topic_seeds")
    if isinstance(entries, list) and entries:
        return [entry for entry in entries if isinstance(entry, dict)]

    timestamp = question.get("created_at") or datetime.now(timezone.utc).isoformat()
    seeds = []
    for label in question.get("knowledge_points", []) or []:
        if not isinstance(label, str) or not label.strip():
            continue
        seeds.append(
            {
                "subject": subject_id,
                "topic_id": normalize_topic_id(label),
                "label": label,
                "source": "ai_response",
                "confidence": 0.5,
                "evidence_question_ids": [question.get("question_id")],
                "first_seen_at": timestamp,
                "last_seen_at": timestamp,
            }
        )
    return seeds


def _topic_label(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, dict):
        value = raw.get("label") or raw.get("topic") or raw.get("topic_id") or raw.get("name")
        if isinstance(value, str):
            return value.strip() or None
    return None


def normalize_topic_id(label: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", label.strip().lower())
    value = value.strip("-")
    return value or "general"


def _safe_subject(subject: Any) -> str:
    try:
        return normalize_subject(str(subject or "math"))
    except ValueError:
        return "math"
