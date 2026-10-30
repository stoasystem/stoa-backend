"""A Bedrock runtime double for the Ask answer (#176).

`FakeBedrock` is the model connection as boto3 hands it out: it counts tokens,
answers buffered and streamed, and records every request body it was sent.
Each call takes the next of `outcomes`: a dict is written back as the model's
JSON, a string as the model's raw text, an exception is raised from the call.
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
        text = self._next(body)
        payload = {
            "id": f"msg_{len(self.requests)}",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": text}],
            "usage": {"input_tokens": 90, "output_tokens": 30},
        }
        return {
            "ResponseMetadata": {"RequestId": f"req-{len(self.requests)}"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }

    def invoke_model_with_response_stream(
        self, *, modelId: str, body: str  # noqa: N803
    ) -> dict[str, Any]:
        text = self._next(body)
        events = [
            {"type": "message_start", "message": {
                "id": f"msg_{len(self.requests)}", "model": modelId,
                "usage": {"input_tokens": 90},
            }},
            # Cut in two, so the steps are found in a partly received answer.
            {"type": "content_block_delta", "delta": {"text": text[: len(text) // 2]}},
            {"type": "content_block_delta", "delta": {"text": text[len(text) // 2 :]}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 30}},
        ]
        return {
            "ResponseMetadata": {"RequestId": f"req-{len(self.requests)}"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }

    def _next(self, body: str) -> str:
        self.requests.append(json.loads(body))
        if self.gate is not None:
            self.gate.wait(5)
        outcome = self.outcomes.pop(0) if self.outcomes else self.answer
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, str):
            return outcome
        return json.dumps(outcome, ensure_ascii=False)


def answer_without_allowance(monkeypatch: Any, model: FakeBedrock) -> FakeBedrock:
    """Ask `model` for the conversation answer with the token allowance left out.

    For tests about what reaches the prompt, which stub the table the allowance
    and the call record would be written to: the worker's allowance client
    hands the request straight to `model`, and the answer carries no allowance
    to settle.
    """
    from stoa.routers import conversations

    class _Unmetered(conversations._ConversationAllowanceBedrockClient):
        def invoke_model(self, **kwargs: Any) -> Any:
            return getattr(model, self._invocation_method)(**kwargs)

    monkeypatch.setattr(conversations, "_ConversationAllowanceBedrockClient", _Unmetered)
    monkeypatch.setattr(
        conversations, "_message_allowance_metadata_from_provider", lambda *_a, **_k: None
    )
    return model
