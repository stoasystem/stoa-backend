#!/usr/bin/env python3
"""Offline evaluation of the AI teacher's replies: language, wording, mixing, refusals.

stoa-docs card 078, stoasystem/stoa-backend#43. The prompt tests only prove
what the prompt says; this asks the real model and reads what it answered.
It is an evaluation, not a gate: no thresholds, not in CI, and it costs money.
(The card names it after the legacy term; the terminology gate keeps that word
out of code, so the files are named for AI replies instead.)

Five readings, over the question set in docs/evals/ai-reply-questions.json:

- language consistency: replies whose language is the one asked for;
- term violations: occurrences of the legacy terms the allowlist names;
- mixed-language replies: replies with parts in another language;
- refusal rate: out-of-syllabus questions the model declined to explain;
- final answer given: replies to a question with a known result (its
  `final_answer`) that state that result, which the prompt says never to do.

Each run is in one answer style (#314), `standard` by default; `--style all`
asks every question once in each of the four styles and compares each style's
readings with `standard`'s, so a style paragraph that costs language
consistency, refusals or answer leaks is seen before it ships. `--style` may be
given more than once, and `--compare-with` takes `standard` from an earlier
report, so re-running two styles after a prompt fix does not pay for standard
again. `--keep-raw-failures` keeps what the model wrote when its reply could
not be parsed, which the readings otherwise never see.

Calls go through ask_answer.answer - production's prompt builder and model
call, without the chat lane's star map, memory context and streaming - with a
Bedrock client from an SSO session. Nothing is written to any table. Two
poisonings are applied in-process, without touching the source:
`language-german` (every language named German) and `pre-e1` (the two
passages E1 changed, put back as they were before it).

Every paid run must be confirmed, and refuses to make more calls than
--max-calls. --dry-run prints the plan and the estimated cost and calls
nothing.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "docs" / "evals" / "ai-reply-questions.json"
# Spelled in two parts, as the terminology gate's own test does: the word is
# what this evaluation looks for, not something it uses.
LEGACY_TERM = "tu" + "tor"
TERM_ALLOWLIST = ROOT / "docs" / "security" / f"{LEGACY_TERM}-term-allowlist.json"
LANGUAGES = ("de", "en", "fr", "it")
POISONS = ("language-german", "pre-e1")
DEFAULT_AWS_ACCOUNT_ID = "562923011260"
SUBSETS = ("all", "in-syllabus", "out-of-syllabus")
# `learning_profile_service.ANSWER_STYLE_CODES`, standard first; a test keeps
# the two the same. Spelled out so a dry run imports nothing from the app.
ANSWER_STYLES = ("standard", "concise", "encouraging", "vivid")
STYLE_CHOICES = (*ANSWER_STYLES, "all")
# The readings compared between a style and `standard`.
COMPARED = (
    "language_consistency_pct",
    "mixed_language_replies",
    "refusal_pct_out_of_syllabus",
    "suggest_teacher_pct_out_of_syllabus",
    "final_answer_given_pct",
)
DEFAULT_MAX_CALLS = 48
# Anthropic's first-party rate for Claude Sonnet 4.6, in USD per million
# tokens. Bedrock is priced by AWS; the estimate on #43 also gives twice this.
PRICE_INPUT_PER_MTOK = 3.0
PRICE_OUTPUT_PER_MTOK = 15.0
ESTIMATE_INPUT_TOKENS = 800
ESTIMATE_OUTPUT_TOKENS = 1500

# E1 (04fd9737) made the grade set how deep an answer goes, not whether there
# is one. It changed two passages; the poisoning puts both back as they were,
# so the prompt does not argue with itself.
E1_CHANGES = (
    (
        "You ONLY answer questions related to {subject}. The student is in {grade}: "
        "use that to choose the depth of the explanation, the examples and the "
        "prerequisites you point to, never to decide whether a question deserves an answer.",
        "You ONLY answer questions related to {subject} at {grade} level.",
    ),
    (
        "- If an in-subject question is far above {grade}, first give a short accessible "
        "explanation with one concrete example or analogy and name the ideas the student "
        "would need first; set suggest_teacher to true only if the student stays stuck "
        "after that, or shows emotional distress. Reject only questions outside {subject}.",
        "- If the question is too complex or involves emotional distress, suggest teacher "
        "intervention.",
    ),
)
# In a language lesson an example sentence in that language is the point, not
# a lapse into another language.
SUBJECT_LANGUAGE = {"german": "de", "english": "en"}

# A few hundred of the commonest words would do better; these are enough to
# tell four languages apart in a school answer, and they need no dependency.
STOPWORDS: dict[str, frozenset[str]] = {
    "de": frozenset(
        "der die das und ist nicht ein eine einen zu mit auf für von den dem des sich "
        "auch es wir du ich sie wenn dann oder aber wie was wird werden kann musst "
        "im in bei nach aus als so noch nur schritt beispiel zuerst hier".split()
    ),
    "en": frozenset(
        "the and is not a an to with on for of in it this that you we they if then or "
        "but how what will can must be are was from as so only step example first here "
        "your".split()
    ),
    "fr": frozenset(
        "le la les et est ne pas un une des du de en avec pour sur dans ce cette que qui "
        "il elle nous vous on si alors ou mais comment quoi peut doit être sont au aux "
        "étape exemple d'abord ici".split()
    ),
    "it": frozenset(
        "il lo la i gli le e è non un una di da in con per su che chi questo questa si "
        "noi voi se allora o ma come cosa può deve essere sono del della dei al alla "
        "passo esempio prima qui".split()
    ),
}
# Phrases with which a reply declines to answer. Deliberately not "too
# advanced" or "outside": a reply that follows E1 says those before it explains.
# A heuristic all the same, so the report lists every reply, for a person to check.
REFUSAL_PHRASES: dict[str, tuple[str, ...]] = {
    # The second line of each is what the pre-E1 replies of 2026-10-02 said (#43).
    "de": ("kann ich nicht beantworten", "kann ich leider nicht", "nicht beantworten",
           "beantworte nur fragen", "nur fragen zu",
           "nicht helfen", "keine vollständige erklärung geben"),
    "en": ("i can't answer", "i cannot answer", "i can only answer", "only answer questions",
           "not able to answer", "unable to answer",
           "not able to cover", "i can only help"),
    "fr": ("je ne peux pas répondre", "je ne peux pas t'aider", "je réponds uniquement",
           "seulement aux questions",
           "pas t'expliquer", "je ne peux t'aider qu"),
    "it": ("non posso rispondere", "non posso aiutarti", "rispondo solo", "solo a domande",
           "posso aiutarti solo"),
}
_LATEX = re.compile(r"\$\$.*?\$\$|\$[^$]*\$", re.DOTALL)
_FRACTION = re.compile(r"\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}")
# Markup that changes how a result looks, not what it says.
_MARKUP = ("\\left", "\\right", "\\text", "\\mathrm", "\\,", "\\;", "\\!", "\\ ")
_SYMBOLS = (("\u2212", "-"), ("\u2013", "-"), ("\\cdot", "*"), ("\\times", "*"),
            ("\u00d7", "*"), ("\u00b7", "*"), ("^2", "\u00b2"), ("\\gt", ">"))
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


class EvalError(RuntimeError):
    """The evaluation cannot be run as asked."""


@dataclass
class Reading:
    item_id: str
    expected_language: str
    out_of_syllabus: bool
    style: str = "standard"
    detected_language: str | None = None
    language_ok: bool = False
    mixed: bool = False
    mixed_segments: list[str] = field(default_factory=list)
    term_violations: int = 0
    refused: bool = False
    suggested_teacher: bool = False
    # None for a question without a known result (`final_answer`).
    gave_final_answer: bool | None = None
    error: str | None = None
    # What the model wrote when it could not be parsed (--keep-raw-failures).
    raw_output: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    excerpt: str = ""
    # Everything the model returned, so a reading can be checked or redone
    # without paying again: the readings use more fields than steps and answer.
    reply: dict[str, Any] = field(default_factory=dict)


def load_questions(path: Path = QUESTIONS) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise EvalError("the question set has no items")
    seen: set[str] = set()
    for item in items:
        for key in ("id", "language", "subject", "grade", "question", "expected_language"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise EvalError(f"question {item.get('id')!r} has no {key}")
        if item["expected_language"] not in LANGUAGES:
            raise EvalError(f"question {item['id']} expects an unknown language")
        if item["id"] in seen:
            raise EvalError(f"question {item['id']} appears twice")
        final = item.get("final_answer")
        if final is not None and (
            not isinstance(final, list)
            or not final
            or not all(isinstance(entry, str) and entry.strip() for entry in final)
        ):
            raise EvalError(f"question {item['id']} has a malformed final_answer")
        seen.add(item["id"])
    return items


def select(items: Sequence[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
    if subset == "in-syllabus":
        return [item for item in items if not item.get("out_of_syllabus")]
    if subset == "out-of-syllabus":
        return [item for item in items if item.get("out_of_syllabus")]
    return list(items)


def _words(text: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(_LATEX.sub(" ", text))]


def detect_language(text: str, *, minimum_hits: int = 2) -> str | None:
    """The language whose common words the text uses most, or None if unclear."""
    words = _words(text)
    scores = {language: sum(word in vocab for word in words) for language, vocab in STOPWORDS.items()}
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    best, best_score = ranked[0]
    if best_score < minimum_hits or best_score == ranked[1][1]:
        return None
    return best


def _segment(entry: Any) -> str:
    """The words of one entry. A knowledge point is `{id, name}` (#142); its words are its name."""
    if isinstance(entry, Mapping):
        return str(entry.get("name") or "")
    return str(entry)


def _segments(content: Mapping[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in ("steps", "hints", "similar_exercises", "knowledge_points"):
        value = content.get(key)
        if isinstance(value, list):
            parts.extend(_segment(entry) for entry in value if _segment(entry).strip())
    answer = content.get("answer")
    if isinstance(answer, str) and answer.strip():
        parts.append(answer)
    return parts


def _normal_math(text: str) -> str:
    """A result as written, without the spacing and LaTeX that do not change it."""
    normal = text.lower()
    for written, meant in _SYMBOLS:
        normal = normal.replace(written, meant)
    normal = _FRACTION.sub(r"\1/\2", normal)
    for markup in _MARKUP:
        normal = normal.replace(markup, "")
    # Spaces, dollars, braces and the Swiss thousands apostrophe.
    return re.sub(r"[\s${}'\u2019]", "", normal)


def _number_continues(text: str, at: int, step: int) -> bool:
    """Whether the number ending (or starting) next to `at` runs on past it."""
    if not 0 <= at < len(text):
        return False
    if text[at].isdigit():
        return True
    beyond = at + step
    return text[at] in ".," and 0 <= beyond < len(text) and text[beyond].isdigit()


def states_final_answer(text: str, spellings: Sequence[str]) -> bool:
    """Whether the text states one of the result's spellings, as a whole number.

    "30" is found in "0.2 * 150 = 30." and not in "300" or "3.30"; "7/12" in
    "$\\frac{7}{12}$". A heuristic like the refusal phrases: the report keeps
    every reply, for a person to check.
    """
    haystack = _normal_math(text)
    for spelling in spellings:
        needle = _normal_math(spelling)
        if not needle:
            continue
        for match in re.finditer(re.escape(needle), haystack):
            if needle[0].isdigit() and _number_continues(haystack, match.start() - 1, -1):
                continue
            if needle[-1].isdigit() and _number_continues(haystack, match.end(), 1):
                continue
            return True
    return False


def forbidden_terms(path: Path = TERM_ALLOWLIST) -> list[str]:
    """The legacy terms, as the terminology allowlist names them."""
    entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    return sorted({str(entry["literal"]).lower() for entry in entries if entry.get("literal")})


def _stems(terms: Sequence[str]) -> list[str]:
    """The shortest forms only: a plural is already counted by its singular."""
    lowered = sorted({str(term).lower() for term in terms if str(term).strip()}, key=len)
    stems: list[str] = []
    for term in lowered:
        if not any(term.startswith(stem) for stem in stems):
            stems.append(term)
    return stems


def _term_pattern(stems: Sequence[str]) -> re.Pattern[str] | None:
    """Whole words only, with the plural and gendered endings the four languages use.

    "tutorial", "tutoriel" and "Tutorium" are other words and do not count.
    """
    if not stems:
        return None
    alternatives = "|".join(re.escape(stem) for stem in stems)
    return re.compile(rf"\b(?:{alternatives})(?:s|in|innen|e|i)?\b", re.IGNORECASE)


def read_reply(
    item: Mapping[str, Any], content: Mapping[str, Any], *, terms: Sequence[str] = ()
) -> Reading:
    """The readings for one reply."""
    expected = str(item["expected_language"])
    segments = _segments(content)
    text = "\n".join(segments)
    reading = Reading(
        item_id=str(item["id"]),
        expected_language=expected,
        out_of_syllabus=bool(item.get("out_of_syllabus")),
        excerpt=text[:240],
        reply=dict(content),
    )
    reading.detected_language = detect_language(text)
    reading.language_ok = reading.detected_language == expected
    # A segment counts as another language only when it is long enough to
    # judge; a formula or a single word decides nothing.
    example_language = SUBJECT_LANGUAGE.get(str(item.get("subject") or ""))
    for segment in segments:
        language = detect_language(segment, minimum_hits=3)
        if language is not None and language not in {expected, example_language}:
            reading.mixed_segments.append(segment[:120])
    reading.mixed = bool(reading.mixed_segments)
    lowered = text.lower()
    pattern = _term_pattern(_stems(terms))
    reading.term_violations = len(pattern.findall(text)) if pattern else 0
    steps = content.get("steps")
    step_count = len([s for s in steps if str(s).strip()]) if isinstance(steps, list) else 0
    declined = any(phrase in lowered for phrase in REFUSAL_PHRASES.get(expected, ()))
    # No steps at all is a refusal, and so is a declining phrase in any step:
    # before E1 the model declined over several steps (#43, 2026-10-02).
    reading.refused = step_count == 0 or declined
    # Before E1 the prompt said to "suggest teacher intervention" for a hard
    # question: the model may explain and hand over rather than decline, so
    # this is read beside the refusals.
    reading.suggested_teacher = content.get("suggest_teacher") is True
    final = item.get("final_answer")
    if final:
        stated = [
            _segment(entry)
            for key in ("steps", "hints")
            if isinstance(content.get(key), list)
            for entry in content[key]
        ]
        if isinstance(content.get("answer"), str):
            stated.append(content["answer"])
        reading.gave_final_answer = states_final_answer("\n".join(stated), final)
    reading.style = str(item.get("answer_style") or "standard")
    return reading


@contextmanager
def poisoned(poison: str | None) -> Iterator[None]:
    """Apply one poisoning to the Ask prompt in this process, and undo it after."""
    from stoa.services import ai_service, ask_answer

    if poison is None:
        yield
        return
    if poison == "language-german":
        original = ai_service.language_name
        ai_service.language_name = lambda language: ai_service.DEFAULT_LANGUAGE_NAME
        try:
            yield
        finally:
            ai_service.language_name = original
        return
    if poison == "pre-e1":
        original_prompt = ask_answer.SYSTEM_PROMPT
        poisoned_prompt = original_prompt
        for current, before in E1_CHANGES:
            if current not in poisoned_prompt:
                raise EvalError("the system prompt no longer reads as E1 left it")
            poisoned_prompt = poisoned_prompt.replace(current, before, 1)
        ask_answer.SYSTEM_PROMPT = poisoned_prompt
        try:
            yield
        finally:
            ask_answer.SYSTEM_PROMPT = original_prompt
        return
    raise EvalError(f"unknown poisoning {poison!r}")


class RawFailures:
    """The text the reply parser last refused, while capturing is on."""

    def __init__(self) -> None:
        self.last: str | None = None

    def take(self) -> str | None:
        text, self.last = self.last, None
        return text


@contextmanager
def capturing_raw_failures(enabled: bool) -> Iterator[RawFailures]:
    """Wrap the reply parser in this process so a refused reply's text is kept.

    Production logs only the size of an unparseable reply; an evaluation of a
    prompt change needs the text to see why. Undone after the run.
    """
    from stoa.services import ai_service

    raw = RawFailures()
    if not enabled:
        yield raw
        return
    original = ai_service._parse_ai_response

    def parse(text: str) -> dict:
        try:
            return original(text)
        except ai_service.AIInvocationFailure:
            raw.last = text
            raise

    ai_service._parse_ai_response = parse
    try:
        yield raw
    finally:
        ai_service._parse_ai_response = original


def estimate_cost(calls: int) -> dict[str, float]:
    per_call = (
        ESTIMATE_INPUT_TOKENS * PRICE_INPUT_PER_MTOK
        + ESTIMATE_OUTPUT_TOKENS * PRICE_OUTPUT_PER_MTOK
    ) / 1_000_000
    return {"calls": calls, "per_call_usd": round(per_call, 4), "total_usd": round(per_call * calls, 2)}


def run(
    items: Sequence[dict[str, Any]],
    *,
    ask: Callable[[dict[str, Any]], tuple[Mapping[str, Any], int, int]],
    poison: str | None = None,
    styles: Sequence[str] = ("standard",),
    keep_raw_failures: bool = False,
) -> list[Reading]:
    """Ask every question in every style and read every reply.

    The style rides on the item as `answer_style`, which `ask_reply` hands to
    the prompt builder. A failed call is recorded, not raised.
    """
    readings: list[Reading] = []
    terms = forbidden_terms()
    unknown = [style for style in styles if style not in ANSWER_STYLES]
    if unknown:
        raise EvalError(f"unknown answer style {unknown[0]!r}")
    asked = [dict(item, answer_style=style) for style in styles for item in items]
    with poisoned(poison), capturing_raw_failures(keep_raw_failures) as raw:
        for item in asked:
            raw.take()
            try:
                content, input_tokens, output_tokens = ask(item)
            except Exception as exc:  # noqa: BLE001 - one bad reply must not lose the run
                failed = Reading(
                    item_id=str(item["id"]),
                    expected_language=str(item["expected_language"]),
                    out_of_syllabus=bool(item.get("out_of_syllabus")),
                    style=str(item["answer_style"]),
                    error=f"{type(exc).__name__}: {str(exc)[:200]}",
                    raw_output=raw.take(),
                )
                # A reply cut off at the token limit failed validation but was
                # paid for in full; its usage rides on the failure.
                usage = getattr(exc, "usage", None)
                if usage is not None:
                    failed.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                    failed.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
                readings.append(failed)
                continue
            reading = read_reply(item, content, terms=terms)
            reading.input_tokens, reading.output_tokens = input_tokens, output_tokens
            readings.append(reading)
    return readings


def summarize(readings: Sequence[Reading]) -> dict[str, Any]:
    answered = [reading for reading in readings if reading.error is None]
    beyond = [reading for reading in answered if reading.out_of_syllabus]
    keyed = [reading for reading in answered if reading.gave_final_answer is not None]
    input_tokens = sum(reading.input_tokens for reading in readings)
    output_tokens = sum(reading.output_tokens for reading in readings)

    def rate(part: int, whole: int) -> float | None:
        return round(100 * part / whole, 1) if whole else None

    return {
        "replies": len(readings),
        "errors": len(readings) - len(answered),
        "language_consistency_pct": rate(sum(r.language_ok for r in answered), len(answered)),
        "term_violations": sum(r.term_violations for r in answered),
        "mixed_language_replies": sum(r.mixed for r in answered),
        "refusal_pct_out_of_syllabus": rate(sum(r.refused for r in beyond), len(beyond)),
        "suggest_teacher_pct_out_of_syllabus": rate(
            sum(r.suggested_teacher for r in beyond), len(beyond)
        ),
        "final_answer_given_pct": rate(sum(bool(r.gave_final_answer) for r in keyed), len(keyed)),
        "tokens": {"input": input_tokens, "output": output_tokens},
        "cost_usd_at_first_party_rate": round(
            (input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK)
            / 1_000_000,
            4,
        ),
    }


def summarize_by_style(readings: Sequence[Reading]) -> dict[str, dict[str, Any]]:
    """One summary per style, in the order the styles are offered."""
    return {
        style: summarize([reading for reading in readings if reading.style == style])
        for style in ANSWER_STYLES
        if any(reading.style == style for reading in readings)
    }


def compare_to_standard(
    by_style: Mapping[str, Mapping[str, Any]],
    standard: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Each style's readings minus `standard`'s: what the style paragraph moved.

    Worse is lower language consistency, or more mixing, refusals, final
    answers given away or failed replies. No threshold: a person reads the
    deltas and the replies. `standard` is this run's unless one is given (from
    an earlier report).
    """
    standard = by_style.get("standard") if standard is None else standard
    if standard is None:
        return {}
    deltas: dict[str, dict[str, Any]] = {}
    for style, summary in by_style.items():
        if style == "standard":
            continue
        deltas[style] = {
            key: (
                None
                if summary.get(key) is None or standard.get(key) is None
                else round(summary[key] - standard[key], 1)
            )
            for key in (*COMPARED, "errors")
        }
    return deltas


def standard_from_report(path: Path) -> dict[str, Any]:
    """The `standard` summary an earlier report measured."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        standard = report["by_style"]["standard"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EvalError(f"no standard summary in {path}") from exc
    if not isinstance(standard, dict):
        raise EvalError(f"no standard summary in {path}")
    return standard


def bedrock_asker(
    profile: str, region: str, account_id: str
) -> Callable[[dict[str, Any]], tuple[Mapping[str, Any], int, int]]:
    """Ask through `ask_answer.answer` with a Bedrock client from an SSO session."""
    from stoa.security.aws_operator_identity import require_sso_operator_session

    session = require_sso_operator_session(
        profile_name=profile, region_name=region, expected_account_id=account_id
    )
    client = session.client("bedrock-runtime", region_name=region)

    def ask(item: dict[str, Any]) -> tuple[Mapping[str, Any], int, int]:
        return ask_reply(item, client, correlation_id=f"eval-{uuid.uuid4().hex[:12]}")

    return ask


def ask_reply(
    item: dict[str, Any], client: Any, *, correlation_id: str | None = None
) -> tuple[Mapping[str, Any], int, int]:
    """One question asked the way production asks it, without a star map:
    the reply as the model wrote it, and its token counts."""
    from stoa.services import ask_answer

    result = ask_answer.answer(
        ask_answer.Asked(content=item["question"]),
        ask_answer.Asker(
            student_id="eval",
            subject=item["subject"],
            grade=item["grade"],
            locale=item["language"],
            answer_style=str(item.get("answer_style") or "standard"),
        ),
        ask_answer.ModelCall(
            model=client, correlation_id=correlation_id, effect_id=f"eval-{item['id']}"
        ),
        read_star_map=lambda *_args, **_kwargs: None,
    )
    assert result.provider is not None
    provider = result.provider
    return provider.content, provider.usage.input_tokens, provider.usage.output_tokens


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--subset", choices=SUBSETS, default="all", help="Which questions.")
    parser.add_argument("--poison", choices=POISONS, default=None, help="Poisoned run.")
    parser.add_argument(
        "--style",
        choices=STYLE_CHOICES,
        action="append",
        default=None,
        help="Answer style to ask in (#314), repeatable; 'all' asks in each of the four.",
    )
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=None,
        help="An earlier report whose standard summary the styles are compared with.",
    )
    parser.add_argument(
        "--keep-raw-failures",
        action="store_true",
        help="Keep the model's text when a reply cannot be parsed.",
    )
    parser.add_argument(
        "--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="Refuse a bigger run."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; call nothing.")
    parser.add_argument(
        "--confirm-cost", action="store_true", help="Required for a run that calls the model."
    )
    parser.add_argument(
        "--profile", default="stoa", help="AWS IAM Identity Center profile for Bedrock."
    )
    parser.add_argument("--region", default="eu-central-2")
    parser.add_argument("--account-id", default=DEFAULT_AWS_ACCOUNT_ID)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "stoa-ai-eval",
        help="Where the report goes; outside the repository by default.",
    )
    parser.add_argument("--label", default="baseline", help="Names the report file.")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    asker: Callable[[dict[str, Any]], tuple[Mapping[str, Any], int, int]] | None = None,
) -> int:
    args = parse_args(argv)
    try:
        items = select(load_questions(args.questions), args.subset)
        chosen = args.style or ["standard"]
        styles = (
            ANSWER_STYLES
            if "all" in chosen
            else tuple(style for style in ANSWER_STYLES if style in chosen)
        )
        compared_standard = (
            standard_from_report(args.compare_with) if args.compare_with else None
        )
        calls = len(items) * len(styles)
        plan = {
            "label": args.label,
            "subset": args.subset,
            "poison": args.poison,
            "styles": list(styles),
            "compare_with": str(args.compare_with) if args.compare_with else None,
            "estimate": estimate_cost(calls),
        }
        if calls > args.max_calls:
            raise EvalError(
                f"{calls} calls planned, more than --max-calls {args.max_calls}"
            )
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        if not args.confirm_cost:
            raise EvalError("a run that calls the model needs --confirm-cost")
        ask = asker or bedrock_asker(args.profile, args.region, args.account_id)
        readings = run(
            items,
            ask=ask,
            poison=args.poison,
            styles=styles,
            keep_raw_failures=args.keep_raw_failures,
        )
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        # The SSO guard's refusal, among others: no session, no run.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    report = {
        "plan": plan,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summarize(readings),
        "by_style": (by_style := summarize_by_style(readings)),
        "vs_standard": compare_to_standard(
            by_style, None if "standard" in by_style else compared_standard
        ),
        "replies": [reading.__dict__ for reading in readings],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"ai-reply-eval-{args.label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        report["summary"] if len(styles) == 1 and not report["vs_standard"]
        else {"by_style": report["by_style"], "vs_standard": report["vs_standard"]},
        indent=2,
    ))
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
