"""A Bedrock runtime double for the Ask answer (#176).

`FakeBedrock` is the model connection as boto3 hands it out: it counts tokens,
answers buffered and streamed, and records every request body it was sent.
Each call takes the next of `outcomes`: a dict is the input of the tool call
the request forces, a string the raw text of that input (#412), a
`model_reply.Prose` a reply that calls no tool, an exception is raised from
the call.
With none left it answers with `answer` (`ANSWER` unless given). An
`Unsent(exception)` is raised while the tokens are counted instead, before the
allowance client records the call: the model was never asked. A `gate`, when
set, holds every answer until it opens.

Only the provider is stood in for: the prompt, the reply's checks and the
allowance client in front of it run as production runs them.
"""

from __future__ import annotations

import io
import json
import threading
from typing import Any

from fakes import model_reply

ANSWER: dict[str, Any] = {
    "language": "de",
    "steps": ["Zähler und Nenner durch den ggT teilen"],
    "answer": "So kürzt man einen Bruch.",
    "hints": ["Was ist der ggT von 6 und 8?"],
    "similar_exercises": [],
    "knowledge_points": ["Brüche kürzen"],
    "suggest_teacher": False,
}


class Unsent:
    """An outcome that ends the attempt before the model is asked."""

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception


class FakeBedrock:
    def __init__(self, *outcomes: Any, answer: dict[str, Any] | None = None) -> None:
        self.outcomes: list[Any] = list(outcomes)
        self.answer = answer or ANSWER
        self.requests: list[dict[str, Any]] = []
        self.counted = 0
        self.gate: threading.Event | None = None
        # How many `input_json_delta` pieces a streamed answer is cut into.
        self.pieces = 2

    # ── What a test reads back ───────────────────────────────────────────────

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Every request body the model was sent, in order."""
        return self.requests

    def system(self, index: int = -1) -> str:
        return self.requests[index]["system"]

    def student_turn(self, index: int = -1) -> str:
        """The text of the student's latest turn, images left out."""
        content = self.requests[index]["messages"][-1]["content"]
        if isinstance(content, str):
            return content
        return "".join(block.get("text", "") for block in content if block.get("type") == "text")

    def images(self, index: int = -1) -> list[dict[str, Any]]:
        content = self.requests[index]["messages"][-1]["content"]
        if isinstance(content, str):
            return []
        return [block for block in content if block.get("type") == "image"]

    # ── The runtime ──────────────────────────────────────────────────────────

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        self.counted += 1
        if self.outcomes and isinstance(self.outcomes[0], Unsent):
            raise self.outcomes.pop(0).exception
        return {
            "inputTokens": 90,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": f"count-{self.counted}"},
        }

    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]:  # noqa: N803
        outcome = self._next(body)
        payload = {
            "id": f"msg_{len(self.requests)}",
            "model": modelId,
            "stop_reason": "tool_use",
            "content": model_reply.content(outcome, self.requests[-1]),
            "usage": {"input_tokens": 90, "output_tokens": 30},
        }
        return {
            "ResponseMetadata": {"RequestId": f"req-{len(self.requests)}"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }

    def invoke_model_with_response_stream(
        self, *, modelId: str, body: str  # noqa: N803
    ) -> dict[str, Any]:
        outcome = self._next(body)
        events = [
            {"type": "message_start", "message": {
                "id": f"msg_{len(self.requests)}", "model": modelId,
                "usage": {"input_tokens": 90},
            }},
            # Cut in pieces, so the steps are found in a partly received answer.
            *model_reply.stream_events(outcome, self.requests[-1], pieces=self.pieces),
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
             "usage": {"output_tokens": 30}},
        ]
        return {
            "ResponseMetadata": {"RequestId": f"req-{len(self.requests)}"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }

    def _next(self, body: str) -> Any:
        self.requests.append(json.loads(body))
        if self.gate is not None:
            self.gate.wait(5)
        outcome = self.outcomes.pop(0) if self.outcomes else self.answer
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
