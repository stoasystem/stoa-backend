#!/usr/bin/env python3
"""Check that Bedrock takes the Ask answer's model-call request (#444).

A field Bedrock's CountTokens did not accept once failed every Ask question
in production (#430). Before a change to the `give_answer` tool or the Ask
prompt ships, an operator runs this once on an SSO session:

1. CountTokens on the body production counts before every answer (free; no
   student's allowance is touched).
2. With `--invoke` only: InvokeModelWithResponseStream, the streamed call
   production makes, on the body production sends, with `max_tokens` cut to 1
   and nothing else changed. It costs the input tokens and one output token
   (well under a cent); no answer is written.

Both bodies are the ones `ask_answer.answer` builds - the system prompt, the
tool with the star to go to, a synthetic star map and practice context with a
recent mistake - captured on their way to the model, so the probe checks what
production sends rather than a copy of it. No real person's data is in them.
Only token counts, stop reasons and Bedrock's own error text are printed.

    python scripts/probe_ask_answer_request.py --profile <SSO profile> [--invoke]
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import sys
import time
from typing import Any

from stoa import config
from stoa.services import ask_answer, model_call
from stoa.services.ai_service import AIInvocationFailure
from stoa.services.model_call.adapter import Adapter, MalformedStream, ProviderError

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
_PROBE_SECONDS = 60

# A synthetic question beside a synthetic exercise: every name and text is made up.
SYNTHETIC_STAR_MAP: list[dict[str, str]] = [
    {
        "ref": "k1",
        "unitId": "unit-synthetic-1",
        "name": "Brüche addieren",
        "subjectId": "math",
        "topicId": "topic-synthetic",
        "topicName": "Brüche",
        "state": "in_progress",
    },
    {
        "ref": "k2",
        "unitId": "unit-synthetic-2",
        "name": "Brüche kürzen",
        "subjectId": "math",
        "topicId": "topic-synthetic",
        "topicName": "Brüche",
        "state": "ready",
    },
]
SYNTHETIC_PRACTICE_CONTEXT: dict[str, Any] = {
    "challengeId": "challenge-synthetic",
    "challengePrompt": "Berechne 1/2 + 1/3.",
    "unitId": "unit-synthetic-1",
    "recentMistakes": [
        {
            "challengeId": "challenge-synthetic",
            "prompt": "Berechne 1/2 + 1/3.",
            "studentAnswer": "2/5",
            "createdAt": "2026-11-16T15:00:00Z",
        }
    ],
}


class _Captured(Exception):
    """Raised by the recording connection once the sent body is in hand."""


class _Recorder:
    """An adapter that keeps the bodies production builds and sends nothing."""

    def __init__(self) -> None:
        self.counted: dict[str, Any] | None = None
        self.sent: dict[str, Any] | None = None

    def connect(self, remaining_seconds: float) -> _Recorder:
        return self

    def count(self, model_id: str, body: Mapping[str, Any]) -> int:
        self.counted = dict(body)
        return 1

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Any:
        self.sent = dict(body)
        raise MalformedStream("captured")


def ask_bodies() -> tuple[dict[str, Any], dict[str, Any]]:
    """The body production would count and the body it sends, for the synthetic question."""
    recorder = _Recorder()
    model_call.install(recorder)
    try:
        ask_answer.answer(
            ask_answer.Asked(
                content="Warum ist 1/2 + 1/3 nicht 2/5?",
                practice_context=SYNTHETIC_PRACTICE_CONTEXT,
            ),
            ask_answer.Asker(
                student_id="synthetic-student",
                subject="math",
                grade="grade_6_primary",
                locale="de",
            ),
            ask_answer.ModelCall(
                deadline_monotonic=time.monotonic() + _PROBE_SECONDS,
                admission=lambda _tokens, _limit: model_call.Admit(),
            ),
            read_star_map=lambda _student, *, locale: list(SYNTHETIC_STAR_MAP),
        )
    except AIInvocationFailure:
        pass
    finally:
        model_call.install(None)
    if recorder.counted is None or recorder.sent is None:
        raise RuntimeError("the Ask answer did not reach the model call")
    return recorder.counted, recorder.sent


def _refusal(error: Exception) -> str:
    if isinstance(error, ProviderError):
        status = f" HTTP {error.http_status}" if error.http_status is not None else ""
        return f"{error.code}{status}: {error.message[:300]}"
    return type(error).__name__


def _stop_reason(events: Any) -> object:
    stop_reason: object = None
    for event in events:
        if isinstance(event, Mapping) and event.get("type") == "message_delta":
            stop_reason = (event.get("delta") or {}).get("stop_reason", stop_reason)
    return stop_reason


def probe(adapter: Adapter, *, model_id: str, invoke: bool) -> list[str]:
    """Run the checks; one line per check, each starting PASS, FAIL or SKIP."""
    counted, sent = ask_bodies()
    tool = sent["tools"][0]
    properties = sorted(tool["input_schema"]["properties"])
    lines = [f"INFO tool {tool['name']} with {', '.join(properties)}"]
    connection = adapter.connect(_PROBE_SECONDS)
    try:
        tokens = connection.count(model_id, counted)
    except Exception as error:
        lines.append(f"FAIL count: {_refusal(error)}")
    else:
        lines.append(f"PASS count: CountTokens took the Ask body, input_tokens={tokens}")
    if not invoke:
        lines.append("SKIP invoke: pass --invoke to send the body (costs under a cent)")
        return lines
    try:
        stream = connection.stream(model_id, {**sent, "max_tokens": 1})
        stop_reason = _stop_reason(stream.events)
    except Exception as error:
        lines.append(f"FAIL invoke: {_refusal(error)}")
    else:
        lines.append(
            "PASS invoke: InvokeModelWithResponseStream took the Ask body (max_tokens 1), "
            f"stop_reason={stop_reason}"
        )
    return lines


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--profile", default="stoa", help="AWS IAM Identity Center profile.")
    parser.add_argument("--region", default="eu-central-2")
    parser.add_argument("--account-id", default=DEFAULT_AWS_ACCOUNT_ID)
    parser.add_argument(
        "--model-id",
        default=None,
        help="Inference profile to probe; the configured one (bedrock_model_id) by default.",
    )
    parser.add_argument(
        "--invoke",
        action="store_true",
        help="Also send the body, cut to one output token (costs under a cent).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, adapter: Adapter | None = None) -> int:
    args = _parse_args(argv)
    model_id = args.model_id or config.settings().bedrock_model_id
    if adapter is None:
        from stoa.security.aws_operator_identity import require_sso_operator_session
        from stoa.services.model_call.bedrock import BedrockAdapter

        session = require_sso_operator_session(
            profile_name=args.profile,
            region_name=args.region,
            expected_account_id=args.account_id,
        )
        adapter = BedrockAdapter(session.client("bedrock-runtime", region_name=args.region))
    print(f"Probing the Ask answer request on {model_id} in {args.region}")
    lines = probe(adapter, model_id=model_id, invoke=args.invoke)
    for line in lines:
        print(line)
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
