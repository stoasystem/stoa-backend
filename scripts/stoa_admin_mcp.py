#!/usr/bin/env python3
"""stoa-admin: a local MCP server that lets an agent run admin operations on SSO (#380, #383).

Claude Code, Codex and other MCP clients start it over stdio:

    claude mcp add stoa-admin -- .venv/Scripts/python scripts/stoa_admin_mcp.py

It holds no password, API key or token of its own. Each tool call:

1. checks the local AWS session is an Identity Center (SSO) session of the
   production account (`require_sso_operator_session`); otherwise the call is
   refused with "run 'aws sso login --sso-session stoa'";
2. signs an STS GetCallerIdentity request with that session, so the function can
   ask STS itself who is calling;
3. invokes the `stoa-api` function's `production` alias directly with the
   operation, its arguments and that signature. The deployed code verifies the
   caller, runs only operations listed in `stoa.operator_calls.catalog`, and
   records each call in the audit trail as `operator:agent_mcp`.

The tool list comes from the same catalog, so it names what the code in this
checkout knows; an operation the deployed function does not know yet is
refused there. Settings, all optional:

- STOA_ADMIN_MCP_PROFILE  (default: AWS_PROFILE, else AdministratorAccess-562923011260)
- STOA_ADMIN_MCP_REGION   (default: eu-central-2)
- STOA_ADMIN_MCP_ACCOUNT  (default: 562923011260)
- STOA_ADMIN_MCP_FUNCTION (default: stoa-api)
- STOA_ADMIN_MCP_ALIAS    (default: production)

The protocol is MCP's stdio transport: one JSON-RPC message per line on stdin
and stdout, diagnostics on stderr. Only what tools need is spoken: initialize,
ping, tools/list and tools/call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, BinaryIO, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from botocore.auth import SigV4Auth  # noqa: E402
from botocore.awsrequest import AWSRequest  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

from stoa.operator_calls import catalog  # noqa: E402
from stoa.security.aws_operator_identity import (  # noqa: E402
    SSO_LOGIN_HINT,
    AwsOperatorIdentityError,
    require_sso_operator_session,
)


SERVER_NAME = "stoa-admin"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_ACCOUNT_ID = "562923011260"
INSTRUCTIONS = (
    "Admin operations on the production STOA back office, run on the operator's AWS "
    "SSO identity and recorded in the audit trail as an agent call. Read-only tools "
    "change nothing. If a call says the SSO session is missing or expired, ask the "
    f"person to {SSO_LOGIN_HINT}; never ask for a password."
)


@dataclass(frozen=True, slots=True)
class Config:
    profile: str
    region: str
    account_id: str
    function_name: str
    alias: str

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "Config":
        env = os.environ if environ is None else environ
        account_id = env.get("STOA_ADMIN_MCP_ACCOUNT") or DEFAULT_ACCOUNT_ID
        return cls(
            profile=(
                env.get("STOA_ADMIN_MCP_PROFILE")
                or env.get("AWS_PROFILE")
                or f"AdministratorAccess-{account_id}"
            ),
            region=env.get("STOA_ADMIN_MCP_REGION") or "eu-central-2",
            account_id=account_id,
            function_name=env.get("STOA_ADMIN_MCP_FUNCTION") or "stoa-api",
            alias=env.get("STOA_ADMIN_MCP_ALIAS") or "production",
        )


class ToolFailure(Exception):
    """A call that did not produce a result; the message goes to the agent as is."""


def sign_caller_identity(session: Any, region: str) -> dict[str, str]:
    """The headers of a GetCallerIdentity request signed by this session, and only those."""
    credentials = session.get_credentials()
    if credentials is None:
        raise AwsOperatorIdentityError(f"No AWS credentials; {SSO_LOGIN_HINT}.")
    request = AWSRequest(
        method="POST",
        url=catalog.sts_endpoint(region),
        data=catalog.STS_BODY.encode("utf-8"),
        headers={"Content-Type": catalog.STS_CONTENT_TYPE},
    )
    SigV4Auth(credentials.get_frozen_credentials(), "sts", region).add_auth(request)
    return {
        name.lower(): str(request.headers[name])
        for name in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token")
        if request.headers.get(name)
    }


SessionFactory = Callable[[Config], Any]


def _sso_session(config: Config) -> Any:
    return require_sso_operator_session(
        profile_name=config.profile,
        region_name=config.region,
        expected_account_id=config.account_id,
    )


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "title": spec.title,
            "description": spec.description,
            "inputSchema": spec.input_schema(),
            "annotations": {
                "title": spec.title,
                "readOnlyHint": spec.effect is catalog.Effect.READ,
                "destructiveHint": False,
                "openWorldHint": False,
            },
        }
        for spec in catalog.OPERATIONS
    ]


class Server:
    def __init__(
        self,
        config: Config,
        *,
        session_factory: SessionFactory = _sso_session,
        log: TextIO = sys.stderr,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.log = log
        self.agent = "unknown"

    # -- one tool call ----------------------------------------------------------

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in catalog.OPERATIONS_BY_NAME:
            raise ToolFailure(f"Unknown tool {name!r}.")
        try:
            session = self.session_factory(self.config)
            signed = sign_caller_identity(session, self.config.region)
        except AwsOperatorIdentityError as exc:
            raise ToolFailure(str(exc)) from exc
        except BotoCoreError as exc:
            raise ToolFailure(
                f"The AWS SSO session could not be used ({type(exc).__name__}); {SSO_LOGIN_HINT}."
            ) from exc
        payload = {
            catalog.OPERATOR_CALL_KEY: {
                "operation": name,
                "arguments": arguments,
                "callerIdentity": signed,
                "agent": self.agent,
            }
        }
        try:
            response = session.client("lambda", region_name=self.config.region).invoke(
                FunctionName=self.config.function_name,
                Qualifier=self.config.alias,
                Payload=json.dumps(payload).encode("utf-8"),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError")
            raise ToolFailure(f"Invoking {self.config.function_name} was refused ({code}).") from exc
        except BotoCoreError as exc:
            raise ToolFailure(
                f"Invoking {self.config.function_name} failed ({type(exc).__name__})."
            ) from exc
        if response.get("FunctionError"):
            raise ToolFailure(
                f"{self.config.function_name} failed while answering; see its logs."
            )
        try:
            answer = json.loads(response["Payload"].read())
        except (KeyError, ValueError) as exc:
            raise ToolFailure(f"{self.config.function_name} gave an unreadable answer.") from exc
        if not isinstance(answer, dict):
            raise ToolFailure(f"{self.config.function_name} gave an unreadable answer.")
        if not answer.get("ok"):
            error = answer.get("error") if isinstance(answer.get("error"), dict) else {}
            raise ToolFailure(f"{error.get('code', 'failed')}: {error.get('message', '')}")
        return answer.get("result")

    # -- JSON-RPC ----------------------------------------------------------------

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid Request")
        method = message.get("method")
        request_id = message.get("id")
        if "id" not in message:
            return None  # a notification, e.g. notifications/initialized
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "initialize":
            client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
            self.agent = str(client.get("name") or "unknown")
            requested = params.get("protocolVersion")
            version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            return _result(
                request_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": INSTRUCTIONS,
                },
            )
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                return _error(request_id, -32602, "arguments must be an object")
            try:
                result = self.call(name, arguments)
            except ToolFailure as failure:
                return _result(
                    request_id,
                    {"content": [{"type": "text", "text": str(failure)}], "isError": True},
                )
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return _result(
                request_id, {"content": [{"type": "text", "text": text}], "isError": False}
            )
        return _error(request_id, -32601, f"Method not found: {method}")

    def serve(self, stdin: Iterable[bytes], stdout: BinaryIO) -> None:
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                reply: dict[str, Any] | None = _error(None, -32700, "Parse error")
            else:
                reply = self.handle(message)
            if reply is not None:
                stdout.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
                stdout.flush()

    def check_session(self) -> None:
        """At start-up, say on stderr whether the SSO session is usable; never fail."""
        try:
            self.session_factory(self.config)
        except (AwsOperatorIdentityError, BotoCoreError) as exc:
            print(f"{SERVER_NAME}: {exc}", file=self.log)
        else:
            print(f"{SERVER_NAME}: SSO session for {self.config.profile} verified.", file=self.log)


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main() -> int:
    server = Server(Config.from_environment())
    server.check_session()
    server.serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
