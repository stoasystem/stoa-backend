"""Learning expansion taxonomy, prompt context, and profile seed aggregation."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any

from stoa.db.dynamodb import stored_int
from stoa.services import (
    curriculum_service,
    locale_service,
    message_catalog,
    student_evidence,
    weak_topics,
)


def supported_subject_ids() -> set[str]:
    return set(curriculum_service.SUPPORTED_SUBJECTS)


def subject_metadata(subject: str | None) -> dict[str, str]:
    """A supported subject's id, label, rollout mark and prompt focus.

    No subject at all is mathematics, as it always was for routing; a subject
    the platform does not teach is a `ValueError`.
    """
    canonical = curriculum_service.subject_id(subject or "math")
    if canonical is None:
        raise ValueError(f"Unsupported subject: {subject}")
    return {"id": canonical, **curriculum_service.SUPPORTED_SUBJECTS[canonical]}


def subject_name(subject: object, locale: str) -> str:
    """The subject as the reader says it, never the stored id (#105).

    A row with no subject, or one this backend does not teach, is "general"
    rather than mathematics, which would be a wrong claim in a sentence. A
    stored number is a subject nobody teaches, not a crash.
    """
    subject_id = curriculum_service.subject_id(subject)
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
# `grade_secondary_i` names a stage rather than a year, for the same reason
# "14" is not mapped at all: legacy "Sek1" says which stage a student is in and
# not which year of it, and choosing a year for them would invent precision the
# stored value never had.
#
# `grade_secondary_ii` (#419) is the other stage, upper secondary: Gymnasium,
# Mittelschule, collège, liceo. It is spelled exactly as
# `knowledge_base_catalog.UPPER_SECONDARY` files its lessons, and it stays one
# stage because the catalog has no per-year rows a finer code could match.
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
    "grade_secondary_ii",
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
#
# The two stages have no single year and map to None: lower secondary spans
# HarmoS 9-11, and upper secondary lies beyond HarmoS altogether (it starts
# after year 11 and runs three to four years, depending on the school). Where
# a stage has to be placed among the years, `knowledge_map_service.SCHOOL_YEAR`
# does it.
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
    # Past compulsory school: beyond HarmoS 11, several years long.
    "grade_secondary_ii": None,
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


# ── Profile fields chosen from a list ─────────────────────────────────────────
#
# A profile field the client fills from a closed list is declared here and
# nowhere else: its codes, in the order they are offered. The client renders
# the list it is sent (`choices` on the profile response) instead of keeping a
# copy, a write outside it is refused with `profile_choice_unknown`, and each
# code's name for the person choosing is the catalog's
# `choice.<field>.<code>`, in four languages. A new field of this kind is one
# entry here and its labels.

# How the assistant talks to a student who picked one (#314). The student picks
# a code, never a sentence: each non-standard code maps to a fixed paragraph in
# `ask_answer.ANSWER_STYLE_RULES`, so nothing the student writes reaches the
# system prompt. `standard` is the answer as it was before styles existed and is
# what a profile that never chose one gets.
ANSWER_STYLE_CODES: tuple[str, ...] = ("standard", "concise", "encouraging", "vivid")
DEFAULT_ANSWER_STYLE = "standard"

PROFILE_CHOICES: dict[str, tuple[str, ...]] = {
    "grade": GRADE_LEVEL_CODES,
    "answer_style": ANSWER_STYLE_CODES,
}


def choice_label(field: str, code: str, locale: str) -> str:
    """One code of a profile field, named for the person choosing it."""
    try:
        resolved = locale_service.normalize_locale(locale)
    except ValueError:
        resolved = locale_service.DEFAULT_LOCALE
    return message_catalog.text(f"choice.{field}.{code}", resolved)


def profile_choices(locale: str) -> dict[str, list[dict[str, str]]]:
    """Every list-chosen profile field: its codes in order, each with its name."""
    return {
        field: [{"code": code, "label": choice_label(field, code, locale)} for code in codes]
        for field, codes in PROFILE_CHOICES.items()
    }


def normalize_choice(field: str, value: str | None) -> str:
    """What a profile write may store for a list-chosen field: one code, or none.

    Nothing and whitespace are the same thing and both mean "not said", which
    stays legal. Anything else must already be one of the field's codes,
    spelled exactly as offered.
    """
    stripped = str(value or "").strip()
    if not stripped:
        return ""
    if stripped not in PROFILE_CHOICES[field]:
        raise ValueError(f"Unsupported {field}: {value}")
    return stripped


def answer_style_code(value: object) -> str:
    """The style an answer is given in: a code the platform knows, else `standard`.

    Read wherever a style is used - the profile response, the question's
    generation context, the worker - so a value nobody can read (a command
    stored before styles existed, a code later withdrawn) answers the way
    every student was answered before #314, never with an error.
    """
    if isinstance(value, str) and value in ANSWER_STYLE_CODES:
        return value
    return DEFAULT_ANSWER_STYLE


def normalize_grade(grade: str | None) -> str:
    """The year group a profile write may store: one code, or none at all.

    Not saying stays legal: a grade is asked for on the learning profile, not
    when an account is opened (#50).
    """
    return normalize_choice("grade", grade)


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


def chosen_subjects(profile: Mapping[str, object]) -> tuple[str, ...]:
    """The subjects a student ticked on their profile, as stored (#321).

    `primary_subjects`, else the older `subjects` - the same precedence as the
    profile response. Read for the star map, so nothing here refuses: a value
    that is not a list, an entry that is not text and a blank entry are passed
    over, and an id no subject goes by simply matches nothing. Not normalised:
    the reader compares through `curriculum_service.subject_key`.
    """
    value = profile.get("primary_subjects") if "primary_subjects" in profile else profile.get("subjects")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


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
    evidence: student_evidence.StudentEvidence,
    asked: list[dict[str, Any]] | None = None,
    locale: str = "de",
) -> dict[str, Any]:
    """The student's activity per subject and their weak topics.

    `questions` are the retired flow's question rows: they make the activity,
    and count among the weak topics as Ask records do. `asked` are the records
    of what the student's Ask questions named (`asked_knowledge_repo`, #143).
    The weak topics are `weak_topics.for_student`'s first ten, named in
    `locale`; nothing here counts them (#673).
    """
    activity: dict[str, dict[str, Any]] = {}
    feedback_totals: dict[str, list[int]] = defaultdict(list)

    for subject_id in curriculum_service.SUPPORTED_SUBJECTS:
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
        feedback = stored_int(question.get("student_feedback"))
        if feedback is not None:
            feedback_totals[subject_id].append(feedback)

    for subject_id, values in feedback_totals.items():
        activity.setdefault(subject_id, _empty_subject_activity(subject_id))["feedbackAverage"] = round(
            sum(values) / len(values), 2
        )

    weak = weak_topics.for_student(evidence, [*questions, *(asked or [])], locale=locale)

    return {
        "studentId": student_id,
        "subjects": [
            {
                "id": subject_id,
                "label": meta["label"],
                "rolloutState": meta["rollout_state"],
            }
            for subject_id, meta in curriculum_service.SUPPORTED_SUBJECTS.items()
        ],
        "subjectActivity": list(activity.values()),
        "weakTopics": [weak_topic_response(topic) for topic in weak[:10]],
        "strengthTopics": [],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def weak_topic_response(topic: weak_topics.WeakTopic) -> dict[str, object]:
    """One weak topic as the learning profile and adaptive memory send it."""
    return {
        "subject": topic.subject,
        "topicId": topic.topic_id,
        "label": topic.name,
        "count": topic.count,
        "score": topic.score,
        "latestEvidenceAt": topic.latest_evidence_at or None,
        "evidenceQuestionIds": list(topic.evidence_question_ids),
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


def normalize_topic_id(label: str) -> str:
    """A name made a slug, as the stored adaptive memory snapshots key their topics.

    Weak topics no longer use it (#673): `weak_topics` keeps a name the
    curriculum does not know as written. It goes with the stored snapshots (#675).
    """
    value = re.sub(r"[^a-z0-9]+", "-", label.strip().lower())
    value = value.strip("-")
    return value or "general"


def _safe_subject(subject: Any) -> str:
    return curriculum_service.counted_subject(subject)
