"""Learning expansion taxonomy, prompt context, and profile seed aggregation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any

from stoa.db.dynamodb import stored_int
from stoa.services import (
    curriculum_service,
    curriculum_translations,
    knowledge_base_catalog,
    locale_service,
    message_catalog,
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
    mistakes: list[dict[str, Any]] | None = None,
    asked: list[dict[str, Any]] | None = None,
    catalog: Mapping[str, Any] | None = None,
    locale: str = "de",
) -> dict[str, Any]:
    """Build subject activity and weak-topic seed aggregates from existing records.

    `asked` are the records of what the student's Ask questions named
    (`asked_knowledge_repo`, #143). They add to the weak topics as a question's
    knowledge points do, and to nothing else: they are not questions.

    `catalog` is the student catalog in `locale` (`curriculum_service.list_catalog`).
    With it, every spelling of a knowledge point the curriculum knows - its unit
    id, an old slug, its title in any language - is one weak topic, named as the
    catalog names it (#390).
    """
    mistakes = mistakes or []
    names = TopicNames(catalog or {}, locale)
    activity: dict[str, dict[str, Any]] = {}
    feedback_totals: dict[str, list[int]] = defaultdict(list)
    topic_counter: Counter[tuple[str, str, str]] = Counter()
    topic_latest: dict[tuple[str, str, str], str] = {}
    topic_evidence: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for subject_id in curriculum_service.SUPPORTED_SUBJECTS:
        activity[subject_id] = _empty_subject_activity(subject_id)

    def count_topics(source: dict[str, Any], subject_id: str) -> None:
        for seed in _question_topic_entries(source, subject_id):
            key = names.key(seed["subject"], seed["topic_id"], seed["label"])
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
        key = names.key(
            subject_id,
            normalize_topic_id(label),
            label,
            unit_id=mistake.get("unit_id"),
            lesson_id=mistake.get("lesson_id"),
        )
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
            for subject_id, meta in curriculum_service.SUPPORTED_SUBJECTS.items()
        ],
        "subjectActivity": list(activity.values()),
        "weakTopics": weak_topics[:10],
        "strengthTopics": [],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


class TopicNames:
    """What the curriculum calls each knowledge point a weak topic was counted under (#390).

    A knowledge point reaches the weak topics spelled however its row was
    written: the unit id a current attempt carries, the lesson an older one
    names, the bare topic id every practice mistake stores, the title an
    answer wrote in the language it was asked in, or the slug made of that
    title. Each spelling the curriculum knows resolves to the current unit,
    which is then named with the catalog's title in the reader's language.

    A topic id resolves to its unit when the topic has only one; otherwise it
    stays the topic, named by the topic's title. A name the curriculum does not
    know at all - one an answer wrote freely - is kept as written.
    """

    def __init__(self, catalog: Mapping[str, Any], locale: str) -> None:
        self.locale = locale
        self._units: dict[str, Mapping[str, Any]] = {
            str(row["id"]): row for row in _rows(catalog, "units") if row.get("id")
        }
        self._topics: dict[str, Mapping[str, Any]] = {
            str(row["id"]): row for row in _rows(catalog, "topics") if row.get("id")
        }
        self._lesson_units: dict[str, str] = {
            str(row["id"]): str(row["unitId"])
            for row in _rows(catalog, "lessons")
            if row.get("id") and str(row.get("unitId") or "") in self._units
        }
        units_of_topic: dict[str, list[str]] = defaultdict(list)
        for unit_id, row in self._units.items():
            units_of_topic[str(row.get("topicId") or "")].append(unit_id)
        self._aliases: dict[str, str] = {}
        # The first claim on a spelling wins: a unit's own names before the
        # names of what hangs under it, and those before a topic's.
        for unit_id, row in self._units.items():
            zap_title = knowledge_base_catalog.ZAP_UNITS.get(unit_id)
            self._claim(unit_id, unit_id, row.get("title"), *_every_title(unit_id))
            self._claim(unit_id, zap_title, _without_aside(zap_title))
        for skill_id, unit_id in curriculum_service.skill_unit_ids().items():
            if unit_id in self._units:
                self._claim(
                    unit_id,
                    skill_id,
                    curriculum_translations.SKILL_TITLES.get(skill_id),
                    *_every_title(skill_id),
                )
        for row in _rows(catalog, "lessons"):
            lesson_id = str(row.get("id") or "")
            if lesson_id in self._lesson_units:
                self._claim(
                    self._lesson_units[lesson_id], lesson_id, row.get("title"), *_every_title(lesson_id)
                )
        for topic_id, row in self._topics.items():
            units = units_of_topic.get(topic_id, [])
            target = units[0] if len(units) == 1 else topic_id
            self._claim(target, topic_id, row.get("title"), *_every_title(topic_id))

    def _claim(self, target: str, *spellings: object) -> None:
        for spelling in spellings:
            if isinstance(spelling, str) and spelling.strip():
                self._aliases.setdefault(normalize_topic_id(spelling), target)

    def resolve(self, *spellings: object, unit_id: object = None, lesson_id: object = None) -> str | None:
        """The unit (or, failing one, the topic) a row's spellings name, if the catalog knows it."""
        if isinstance(unit_id, str) and unit_id in self._units:
            return unit_id
        if isinstance(lesson_id, str) and lesson_id in self._lesson_units:
            return self._lesson_units[lesson_id]
        for spelling in spellings:
            if isinstance(spelling, str) and spelling.strip():
                found = self._aliases.get(normalize_topic_id(spelling))
                if found:
                    return found
        return None

    def name(self, *spellings: object, unit_id: object = None, lesson_id: object = None) -> str | None:
        """The catalog's name, in the reader's language, for what the spellings mean."""
        content_id = self.resolve(*spellings, unit_id=unit_id, lesson_id=lesson_id)
        if content_id is None:
            return None
        return _title(self._row(content_id))

    def key(
        self,
        subject_id: str,
        topic_id: str,
        label: str,
        *,
        unit_id: object = None,
        lesson_id: object = None,
    ) -> tuple[str, str, str]:
        """The weak topic a row counts under: (subject, id, label in the reader's language)."""
        content_id = self.resolve(topic_id, label, unit_id=unit_id, lesson_id=lesson_id)
        if content_id is None:
            return (subject_id, topic_id, label)
        row = self._row(content_id)
        return (_safe_subject(row.get("subjectId") or subject_id), content_id, _title(row) or label)

    def _row(self, content_id: str) -> Mapping[str, Any]:
        return self._units.get(content_id) or self._topics[content_id]


def _rows(catalog: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    return [row for row in catalog.get(key) or () if isinstance(row, Mapping)]


def _title(row: Mapping[str, Any]) -> str | None:
    title = row.get("title")
    return title if isinstance(title, str) and title.strip() else None


def _every_title(content_id: str) -> tuple[str, ...]:
    """A content id's translated titles: English, French and Italian."""
    return tuple(curriculum_translations.TITLE_TRANSLATIONS.get(content_id, {}).values())


def _without_aside(title: str | None) -> str | None:
    """A ZAP unit's import title without its bracketed aside, as the catalog shows it."""
    if not title:
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", title)


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
    return curriculum_service.counted_subject(subject)
