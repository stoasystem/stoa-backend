#!/usr/bin/env python3
"""Draft a star's lesson with the model: outline, a person's confirmation, then block by block.

stoasystem/stoa-backend#441. The curriculum's lessons and exercises come from
editorial batches and the knowledge base import; this is the other way, for a
star nothing else covers yet: the model drafts, a person confirms, two
independent AI checkers check, and what passes becomes a migration manifest
with every lesson `"publish": false`. The flow borrows OpenMAIC's (outline
first, wait for review, generate per block with what came before, keep every
step) and adds what it lacks, a check that the answers are right (#422's six
checks).

    outline   star → outline/<star>.json: the explanation cards and the exercises
              (what each tests, its question type and difficulty), and
              review-outlines.md, the review package a person reads
    confirm   a person's yes to an outline: outline/<star>.confirmed.json holds
              its hash, and an outline edited after it needs a new yes
    generate  confirmed outline → blocks/<star>/<block>.json: the cards, then the
              exercises a few at a time, each block told what the earlier ones hold
    check     the drafted exercises mixed blind with the star's imported drafts
              (--imported), cut in chunks, each chunk checked by two checkers who
              never see each other's verdicts (B reads it backwards) →
              check/<chunk>.<A|B>.json, then check/verdicts.json
    manifest  passed drafts → manifests/manifest-001.json and report.json
    dry-run   each manifest through curriculum_migration_service.dry_run against
              an in-memory table seeded with the knowledge base stars → dry-run.json
    report    the comparison: drafted against imported, per bucket, the failure
              reasons, and every star's tokens, cost and time → report.md

Every model call writes its own file the moment it returns, and a step reads
what is already there before it calls: a step that fails (a timeout, a reply
that does not validate) is run again and redoes only the files it lacks.
`--fail <file stem>` makes that one call fail on purpose, to see it.

The model sees only the star's names and description, its prerequisites' names
and descriptions, its question types and grade level, and the conventions of
the platform: no textbook text. What it writes is checked by code before any
checker sees it (four languages, one right option, the platform's limits, unit
spellings in `accepted_answers`); an exercise that still fails after its block
is retried is left out with its reason, never shortened or approximated.

Model calls go to Bedrock with a client from an SSO session, like
eval_ai_replies.py. Every command that calls the model refuses to run without
--confirm-cost and refuses more calls than --max-calls; --plan prints the calls
and an estimate and calls nothing. Nothing here writes to any table: the dry
run reads a table built in memory.

    uv run python scripts/ai_lesson_draft.py outline --work .scratch/ai-lesson-draft \\
        --star physik-mechanik-masse-dichte-und-gewichtskraft --imported .scratch/knowledge-base/manifests \\
        --confirm-cost
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from typing import Any

from stoa.services import answer_judging, knowledge_base_catalog as catalog

ROOT = Path(__file__).resolve().parents[1]
LOCALES = catalog.LOCALES
SUBJECT = "physics"
SOURCE_ID = "ai-lesson-draft"
OPERATOR_NOTE = (
    "AI-drafted lessons (stoa-backend#441): outline confirmed by a person, exercises "
    "checked by two independent AI checkers. Drafts only; review and publish in the "
    "curriculum workflow."
)
DEFAULT_MODEL = "eu.anthropic.claude-sonnet-4-6"
DEFAULT_PROFILE = "stoa"
DEFAULT_REGION = "eu-central-2"
DEFAULT_AWS_ACCOUNT_ID = "562923011260"
#: USD per million tokens, input and output, by model id; an unknown model has no estimate.
PRICES = {
    "eu.anthropic.claude-sonnet-4-6": (3.0, 15.0),
    "eu.anthropic.claude-opus-4-6": (5.0, 25.0),
    "eu.anthropic.claude-haiku-4-5": (1.0, 5.0),
}
#: What --plan assumes one call reads and writes, per step.
ESTIMATE_TOKENS = {"outline": (3_000, 2_500), "generate": (6_000, 7_000), "check": (16_000, 4_000)}

#: The authoring limits the manifest has to keep (CurriculumExerciseDraftRequest).
MAX_TEXT = 2000
MAX_OPTION = 300
MAX_CARD_BODY = 1500
MIN_EXERCISES = 5
MAX_EXERCISES = 10
EXERCISES_PER_BLOCK = 3
CHECK_CHUNK = 20
MINUTES_PER_EXERCISE = 3
#: Lessons drafted here come after the star's own practice sets.
FIRST_ORDER = 800
GRADE_ORDER = {catalog.GRADE_LEVELS[8]: 0, catalog.GRADE_LEVELS[9]: 1, catalog.UPPER_SECONDARY: 2}
DIFFICULTIES = ("basic", "standard", "advanced")
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")
#: Wording that points at a textbook, or at a figure practice cannot show.
TEXTBOOK = re.compile(
    r"人教|北师|教材|课本|Lehrbuch|Schulbuch|textbook|manuel scolaire|libro di testo|"
    r"\b(Kapitel|Lektion|chapter|chapitre|capitolo) \d|\bSeite \d|\bpage \d",
    re.I,
)
FIGURE = re.compile(
    r"\b(Abbildung|Abb\.|Skizze|Bild unten|figure|fig\.|picture|illustration|schéma ci|"
    r"figura|immagine)\b",
    re.I,
)
LEADING_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?")


class DraftError(Exception):
    """A step that cannot go on; the message says why."""


# ── the star ─────────────────────────────────────────────────────────────────


def star_context(unit_id: str, imported: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Everything the model may see of a star: names, description, prerequisites,
    question types and grade level. Nothing of any textbook."""
    stars = json.loads(catalog.STARS_FILE.read_text(encoding="utf-8"))["stars"]
    skills = json.loads(catalog.SKILLS_FILE.read_text(encoding="utf-8"))["skills"]
    star = stars.get(unit_id)
    if star is None or star["subject_id"] != SUBJECT:
        raise DraftError(f"{unit_id} is not a {SUBJECT} star of the knowledge base")
    registered = {skill_id.split("--", 1)[1] for skill_id, s in skills.items() if s["unit"] == unit_id}
    types = [
        {"slug": slug, "title": titles["de"], "scope": scope, "extension": catalog.is_extension(SUBJECT, slug)}
        for slug, titles, scope in catalog.QUESTION_TYPES[SUBJECT] if slug in registered
    ]
    grades = sorted(
        {row["lesson"]["gradeLevel"] for row in imported if row["lesson"]["unitId"] == unit_id},
        key=lambda g: GRADE_ORDER.get(g, 9),
    )
    return {
        "unitId": unit_id,
        "topicId": star["topic_id"],
        "titles": star["titles"],
        "description": star["description"],
        "gradeLevel": grades[0] if grades else catalog.SUBJECT_GRADE_LEVELS[SUBJECT][0],
        "prerequisites": [
            {"unitId": pre, "title": stars[pre]["titles"]["de"], "description": stars[pre]["description"]}
            for pre in star["prerequisites"] if pre in stars
        ],
        "questionTypes": types,
    }


def imported_rows(manifest_dir: Path | None, units: Iterable[str]) -> list[dict[str, Any]]:
    """The imported practice sets of these stars, from the knowledge base manifests."""
    if manifest_dir is None:
        return []
    wanted = set(units)
    return [
        row
        for path in sorted(manifest_dir.glob("manifest-*.json"))
        for row in _read(path)["lessons"]
        if row["lesson"]["unitId"] in wanted
    ]


GRADE_WORDS = {
    catalog.GRADE_LEVELS[8]: "Sekundarstufe I, 8. Schuljahr (Lehrplan 21, Zyklus 3)",
    catalog.GRADE_LEVELS[9]: "Sekundarstufe I, 9. Schuljahr (Lehrplan 21, Zyklus 3)",
    catalog.UPPER_SECONDARY: "Sekundarstufe II (Gymnasium, Rahmenlehrplan Physik)",
}


def _star_brief(star: Mapping[str, Any]) -> str:
    lines = [
        f"Stern: {star['titles']['de']} (en: {star['titles']['en']})",
        f"Beschreibung: {star['description']}",
        f"Stufe: {GRADE_WORDS.get(star['gradeLevel'], star['gradeLevel'])}",
        "Voraussetzungen (andere Sterne, schon gelernt):",
        *(f"- {p['title']}: {p['description']}" for p in star["prerequisites"]),
        *([] if star["prerequisites"] else ["- keine"]),
        "Aufgabentypen dieses Sterns (questionType):",
        *(f"- {t['slug']}: {t['title']}. {t['scope']}" + (" (Vertiefung)" if t["extension"] else "")
          for t in star["questionTypes"]),
    ]
    return "\n".join(lines)


# ── model calls ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reply:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    seconds: float
    model: str


Model = Callable[[str, str, Mapping[str, Any], int], Reply]


def bedrock_model(profile: str, region: str, account_id: str, model_id: str) -> Model:
    """A model that answers through one forced tool, so the reply is JSON of a schema."""
    from botocore.config import Config

    from stoa.security.aws_operator_identity import require_sso_operator_session

    session = require_sso_operator_session(
        profile_name=profile, region_name=region, expected_account_id=account_id
    )
    client = session.client(
        "bedrock-runtime", region_name=region,
        config=Config(read_timeout=600, retries={"max_attempts": 4, "mode": "adaptive"}),
    )

    def call(system: str, user: str, schema: Mapping[str, Any], max_tokens: int) -> Reply:
        started = time.monotonic()
        response = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens},
            toolConfig={
                "tools": [{"toolSpec": {"name": "submit", "description": "Submit the result.",
                                        "inputSchema": {"json": dict(schema)}}}],
                "toolChoice": {"tool": {"name": "submit"}},
            },
        )
        seconds = time.monotonic() - started
        usage = response.get("usage") or {}
        if response.get("stopReason") == "max_tokens":
            raise DraftError(f"the reply was cut at {max_tokens} tokens")
        content = response["output"]["message"]["content"]
        data = next((part["toolUse"]["input"] for part in content if "toolUse" in part), None)
        if not isinstance(data, dict):
            raise DraftError("the reply has no submitted result")
        return Reply(data, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0)),
                     round(seconds, 1), model_id)

    return call


def _usage(reply: Reply) -> dict[str, Any]:
    return {"model": reply.model, "inputTokens": reply.input_tokens,
            "outputTokens": reply.output_tokens, "seconds": reply.seconds}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 4)


# ── outline ──────────────────────────────────────────────────────────────────

OUTLINE_SYSTEM = """Du planst eine kurze Lerneinheit Physik für eine Schweizer Lernplattform (Deutsch, \
Englisch, Französisch, Italienisch). Die Einheit gehört zu einem Stern der Sternkarte: \
ein paar Erklärkarten, dann Übungsaufgaben, von leicht nach schwer.

Du schreibst nur den Plan, noch keine Aufgaben. Ein Mensch prüft ihn, bevor etwas erzeugt wird.

Regeln für den Plan:
- 2 bis 4 Erklärkarten. Jede erklärt eine Sache, die die Aufgaben brauchen.
- 6 bis 9 Aufgaben. Jede hat einen questionType aus der Liste des Sterns; die Kerntypen \
(ohne "Vertiefung") zuerst und am meisten.
- Jede Aufgabe muss die Plattform heute bewerten können: Einfachauswahl mit genau einer \
richtigen Option ("choice") oder eine kurze Antwort ("short"): eine Zahl, eine Zahl mit \
Einheit, ein Wort oder ein kurzer Ausdruck. Keine Bilder, Skizzen, Diagramme, Graphen \
oder Schaltpläne, keine Erklärung in ganzen Sätzen als Antwort, kein Experiment, das man \
durchführen muss.
- Die Aufgabe muss ohne ein Lehrbuch verständlich sein; keine Verweise auf Kapitel, Seiten \
oder bestimmte Schulbücher; Alltag und Masseinheiten wie in der Schweiz.
- Nur Stoff dieses Sterns und seiner Voraussetzungen, auf der angegebenen Stufe.
- "tests" sagt in einem Satz, was die Aufgabe prüft; "answerShape" sagt, wie die Antwort \
aussieht (z. B. "Zahl in N", "eine von vier Aussagen", "ein Wort").
- Alles auf Deutsch."""

OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "explains": {"type": "string"},
                    "formulas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "explains"],
            },
        },
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "questionType": {"type": "string"},
                    "format": {"type": "string", "enum": ["choice", "short"]},
                    "difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
                    "tests": {"type": "string"},
                    "answerShape": {"type": "string"},
                },
                "required": ["questionType", "format", "difficulty", "tests", "answerShape"],
            },
        },
    },
    "required": ["cards", "exercises"],
}


def outline_problems(outline: Mapping[str, Any], star: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The outline with what the platform cannot take dropped (OpenMAIC's fallbacks), and
    what is still wrong with it."""
    types = {t["slug"] for t in star["questionTypes"]}
    cards = [c for c in outline.get("cards") or [] if str(c.get("title") or "").strip()]
    exercises, dropped = [], []
    for item in outline.get("exercises") or []:
        if item.get("questionType") not in types:
            dropped.append({"planned": item, "reason": f"question type {item.get('questionType')!r} "
                                                       "is not one of the star's"})
        elif item.get("format") not in {"choice", "short"} or item.get("difficulty") not in DIFFICULTIES:
            dropped.append({"planned": item, "reason": "format or difficulty the platform does not know"})
        else:
            exercises.append({**item, "slot": len(exercises) + 1})
    problems = []
    if not 1 <= len(cards) <= 4:
        problems.append(f"{len(cards)} cards, wanted 2 to 4")
    if not MIN_EXERCISES <= len(exercises) <= MAX_EXERCISES:
        problems.append(f"{len(exercises)} usable exercises, wanted {MIN_EXERCISES} to {MAX_EXERCISES}")
    return {"cards": cards, "exercises": exercises, "dropped": dropped}, problems


def make_outline(star: Mapping[str, Any], model: Model) -> dict[str, Any]:
    calls, feedback = [], ""
    for _attempt in range(2):
        reply = model(OUTLINE_SYSTEM, _star_brief(star) + feedback, OUTLINE_SCHEMA, 4000)
        calls.append(_usage(reply))
        outline, problems = outline_problems(reply.data, star)
        if not problems:
            return {"star": star["unitId"], "context": dict(star), "outline": outline, "calls": calls}
        feedback = "\n\nDein letzter Plan hatte diese Fehler, behebe sie: " + "; ".join(problems)
    raise DraftError(f"{star['unitId']}: the outline still has problems: {'; '.join(problems)}")


def outline_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record["outline"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def review_package(records: Sequence[Mapping[str, Any]]) -> str:
    """The outlines as a person reviews them: one section per star."""
    parts = ["## 大纲审阅包（AI 起草课时，#441）", "",
             "每颗星：讲解卡（标题 / 讲什么 / 公式），然后是题（题型 · 形式 · 难度 · 考什么 · 答案形式）。"
             "确认 = 照此生成；要改的写明哪一条怎么改，或整颗打回。", ""]
    for record in records:
        star, outline = record["context"], record["outline"]
        parts += [f"### {star['titles']['de']}（`{star['unitId']}`）", "",
                  f"{star['description']} 年级：`{star['gradeLevel']}`", "", "**讲解卡**", ""]
        for index, card in enumerate(outline["cards"], start=1):
            formulas = "；".join(f"`{f}`" for f in card.get("formulas") or [])
            parts.append(f"{index}. **{card['title']}**：{card['explains']}" + (f"（{formulas}）" if formulas else ""))
        parts += ["", "**题**", "", "| # | 题型 | 形式 | 难度 | 考什么 | 答案形式 |", "| ---: | --- | --- | --- | --- | --- |"]
        for item in outline["exercises"]:
            cells = [str(item["slot"]), item["questionType"], item["format"], item["difficulty"],
                     item["tests"], item["answerShape"]]
            parts.append("| " + " | ".join(c.replace("|", "/").replace("\n", " ") for c in cells) + " |")
        for drop in outline["dropped"]:
            parts.append(f"\n已按平台限制去掉：{drop['planned'].get('tests', '')}（{drop['reason']}）")
        parts.append("")
    return "\n".join(parts)


# ── generate ─────────────────────────────────────────────────────────────────

CONTRACT = """Regeln für jede Aufgabe (die Plattform prüft sie, eine Aufgabe, die eine verletzt, \
wird verworfen):
- Vier Sprachen: de, en, fr, it, inhaltlich gleich; Schweizer Deutsch-Schreibung (ss statt ß).
- "multiple_choice": 3 bis 5 Optionen, genau eine richtig; correctAnswer ist wörtlich eine \
der Optionen; in allen Sprachen dieselbe Reihenfolge, die richtige an derselben Stelle; \
acceptedAnswers leer.
- "text_input": eine kurze Antwort. Zahlen mit Dezimalpunkt im Schlüssel. acceptedAnswers \
listet alle anderen richtigen Schreibweisen desselben Werts: fragt die Aufgabe "in N", ist \
der Schlüssel die Zahl ("5") und acceptedAnswers enthält "5 N" und "5 Newton"; ist die \
Einheit Teil der Antwort, ist der Schlüssel "5 N" und acceptedAnswers enthält "5", \
"5 Newton". Gerundete Werte nur, wenn die Aufgabe sagt, worauf gerundet wird. Nie einen \
anderen Wert in acceptedAnswers. Mehrere Werte mit "; " trennen, nie mit Komma.
- Kein Bild, keine Skizze, kein Graph, kein Schaltplan; alles, was man braucht, steht im Text.
- Kein Bezug auf ein Lehrbuch, Kapitel oder eine bestimmte Schule.
- explanation: der Lösungsweg in 1 bis 4 Sätzen, mit der Formel und den Zahlen.
- Jede Aufgabe hat den slot aus dem Plan."""

GENERATE_SYSTEM = """Du schreibst Inhalte für eine Schweizer Lernplattform Physik in vier \
Sprachen (de, en, fr, it). Grundlage ist ein von einem Menschen bestätigter Plan. \
Du schreibst nur, was der Plan für diesen Block vorsieht, und knüpfst an das an, was die \
früheren Blöcke schon enthalten (keine Wiederholung derselben Aufgabe, gleiche Begriffe \
und Formelzeichen)."""

TEXT = {"type": "string"}
LOCALE_EXERCISE = {
    "type": "object",
    "properties": {
        "prompt": TEXT, "options": {"type": "array", "items": TEXT}, "correctAnswer": TEXT,
        "acceptedAnswers": {"type": "array", "items": TEXT}, "explanation": TEXT,
    },
    "required": ["prompt", "correctAnswer", "explanation"],
}
EXERCISES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"exercises": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "slot": {"type": "integer"},
            "type": {"type": "string", "enum": ["multiple_choice", "text_input"]},
            **{locale: LOCALE_EXERCISE for locale in LOCALES},
        },
        "required": ["slot", "type", *LOCALES],
    }}},
    "required": ["exercises"],
}
LOCALE_CARD = {"type": "object", "properties": {"title": TEXT, "body": TEXT}, "required": ["title", "body"]}
CARDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"cards": {"type": "array", "items": {
        "type": "object", "properties": {locale: LOCALE_CARD for locale in LOCALES}, "required": list(LOCALES),
    }}},
    "required": ["cards"],
}


def blocks_of(outline: Mapping[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The blocks of a star: its cards, then its exercises a few at a time."""
    exercises = outline["exercises"]
    return [("01-cards", list(outline["cards"]))] + [
        (f"{index + 2:02d}-exercises", exercises[start:start + EXERCISES_PER_BLOCK])
        for index, start in enumerate(range(0, len(exercises), EXERCISES_PER_BLOCK))
    ]


def _text(value: object) -> str:
    return str(value or "").strip()


def _leading_number(value: str) -> str | None:
    match = LEADING_NUMBER.match(answer_judging.normalize_answer(value))
    return match.group(0) if match else None


def card_problems(card: Mapping[str, Any]) -> list[str]:
    problems = []
    for locale in LOCALES:
        text = card.get(locale) or {}
        if not _text(text.get("title")) or not _text(text.get("body")):
            problems.append(f"{locale}: no title or body")
        elif len(_text(text["body"])) > MAX_CARD_BODY:
            problems.append(f"{locale}: body longer than {MAX_CARD_BODY} characters")
        if CJK.search(json.dumps(text, ensure_ascii=False)):
            problems.append(f"{locale}: Chinese characters")
    return problems


def exercise_problems(exercise: Mapping[str, Any]) -> list[str]:
    """What keeps an exercise out of the manifest, the way the platform reads it."""
    problems: list[str] = []
    kind = exercise.get("type")
    texts = {locale: exercise.get(locale) or {} for locale in LOCALES}
    blob = json.dumps(texts, ensure_ascii=False)
    if CJK.search(blob):
        problems.append("Chinese characters")
    if TEXTBOOK.search(blob):
        problems.append(f"points at a textbook: {TEXTBOOK.search(blob).group(0)!r}")
    if FIGURE.search(blob):
        problems.append(f"needs a figure: {FIGURE.search(blob).group(0)!r}")
    for locale, text in texts.items():
        for field in ("prompt", "correctAnswer", "explanation"):
            value = _text(text.get(field))
            if not value:
                problems.append(f"{locale}: no {field}")
            elif len(value) > MAX_TEXT:
                problems.append(f"{locale}: {field} longer than {MAX_TEXT} characters")
    if problems:
        return problems
    if kind == "multiple_choice":
        de_options = [_text(o) for o in texts["de"].get("options") or []]
        if not 3 <= len(de_options) <= 5:
            return [f"{len(de_options)} options, wanted 3 to 5"]
        right = de_options.index(_text(texts["de"]["correctAnswer"])) if _text(
            texts["de"]["correctAnswer"]) in de_options else None
        for locale, text in texts.items():
            options = [_text(o) for o in text.get("options") or []]
            if len(options) != len(de_options):
                problems.append(f"{locale}: {len(options)} options, German has {len(de_options)}")
                continue
            if len({answer_judging.normalize_answer(o) for o in options}) != len(options):
                problems.append(f"{locale}: two options read the same")
            if any(len(o) > MAX_OPTION or not o for o in options):
                problems.append(f"{locale}: an option empty or longer than {MAX_OPTION} characters")
            key = _text(text["correctAnswer"])
            if key not in options:
                problems.append(f"{locale}: correctAnswer is not an option")
            elif right is not None and options.index(key) != right:
                problems.append(f"{locale}: the right option is at another place than in German")
            if text.get("acceptedAnswers"):
                problems.append(f"{locale}: a choice lists accepted answers")
    elif kind == "text_input":
        de_key = _text(texts["de"]["correctAnswer"])
        number = _leading_number(de_key)
        for locale, text in texts.items():
            if text.get("options"):
                problems.append(f"{locale}: a short answer has options")
            key = _text(text["correctAnswer"])
            accepted = [_text(a) for a in text.get("acceptedAnswers") or [] if _text(a)]
            if len(accepted) > answer_judging.MAX_ACCEPTED_ANSWERS or any(
                len(a) > answer_judging.MAX_ACCEPTED_ANSWER_LENGTH for a in accepted
            ):
                problems.append(f"{locale}: too many or too long accepted answers")
            if number is None:
                continue
            if _leading_number(key) != number:
                problems.append(f"{locale}: key {key!r} is another value than the German {de_key!r}")
            other = [a for a in accepted if _leading_number(a) not in (None, number)]
            if other:
                problems.append(f"{locale}: accepted answers of another value: {other}")
            if not any(answer_judging.normalize_answer(a) != answer_judging.normalize_answer(key)
                       for a in accepted):
                problems.append(f"{locale}: a numeric answer lists no other spelling (unit, unit name)")
    else:
        problems.append(f"type {kind!r} is neither multiple_choice nor text_input")
    return problems


def _earlier(blocks: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for block in blocks:
        for item in block["items"]:
            if "title" in item.get("de", {}):
                lines.append(f"Karte: {item['de']['title']}: {item['de']['body']}")
            else:
                lines.append(f"Aufgabe {item['slot']}: {item['de']['prompt']} → {item['de']['correctAnswer']}")
    return "\n".join(lines) or "(noch nichts)"


def make_block(
    record: Mapping[str, Any], name: str, planned: Sequence[Mapping[str, Any]],
    earlier: Sequence[Mapping[str, Any]], model: Model, attempts: int = 2,
) -> dict[str, Any]:
    """One block, retried with its problems named; what still fails is left out with its reason."""
    star, outline = record["context"], record["outline"]
    cards = name.endswith("cards")
    plan = json.dumps({"cards": outline["cards"], "exercises": outline["exercises"]}, ensure_ascii=False, indent=1)
    if cards:
        task = ("Schreibe jetzt die Erklärkarten des Plans, in der Reihenfolge des Plans, je in "
                "de, en, fr, it: title und body (body höchstens 900 Zeichen, mit den Formeln und "
                "einem kurzen Beispiel aus dem Alltag). Keine Bilder.")
    else:
        task = ("Schreibe jetzt diese Aufgaben des Plans (slot, questionType, Format, Schwierigkeit "
                "wie geplant; \"choice\" heisst multiple_choice, \"short\" heisst text_input):\n"
                + json.dumps(list(planned), ensure_ascii=False, indent=1) + "\n\n" + CONTRACT)
    base = (f"{_star_brief(star)}\n\nBestätigter Plan:\n{plan}\n\nWas die früheren Blöcke "
            f"schon enthalten:\n{_earlier(earlier)}\n\n{task}")
    calls, feedback, kept, left_out = [], "", [], []
    wanted = [] if cards else [p["slot"] for p in planned]
    for attempt in range(attempts):
        reply = model(GENERATE_SYSTEM, base + feedback, CARDS_SCHEMA if cards else EXERCISES_SCHEMA, 12000)
        calls.append(_usage(reply))
        if cards:
            items = list(reply.data.get("cards") or [])
            found = {index: card_problems(card) for index, card in enumerate(items)}
            if len(items) != len(outline["cards"]):
                found[-1] = [f"{len(items)} cards, the plan has {len(outline['cards'])}"]
        else:
            by_slot = {item.get("slot"): item for item in reply.data.get("exercises") or []}
            items = [by_slot[slot] for slot in wanted if slot in by_slot]
            found = {item["slot"]: exercise_problems(item) for item in items}
            for slot in wanted:
                if slot not in by_slot:
                    found[slot] = ["not written"]
            planned_by_slot = {p["slot"]: p for p in planned}
            for item in items:
                plan_item = planned_by_slot[item["slot"]]
                want = "multiple_choice" if plan_item["format"] == "choice" else "text_input"
                if item.get("type") != want:
                    found[item["slot"]].append(f"type {item.get('type')!r}, the plan says {want}")
        failing = {key: value for key, value in found.items() if value}
        if not failing:
            kept, left_out = items, []
            break
        if cards:
            kept, left_out = [], [{"card": key, "problems": value} for key, value in failing.items()]
        else:
            kept = [item for item in items if not found.get(item["slot"])]
            left_out = [{"slot": key, "problems": value} for key, value in failing.items()]
        feedback = ("\n\nDein letzter Entwurf dieses Blocks hatte diese Fehler; schreibe den ganzen Block "
                    "neu und behebe sie:\n" + json.dumps(failing, ensure_ascii=False))
    if not cards:
        planned_by_slot = {p["slot"]: p for p in planned}
        kept = [{**item, "questionType": planned_by_slot[item["slot"]]["questionType"],
                 "difficulty": planned_by_slot[item["slot"]]["difficulty"]} for item in kept]
    return {"star": star["unitId"], "block": name, "outlineHash": outline_hash(record),
            "items": kept, "leftOut": left_out, "calls": calls}


# ── check ────────────────────────────────────────────────────────────────────

CHECKS = {
    "answer": "Die Antwort ist exakt richtig (Wert, Einheit, Rundung, Lösungsweg).",
    "single_choice": "Eine Auswahlaufgabe hat genau eine richtige Option.",
    "standalone": "Der Aufgabentext ist ohne Lehrbuch verständlich und hat keine Spuren eines "
                  "chinesischen Lehrbuchs (Kapitel, Ausgabe, chinesische Gegebenheiten).",
    "judgeable": "Die Plattform kann sie heute bewerten: kurze Antwort oder eine Option, kein Bild nötig.",
    "equivalents": "acceptedAnswers listet alle üblichen richtigen Schreibweisen (Einheit mit/ohne "
                   "Leerzeichen zählt gleich; Einheitenname, Zahl ohne Einheit wenn passend), und keine falsche.",
    "translations": "en, fr, it sagen dasselbe wie de, mit derselben Antwort.",
}
VERDICTS = ("pass", "missing_equivalents", "doubtful", "reject")
CHECK_SYSTEM = (
    "Du prüfst Übungsaufgaben Physik einer Schweizer Lernplattform, unabhängig von anderen "
    "Prüfern. Für jede Aufgabe: die sechs Prüfungen\n"
    + "\n".join(f"- {code}: {text}" for code, text in CHECKS.items())
    + "\n\nUrteil: \"pass\" wenn alle sechs erfüllt sind; \"missing_equivalents\" wenn nur "
    "equivalents fehlt (dann in suggestedAccepted die fehlenden Schreibweisen, in der Sprache "
    "de); \"reject\" wenn die Aufgabe falsch oder unbrauchbar ist; sonst \"doubtful\". In "
    "failed die Codes der nicht erfüllten Prüfungen, in note kurz warum (deutsch). Rechne "
    "jede Rechenaufgabe selbst nach. Beurteile jede Aufgabe für sich; woher sie kommt, weisst "
    "du nicht und spielt keine Rolle."
)
CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": TEXT, "verdict": {"type": "string", "enum": list(VERDICTS)},
            "failed": {"type": "array", "items": {"type": "string", "enum": list(CHECKS)}},
            "note": TEXT, "suggestedAccepted": {"type": "array", "items": TEXT},
        },
        "required": ["id", "verdict", "failed"],
    }}},
    "required": ["verdicts"],
}


def _check_text(text: Mapping[str, Any]) -> dict[str, Any]:
    return {key: text[key] for key in ("prompt", "options", "correctAnswer", "acceptedAnswers", "explanation")
            if text.get(key) not in (None, [], "")}


def drafted_item(star: Mapping[str, Any], exercise: Mapping[str, Any]) -> dict[str, Any]:
    return {"star": star["unitId"], "starTitle": star["titles"]["de"], "type": exercise["type"],
            **{locale: _check_text(exercise[locale]) for locale in LOCALES}}


def imported_item(row: Mapping[str, Any], exercise: Mapping[str, Any], title: str) -> dict[str, Any]:
    de = {"prompt": exercise["prompt"], "options": exercise.get("options"),
          "correctAnswer": exercise["answerKey"], "acceptedAnswers": exercise.get("acceptedAnswers"),
          "explanation": exercise["explanation"]}
    texts = {"de": de, **(exercise.get("translations") or {})}
    return {"star": row["lesson"]["unitId"], "starTitle": title, "type": exercise["type"],
            **{locale: _check_text(texts.get(locale) or {}) for locale in LOCALES}}


def blind_pool(
    drafted: Sequence[tuple[str, dict[str, Any]]], imported: Sequence[tuple[str, dict[str, Any]]], seed: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Both sides mixed and renamed, so a checker cannot tell where an item comes from;
    the key says which is which."""
    tagged = [("drafted", ref, item) for ref, item in drafted] + [("imported", ref, item) for ref, item in imported]
    random.Random(seed).shuffle(tagged)
    pool, key = [], {}
    for index, (origin, ref, item) in enumerate(tagged, start=1):
        neutral = f"c{index:04d}"
        pool.append({"id": neutral, **item})
        key[neutral] = {"origin": origin, "ref": ref}
    return pool, key


def check_chunks(pool: Sequence[Mapping[str, Any]], size: int = CHECK_CHUNK) -> dict[str, list[dict[str, Any]]]:
    """The pool cut per star, so a checker sees one star at a time."""
    by_star: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in pool:
        by_star[item["star"]].append(dict(item))
    chunks = {}
    for star, items in sorted(by_star.items()):
        for index, start in enumerate(range(0, len(items), size), start=1):
            chunks[f"{star}-{index:02d}"] = items[start:start + size]
    return chunks


def run_checker(name: str, items: Sequence[Mapping[str, Any]], checker: str, model: Model) -> dict[str, Any]:
    ordered = list(items) if checker == "A" else list(reversed(items))
    shown = [{k: v for k, v in item.items() if k != "star"} for item in ordered]
    ids = [item["id"] for item in ordered]
    calls, feedback = [], ""
    for _attempt in range(2):
        reply = model(CHECK_SYSTEM, "Aufgaben:\n" + json.dumps(shown, ensure_ascii=False, indent=1) + feedback,
                      CHECK_SCHEMA, 16000)
        calls.append(_usage(reply))
        verdicts = {v.get("id"): v for v in reply.data.get("verdicts") or [] if v.get("verdict") in VERDICTS}
        missing = [i for i in ids if i not in verdicts]
        if not missing:
            return {"chunk": name, "checker": checker, "verdicts": [verdicts[i] for i in ids], "calls": calls}
        feedback = f"\n\nIm letzten Durchgang fehlte ein gültiges Urteil für: {', '.join(missing)}. Beurteile alle."
    raise DraftError(f"{name}.{checker}: no verdict for {', '.join(missing)}")


def bucket(a: Mapping[str, Any], b: Mapping[str, Any]) -> str:
    """#422's buckets: both pass; both only missing equivalents; both reject; anything else doubtful."""
    pair = {a["verdict"], b["verdict"]}
    if pair == {"pass"}:
        return "pass"
    if pair == {"missing_equivalents"}:
        return "missing_equivalents"
    if pair == {"reject"}:
        return "reject"
    return "doubtful"


def verdicts(chunks: Mapping[str, Sequence[Mapping[str, Any]]], results: Mapping[str, Mapping[str, Any]],
             key: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    out = []
    for name, items in chunks.items():
        a = {v["id"]: v for v in results[f"{name}.A"]["verdicts"]}
        b = {v["id"]: v for v in results[f"{name}.B"]["verdicts"]}
        for item in items:
            va, vb = a[item["id"]], b[item["id"]]
            out.append({"id": item["id"], **key[item["id"]], "star": item["star"], "bucket": bucket(va, vb),
                        "disagree": va["verdict"] != vb["verdict"],
                        "failed": sorted(set(va.get("failed") or []) | set(vb.get("failed") or [])),
                        "notes": [va.get("note") or "", vb.get("note") or ""],
                        "suggestedAccepted": sorted(set(va.get("suggestedAccepted") or [])
                                                    | set(vb.get("suggestedAccepted") or []))})
    return out


# ── manifest ─────────────────────────────────────────────────────────────────


def _locale_exercise(text: Mapping[str, Any], kind: str, extra: Sequence[str] = ()) -> dict[str, Any]:
    out = {"prompt": _text(text["prompt"]), "correctAnswer": _text(text["correctAnswer"]),
           "explanation": _text(text["explanation"])}
    if kind == "multiple_choice":
        out["options"] = [_text(o) for o in text["options"]]
    else:
        key = answer_judging.normalize_answer(out["correctAnswer"])
        accepted = dict.fromkeys(_text(a) for a in [*(text.get("acceptedAnswers") or []), *extra])
        out["acceptedAnswers"] = [
            a for a in accepted if a and answer_judging.normalize_answer(a) != key
        ][:answer_judging.MAX_ACCEPTED_ANSWERS]
    return out


def manifest_rows(
    stars: Mapping[str, Mapping[str, Any]], drafted: Mapping[str, Sequence[Mapping[str, Any]]],
    cards: Mapping[str, Sequence[Mapping[str, Any]]], extra_accepted: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    """One draft practice set per star and question type; the star's cards go on its first set."""
    rows = []
    type_order = [slug for slug, _titles, _scope in catalog.QUESTION_TYPES[SUBJECT]]
    for unit_id, exercises in sorted(drafted.items()):
        star = stars[unit_id]
        by_type: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for exercise in exercises:
            by_type[exercise["questionType"]].append(exercise)
        first = True
        for slug in [s for s in type_order if s in by_type]:
            skill = catalog.skill_id(unit_id, slug)
            titles = catalog.question_type_titles(SUBJECT, slug)
            items = sorted(by_type[slug], key=lambda e: e["slot"])
            lesson: dict[str, Any] = {
                "title": f"{titles['de']} · KI-Entwurf", "objective": star["description"],
                "description": star["description"], "subjectId": SUBJECT, "topicId": star["topicId"],
                "unitId": unit_id, "gradeLevel": star["gradeLevel"], "difficulty": "practice",
                "estimatedMinutes": max(5, MINUTES_PER_EXERCISE * len(items)), "language": "de",
                "order": FIRST_ORDER + type_order.index(slug) * 10,
                "extension": catalog.is_extension(SUBJECT, slug), "requiresPoints": [],
                "tags": ["ai-draft"],
            }
            if first and cards.get(unit_id):
                lesson["sections"] = [
                    {"id": f"card-{index}", "title": card["de"]["title"], "body": card["de"]["body"],
                     "translations": {loc: {"title": card[loc]["title"], "body": card[loc]["body"]}
                                      for loc in LOCALES if loc != "de"}}
                    for index, card in enumerate(cards[unit_id], start=1)
                ]
            first = False
            rows.append({"publicLessonId": f"{skill}--ki", "publish": False, "lesson": lesson, "exercises": [
                _manifest_exercise(unit_id, exercise, order, skill, extra_accepted.get(_ref(unit_id, exercise), ()))
                for order, exercise in enumerate(items, start=1)
            ]})
    return rows


def _ref(unit_id: str, exercise: Mapping[str, Any]) -> str:
    return f"{unit_id}--ki-q{exercise['slot']:02d}"


def _manifest_exercise(unit_id: str, exercise: Mapping[str, Any], order: int, skill: str,
                       extra: Sequence[str]) -> dict[str, Any]:
    kind = exercise["type"]
    german = _locale_exercise(exercise["de"], kind, extra)
    row: dict[str, Any] = {
        "exerciseId": _ref(unit_id, exercise), "type": kind, "difficulty": exercise["difficulty"],
        "order": order, "prompt": german["prompt"], "answerKey": german["correctAnswer"],
        "explanation": german["explanation"], "skills": [skill], "tags": ["ai-draft"],
        "translations": {loc: _locale_exercise(exercise[loc], kind) for loc in LOCALES if loc != "de"},
    }
    if "options" in german:
        row["options"] = german["options"]
    if german.get("acceptedAnswers"):
        row["acceptedAnswers"] = german["acceptedAnswers"]
    return row


def local_dry_run(manifests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each manifest through the real dry run, against a table held in memory and seeded with
    the knowledge base stars the way the seed writes them. Nothing reaches AWS."""
    sys.path.insert(0, str(ROOT / "tests"))
    from fakes.dynamodb import FakeTable  # noqa: PLC0415 - the suite's table double

    from scripts import seed_practice
    from stoa.db import table as db_table
    from stoa.services import curriculum_migration_service, curriculum_ops_service

    table = FakeTable()
    subjects, topics, units = seed_practice.knowledge_base_rows(live=False)
    table.seed(
        *({"PK": "PRACTICE", "SK": f"SUBJECT#{s['subject_id']}", **s} for s in subjects),
        *({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics),
        *({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units),
    )
    db_table.install(table)
    operator = {"sub": "ai-lesson-draft", "role": "admin", "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    }}
    try:
        results = []
        for manifest in manifests:
            preview = curriculum_migration_service.dry_run(dict(manifest), operator)
            results.append({
                "summary": preview["summary"], "publishReady": preview["publishReady"],
                "issues": [{"row": r["publicLessonId"], "action": r["action"], "issues": r["validationIssues"],
                            "conflicts": r["conflicts"]}
                           for r in preview["rows"] if r["validationIssues"] or r["conflicts"]],
            })
        return results
    finally:
        db_table.install(None)


# ── the report ───────────────────────────────────────────────────────────────

BUCKET_NAMES = {"pass": "通过", "missing_equivalents": "只缺等值写法", "doubtful": "存疑", "reject": "剔除"}


def _rate(n: int, total: int) -> str:
    return f"{n} ({n / total:.0%})" if total else "0"


def comparison(verdict_rows: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]],
               titles: Mapping[str, str]) -> str:
    """The comparison table, the failure reasons, and each star's cost and time, as markdown."""
    lines = ["| 来源 | 题数 | " + " | ".join(BUCKET_NAMES.values()) + " | 两位意见不一致 |",
             "| --- | ---: | " + " | ".join("---:" for _ in BUCKET_NAMES) + " | ---: |"]
    for origin, name in (("drafted", "AI 起草"), ("imported", "导入草稿")):
        rows = [v for v in verdict_rows if v["origin"] == origin]
        counts = Counter(v["bucket"] for v in rows)
        lines.append(f"| {name} | {len(rows)} | " + " | ".join(_rate(counts[b], len(rows)) for b in BUCKET_NAMES)
                     + f" | {_rate(sum(v['disagree'] for v in rows), len(rows))} |")
    lines += ["", "**存疑和剔除的原因**（至少一位核对者标了这一项；一道题可以有几项）", "",
              "| 检查项 | AI 起草 | 导入草稿 |", "| --- | ---: | ---: |"]
    for code in CHECKS:
        counts = [sum(1 for v in verdict_rows if v["origin"] == o and v["bucket"] in {"doubtful", "reject"}
                      and code in v["failed"]) for o in ("drafted", "imported")]
        lines.append(f"| {code} | {counts[0]} | {counts[1]} |")
    lines += ["", "**每颗星**（AI 起草：大纲 + 生成 + 它那几块核对按题数分摊；导入：只有核对分摊）", "",
              "| 星 | AI 题 / 通过 | 导入题 / 通过 | AI 输入 tok | AI 输出 tok | AI 费用 USD | AI 用时 s | 导入核对费用 USD |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for unit_id in sorted({v["star"] for v in verdict_rows}):
        mine = [v for v in verdict_rows if v["star"] == unit_id]
        spend = {o: {"in": 0, "out": 0, "usd": 0.0, "s": 0.0} for o in ("drafted", "imported")}
        for entry in ledger:
            if entry["star"] != unit_id:
                continue
            for origin, share in entry["shares"].items():
                s = spend[origin]
                s["in"] += entry["inputTokens"] * share
                s["out"] += entry["outputTokens"] * share
                s["usd"] += (entry["usd"] or 0) * share
                s["s"] += entry["seconds"] * share
        d = [v for v in mine if v["origin"] == "drafted"]
        i = [v for v in mine if v["origin"] == "imported"]
        lines.append(
            f"| {titles.get(unit_id, unit_id)} | {len(d)} / {sum(v['bucket'] == 'pass' for v in d)} | "
            f"{len(i)} / {sum(v['bucket'] == 'pass' for v in i)} | {spend['drafted']['in']:,.0f} | "
            f"{spend['drafted']['out']:,.0f} | {spend['drafted']['usd']:.2f} | {spend['drafted']['s']:,.0f} | "
            f"{spend['imported']['usd']:.2f} |"
        )
    return "\n".join(lines)


# ── the work folder ──────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


@dataclass
class Work:
    root: Path

    def outline(self, star: str) -> Path:
        return self.root / "outline" / f"{star}.json"

    def confirmed(self, star: str) -> Path:
        return self.root / "outline" / f"{star}.confirmed.json"

    def block(self, star: str, name: str) -> Path:
        return self.root / "blocks" / star / f"{name}.json"

    def check(self, name: str) -> Path:
        return self.root / "check" / f"{name}.json"


def _confirmed_record(work: Work, star: str) -> dict[str, Any]:
    if not work.outline(star).exists():
        raise DraftError(f"{star}: no outline yet; run outline first")
    record = _read(work.outline(star))
    if not work.confirmed(star).exists():
        raise DraftError(f"{star}: the outline is not confirmed; a person runs confirm after reading it")
    if _read(work.confirmed(star))["outlineHash"] != outline_hash(record):
        raise DraftError(f"{star}: the outline changed after it was confirmed; confirm it again")
    return record


def _run_jobs(jobs: Sequence[tuple[Path, Callable[[], dict[str, Any]]]], workers: int,
              fail: str | None) -> list[str]:
    """Run each job whose file is missing and write its file the moment it returns;
    a job that fails leaves no file and does not stop the others."""
    errors: list[str] = []

    def run(path: Path, job: Callable[[], dict[str, Any]]) -> None:
        try:
            if fail and path.stem == fail:
                raise DraftError("failed on purpose (--fail)")
            _write(path, job())
            print(f"wrote {path}")
        except Exception as exc:  # noqa: BLE001 - one block's failure must not lose the others
            errors.append(f"{path}: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(lambda pair: run(*pair), jobs))
    return errors


def _guard(planned: Sequence[tuple[str, int]], args: argparse.Namespace) -> None:
    """Refuse a run that calls the model without the operator's yes or with too many calls."""
    calls = sum(n for _step, n in planned)
    price = PRICES.get(args.model)
    estimate = None if price is None else sum(
        n * (ESTIMATE_TOKENS[step][0] * price[0] + ESTIMATE_TOKENS[step][1] * price[1]) / 1_000_000
        for step, n in planned
    )
    usd = "unknown" if estimate is None else f"about {estimate:.2f} USD (retries can double it)"
    print(f"{calls} model calls planned with {args.model}: {usd}")
    if args.plan:
        raise SystemExit(0)
    if calls > args.max_calls:
        raise DraftError(f"{calls} calls planned, more than --max-calls {args.max_calls}")
    if not args.confirm_cost:
        raise DraftError("a run that calls the model needs --confirm-cost")


def _ledger(work: Work) -> list[dict[str, Any]]:
    """Every call made, with the star it was for and how its cost is shared between the two
    sides: outline and generation are the drafted side's, a check chunk is shared by item."""
    ledger = []

    def add(star: str, calls: Iterable[Mapping[str, Any]], shares: Mapping[str, float]) -> None:
        for call in calls:
            ledger.append({"star": star, **call, "shares": dict(shares),
                           "usd": cost_usd(call["model"], call["inputTokens"], call["outputTokens"])})

    for path in sorted((work.root / "outline").glob("*.json")):
        if not path.name.endswith(".confirmed.json"):
            record = _read(path)
            add(record["star"], record["calls"], {"drafted": 1.0})
    for path in sorted((work.root / "blocks").glob("*/*.json")):
        block = _read(path)
        add(block["star"], block["calls"], {"drafted": 1.0})
    key_path = work.check("key")
    if key_path.exists():
        key, chunks = _read(key_path), _read(work.check("chunks"))
        for name, items in chunks.items():
            counts = Counter(key[item["id"]]["origin"] for item in items)
            shares = {origin: n / len(items) for origin, n in counts.items()}
            for checker in "AB":
                path = work.check(f"{name}.{checker}")
                if path.exists():
                    add(items[0]["star"], _read(path)["calls"], shares)
    return ledger


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def main(argv: Sequence[str] | None = None, model: Model | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["outline", "confirm", "generate", "check", "manifest", "dry-run",
                                            "report"])
    parser.add_argument("--work", type=Path, required=True, help="the folder every step keeps its files in")
    parser.add_argument("--star", action="append", default=[], help="a star's unit id, repeatable")
    parser.add_argument("--imported", type=Path, help="the knowledge base manifests (manifest-*.json)")
    parser.add_argument("--by", default="", help="confirm: who confirmed the outline")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--checker-model", help="the checkers' model, if not --model")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--account-id", default=DEFAULT_AWS_ACCOUNT_ID)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=441, help="how the blind pool is shuffled")
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--confirm-cost", action="store_true", help="required for a run that calls the model")
    parser.add_argument("--plan", action="store_true", help="print the calls and the estimate, call nothing")
    parser.add_argument("--fail", help="the file stem of one call to fail on purpose")
    args = parser.parse_args(argv)
    work = Work(args.work)
    stars_file = work.root / "stars.json"
    if args.star and args.command == "outline":
        rows = imported_rows(args.imported, args.star)
        known = _read(stars_file) if stars_file.exists() else {}
        _write(stars_file, {**known, **{unit: star_context(unit, rows) for unit in args.star}})
    if not stars_file.exists():
        raise DraftError("name the stars with --star the first time")
    stars: dict[str, dict[str, Any]] = _read(stars_file)

    def the_model(checker: bool = False) -> Model:
        if model is not None:
            return model
        model_id = (args.checker_model or args.model) if checker else args.model
        return bedrock_model(args.profile, args.region, args.account_id, model_id)

    if args.command == "outline":
        todo = [unit for unit in stars if not work.outline(unit).exists()]
        _guard([("outline", len(todo))], args)
        call = the_model()
        errors = _run_jobs([(work.outline(u), lambda u=u: make_outline(stars[u], call)) for u in todo],
                           args.workers, args.fail)
        records = [_read(work.outline(u)) for u in stars if work.outline(u).exists()]
        (work.root / "review-outlines.md").write_text(review_package(records), encoding="utf-8", newline="\n")
        print(f"review package: {work.root / 'review-outlines.md'}")
    elif args.command == "confirm":
        if not args.by:
            raise DraftError("confirm needs --by: who read and confirmed the outlines")
        for unit in args.star or list(stars):
            record = _read(work.outline(unit))
            _write(work.confirmed(unit), {"star": unit, "outlineHash": outline_hash(record), "by": args.by,
                                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            print(f"confirmed {unit}")
        errors = []
    elif args.command == "generate":
        records = {unit: _confirmed_record(work, unit) for unit in stars}
        todo = [(unit, name, planned) for unit, record in records.items()
                for name, planned in blocks_of(record["outline"]) if not work.block(unit, name).exists()]
        _guard([("generate", len(todo))], args)
        call = the_model()
        # A block is told what the earlier blocks of its star hold, so a star's blocks go
        # one after another; the stars go side by side.

        def star_job(unit: str) -> list[str]:
            failed = []
            for name, planned in blocks_of(records[unit]["outline"]):
                path = work.block(unit, name)
                if path.exists():
                    continue
                earlier = [_read(p) for p in sorted(path.parent.glob("*.json")) if p.stem < name]
                failed += _run_jobs([(path, lambda n=name, p=planned, e=earlier:
                                      make_block(records[unit], n, p, e, call))], 1, args.fail)
                if failed:
                    break  # the later blocks build on this one
            return failed

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            errors = [e for found in pool.map(star_job, {u for u, _n, _p in todo}) for e in found]
    elif args.command == "check":
        if not work.check("key").exists():
            drafted, imported = [], []
            for unit in stars:
                record = _confirmed_record(work, unit)
                for name, _planned in blocks_of(record["outline"])[1:]:
                    if not work.block(unit, name).exists():
                        raise DraftError(f"{unit}: block {name} not generated yet")
                    drafted += [(_ref(unit, e), drafted_item(stars[unit], e))
                                for e in _read(work.block(unit, name))["items"]]
            for row in imported_rows(args.imported, stars):
                title = stars[row["lesson"]["unitId"]]["titles"]["de"]
                imported += [(e["exerciseId"], imported_item(row, e, title)) for e in row["exercises"]]
            if not imported:
                raise DraftError("no imported drafts of these stars; name the manifests with --imported")
            pool, key = blind_pool(drafted, imported, args.seed)
            _write(work.check("chunks"), check_chunks(pool))
            _write(work.check("key"), key)
        chunks = _read(work.check("chunks"))
        todo = [(name, checker) for name in chunks for checker in "AB" if not work.check(f"{name}.{checker}").exists()]
        _guard([("check", len(todo))], args)
        call = the_model(checker=True)
        errors = _run_jobs([(work.check(f"{n}.{c}"), lambda n=n, c=c: run_checker(n, chunks[n], c, call))
                            for n, c in todo], args.workers, args.fail)
        if not errors:
            results = {f"{n}.{c}": _read(work.check(f"{n}.{c}")) for n in chunks for c in "AB"}
            _write(work.check("verdicts"), verdicts(chunks, results, _read(work.check("key"))))
            print(f"verdicts: {work.check('verdicts')}")
    elif args.command == "manifest":
        rows = _read(work.check("verdicts"))
        keep = {v["ref"]: v for v in rows if v["origin"] == "drafted"
                and v["bucket"] in {"pass", "missing_equivalents"}}
        drafted: dict[str, list[dict[str, Any]]] = defaultdict(list)
        cards: dict[str, list[dict[str, Any]]] = {}
        left: list[dict[str, Any]] = []
        for unit in stars:
            record = _confirmed_record(work, unit)
            for name, _planned in blocks_of(record["outline"]):
                block = _read(work.block(unit, name))
                left += [{"star": unit, "block": name, **item} for item in block["leftOut"]]
                if name.endswith("cards"):
                    cards[unit] = block["items"]
                    continue
                for exercise in block["items"]:
                    if _ref(unit, exercise) in keep:
                        drafted[unit].append(exercise)
        extra = {ref: v["suggestedAccepted"] for ref, v in keep.items() if v["bucket"] == "missing_equivalents"}
        made = manifest_rows(stars, drafted, cards, extra)
        manifest = {"source": {"sourceId": SOURCE_ID, "sourceVersion": _git_head(), "sourceType": "ai_draft"},
                    "operatorNote": OPERATOR_NOTE, "lessons": made}
        _write(work.root / "manifests" / "manifest-001.json", manifest)
        _write(work.root / "manifests" / "report.json", {
            "practiceSets": len(made), "exercises": sum(len(r["exercises"]) for r in made),
            "notCarried": [{"ref": v["ref"], "bucket": v["bucket"], "failed": v["failed"], "notes": v["notes"]}
                           for v in rows if v["origin"] == "drafted" and v["ref"] not in keep],
            "leftOutWhenGenerated": left,
        })
        print(f"{len(made)} practice sets, {sum(len(r['exercises']) for r in made)} exercises")
        errors = []
    elif args.command == "dry-run":
        manifests = [_read(p) for p in sorted((work.root / "manifests").glob("manifest-*.json"))]
        results = local_dry_run(manifests)
        _write(work.root / "dry-run.json", results)
        for result in results:
            print(json.dumps(result["summary"]), "publishReady" if result["publishReady"] else "NOT READY")
        errors = [json.dumps(r["issues"], ensure_ascii=False)[:400] for r in results if not r["publishReady"]]
    else:
        titles = {unit: star["titles"]["de"] for unit, star in stars.items()}
        text = comparison(_read(work.check("verdicts")), _ledger(work), titles)
        (work.root / "report.md").write_text(text + "\n", encoding="utf-8", newline="\n")
        print(text)
        errors = []
    for error in errors:
        print(f"FAILED {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DraftError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
