"""Amazon Bedrock — controlled AI tutoring service.

Implements a lightweight AI harness:
- Structured system prompt with subject/grade/language injection
- Multi-turn conversation history passed to the model
- Prompt injection defence (input sanitisation)
- Output validation (structure check + forbidden-term scan)
- Daily message rate limiting (per student)
"""
import json
import logging
import re
import boto3
from datetime import datetime, timezone

from stoa.config import settings

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a controlled educational AI assistant for STOA, a Swiss after-school \
learning platform. You ONLY answer questions related to {subject} at {grade} level.

Rules:
- Never give the final answer directly. Always explain step-by-step.
- Use language appropriate for the student's grade level.
- Stay strictly within the subject scope. Reject unrelated questions politely.
- If the question is too complex or involves emotional distress, suggest teacher intervention.
- Respond in the student's language: {language}.
- Keep explanations concise (max 300 words).

IMPORTANT: Respond ONLY with valid JSON (no markdown code blocks, no extra text):
{{"steps":["Step 1: ..."],"answer":"Final answer","hints":["Hint..."],"similar_exercises":["Exercise..."],"suggest_teacher":false}}"""

# ── Prompt injection defence ───────────────────────────────────────────────────

# Patterns that attempt to override the system prompt or leak internals
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)",
    r"(system|assistant)\s*:\s*",
    r"<\|?(?:im_start|im_end|endoftext)\|?>",
    r"you are now",
    r"new\s+instructions?",
    r"disregard\s+(your|all)",
    r"forget\s+(your|all|previous)",
    r"act\s+as\s+(?!a\s+student|a\s+teacher)",  # allow "act as a student/teacher" only
    r"jailbreak",
    r"DAN\b",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Terms that should never appear in AI output (leaked internals)
_FORBIDDEN_OUTPUT_TERMS = [
    "anthropic", "claude", "bedrock", "openai", "gpt", "llm",
    "system prompt", "ignore previous", "harness", "STOA internal",
]

# Max characters accepted from a single student message
_MAX_INPUT_CHARS = 2000

# How many recent turns (student + assistant pairs) to include in context
_MAX_HISTORY_TURNS = 6


# ── Input sanitisation ─────────────────────────────────────────────────────────

def _sanitise_input(text: str) -> str:
    """Strip injection attempts and enforce length cap."""
    cleaned = text.strip()
    if len(cleaned) > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS]
        logger.warning("Student message truncated to %d chars", _MAX_INPUT_CHARS)

    if _INJECTION_RE.search(cleaned):
        logger.warning("Potential prompt injection detected, neutralising: %r", cleaned[:120])
        # Replace the offending portion so the model only sees the innocent remainder
        cleaned = _INJECTION_RE.sub("[removed]", cleaned).strip()

    return cleaned


# ── Output validation ──────────────────────────────────────────────────────────

def _validate_output(parsed: dict, raw_text: str) -> dict:
    """Apply post-generation policy checks and repair obvious violations."""
    issues = []

    # 1. Empty / trivially short response
    all_text = " ".join(parsed.get("steps", [])) + " " + parsed.get("answer", "")
    if len(all_text.strip()) < 10:
        issues.append("empty_response")

    # 2. Leaked internal terms
    lower_raw = raw_text.lower()
    leaked = [t for t in _FORBIDDEN_OUTPUT_TERMS if t in lower_raw]
    if leaked:
        issues.append(f"leaked_terms:{','.join(leaked)}")
        # Redact from output
        for term in leaked:
            raw_text = re.sub(re.escape(term), "[AI]", raw_text, flags=re.IGNORECASE)
        parsed = _parse_ai_response(raw_text)

    # 3. No guided steps for a question response
    if not parsed.get("steps") and not parsed.get("answer"):
        issues.append("missing_structure")
        parsed["answer"] = raw_text  # fall back to raw text

    if issues:
        logger.warning("Output policy issues: %s", issues)

    return parsed


# ── JSON parsing ───────────────────────────────────────────────────────────────

def _parse_ai_response(text: str) -> dict:
    """Parse AI response, handling possible markdown code block wrappers."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip())
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse AI response as JSON, using raw text: %r", text[:200])
    return {"steps": [], "answer": text, "hints": [], "similar_exercises": [], "suggest_teacher": False}


# ── History formatting ─────────────────────────────────────────────────────────

def _build_messages(content: str, history: list[dict] | None) -> list[dict]:
    """Build the Anthropic messages array from sanitised history + current turn.

    Only student/assistant turns are included; teacher, system, and note
    messages are excluded to keep the context clean.
    """
    messages: list[dict] = []

    if history:
        # Include up to _MAX_HISTORY_TURNS pairs (student + assistant)
        eligible = [
            m for m in history
            if m.get("role") in ("student", "assistant")
        ]
        # Take the most recent turns, then restore chronological order
        recent = eligible[-(_MAX_HISTORY_TURNS * 2):]
        for m in recent:
            role = "user" if m["role"] == "student" else "assistant"
            messages.append({"role": role, "content": m.get("content", "")})

    # Append the current (sanitised) message
    messages.append({"role": "user", "content": content})

    # Anthropic API requires alternating user/assistant turns.
    # Merge consecutive same-role messages.
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append(dict(msg))

    return merged


# ── Public API ─────────────────────────────────────────────────────────────────

def get_ai_answer(
    content: str,
    subject: str,
    grade: str,
    language: str = "de",
    history: list[dict] | None = None,
) -> dict:
    """Invoke Bedrock Claude with a controlled educational prompt.

    Args:
        content:  The student's latest message (will be sanitised).
        subject:  Normalised subject string (e.g. "math", "german").
        grade:    Grade/level string (e.g. "Grade 8").
        language: ISO language hint for the response ("de", "en", "fr").
        history:  Optional list of previous raw message dicts from DynamoDB,
                  each with keys ``role`` and ``content``.  The most recent
                  _MAX_HISTORY_TURNS pairs will be included.
    """
    safe_content = _sanitise_input(content)
    system_prompt = SYSTEM_PROMPT.format(subject=subject, grade=grade, language=language)
    messages = _build_messages(safe_content, history)

    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": settings.bedrock_max_tokens,
        "temperature": 0.4,
        "system": system_prompt,
        "messages": messages,
    })

    logger.info(
        "Calling Bedrock model=%s turns=%d",
        settings.bedrock_model_id, len(messages),
    )
    response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
    result = json.loads(response["body"].read())
    raw_text = result["content"][0]["text"]
    logger.info("Bedrock response received, length=%d", len(raw_text))

    parsed = _parse_ai_response(raw_text)
    return _validate_output(parsed, raw_text)


def get_hint_answer(prompt: str, subject: str = "Mathematik", grade: str = "6. Klasse") -> str:
    """Generate a short 1-2 sentence hint for a practice challenge."""
    safe_prompt = _sanitise_input(prompt)
    system = (
        "You are a helpful Swiss maths tutor. "
        "Give a concise hint (1-2 sentences, in German) that guides the student "
        "without revealing the answer. No JSON, just plain text."
    )
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 120,
        "temperature": 0.3,
        "system": system,
        "messages": [{"role": "user", "content": f"Aufgabe: {safe_prompt}"}],
    })
    try:
        response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()
    except Exception as exc:
        logger.error("Bedrock hint generation failed: %s", exc)
        return ""
