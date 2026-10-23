"""Exercises in the reader's language.

An exercise row holds its text in one language - German for the ZAP curriculum
and for the imported knowledge base. It may also carry `translations`: for a
locale, the prompt, options, answer, accepted answers and explanation in that
language. A reader sees the exercise in their locale where it has one and in its
stored language otherwise, and their answer is judged against that locale's key
and the stored one, so an option or answer written in the stored language still
counts after a reader switches language.

The stored row is never changed: its content hash and version cover the
translations as they are, so a localized copy is for showing and judging only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stoa.services import answer_judging

#: Locales an exercise can be translated into.
LOCALES = frozenset({"de", "en", "fr", "it"})
#: What one locale of an exercise holds, and the authoring aliases of each field.
TRANSLATION_FIELDS = {
    "prompt": "prompt",
    "options": "options",
    "choices": "options",
    "correct_answer": "correct_answer",
    "correctAnswer": "correct_answer",
    "answer_key": "correct_answer",
    "answerKey": "correct_answer",
    "accepted_answers": "accepted_answers",
    "acceptedAnswers": "accepted_answers",
    "explanation": "explanation",
}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_translations(value: object) -> dict[str, dict[str, Any]]:
    """An authored `translations` mapping in stored form; what is not a locale's text is left out."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for locale, raw in value.items():
        if not isinstance(raw, Mapping):
            continue
        text: dict[str, Any] = {}
        for source, target in TRANSLATION_FIELDS.items():
            if source not in raw or target in text:
                continue
            if target in {"options", "accepted_answers"}:
                items = raw[source] if isinstance(raw[source], list | tuple) else []
                text[target] = [_text(item) for item in items if _text(item)]
            else:
                text[target] = _text(raw[source])
        if text:
            out[_text(locale).lower()] = text
    return out


def localized(challenge: Mapping[str, Any], locale: str) -> dict[str, Any]:
    """A copy of the exercise as a reader in `locale` sees and answers it."""
    shown = dict(challenge)
    translations = challenge.get("translations")
    text = translations.get(locale) if isinstance(translations, Mapping) else None
    if not isinstance(text, Mapping):
        return shown
    for field in ("prompt", "explanation"):
        if _text(text.get(field)):
            shown[field] = text[field]
    options, stored_options = text.get("options"), challenge.get("options")
    if isinstance(options, list) and isinstance(stored_options, list) and len(options) == len(stored_options):
        shown["options"] = list(options)
    key = _text(text.get("correct_answer"))
    if key:
        stored_key = challenge.get("correct_answer", challenge.get("answer_key"))
        also = [*_list(text.get("accepted_answers")), _text(stored_key),
                *answer_judging.accepted_answers(challenge)]
        shown["correct_answer"] = shown["answer_key"] = key
        shown["accepted_answers"] = [item for item in dict.fromkeys(also) if item and item != key]
    return shown


def _list(value: object) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def translation_issues(exercise: Mapping[str, Any], *, max_text: int) -> list[tuple[str, str]]:
    """What is wrong with an exercise's translations, as (field, message) pairs."""
    translations = exercise.get("translations")
    if translations in (None, {}):
        return []
    if not isinstance(translations, Mapping):
        return [("translations", "Translations must map a locale to its text.")]
    issues: list[tuple[str, str]] = []
    options = exercise.get("options") if isinstance(exercise.get("options"), list) else None
    stored_key = _text(exercise.get("correct_answer", exercise.get("answer_key")))
    key_index = options.index(stored_key) if options and stored_key in options else None
    for locale, text in translations.items():
        field = f"translations.{locale}"
        if locale not in LOCALES:
            issues.append((field, f"Unsupported locale '{locale}'."))
            continue
        if not isinstance(text, Mapping) or not _text(text.get("prompt")):
            issues.append((field, "A translation needs its prompt."))
            continue
        too_long = [
            name for name in ("prompt", "explanation", "correct_answer")
            if len(_text(text.get(name))) > max_text
        ]
        if too_long:
            issues.append((field, f"Too long: {', '.join(too_long)}."))
        if options is not None:
            translated = text.get("options")
            if not isinstance(translated, list) or len(translated) != len(options):
                issues.append((field, "A translation needs one option for each option."))
            elif key_index is not None and _text(text.get("correct_answer")) != _text(translated[key_index]):
                issues.append((field, "The translated answer must be the translated right option."))
        elif stored_key and not _text(text.get("correct_answer")):
            issues.append((field, "A translation needs its answer."))
        accepted = text.get("accepted_answers") or []
        if len(accepted) > answer_judging.MAX_ACCEPTED_ANSWERS or any(
            len(_text(item)) > answer_judging.MAX_ACCEPTED_ANSWER_LENGTH for item in accepted
        ):
            issues.append((field, "Too many or too long accepted answers."))
    return issues
