"""Whether a submitted practice answer is right.

An answer is right when, after normalization, it equals the exercise's
`correct_answer` or one of its `accepted_answers`. Normalization only erases
differences in how a value is *written*, never in what it is:

- case, surrounding whitespace, runs of whitespace, and spaces next to an operator
  (`x - 8 = 17` is `x-8=17`);
- a Swiss decimal comma (`31,4` is `31.4`), trailing decimal zeros (`10.80` is
  `10.8`), a thousands apostrophe (`1'200` is `1200`) and a price written `34.–`;
- the Unicode minus and a trailing full stop.

It does not make different values equal. `4/6` is not `2/3`: several exercises ask
for the reduced fraction, so which equivalent forms count is the author's call,
written down as `accepted_answers` (a mixed number, a decimal, a value with its
unit). Before this, the prompts wrote `π ≈ 3,14` while the keys said `31.4`, and a
student who answered in the prompt's own notation was marked wrong.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any


#: How many alternative answers one exercise may list, and how long each may be.
MAX_ACCEPTED_ANSWERS = 20
MAX_ACCEPTED_ANSWER_LENGTH = 200

_MINUS_SIGNS = str.maketrans({"−": "-", "⁄": "/", "∕": "/"})
# 34.– / 34.- / 34.— : Swiss prices with no centimes.
_WHOLE_PRICE = re.compile(r"(\d)\.[-–—]+(?!\d)")
# A number as a pupil writes it: optional apostrophe thousands, optional , or . decimals.
_NUMBER = re.compile(r"(?<![\d.,])\d+(?:['’]\d{3})*(?:[.,]\d+)?(?![\d'’])")
_OPERATOR_SPACING = re.compile(r"\s*([=+\-*/:·×()<>])\s*")
_DIGIT_THEN_LETTER = re.compile(r"(\d)([^\W\d_])")
_WHITESPACE = re.compile(r"\s+")


def _canonical_number(match: re.Match[str]) -> str:
    text = match.group(0).replace("'", "").replace("’", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return match.group(0)
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def normalize_answer(value: object) -> str:
    """One answer in the form two writings of the same value share."""
    text = unicodedata.normalize("NFKC", str(value)).translate(_MINUS_SIGNS).lower()
    text = _WHITESPACE.sub(" ", text).strip()
    text = _WHOLE_PRICE.sub(r"\1", text)
    text = _NUMBER.sub(_canonical_number, text)
    text = _OPERATOR_SPACING.sub(r"\1", text)
    text = _DIGIT_THEN_LETTER.sub(r"\1 \2", text)
    return text.rstrip(".").strip()


def _normalized(value: object) -> str:
    if isinstance(value, list):
        return "|".join(normalize_answer(item) for item in value)
    return normalize_answer(value)


def judge(submitted: Any, correct_answer: Any, accepted_answers: Iterable[Any] = ()) -> bool:
    """Compare a submission with the key and every listed alternative."""
    answer = _normalized(submitted)
    if not answer:
        return False
    return any(answer == _normalized(key) for key in (correct_answer, *accepted_answers))


def accepted_answers(challenge: Mapping[str, Any]) -> list[str]:
    """The alternatives a challenge row lists; anything malformed counts as none."""
    raw = challenge.get("accepted_answers")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item.strip()]


def judge_challenge(submitted: Any, challenge: Mapping[str, Any]) -> bool:
    """Judge a submission against one stored challenge row."""
    return judge(
        submitted,
        challenge.get("correct_answer", challenge.get("answer_key", "")),
        accepted_answers(challenge),
    )
