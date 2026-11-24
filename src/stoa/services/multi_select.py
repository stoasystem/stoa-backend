"""Choose-several exercises: the student picks a set of options (#593).

A `multi_select` exercise lists 2 to `MAX_OPTIONS` options - words, option
figures (`option_figures`), or hotspots in its figure - and its key is the set
of the right ones, `correct_options`: option numbers, 0 for the first. The set
is the same in every language; a translation translates the options and keeps
their order.

**Hotspots.** An element of the exercise's figure carrying `data-choice="B"`
is the second option drawn in the figure: the student may pick it there or in
the option list, it is the same option. The letter is the option's place, `A`
for the first, so one figure serves every language whatever the options say.
Each hotspot names an option, and each option has at most one hotspot.

**Answer.** The student sends the numbers of the options they picked, in any
order: `[0, 2]`. Not a list, empty, a number that is no option or the same one
twice is not an answer (`submitted_selection` raises `ValueError`). Right is
exactly the key's set - one missing, one extra or one wrong is wrong; there is
no partial credit, so a star, a quiz and a review count it like any other
exercise. The receipt records the picked options as the student read them.

**What is stored as `correct_answer`.** The right options in order, joined with
`; ` (`answer_text`): what a teacher's preview, the receipt's standard answer
and the publish check read, in the reader's language where the options are
translated. Judging never reads it.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from stoa.services import figure_svg
from stoa.services.curriculum_issues import Issue, IssueCode

#: The exercise type.
TYPE = "multi_select"
#: The stored field holding the key: the numbers of the right options.
FIELD = "correct_options"
#: Most options one exercise may list: one letter each, `A` to `L`.
MAX_OPTIONS = 12
#: How the right options are joined into one `correct_answer`.
SEPARATOR = "; "


def is_one(challenge: Mapping[str, Any]) -> bool:
    return challenge.get("type") == TYPE


def letter(index: int) -> str:
    """The hotspot letter of the option at `index`: `A` for the first."""
    return chr(ord("A") + index)


def _index(value: object) -> int | None:
    """An option number as authored or as read back from the table (a `Decimal`)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return None


def normalize_key(value: object) -> object:
    """The authored key in stored form: whole numbers as `int`, anything else as given,
    so the validation report can say what is wrong with it."""
    if not isinstance(value, list | tuple):
        return value
    indices = [_index(item) for item in value]
    if any(index is None for index in indices):
        return list(value)
    return indices


def correct_options(challenge: Mapping[str, Any]) -> list[int] | None:
    """The key: distinct option numbers in order, or `None` when it is not a valid one."""
    options = challenge.get("options")
    raw = challenge.get(FIELD)
    if not isinstance(options, list) or not isinstance(raw, list) or not raw:
        return None
    indices = [_index(item) for item in raw]
    if any(index is None or not 0 <= index < len(options) for index in indices):
        return None
    if len(set(indices)) != len(indices):
        return None
    return sorted(index for index in indices if index is not None)


def answer_text(options: list[Any], indices: list[int]) -> str:
    """The options at `indices`, in order, as one line: what `correct_answer` holds."""
    return SEPARATOR.join(str(options[index]) for index in sorted(indices))


def submitted_selection(raw: object, option_count: int) -> list[int]:
    """The option numbers a student sent, sorted; `ValueError` when it is not an answer."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("a multi_select answer is a non-empty list of option numbers")
    if any(type(item) is not int for item in raw):
        raise ValueError("a multi_select answer holds option numbers only")
    if any(not 0 <= item < option_count for item in raw):
        raise ValueError("a multi_select answer names an option the exercise does not have")
    if len(set(raw)) != len(raw):
        raise ValueError("a multi_select answer names an option twice")
    return sorted(raw)


def judge(selection: list[int], challenge: Mapping[str, Any]) -> bool:
    """Whether the picked set is exactly the key's set."""
    key = correct_options(challenge)
    return key is not None and set(selection) == set(key)


def issues(exercise: Mapping[str, Any]) -> list[tuple[str, Issue]]:
    """What is wrong with a `multi_select` exercise's options, key and hotspots.

    Options reading the same are reported by the caller, as for a one-choice
    exercise; a translation's option count by `exercise_localization`.
    """
    options = exercise.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return [("options", Issue.of(IssueCode.TOO_FEW_OPTIONS))]
    found: list[tuple[str, Issue]] = []
    if len(options) > MAX_OPTIONS:
        found.append(("options", Issue.of(IssueCode.TOO_MANY_OPTIONS, max_options=MAX_OPTIONS)))
    if correct_options(exercise) is None:
        found.append((FIELD, Issue.of(IssueCode.CORRECT_OPTIONS_INVALID)))
    stored = exercise.get("figure")
    found.extend(("figure", issue) for issue in _hotspot_issues(stored, len(options)))
    translations = exercise.get("translations")
    if isinstance(translations, Mapping):
        for locale, text in translations.items():
            if not isinstance(text, Mapping) or text.get("figure") in (None, ""):
                continue
            field = f"translations.{locale}.figure"
            found.extend((field, issue) for issue in _hotspot_issues(text["figure"], len(options)))
            if sorted(figure_svg.hotspots(text["figure"])) != sorted(figure_svg.hotspots(stored)):
                found.append((field, Issue.of(IssueCode.TRANSLATION_HOTSPOTS_MISMATCH)))
    return found


def _hotspot_issues(figure: object, option_count: int) -> list[Issue]:
    letters = {letter(index) for index in range(option_count)}
    found: list[Issue] = []
    seen: set[str] = set()
    for choice in figure_svg.hotspots(figure):
        if choice not in letters:
            found.append(Issue.of(IssueCode.HOTSPOT_NOT_AN_OPTION, choice=choice))
        elif choice in seen:
            found.append(Issue.of(IssueCode.HOTSPOT_REPEATED, choice=choice))
        seen.add(choice)
    return list(dict.fromkeys(found))


def stray_issues(exercise: Mapping[str, Any]) -> list[tuple[str, Issue]]:
    """A key or hotspots on an exercise of another type: only `multi_select` reads them."""
    found: list[tuple[str, Issue]] = []
    if exercise.get(FIELD) not in (None, []):
        found.append((FIELD, Issue.of(IssueCode.CORRECT_OPTIONS_WITHOUT_MULTI_SELECT)))
    figures = [("figure", exercise.get("figure"))]
    translations = exercise.get("translations")
    if isinstance(translations, Mapping):
        figures.extend(
            (f"translations.{locale}.figure", text.get("figure"))
            for locale, text in translations.items()
            if isinstance(text, Mapping)
        )
    found.extend(
        (field, Issue.of(IssueCode.HOTSPOT_WITHOUT_MULTI_SELECT))
        for field, figure in figures
        if figure_svg.hotspots(figure)
    )
    return found
