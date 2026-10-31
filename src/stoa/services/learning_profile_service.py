"""Learning expansion taxonomy, prompt context, and profile seed aggregation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from stoa.db.dynamodb import stored_int
from stoa.services import locale_service, message_catalog


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


def subject_name(subject: object, locale: str) -> str:
    """The subject as the reader says it, never the stored id (#105).

    A row with no subject, or one this backend does not teach, is "general"
    rather than mathematics: `normalize_subject` defaults to math for routing,
    which would be a wrong claim in a sentence. Whatever the row holds is read
    as text first; a stored number is a subject nobody teaches, not a crash.
    """
    try:
        subject_id = normalize_subject(str(subject)) if subject else None
    except ValueError:
        subject_id = None
    if subject_id is None:
        return message_catalog.text("activity.subject.unknown", locale)
    return message_catalog.text(f"subject.{subject_id}", locale)


def subject_prompt_context(subject: str) -> str:
    meta = subject_metadata(subject)
    return (
        f"Subject label: {meta['label']}. "
        f"Rollout state: {meta['rollout_state']}. "
        f"Subject behavior: {meta['prompt_focus']} "
        "This foundation milestone does not imply full curriculum coverage or automatic exercise generation."
    )


# ── Year groups ───────────────────────────────────────────────────────────────
#
# The learning profile's `grade` was free text, and production holds what free
# text always holds: "Grade 6", "Sek1", a field of two spaces, and "14" - an age
# written into a year-group box. The curriculum meanwhile spells its own year
# group `grade_6_primary` on every row. The two vocabularies never met, so the
# one place a grade is read - "The student is in {grade}" in the system prompt -
# told the model "The student is in 14".
#
# One vocabulary now, and it is the curriculum's: `grade_<Klasse>_<stage>`, with
# `grade_6_primary` kept exactly as the catalog spells it and the rest built the
# same way. The number is the Swiss Klasse number, so it keeps counting across
# the stage boundary: 6. Primarklasse, then 7. Klasse in der Sek.
#
# `grade_secondary_i` is the one member naming a stage rather than a year, for
# the same reason "14" is not mapped at all: legacy "Sek1" says which stage a
# student is in and not which year of it, and choosing a year for them would
# invent precision the stored value never had.
GRADE_LEVEL_CODES: tuple[str, ...] = (
    "grade_1_primary",
    "grade_2_primary",
    "grade_3_primary",
    "grade_4_primary",
    "grade_5_primary",
    "grade_6_primary",
    "grade_7_secondary",
    "grade_8_secondary",
    "grade_9_secondary",
    "grade_secondary_i",
)

# Which year of compulsory school each code is, counted the one way the whole
# country agrees on: the HarmoS year, 1 to 11, kindergarten included. It is the
# anchor the four languages are translated against, because each language area
# numbers its own years differently and translating the German label word for
# word produces a year that does not exist (Ticino has no 6ª elementare) or a
# different one (Romandie's 6e année primaire is two years younger).
#
#   HarmoS 3-8  = Zurich 1.-6. Primarklasse = Romandie 3P-8P
#                 = Ticino 1ª-5ª elementare (3-7) and 1ª media (8)
#   HarmoS 9-11 = Zurich 1.-3. Sek (7.-9. Klasse) = Romandie 9e-11e
#                 = Ticino 2ª-4ª media
#
# Sources: zh.ch / Lehrplan 21 "Gliederung der Volksschule" (Zyklus 2 = school
# years 5-8 = 3.-6. Primarklasse, Zyklus 3 = 9-11 = Sekundarstufe I); PER /
# HarmoS degree tables for Romandie (3H = 1re primaire ... 8H = 8P, 11-12 years
# old); DECS Ticino HarmoS structure note (1ª elementare = 3H ... 5ª elementare
# = 7H, 1ª media = 8H ... 4ª media = 11H, Ticino keeping 5+4 under a derogation).
# The seed's own label, "6. Primarklasse (ZAP)", is the ZAP year, ~12 years old,
# and lands on HarmoS 8 in all three.
GRADE_LEVEL_HARMOS_YEARS: dict[str, int | None] = {
    "grade_1_primary": 3,
    "grade_2_primary": 4,
    "grade_3_primary": 5,
    "grade_4_primary": 6,
    "grade_5_primary": 7,
    "grade_6_primary": 8,
    "grade_7_secondary": 9,
    "grade_8_secondary": 10,
    "grade_9_secondary": 11,
    # The band names a stage, so it has no single year: HarmoS 9 to 11.
    "grade_secondary_i": None,
}

# What the free text already in the table means. Read-only: a row written before
# the codes existed is still understood, so a student who typed one of these
# keeps a usable prompt without waiting for the backfill. The write path never
# consults it, or free text would come straight back in.
LEGACY_GRADE_SPELLINGS: dict[str, str] = {
    "grade 6": "grade_6_primary",
    "sek1": "grade_secondary_i",
}


def supported_grade_codes() -> tuple[str, ...]:
    """Every year group a profile may store, in school order."""
    return GRADE_LEVEL_CODES


def normalize_grade(grade: str | None) -> str:
    """The year group a profile write may store: one code, or none at all.

    Nothing and whitespace are the same thing and both mean "not said", which
    stays legal: a grade is asked for on the learning profile, not when an
    account is opened (#50). Anything else must already be a code.

    **Not yet wired into the profile route.** The live client's grade box is
    free text and its own hint asks the student for "6. Klasse", so refusing
    that today would turn a working field into a permanent 422 shown as "try
    again". `students.py` stores what it is sent until the client sends codes;
    the prompt is held safe in the meantime by `resolve_grade_code`, which is
    where an unreadable value stops being passed on.
    """
    value = str(grade or "").strip()
    if not value:
        return ""
    if value not in GRADE_LEVEL_CODES:
        raise ValueError(f"Unsupported grade level: {grade}")
    return value


def resolve_grade_code(grade: str | None) -> str | None:
    """What a stored year group means: a code, "" for none said, None for unreadable.

    The three outcomes are kept apart on purpose. "Nobody said" is something the
    assistant is already told how to handle (#50); "the row holds something
    nobody can read" is a different thing to say, and saying the first in place
    of the second claims the profile is empty when it holds "14".
    """
    value = str(grade or "").strip()
    if not value:
        return ""
    if value in GRADE_LEVEL_CODES:
        return value
    return LEGACY_GRADE_SPELLINGS.get(" ".join(value.lower().split()))


def grade_label(code: str, locale: str) -> str:
    """One year group written out for somebody to read, in their language."""
    try:
        resolved = locale_service.normalize_locale(locale)
    except ValueError:
        resolved = locale_service.DEFAULT_LOCALE
    return message_catalog.text(f"grade.{code}", resolved)


def build_learning_profile(
    *,
    student_id: str,
    questions: list[dict[str, Any]],
    mistakes: list[dict[str, Any]] | None = None,
    asked: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build subject activity and weak-topic seed aggregates from existing records.

    `asked` are the records of what the student's Ask questions named
    (`asked_knowledge_repo`, #143). They add to the weak topics as a question's
    knowledge points do, and to nothing else: they are not questions.
    """
    mistakes = mistakes or []
    activity: dict[str, dict[str, Any]] = {}
    feedback_totals: dict[str, list[int]] = defaultdict(list)
    topic_counter: Counter[tuple[str, str, str]] = Counter()
    topic_latest: dict[tuple[str, str, str], str] = {}
    topic_evidence: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for subject_id in SUPPORTED_SUBJECTS:
        activity[subject_id] = _empty_subject_activity(subject_id)

    def count_topics(source: dict[str, Any], subject_id: str) -> None:
        for seed in _question_topic_entries(source, subject_id):
            key = (seed["subject"], seed["topic_id"], seed["label"])
            topic_counter[key] += 1
            latest = seed.get("last_seen_at") or source.get("created_at") or ""
            if latest and latest > topic_latest.get(key, ""):
                topic_latest[key] = latest
            for evidence_id in seed.get("evidence_question_ids") or [source.get("question_id")]:
                if evidence_id:
                    topic_evidence[key].add(str(evidence_id))

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
        feedback = stored_int(question.get("student_feedback"))
        if feedback is not None:
            feedback_totals[subject_id].append(feedback)

        count_topics(question, subject_id)

    for record in asked or []:
        count_topics(record, _safe_subject(record.get("subject")))

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

    weak_topics: list[dict[str, object]] = [
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
    weak_topics.sort(key=_weak_topic_sort_key)

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


def _weak_topic_sort_key(item: dict[str, object]) -> tuple[int, str, str]:
    count = item.get("count")
    subject = item.get("subject")
    label = item.get("label")
    if not isinstance(count, int) or isinstance(count, bool) or not isinstance(subject, str) or not isinstance(label, str):
        raise ValueError("Learning profile weak topic is incomplete")
    return (-count, subject, label)


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


def normalize_topic_id(label: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", label.strip().lower())
    value = value.strip("-")
    return value or "general"


def _safe_subject(subject: Any) -> str:
    try:
        return normalize_subject(str(subject or "math"))
    except ValueError:
        return "math"
