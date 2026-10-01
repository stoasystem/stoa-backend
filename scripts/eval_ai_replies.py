#!/usr/bin/env python3
"""Offline evaluation of the AI teacher's replies: language, wording, mixing, refusals.

stoa-docs card 078, stoasystem/stoa-backend#43. The prompt tests only prove
what the prompt says; this asks the real model and reads what it answered.
It is an evaluation, not a gate: no thresholds, not in CI, and it costs money.
(The card names it after the legacy term; the terminology gate keeps that word
out of code, so the files are named for AI replies instead.)

Four readings, over the question set in docs/evals/ai-reply-questions.json:

- language consistency: replies whose language is the one asked for;
- term violations: occurrences of the legacy terms the allowlist names;
- mixed-language replies: replies with parts in another language;
- refusal rate: out-of-syllabus questions the model declined to explain.

Calls go through ai_service.get_ai_answer - production's prompt builder and
model call, without the chat lane's memory context and streaming - with a
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
    "de": ("kann ich nicht beantworten", "kann ich leider nicht", "nicht beantworten",
           "beantworte nur fragen", "nur fragen zu"),
    "en": ("i can't answer", "i cannot answer", "i can only answer", "only answer questions",
           "not able to answer", "unable to answer"),
    "fr": ("je ne peux pas répondre", "je ne peux pas t'aider", "je réponds uniquement",
           "seulement aux questions"),
    "it": ("non posso rispondere", "non posso aiutarti", "rispondo solo", "solo a domande"),
}
_LATEX = re.compile(r"\$\$.*?\$\$|\$[^$]*\$", re.DOTALL)
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


class EvalError(RuntimeError):
    """The evaluation cannot be run as asked."""


@dataclass
class Reading:
    item_id: str
    expected_language: str
    out_of_syllabus: bool
    detected_language: str | None = None
    language_ok: bool = False
    mixed: bool = False
    mixed_segments: list[str] = field(default_factory=list)
    term_violations: int = 0
    refused: bool = False
    suggested_teacher: bool = False
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    excerpt: str = ""


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


def _segments(content: Mapping[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in ("steps", "hints", "similar_exercises", "knowledge_points"):
        value = content.get(key)
        if isinstance(value, list):
            parts.extend(str(entry) for entry in value if str(entry).strip())
    answer = content.get("answer")
    if isinstance(answer, str) and answer.strip():
        parts.append(answer)
    return parts


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
    """The four readings for one reply."""
    expected = str(item["expected_language"])
    segments = _segments(content)
    text = "\n".join(segments)
    reading = Reading(
        item_id=str(item["id"]),
        expected_language=expected,
        out_of_syllabus=bool(item.get("out_of_syllabus")),
        excerpt=text[:240],
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
    # No steps at all is a refusal; one step is one only if it also declines.
    reading.refused = step_count == 0 or (step_count < 2 and declined)
    # Before E1 the prompt said to "suggest teacher intervention" for a hard
    # question: the model may explain and hand over rather than decline, so
    # this is read beside the refusals.
    reading.suggested_teacher = content.get("suggest_teacher") is True
    return reading


@contextmanager
def poisoned(poison: str | None) -> Iterator[None]:
    """Apply one poisoning to ai_service in this process, and undo it after."""
    from stoa.services import ai_service

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
        original_prompt = ai_service.SYSTEM_PROMPT
        poisoned_prompt = original_prompt
        for current, before in E1_CHANGES:
            if current not in poisoned_prompt:
                raise EvalError("the system prompt no longer reads as E1 left it")
            poisoned_prompt = poisoned_prompt.replace(current, before, 1)
        ai_service.SYSTEM_PROMPT = poisoned_prompt
        try:
            yield
        finally:
            ai_service.SYSTEM_PROMPT = original_prompt
        return
    raise EvalError(f"unknown poisoning {poison!r}")


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
) -> list[Reading]:
    """Ask every question and read every reply; a failed call is recorded, not raised."""
    readings: list[Reading] = []
    terms = forbidden_terms()
    with poisoned(poison):
        for item in items:
            try:
                content, input_tokens, output_tokens = ask(item)
            except Exception as exc:  # noqa: BLE001 - one bad reply must not lose the run
                failed = Reading(
                    item_id=str(item["id"]),
                    expected_language=str(item["expected_language"]),
                    out_of_syllabus=bool(item.get("out_of_syllabus")),
                    error=f"{type(exc).__name__}: {str(exc)[:200]}",
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
        "tokens": {"input": input_tokens, "output": output_tokens},
        "cost_usd_at_first_party_rate": round(
            (input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK)
            / 1_000_000,
            4,
        ),
    }


def bedrock_asker(
    profile: str, region: str, account_id: str
) -> Callable[[dict[str, Any]], tuple[Mapping[str, Any], int, int]]:
    """Ask through get_ai_answer with a Bedrock client from an SSO session."""
    from stoa.security.aws_operator_identity import require_sso_operator_session
    from stoa.services import ai_service

    session = require_sso_operator_session(
        profile_name=profile, region_name=region, expected_account_id=account_id
    )
    client = session.client("bedrock-runtime", region_name=region)

    def ask(item: dict[str, Any]) -> tuple[Mapping[str, Any], int, int]:
        result = ai_service.get_ai_answer(
            content=item["question"],
            subject=item["subject"],
            grade=item["grade"],
            language=item["language"],
            client=client,
            correlation_id=f"eval-{uuid.uuid4().hex[:12]}",
            effect_id=f"eval-{item['id']}",
        )
        return result.content, result.usage.input_tokens, result.usage.output_tokens

    return ask


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--subset", choices=SUBSETS, default="all", help="Which questions.")
    parser.add_argument("--poison", choices=POISONS, default=None, help="Poisoned run.")
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
        plan = {
            "label": args.label,
            "subset": args.subset,
            "poison": args.poison,
            "estimate": estimate_cost(len(items)),
        }
        if len(items) > args.max_calls:
            raise EvalError(
                f"{len(items)} calls planned, more than --max-calls {args.max_calls}"
            )
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        if not args.confirm_cost:
            raise EvalError("a run that calls the model needs --confirm-cost")
        ask = asker or bedrock_asker(args.profile, args.region, args.account_id)
        readings = run(items, ask=ask, poison=args.poison)
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
        "replies": [reading.__dict__ for reading in readings],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"ai-reply-eval-{args.label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
