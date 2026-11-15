"""错因: why a wrong answer was wrong (#452, vocabulary in CONTEXT.md).

A cause is one of four categories - structural (the concept is not built),
deviation (knows it, got it wrong), application (fails once the setting
changes), metacognitive (does not know they do not know) - and, when it is
known, the misconception it stands for: one sentence in each locale.

Causes come from authoring, never from a model: each wrong option of a choice
exercise may carry one (`option_error_causes`, one entry per option, `None`
where an option has none). A wrong answer that picks a tagged option records
that cause on its receipt; every other wrong answer records `unclassified`.

Stored forms:

* on the exercise, `option_error_causes`: ``[None | {"category", "misconception": {locale: text}}]``
* on the receipt, `error_cause`: the picked option's cause, or ``{"category": "unclassified"}``
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stoa.services import answer_judging
from stoa.services.curriculum_issues import Issue, IssueCode

#: The categories an author may tag a distractor with.
CATEGORIES: tuple[str, ...] = ("structural", "deviation", "application", "metacognitive")
#: What a wrong answer records when nothing tagged explains it. Never authored.
UNCLASSIFIED = "unclassified"
#: Every misconception is written in each of these.
LOCALES: tuple[str, ...] = ("de", "en", "fr", "it")
#: One sentence, not an explanation.
MAX_MISCONCEPTION_LENGTH = 300

#: The authoring names of the exercise field.
FIELD = "option_error_causes"
ALIASES = ("option_error_causes", "optionErrorCauses")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def authored(exercise: Mapping[str, Any]) -> object:
    """The causes as the author wrote them, under either name; `None` when absent."""
    for name in ALIASES:
        if exercise.get(name) is not None:
            return exercise[name]
    return None


def normalize(value: object) -> list[dict[str, Any] | None] | object:
    """Authored causes in stored form; empty when no option carries one.

    A list is kept one entry per option, so it still lines up with the options;
    an entry that names no category becomes `None`. What is not a list is
    returned as it is, for validation to report.
    """
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        return value
    causes: list[dict[str, Any] | None] = []
    for raw in value:
        if not isinstance(raw, Mapping) or not _text(raw.get("category")):
            causes.append(None)
            continue
        cause: dict[str, Any] = {"category": _text(raw.get("category")).lower()}
        misconception = raw.get("misconception")
        if isinstance(misconception, Mapping):
            cause["misconception"] = {
                _text(locale).lower(): _text(text)
                for locale, text in misconception.items()
                if _text(text)
            }
        elif misconception is not None:
            cause["misconception"] = misconception
        causes.append(cause)
    return causes if any(causes) else []


def issues(exercise: Mapping[str, Any]) -> list[tuple[str, Issue]]:
    """What is wrong with an exercise's stored causes, as (field, issue) pairs.

    One cause per option, never on the right option, from the four categories,
    with its misconception in every locale.
    """
    causes = exercise.get(FIELD)
    if causes in (None, []):
        return []
    options = exercise.get("options")
    if (
        exercise.get("type") != "multiple_choice"
        or not isinstance(causes, list)
        or not isinstance(options, list)
        or len(causes) != len(options)
    ):
        return [(FIELD, Issue.of(IssueCode.OPTION_ERROR_CAUSES_MISMATCH))]
    key = answer_judging.normalize_answer(
        exercise.get("correct_answer", exercise.get("answer_key")) or ""
    )
    found: list[tuple[str, Issue]] = []
    for index, (option, cause) in enumerate(zip(options, causes, strict=True)):
        if cause is None:
            continue
        field = f"{FIELD}[{index}]"
        if key and answer_judging.normalize_answer(option) == key:
            found.append((field, Issue.of(IssueCode.ERROR_CAUSE_ON_ANSWER)))
            continue
        if not isinstance(cause, Mapping):
            found.append((field, Issue.of(IssueCode.OPTION_ERROR_CAUSES_MISMATCH)))
            continue
        category = _text(cause.get("category"))
        if category not in CATEGORIES:
            found.append(
                (f"{field}.category", Issue.of(IssueCode.ERROR_CAUSE_CATEGORY_UNKNOWN, category=category))
            )
        misconception = cause.get("misconception")
        written = misconception if isinstance(misconception, Mapping) else {}
        missing = [
            locale
            for locale in LOCALES
            if not _text(written.get(locale))
            or len(_text(written.get(locale))) > MAX_MISCONCEPTION_LENGTH
        ]
        if missing:
            found.append(
                (
                    f"{field}.misconception",
                    Issue.of(IssueCode.ERROR_CAUSE_MISCONCEPTION_MISSING, locales=", ".join(missing)),
                )
            )
    return found


def _valid(cause: object) -> dict[str, Any] | None:
    """A stored cause as a receipt keeps it, or `None` when it is not a whole one."""
    if not isinstance(cause, Mapping) or cause.get("category") not in CATEGORIES:
        return None
    misconception = cause.get("misconception")
    if not isinstance(misconception, Mapping) or not all(
        _text(misconception.get(locale)) for locale in LOCALES
    ):
        return None
    return {
        "category": cause["category"],
        "misconception": {locale: _text(misconception[locale]) for locale in LOCALES},
    }


def of_wrong_answer(
    challenge: Mapping[str, Any], shown: Mapping[str, Any], answer: object
) -> dict[str, Any]:
    """The cause a wrong answer records: the picked option's, else unclassified.

    The answer is matched to an option the way it was judged - against the
    option as the reader saw it and as it is stored, so an answer written in
    the stored language still finds its option after a switch of language.
    """
    causes = challenge.get(FIELD)
    stored = challenge.get("options")
    seen = shown.get("options")
    if isinstance(causes, list) and isinstance(stored, list) and len(causes) == len(stored) and answer:
        picked = answer_judging.normalize_answer(answer if isinstance(answer, str) else "|".join(answer))
        for index, cause in enumerate(causes):
            writings = [stored[index]]
            if isinstance(seen, list) and len(seen) == len(stored):
                writings.append(seen[index])
            if any(answer_judging.normalize_answer(text) == picked for text in writings):
                valid = _valid(cause)
                if valid is not None:
                    return valid
                break
    return {"category": UNCLASSIFIED}
