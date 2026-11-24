#!/usr/bin/env python3
"""Send Bedrock the two model-call requests production makes, through the Bedrock adapter (#439).

Before a PR that changes what a model call sends (a prompt, a tool, a field of
the body) merges, an operator runs this once on an SSO session (#435 item 4),
so a request Bedrock refuses is found before production finds it (#430). For
the Ask answer and for the weekly report, each in turn:

1. CountTokens on the body production counts (free);
2. InvokeModelWithResponseStream, the streamed call production makes, on the
   body production sends with `max_tokens` cut to 1 and nothing else changed.
   It costs the input tokens and one output token, well under a cent each.

`--count-only` leaves out step 2, so nothing is paid: what is printed is then
how many input tokens each request costs, to compare a prompt before and
after a change (#442).

The bodies are the ones the production code builds from synthetic inputs, with
no real person's data in them (`probe_ask_answer_request.ask_bodies`,
`probe_weekly_report_request.report_bodies`), and they reach Bedrock through
`model_call.bedrock.BedrockAdapter`, as every model call does. Printed are the
counted input tokens, the stop reason and usage Bedrock reports for the sent
body (cache write and read tokens too, when there are any), and Bedrock's own
words when it refuses a body. The run fails when either request fails.

    python scripts/probe_bedrock_token_count.py [--profile stoa] [--count-only]
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    # Run as a file: the sibling probes are imported from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import probe_ask_answer_request, probe_weekly_report_request  # noqa: E402
from stoa import config  # noqa: E402
from stoa.services import model_call  # noqa: E402
from stoa.services.model_call.adapter import Adapter, Connection, ProviderError  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
_PROBE_SECONDS = 60

Bodies = Callable[[], tuple[dict[str, Any], dict[str, Any]]]

# The two requests production makes, by name: what builds the counted and the sent body.
REQUESTS: tuple[tuple[str, Bodies], ...] = (
    ("ask", probe_ask_answer_request.ask_bodies),
    ("report", probe_weekly_report_request.report_bodies),
)

# The usage Bedrock reports for a reply, in the order printed.
_USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def _refusal(error: Exception) -> str:
    if isinstance(error, ProviderError):
        status = f" HTTP {error.http_status}" if error.http_status is not None else ""
        return f"{error.code}{status}: {error.message[:300]}"
    return type(error).__name__


def _reply(events: Iterable[Any]) -> tuple[object, dict[str, Any]]:
    """The stop reason and usage of a streamed reply: the usage comes in two parts."""
    stop_reason: object = None
    usage: dict[str, Any] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        if event.get("type") == "message_start":
            model_call._merge_usage(usage, (event.get("message") or {}).get("usage") or {})
        elif event.get("type") == "message_delta":
            model_call._merge_usage(usage, event.get("usage") or {})
            stop_reason = (event.get("delta") or {}).get("stop_reason", stop_reason)
    return stop_reason, usage


def probe_request(
    connection: Connection,
    *,
    name: str,
    bodies: Bodies,
    model_id: str,
    invoke: bool,
    invoked_id: str | None = None,
) -> list[str]:
    """Count one request and, with `invoke`, send it; one line per step, PASS or FAIL.

    Counted on `model_id`, sent through `invoked_id` when given (#612).
    """
    counted, sent = bodies()
    lines: list[str] = []
    try:
        tokens = connection.count(model_id, counted)
    except Exception as error:
        lines.append(f"FAIL {name} count: {_refusal(error)}")
    else:
        lines.append(f"PASS {name} count: CountTokens took the body, input_tokens={tokens}")
    if not invoke:
        return lines
    try:
        stream = connection.stream(invoked_id or model_id, {**sent, "max_tokens": 1})
        stop_reason, usage = _reply(stream.events)
    except Exception as error:
        lines.append(f"FAIL {name} invoke: {_refusal(error)}")
    else:
        reported = "".join(
            f" {field}={usage[field]}" for field in _USAGE_FIELDS if field in usage
        )
        lines.append(
            f"PASS {name} invoke: InvokeModelWithResponseStream took the body (max_tokens 1), "
            f"stop_reason={stop_reason}{reported}"
        )
    return lines


def probe(
    adapter: Adapter, *, model_id: str, invoke: bool = True, invoked_id: str | None = None
) -> list[str]:
    """Both requests, the Ask answer first, on one connection."""
    connection = adapter.connect(_PROBE_SECONDS)
    lines: list[str] = []
    for name, bodies in REQUESTS:
        lines += probe_request(
            connection,
            name=name,
            bodies=bodies,
            model_id=model_id,
            invoke=invoke,
            invoked_id=invoked_id,
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
        "--count-only",
        action="store_true",
        help="Only count the input tokens of each request; send nothing, pay nothing.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, adapter: Adapter | None = None) -> int:
    args = _parse_args(argv)
    model_id = args.model_id or config.settings().bedrock_model_id
    invoked_id = None
    if adapter is None:
        from botocore.exceptions import BotoCoreError

        from stoa.security.aws_operator_identity import (
            SSO_LOGIN_HINT,
            AwsOperatorIdentityError,
            require_sso_operator_session,
        )
        from stoa.services.model_call.bedrock import BedrockAdapter
        from stoa.services.model_call.development_profile import development_profile

        try:
            session = require_sso_operator_session(
                profile_name=args.profile,
                region_name=args.region,
                expected_account_id=args.account_id,
            )
        except AwsOperatorIdentityError as error:
            print(f"FAIL sso: {error}")
            return 2
        except BotoCoreError as error:
            print(f"FAIL sso: {error}; {SSO_LOGIN_HINT}")
            return 2
        adapter = BedrockAdapter(session.client("bedrock-runtime", region_name=args.region))
        if not args.count_only:
            invoked_id = development_profile(session, region=args.region, model_id=model_id)
    print(f"Probing the model-call requests on {model_id} in {args.region}")
    lines = probe(
        adapter, model_id=model_id, invoke=not args.count_only, invoked_id=invoked_id
    )
    for line in lines:
        print(line)
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
