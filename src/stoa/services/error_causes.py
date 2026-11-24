"""错因: why a wrong answer was wrong (#452, vocabulary in CONTEXT.md).

A cause is one of four categories - structural (the concept is not built),
deviation (knows it, got it wrong), application (fails once the setting
changes), metacognitive (does not know they do not know) - and, when it is
known, the misconception it stands for: one sentence in each locale.

Causes come from authoring or from fixed rules, never from a model:

* each wrong option of a choice exercise may carry one (`option_error_causes`,
  one entry per option, `None` where an option has none), and a wrong answer
  that picks a tagged option records that cause on its receipt (#452);
* a wrong typed answer (any exercise that is not a choice) is compared with
  the key by the rules in `infer` (#453): the same number with the other sign,
  a number very close to the key, or the key's value as a fraction not reduced
  (#565), is a deviation, with the rule's fixed misconception sentence from the
  message catalog (`error_cause.<rule>`). The student is told the rule's own
  line instead (`practice.feedback.<rule>`, read by `typed_rule`'s callers): the
  misconception is written about the student, for a teacher.

Every other wrong answer records `unclassified`.

Stored forms:

* on the exercise, `option_error_causes`: ``[None | {"category", "misconception": {locale: text}}]``
* on the receipt, `error_cause`: the picked option's cause, a rule's cause, or
  ``{"category": "unclassified"}``
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from fractions import Fraction
from math import gcd
import re
from typing import Any

from stoa.services import answer_judging, message_catalog
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


# ── rules for typed answers (#453) ───────────────────────────────────────────

#: The answer is the key's number with the other sign: `5` for `-5`.
RULE_SIGN = "sign"
#: The answer's number is very close to the key's: see `_close`.
RULE_CLOSE = "close"
#: The answer is the key's value as a fraction that is not reduced: `48/72`
#: for `2/3`. See `_unreduced`.
RULE_UNREDUCED = "unreduced"
#: In the order they are tried; the first that explains the answer wins.
RULES: tuple[str, ...] = (RULE_SIGN, RULE_CLOSE, RULE_UNREDUCED)

#: How far, relative to the key, a number may be off and still count as close:
#: 2 % takes a rounding slip (3.1 for 3.14) or a slip in the last digit of a
#: larger number (98 for 100), and leaves a guess in the neighbourhood (97 for
#: 100, 3 for 3.14) unexplained. Conservative on purpose: a cause recorded
#: wrongly misleads the teacher, an unclassified one only says nothing.
CLOSE_RELATIVE_ERROR = Decimal("0.02")
#: A whole number off by exactly one is a slipped calculation step (57 for
#: 7 · 8) - but only from this size of key up; under it, 4 for 5 is as likely
#: a different answer as a slip.
CLOSE_OFF_BY_ONE_FROM = Decimal(10)


def rule_cause(rule: str) -> dict[str, Any]:
    """The cause a rule records: a deviation, with the rule's sentence in every locale."""
    sentences = message_catalog.TEXT[f"error_cause.{rule}"]
    return {
        "category": "deviation",
        "misconception": {locale: sentences[locale] for locale in LOCALES},
    }


def _whole(number: Decimal) -> bool:
    return number == number.to_integral_value()


def _close(given: Decimal, expected: Decimal) -> bool:
    """Not the key, the same sign, and within `CLOSE_RELATIVE_ERROR` or off by one."""
    if given == expected or expected == 0 or (given < 0) != (expected < 0):
        return False
    off = abs(given - expected)
    if off <= CLOSE_RELATIVE_ERROR * abs(expected):
        return True
    return (
        off == 1
        and _whole(given)
        and _whole(expected)
        and abs(expected) >= CLOSE_OFF_BY_ONE_FROM
    )


def _matches(rule: str, given: Decimal, expected: Decimal) -> bool:
    if rule == RULE_SIGN:
        return expected != 0 and given == -expected
    return _close(given, expected)


# A fraction in a normalized answer, its minus kept only where that cannot be
# an operator, as `answer_judging` reads a signed number.
_FRACTION = re.compile(r"(?<![\w./])(-?)(\d+)/(\d+)(?![\w./])")


def _single_fraction(value: str) -> tuple[str, Fraction, int] | None:
    """An answer holding one fraction and no other number: the text around it,
    its value, and the common divisor of its numerator and denominator."""
    text = answer_judging.normalize_answer(value)
    found = list(_FRACTION.finditer(text))
    if len(found) != 1:
        return None
    match = found[0]
    around = f"{text[: match.start()]}#{text[match.end() :]}"
    numerator, denominator = int(match.group(2)), int(match.group(3))
    if any(character.isdigit() for character in around) or denominator == 0:
        return None
    sign = -1 if match.group(1) else 1
    return around, Fraction(sign * numerator, denominator), gcd(numerator, denominator)


def _reduced_key(key: str) -> tuple[str, Fraction] | None:
    """A key that is a reduced fraction or a whole number: its text around, its value."""
    fraction = _single_fraction(key)
    if fraction is not None:
        return (fraction[0], fraction[1]) if fraction[2] == 1 else None
    number = answer_judging.single_number(key)
    if number is None or not _whole(number[1]):
        return None
    return number[0], Fraction(int(number[1]))


def _unreduced(answer: str, keys: list[str]) -> bool:
    """A fraction with the value of a key that is reduced (or whole), itself not
    reduced, written with the same text around: `x = 4/6` for `x = 2/3`, `6/2`
    for `3`. A key that is itself not reduced is left alone: the author wanted
    that form, and "reduce it" would be wrong."""
    given = _single_fraction(answer)
    if given is None or given[2] == 1:
        return False
    return any(
        expected is not None and expected == (given[0], given[1])
        for expected in (_reduced_key(key) for key in keys)
    )


def rule_of(answer: object, keys: Iterable[object]) -> str | None:
    """The rule that explains a wrong typed answer, else `None`.

    The answer and each writing of the key must each hold one number, read the
    way judging reads it (`answer_judging.single_number`), with the same text
    around it: `x = 5` is compared with `x = -5`, never with `-5` or `5 cm`.
    The fraction rule reads one fraction the same way (`_unreduced`).
    """
    if not isinstance(answer, str):
        return None
    texts = [key for key in keys if isinstance(key, str)]
    given = answer_judging.single_number(answer)
    if given is not None:
        expected = [
            found[1]
            for found in (answer_judging.single_number(key) for key in texts)
            if found is not None and found[0] == given[0]
        ]
        for rule in (RULE_SIGN, RULE_CLOSE):
            if any(_matches(rule, given[1], number) for number in expected):
                return rule
    if _unreduced(answer, texts):
        return RULE_UNREDUCED
    return None


def infer(answer: object, keys: Iterable[object]) -> dict[str, Any] | None:
    """The cause a rule finds for a wrong typed answer (`rule_of`), else `None`."""
    rule = rule_of(answer, keys)
    return None if rule is None else rule_cause(rule)


def _keys(*exercises: Mapping[str, Any]) -> list[object]:
    keys: list[object] = []
    for exercise in exercises:
        keys.append(exercise.get("correct_answer", exercise.get("answer_key")))
        keys.extend(answer_judging.accepted_answers(exercise))
    return keys


def typed_rule(
    challenge: Mapping[str, Any], shown: Mapping[str, Any], answer: object
) -> str | None:
    """The rule that explains a wrong answer to a typed exercise, else `None`.

    A choice exercise has none: its causes are authored on the options, and a
    choose-several one (`multi_select`, #593) gets no cause per option yet. The
    key is read as the reader saw it and as it is stored, as in `of_wrong_answer`.
    """
    if challenge.get("type") in {"multiple_choice", "multi_select"}:
        return None
    return rule_of(answer, _keys(shown, challenge))


def of_wrong_answer(
    challenge: Mapping[str, Any], shown: Mapping[str, Any], answer: object
) -> dict[str, Any]:
    """The cause a wrong answer records: the picked option's, a rule's, else unclassified.

    The answer is matched to an option the way it was judged - against the
    option as the reader saw it and as it is stored, so an answer written in
    the stored language still finds its option after a switch of language.
    A typed answer is compared by the rules with the key the same two ways.
    """
    if challenge.get("type") != "multiple_choice":
        rule = typed_rule(challenge, shown, answer)
        return {"category": UNCLASSIFIED} if rule is None else rule_cause(rule)
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
