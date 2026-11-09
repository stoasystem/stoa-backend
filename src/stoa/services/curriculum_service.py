"""Curriculum catalog projections built from existing practice content, and
the one entry point for subject ids (#354): the alias table, the supported
subjects, and how a subject is read, compared and refused."""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.services import practice_projection_service
from stoa.services import curriculum_translations
from stoa.services.curriculum_translations import translated_title
from stoa.services.practice_errors import PracticeErrorCode, PracticeViolation

# ── Subject ids ───────────────────────────────────────────────────────────
#
# The one place a subject id is read (#317, #354). `math` is canonical: every
# response, profile and conversation says it. The content rows keep the key
# they were seeded with (`mathematics`), and the progress and answer rows copy
# it, so stored values are normalised when read rather than migrated.

# Every subject the platform teaches, with its rollout mark and how the answer
# model is told to treat it.
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

# Other spellings of a supported subject, lowercased. Matched after trimming
# and lowercasing, so `Mathematik` and ` MATHEMATICS ` are found here too.
_SUBJECT_ALIASES = {
    "mathematics": "math",
    "mathematik": "math",
    "physik": "physics",
    "deutsch": "german",
    "englisch": "english",
}


def subject_id(value: object) -> str | None:
    """The canonical id of a subject the platform teaches, else None.

    Nothing unknown is guessed: `chemistry`, a blank or a number is None, not
    `math`. A caller that has to have a subject refuses (`require_subject`);
    one that only compares uses `subject_key`.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    text = _SUBJECT_ALIASES.get(text, text)
    return text if text in SUPPORTED_SUBJECTS else None


def subject_key(value: object) -> str:
    """What two subject values are compared by: the canonical id when known,
    else the stored text trimmed and lowercased, so an unknown value still
    matches only itself."""
    return subject_id(value) or str(value if value is not None else "").strip().lower()


def readable_subject(stored: object) -> str:
    """A stored subject as a client reads it back: the canonical id, else the
    stored text unchanged, so a value written before writes were checked can
    still be seen and corrected."""
    return subject_id(stored) or str(stored if stored is not None else "")


def counted_subject(stored: object) -> str:
    """The subject a stored record is counted under in learning aggregates:
    the canonical id, with no subject and an unknown one counted as math.

    Only for tallies over old records (weak topics, activity, memory), where a
    record has to land in some bucket and math is the subject the platform
    teaches in full. Nothing a client writes and no prompt goes through here.
    """
    return subject_id(stored) or "math"


def same_subject(stored: object, requested: object) -> bool:
    return subject_key(stored) == subject_key(requested)


def require_subject(value: object, *, field: str) -> str:
    """The canonical id of a subject a client is writing; anything else is
    refused with `subject_unknown`, naming the request field."""
    canonical = subject_id(value)
    if canonical is None:
        raise PracticeViolation(PracticeErrorCode.SUBJECT_UNKNOWN, fields=[field])
    return canonical


def require_subjects(values: Iterable[object], *, field: str) -> list[str]:
    """Each subject of a list a client is writing, canonical and each once."""
    return list(dict.fromkeys(require_subject(value, field=field) for value in values))


VISIBLE_STATES = {"active"}
PREVIEW_ROLES = {"admin", "teacher"}


def list_catalog(
    *,
    subject_id: str | None = None,
    grade_level: str | None = None,
    rollout_state: str | None = None,
    include_preview: bool = False,
    locale: str = "de",
) -> dict[str, Any]:
    subjects = [
        _build_subject(subject, locale)
        for subject in sorted(practice_repo.get_subjects(), key=lambda item: _as_int(item.get("order", 0)))
        if _subject_matches(subject, subject_id, grade_level)
        and _matches_state(subject, rollout_state, include_preview)
        and subject_key(subject.get("subject_id", "")) in SUPPORTED_SUBJECTS
    ]
    topics = [
        _build_topic(topic, locale)
        for topic in sorted(practice_repo.get_topics(subject_id), key=lambda item: _as_int(item.get("order", 0)))
        if _topic_matches(topic, subject_id, grade_level) and _matches_state(topic, rollout_state, include_preview)
    ]
    units = [
        _build_unit(unit, locale)
        for unit in sorted(_all_units(topics), key=lambda item: (subject_key(item.get("subject_id", "")), item.get("topic_id", ""), _as_int(item.get("order", 0))))
        if _matches_state(unit, rollout_state, include_preview)
    ]
    lessons = [
        _build_lesson(lesson, exercise_count=_exercise_count(lesson, include_preview), locale=locale)
        for lesson in sorted(practice_repo.get_lessons(), key=lambda item: (item.get("topic_id", ""), item.get("unit_id", ""), _as_int(item.get("order", 0))))
        if _lesson_matches(lesson, subject_id, grade_level) and _matches_state(lesson, rollout_state, include_preview)
    ]

    return {
        "subjects": subjects,
        "topics": topics,
        "units": units,
        "lessons": lessons,
        "rolloutSubjects": sorted(SUPPORTED_SUBJECTS),
        "includePreview": include_preview,
        "source": "practice_backfill",
    }


def get_lesson_detail(
    lesson_id: str,
    *,
    include_preview: bool = False,
    locale: str = "de",
) -> dict[str, Any] | None:
    lesson = practice_repo.get_lesson(lesson_id)
    if not lesson or not _is_visible(lesson, include_preview):
        return None

    exercises = [
        practice_projection_service.build_exercise_preview(exercise, locale)
        for exercise in _active_exercises_for_lesson(lesson_id, include_preview)
    ]
    return practice_projection_service.build_curriculum_lesson_preview(lesson, exercises, locale=locale)


def list_exercises(
    *,
    lesson_id: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
    difficulty: str | None = None,
    rollout_state: str | None = None,
    include_preview: bool = False,
    locale: str = "de",
) -> dict[str, Any]:
    raw_items = practice_repo.get_all_challenges(lesson_id=lesson_id, subject_id=subject_id, topic_id=topic_id)
    items = [
        practice_projection_service.build_exercise_preview(item, locale)
        for item in sorted(raw_items, key=lambda challenge: (challenge.get("lesson_id", ""), _as_int(challenge.get("order", 0))))
        if _matches_state(item, rollout_state, include_preview)
        and (difficulty is None or str(item.get("difficulty", "")).lower() == difficulty.lower())
    ]
    return {"items": items, "count": len(items)}


def skill_unit_ids(*, subject_id: str | None = None) -> dict[str, str]:
    """Every skill in the vocabulary mapped to the one unit it hangs under (#58).

    A skill claimed by two units is refused rather than resolved: merging the
    per-subject maps would silently keep the last one, and the star map would
    then draw the same skill point under two stars.
    """
    found: dict[str, str] = {}
    for subject, skills in curriculum_translations.SKILL_UNITS.items():
        if subject_id and subject_key(subject) != subject_key(subject_id):
            continue
        for skill_id, unit_id in skills.items():
            if found.get(skill_id, unit_id) != unit_id:
                raise ValueError(f"skill {skill_id} is declared under more than one unit")
            found[skill_id] = unit_id
    return found


def list_skills(*, subject_id: str | None = None, locale: str = "de") -> dict[str, Any]:
    """The skill vocabulary, named in the requested locale."""
    items = [
        {
            "id": skill_id,
            "subjectId": subject_key(subject),
            "unitId": unit_id,
            "name": curriculum_translations.skill_title(skill_id, locale),
        }
        for subject, skills in curriculum_translations.SKILL_UNITS.items()
        if not subject_id or subject_key(subject) == subject_key(subject_id)
        for skill_id, unit_id in skills.items()
    ]
    return {"items": items, "count": len(items)}


def skill_ids_by_unit(*, subject_id: str | None = None) -> dict[str, list[str]]:
    """The skills each unit owns, in vocabulary order."""
    by_unit: dict[str, list[str]] = {}
    for skill_id, unit_id in skill_unit_ids(subject_id=subject_id).items():
        by_unit.setdefault(unit_id, []).append(skill_id)
    return by_unit


def can_preview(user: dict[str, Any]) -> bool:
    return str(user.get("role", "")).lower() in PREVIEW_ROLES


def _all_units(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for topic in topics:
        units.extend(practice_repo.get_units(topic["id"]))
    return units


def _exercise_count(lesson: dict[str, Any], include_preview: bool) -> int:
    """From the lesson's own exercise index where it has one; a preview reader also
    sees exercises not yet live, which only the challenge rows know of."""
    index = practice_repo.indexed_exercises(lesson)
    if index is not None and not include_preview:
        return len(index)
    return len(_active_exercises_for_lesson(lesson["lesson_id"], include_preview))


def _active_exercises_for_lesson(lesson_id: str, include_preview: bool) -> list[dict[str, Any]]:
    return [
        challenge
        for challenge in practice_repo.get_challenges(lesson_id)
        if _is_visible(challenge, include_preview)
    ]


def _build_subject(raw: dict[str, Any], locale: str = "de") -> dict[str, Any]:
    name = raw.get("name", raw["subject_id"].title())
    return {
        "id": subject_key(raw["subject_id"]),
        "name": translated_title(raw["subject_id"], name, locale),
        "description": raw.get("description", ""),
        "gradeLevels": raw.get("grade_levels", []),
        "language": raw.get("language", _subject_language(raw["subject_id"])),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
    }


def _build_topic(raw: dict[str, Any], locale: str = "de") -> dict[str, Any]:
    title = raw.get("title", raw["topic_id"])
    return {
        "id": raw["topic_id"],
        "subjectId": subject_key(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "title": translated_title(raw["topic_id"], title, locale),
        "description": raw.get("description", ""),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
        **_placement(raw, "radius"),
    }


def _placement(raw: dict[str, Any], *extra: str) -> dict[str, Any]:
    """The offline layout's coordinates, when the row has been given them (#60).

    Absent until the layout script has run, and the read model falls back to
    its own arrangement — so a row without them is not an error, it is a map
    that has not been laid out yet.
    """
    placed: dict[str, Any] = {}
    for key in ("x", "y", *extra):
        value = raw.get(key)
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            placed[key] = float(value)
    version = raw.get("layout_version")
    if isinstance(version, str) and version:
        placed["layoutVersion"] = version
    return placed


def _build_unit(raw: dict[str, Any], locale: str = "de") -> dict[str, Any]:
    title = raw.get("title", raw["unit_id"])
    return {
        "id": raw["unit_id"],
        "subjectId": subject_key(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "topicId": raw["topic_id"],
        "title": translated_title(raw["unit_id"], title, locale),
        "description": raw.get("description", ""),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
        "prerequisiteUnitIds": _prerequisite_unit_ids(raw),
        **_placement(raw),
    }


def _prerequisite_unit_ids(raw: dict[str, Any]) -> list[str]:
    value = raw.get("prerequisite_unit_ids")
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def get_prerequisites(subject_id: str) -> dict[str, list[str]]:
    """The unit prerequisite graph of one subject, one entry per unit of that subject."""
    subject = subject_key(subject_id)
    return {
        str(unit.get("unit_id") or ""): _prerequisite_unit_ids(unit)
        for unit in curriculum_ops_repo.list_practice_units()
        if subject_key(str(unit.get("subject_id") or "")) == subject
        and str(unit.get("unit_id") or "")
    }


def _build_lesson(raw: dict[str, Any], *, exercise_count: int, locale: str = "de") -> dict[str, Any]:
    title = raw.get("title", raw["lesson_id"])
    return {
        "id": raw["lesson_id"],
        "subjectId": subject_key(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "unitId": raw.get("unit_id", ""),
        "topicId": raw["topic_id"],
        "title": translated_title(raw["lesson_id"], title, locale),
        "objective": raw.get("objective", raw.get("description", "")),
        "difficulty": raw.get("difficulty", "practice"),
        "estimatedMinutes": _as_int(raw.get("estimated_minutes", 10)),
        "rolloutState": _content_state(raw),
        "exerciseCount": exercise_count,
        "source": raw.get("source", "practice_backfill"),
        **_readiness(raw),
    }


def _readiness(raw: dict[str, Any]) -> dict[str, Any]:
    """A lesson that only deepens its unit, and the knowledge points that come
    before it; absent on a lesson that states neither."""
    out: dict[str, Any] = {}
    if raw.get("extension"):
        out["extension"] = True
    points = [str(item) for item in raw.get("requires_points") or () if str(item).strip()]
    if points:
        out["requiresPoints"] = points
    return out


def _build_exercise(raw: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper; student curriculum projections are always answer-free."""
    return practice_projection_service.build_exercise_preview(raw)


def _subject_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and subject_key(raw.get("subject_id", "")) != subject_key(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _topic_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and subject_key(raw.get("subject_id", "")) != subject_key(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _lesson_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and subject_key(raw.get("subject_id", "")) != subject_key(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _grade_matches(raw: dict[str, Any], grade_level: str | None) -> bool:
    if not grade_level:
        return True
    grade_values = raw.get("grade_levels") or [raw.get("grade_level", raw.get("grade_band", ""))]
    return grade_level in grade_values


def visible_to_students(raw: dict[str, Any]) -> bool:
    """Whether the student catalog shows this subject, topic, unit or lesson row:
    not archived, not in preview."""
    return _is_visible(raw, include_preview=False)


def _is_visible(raw: dict[str, Any], include_preview: bool) -> bool:
    state = _content_state(raw)
    return include_preview or state in VISIBLE_STATES


def _matches_state(raw: dict[str, Any], rollout_state: str | None, include_preview: bool) -> bool:
    if not _is_visible(raw, include_preview):
        return False
    return rollout_state is None or _content_state(raw) == rollout_state.lower()


def _content_state(raw: dict[str, Any]) -> str:
    """The rollout state of a content row, read the same way the practice projection reads it.

    The seeded topics carry `status: "available"`, the practice domain's
    student-facing availability; read as a rollout state it hid every seeded topic,
    and every unit under them, from the student catalog while `includePreview`
    showed all five. A lifecycle `status` (`draft`, `archived`) still hides a row.
    """
    return practice_projection_service.content_state(raw)


def _subject_language(subject_id: str) -> str:
    subject = subject_key(subject_id)
    if subject == "german":
        return "de"
    if subject == "english":
        return "en"
    return "neutral"


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    return int(value)
