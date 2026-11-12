"""The model's reply as the Bedrock runtime hands back a forced tool call (#412).

The Ask answer is asked for as one call of the tool the request names in
`tool_choice`, so a reply is a `tool_use` block, buffered, or the tool's input
streamed as `input_json_delta` pieces. A fake model writes its answer as the
tool's input text: a dict is that text as JSON; a string is taken as it is, so
a test can stream input that never closes. `Prose` is a reply that calls no
tool at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

FALLBACK_TOOL_NAME = "give_answer"


@dataclass(frozen=True)
class Prose:
    """A reply of plain text, without the tool call it was asked for."""

    text: str


def tool_name(request: dict[str, Any]) -> str:
    """The tool the request forces, as the model would call it."""
    choice = request.get("tool_choice")
    if isinstance(choice, dict) and isinstance(choice.get("name"), str):
        return choice["name"]
    return FALLBACK_TOOL_NAME


def input_text(outcome: Any) -> str:
    """The tool input a fake answers with, as the text the model writes."""
    if isinstance(outcome, str):
        return outcome
    return json.dumps(outcome, ensure_ascii=False)


def content(outcome: Any, request: dict[str, Any]) -> list[dict[str, Any]]:
    """The `content` of a buffered reply."""
    if isinstance(outcome, Prose):
        return [{"type": "text", "text": outcome.text}]
    text = input_text(outcome)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        # A buffered reply carries the input already read; what does not read
        # as an object stands as the model's text.
        return [{"type": "text", "text": text}]
    return [{"type": "tool_use", "id": "toolu_fake", "name": tool_name(request), "input": value}]


def stream_events(outcome: Any, request: dict[str, Any], *, pieces: int = 2) -> list[dict[str, Any]]:
    """The content events of a streamed reply, the input cut into `pieces`."""
    if isinstance(outcome, Prose):
        return [
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": outcome.text}},
            {"type": "content_block_stop", "index": 0},
        ]
    text = input_text(outcome)
    size = max(1, -(-len(text) // max(1, pieces)))
    return [
        {"type": "content_block_start", "index": 0, "content_block": {
            "type": "tool_use", "id": "toolu_fake", "name": tool_name(request), "input": {},
        }},
        *(
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": text[start : start + size]}}
            for start in range(0, len(text), size)
        ),
        {"type": "content_block_stop", "index": 0},
    ]
