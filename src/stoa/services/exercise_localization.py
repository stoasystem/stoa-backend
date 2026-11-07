"""Exercises in the reader's language.

An exercise row holds its text - and its figure, if it has one - in one language - German for the ZAP curriculum
and for the imported knowledge base. It may also carry `translations`: for a
locale, the prompt, options, answer, accepted answers, explanation and the
feedback for a right and a wrong answer in that language. A reader sees the
exercise in their locale where it has one and in its stored language otherwise,
and their answer is judged against that locale's key and the stored one, so an option or answer written in the stored language still
counts after a reader switches language.

The stored row is never changed: its content hash and version cover the
translations as they are, so a localized copy is for showing and judging only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stoa.services import answer_judging, figure_svg
from stoa.services.curriculum_issues import Issue, IssueCode

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
    "figure": "figure",
    "option_figures": "option_figures",
    "optionFigures": "option_figures",
    "correct_feedback": "correct_feedback",
    "correctFeedback": "correct_feedback",
    "incorrect_feedback": "incorrect_feedback",
    "incorrectFeedback": "incorrect_feedback",
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
            if target == "option_figures":
                items = raw[source] if isinstance(raw[source], list | tuple) else []
                text[target] = [_text(item) for item in items]
            elif target in {"options", "accepted_answers"}:
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
    for field in ("prompt", "explanation", "figure", "correct_feedback", "incorrect_feedback"):
        if _text(text.get(field)):
            shown[field] = text[field]
    options, stored_options = text.get("options"), challenge.get("options")
    if isinstance(options, list) and isinstance(stored_options, list) and len(options) == len(stored_options):
        shown["options"] = list(options)
    figures, stored_figures = text.get("option_figures"), challenge.get("option_figures")
    if isinstance(figures, list) and isinstance(stored_figures, list) and len(figures) == len(stored_figures):
        shown["option_figures"] = list(figures)
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


def figure_issues(exercise: Mapping[str, Any], options: list | None) -> list[Issue]:
    """What is wrong with the figure and the option figures of an exercise or of
    one of its translations."""
    issues: list[Issue] = []
    figure = exercise.get("figure")
    if figure not in (None, ""):
        issues.extend(figure_svg.figure_issues(figure))
    option_figures = exercise.get("option_figures")
    if option_figures not in (None, []):
        if not isinstance(option_figures, list) or options is None or len(option_figures) != len(options):
            issues.append(Issue.of(IssueCode.OPTION_FIGURES_MISMATCH))
        else:
            for item in option_figures:
                if _text(item):
                    issues.extend(figure_svg.figure_issues(item))
    return list(dict.fromkeys(issues))


def translation_issues(exercise: Mapping[str, Any], *, max_text: int) -> list[tuple[str, Issue]]:
    """What is wrong with an exercise's translations, as (field, issue) pairs."""
    translations = exercise.get("translations")
    if translations in (None, {}):
        return []
    if not isinstance(translations, Mapping):
        return [("translations", Issue.of(IssueCode.TRANSLATIONS_NOT_A_MAP))]
    issues: list[tuple[str, Issue]] = []
    options = exercise.get("options") if isinstance(exercise.get("options"), list) else None
    stored_key = _text(exercise.get("correct_answer", exercise.get("answer_key")))
    key_index = options.index(stored_key) if options and stored_key in options else None
    for locale, text in translations.items():
        field = f"translations.{locale}"
        if locale not in LOCALES:
            issues.append((field, Issue.of(IssueCode.TRANSLATION_LOCALE_UNSUPPORTED, language=locale)))
            continue
        if not isinstance(text, Mapping) or not _text(text.get("prompt")):
            issues.append((field, Issue.of(IssueCode.TRANSLATION_PROMPT_MISSING)))
            continue
        too_long = [
            name for name in ("prompt", "explanation", "correct_answer")
            if len(_text(text.get(name))) > max_text
        ]
        if too_long:
            issues.append((field, Issue.of(IssueCode.TRANSLATION_TOO_LONG, fields=", ".join(too_long))))
        if options is not None:
            translated = text.get("options")
            if not isinstance(translated, list) or len(translated) != len(options):
                issues.append((field, Issue.of(IssueCode.TRANSLATION_OPTIONS_MISMATCH)))
            elif key_index is not None and _text(text.get("correct_answer")) != _text(translated[key_index]):
                issues.append((field, Issue.of(IssueCode.TRANSLATION_ANSWER_NOT_THE_OPTION)))
        elif stored_key and not _text(text.get("correct_answer")):
            issues.append((field, Issue.of(IssueCode.TRANSLATION_ANSWER_MISSING)))
        issues.extend((field, issue) for issue in figure_issues(text, options))
        accepted = text.get("accepted_answers") or []
        if len(accepted) > answer_judging.MAX_ACCEPTED_ANSWERS or any(
            len(_text(item)) > answer_judging.MAX_ACCEPTED_ANSWER_LENGTH for item in accepted
        ):
            issues.append((field, Issue.of(IssueCode.ACCEPTED_ANSWERS_OUT_OF_BOUNDS)))
    return issues
