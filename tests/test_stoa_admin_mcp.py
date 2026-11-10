"""#383: the local stdio MCP server an agent talks to."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

from botocore.credentials import Credentials
from botocore.exceptions import ClientError, UnauthorizedSSOTokenError
import pytest

import stoa_admin_mcp
from stoa.operator_calls import catalog
from stoa.security.aws_operator_identity import AwsOperatorIdentityError


CONFIG = stoa_admin_mcp.Config(
    profile="AdministratorAccess-562923011260",
    region="eu-central-2",
    account_id="562923011260",
    function_name="stoa-api",
    alias="production",
)


class FakeLambda:
    def __init__(self, answer: Any = None, error: Exception | None = None, **extra: Any):
        self.answer = answer
        self.error = error
        self.extra = extra
        self.invocations: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.invocations.append(kwargs)
        if self.error:
            raise self.error
        return {"Payload": io.BytesIO(json.dumps(self.answer).encode()), **self.extra}


class FakeSession:
    def __init__(self, lambda_client: FakeLambda):
        self.lambda_client = lambda_client
        self.credentials = Credentials("ASIAEXAMPLE", "secret-key", "session-token")

    def get_credentials(self):
        return self.credentials

    def client(self, name: str, **_kwargs: Any):
        assert name == "lambda"
        return self.lambda_client


def _server(lambda_client: FakeLambda | None = None, factory=None) -> stoa_admin_mcp.Server:
    session = FakeSession(lambda_client or FakeLambda({"ok": True, "result": {}}))
    return stoa_admin_mcp.Server(
        CONFIG, session_factory=factory or (lambda _config: session), log=io.StringIO()
    )


def _rpc(server: stoa_admin_mcp.Server, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    stdin = [json.dumps(message).encode() + b"\n" for message in messages]
    stdout = io.BytesIO()
    server.serve(stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def _call(name: str, arguments: dict[str, Any] | None = None, request_id: int = 2):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "claude-code", "version": "2.0"},
    },
}


def test_handshake_then_tools_list_names_the_catalog() -> None:
    replies = _rpc(
        _server(),
        INITIALIZE,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert [reply["id"] for reply in replies] == [1, 2]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert replies[0]["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert "aws sso login --sso-session stoa" in replies[0]["result"]["instructions"]
    tools = {tool["name"]: tool for tool in replies[1]["result"]["tools"]}
    assert set(tools) == set(catalog.OPERATIONS_BY_NAME)
    assert tools["find_accounts"]["annotations"]["readOnlyHint"] is True
    assert tools["get_account"]["inputSchema"]["type"] == "object"


def test_write_tools_say_so_and_ask_for_a_rehearsal_first() -> None:
    replies = _rpc(_server(), INITIALIZE, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert "dryRun=true first" in replies[0]["result"]["instructions"]
    tools = {tool["name"]: tool for tool in replies[1]["result"]["tools"]}
    hints = {
        name: (tool["annotations"]["readOnlyHint"], tool["annotations"]["destructiveHint"])
        for name, tool in tools.items()
    }
    assert hints == {
        "find_accounts": (True, False),
        "get_account": (True, False),
        "invite_account": (False, False),
        "reissue_invitation": (False, True),
        "revoke_invitation": (False, True),
    }
    for name in ("invite_account", "reissue_invitation", "revoke_invitation"):
        assert "dryRun" in tools[name]["inputSchema"]["required"]
        assert "confirm with the person" in tools[name]["description"]


def test_a_write_call_passes_dry_run_through_unchanged() -> None:
    lambda_client = FakeLambda({"ok": True, "result": {"dryRun": True}})

    _rpc(
        _server(lambda_client),
        _call("revoke_invitation", {"accountNumber": "S26-0001", "dryRun": True}),
    )

    (invocation,) = lambda_client.invocations
    call = json.loads(invocation["Payload"])[catalog.OPERATOR_CALL_KEY]
    assert call["operation"] == "revoke_invitation"
    assert call["arguments"] == {"accountNumber": "S26-0001", "dryRun": True}


def test_an_unknown_protocol_version_gets_the_latest_supported() -> None:
    message = {**INITIALIZE, "params": {**INITIALIZE["params"], "protocolVersion": "1999-01-01"}}

    reply = _rpc(_server(), message)[0]

    assert reply["result"]["protocolVersion"] == stoa_admin_mcp.SUPPORTED_PROTOCOLS[0]


def test_a_call_invokes_the_production_alias_with_a_signature_only() -> None:
    lambda_client = FakeLambda({"ok": True, "result": {"items": [], "count": 0}})

    replies = _rpc(_server(lambda_client), INITIALIZE, _call("find_accounts", {"role": "student"}))

    assert replies[1]["result"]["isError"] is False
    assert json.loads(replies[1]["result"]["content"][0]["text"]) == {"items": [], "count": 0}
    (invocation,) = lambda_client.invocations
    assert invocation["FunctionName"] == "stoa-api"
    assert invocation["Qualifier"] == "production"
    call = json.loads(invocation["Payload"])[catalog.OPERATOR_CALL_KEY]
    assert call["operation"] == "find_accounts"
    assert call["arguments"] == {"role": "student"}
    assert call["agent"] == "claude-code"
    assert set(call["callerIdentity"]) == {"authorization", "x-amz-date", "x-amz-security-token"}
    assert "secret-key" not in invocation["Payload"].decode()


@pytest.mark.parametrize(
    "failure",
    [
        AwsOperatorIdentityError("Refusing non-SSO AWS credentials; run 'aws sso login --sso-session stoa'."),
        UnauthorizedSSOTokenError(),
    ],
)
def test_without_a_live_sso_session_every_tool_refuses_with_the_login_hint(failure) -> None:
    def no_session(_config):
        raise failure

    reply = _rpc(_server(factory=no_session), _call("get_account", {"userId": "x"}))[0]

    assert reply["result"]["isError"] is True
    assert "aws sso login --sso-session stoa" in reply["result"]["content"][0]["text"]


def test_a_refusal_from_the_function_reaches_the_agent() -> None:
    lambda_client = FakeLambda(
        {"ok": False, "error": {"code": "account_not_found", "message": "Refused: account_not_found."}}
    )

    reply = _rpc(_server(lambda_client), _call("get_account", {"userId": "x"}))[0]

    assert reply["result"] == {
        "content": [{"type": "text", "text": "account_not_found: Refused: account_not_found."}],
        "isError": True,
    }


def test_a_function_crash_or_refused_invoke_is_a_tool_error() -> None:
    crashed = FakeLambda({"errorMessage": "boom"}, FunctionError="Unhandled")
    denied = FakeLambda(
        error=ClientError({"Error": {"Code": "AccessDeniedException", "Message": "x"}}, "Invoke")
    )

    crash = _rpc(_server(crashed), _call("find_accounts"))[0]["result"]
    deny = _rpc(_server(denied), _call("find_accounts"))[0]["result"]

    assert crash["isError"] is True and "boom" not in crash["content"][0]["text"]
    assert deny["isError"] is True and "AccessDeniedException" in deny["content"][0]["text"]


def test_an_unlisted_tool_never_reaches_aws() -> None:
    lambda_client = FakeLambda({"ok": True, "result": {}})

    reply = _rpc(_server(lambda_client), _call("delete_account", {"userId": "x"}))[0]

    assert reply["result"]["isError"] is True
    assert lambda_client.invocations == []


def test_protocol_errors() -> None:
    server = _server()
    stdout = io.BytesIO()
    server.serve([b"{not json\n", b"\n"], stdout)

    assert json.loads(stdout.getvalue())["error"]["code"] == -32700
    assert _rpc(server, {"jsonrpc": "2.0", "id": 9, "method": "resources/list"})[0]["error"][
        "code"
    ] == -32601
    assert _rpc(server, {"jsonrpc": "2.0", "id": 3, "method": "ping"})[0]["result"] == {}


def test_configuration_defaults_and_overrides() -> None:
    assert stoa_admin_mcp.Config.from_environment({}) == CONFIG
    assert stoa_admin_mcp.Config.from_environment({"AWS_PROFILE": "other"}).profile == "other"
    assert (
        stoa_admin_mcp.Config.from_environment(
            {"AWS_PROFILE": "other", "STOA_ADMIN_MCP_PROFILE": "mine"}
        ).profile
        == "mine"
    )


def test_start_up_reports_the_session_without_failing() -> None:
    log = io.StringIO()

    def no_session(_config):
        raise AwsOperatorIdentityError("Unable to verify; run 'aws sso login --sso-session stoa'.")

    stoa_admin_mcp.Server(CONFIG, session_factory=no_session, log=log).check_session()

    assert "aws sso login --sso-session stoa" in log.getvalue()


def test_signing_needs_credentials() -> None:
    with pytest.raises(AwsOperatorIdentityError, match="aws sso login"):
        stoa_admin_mcp.sign_caller_identity(
            SimpleNamespace(get_credentials=lambda: None), "eu-central-2"
        )
