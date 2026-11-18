#!/usr/bin/env python3
"""Check that Bedrock takes the weekly report's model-call request (#438).

The weekly report asks the model through 模型调用 with a forced, strict tool.
Before a change to that request ships, an operator runs this once on an SSO
session, as #435 item 4 asks:

1. CountTokens on the body that would be counted (free). Production does not
   count the report (no admission hook), but CountTokens must take it, as the
   module counts every body a hook is given (#430).
2. With `--invoke` only: InvokeModelWithResponseStream on the body that is
   sent, with the output limit cut to one token. It costs the input tokens and
   one output token (well under a cent); no report is written.

Both bodies are built by the production code from a synthetic week with no
real person's data in it. Only token counts, stop reasons and Bedrock's own
error text are printed.

    python scripts/probe_weekly_report_request.py --profile stoa [--invoke]
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import sys
from typing import Any

from stoa import config
from stoa.services import model_call, report_service
from stoa.services.model_call.adapter import Adapter, ProviderError

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
_PROBE_SECONDS = 60

# A synthetic week: every name and text is made up.
SYNTHETIC_PAYLOAD: dict[str, Any] = {
    "student": {"name": "Synthetic Student", "grade": 5},
    "week": {"start": "2026-11-09", "end": "2026-11-15"},
    "metrics": {
        "questionsAsked": 3,
        "aiResolved": 2,
        "teacherHelpRequests": 1,
        "practiceLessonsCompleted": 2,
        "mistakesLogged": 1,
    },
    "weakTopics": [{"topic": "Fractions", "count": 2}],
    "sourceCounts": {"questions": 3, "practiceProgress": 2, "mistakes": 1, "conversations": 1},
    "activities": [
        {
            "type": "question",
            "title": "How do I simplify 6/8?",
            "summary": "Asked how to simplify a fraction.",
            "subject": "math",
            "createdAt": "2026-11-10T15:00:00Z",
        },
        {
            "type": "practice",
            "title": "Fractions, level 1",
            "summary": "Completed a practice lesson.",
            "subject": "math",
            "createdAt": "2026-11-12T16:00:00Z",
        },
    ],
}


def report_bodies() -> tuple[dict[str, Any], dict[str, Any]]:
    """The body production would count and the body it sends, for the synthetic week."""
    request = report_service.weekly_report_request(SYNTHETIC_PAYLOAD)
    sent = model_call._invoke_body(
        system=request["system"],
        messages=request["messages"],
        tool=request["tool"],
        max_tokens=request["max_tokens"],
        temperature=request["temperature"],
    )
    return model_call._count_body(sent), sent


def _refusal(error: Exception) -> str:
    if isinstance(error, ProviderError):
        status = f" HTTP {error.http_status}" if error.http_status is not None else ""
        return f"{error.code}{status}: {error.message[:300]}"
    return type(error).__name__


def probe(adapter: Adapter, *, model_id: str, invoke: bool) -> list[str]:
    """Run the checks; one line per check, each starting PASS or FAIL."""
    counted, sent = report_bodies()
    connection = adapter.connect(_PROBE_SECONDS)
    lines: list[str] = []
    try:
        tokens = connection.count_tokens(model_id, counted)
    except Exception as error:
        lines.append(f"FAIL count: {_refusal(error)}")
    else:
        lines.append(f"PASS count: CountTokens took the report body, input_tokens={tokens}")
    if not invoke:
        lines.append("SKIP invoke: pass --invoke to send the body (costs under a cent)")
        return lines
    try:
        stream = connection.stream(model_id, {**sent, "max_tokens": 1})
        stop_reason = _stop_reason(stream.events)
    except Exception as error:
        lines.append(f"FAIL invoke: {_refusal(error)}")
    else:
        lines.append(f"PASS invoke: InvokeModel took the report body, stop_reason={stop_reason}")
    return lines


def _stop_reason(events: Any) -> object:
    stop_reason: object = None
    for event in events:
        if isinstance(event, Mapping) and event.get("type") == "message_delta":
            stop_reason = (event.get("delta") or {}).get("stop_reason", stop_reason)
    return stop_reason


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
    print(f"Probing the weekly report request on {model_id} in {args.region}")
    lines = probe(adapter, model_id=model_id, invoke=args.invoke)
    for line in lines:
        print(line)
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
