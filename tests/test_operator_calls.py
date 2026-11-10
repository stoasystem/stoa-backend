"""#383: operator calls - an agent's admin operations on an operator's SSO identity."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from stoa import main
from stoa.db.repositories import security_audit_repo
from stoa.operator_calls import caller_identity, catalog, entry
from stoa.security.identity import AccountStatus, CanonicalRole
from stoa.services import usage_period


ACCOUNT_ID = "562923011260"
FUNCTION_ARN = f"arn:aws:lambda:eu-central-2:{ACCOUNT_ID}:function:stoa-api:production"
OPERATOR_ARN = (
    f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/"
    "AWSReservedSSO_AdministratorAccess_0123456789abcdef/operator@stoa.test"
)
AUDIT_KEY = security_audit_repo.AuthorizationAuditKey("test-key", b"k" * 16 + b"0123456789abcdef")
SIGNED = {
    "authorization": "AWS4-HMAC-SHA256 Credential=ASIA.../sts/aws4_request, Signature=abc",
    "x-amz-date": "20261110T120000Z",
    "x-amz-security-token": "session-token",
}
SECRET_WORDS = ("token", "password", "secret", "credential", "signature", "activation")


def _sts_xml(account: str = ACCOUNT_ID, arn: str = OPERATOR_ARN) -> bytes:
    return (
        '<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
        f"<GetCallerIdentityResult><Arn>{arn}</Arn><UserId>AROA:x</UserId>"
        f"<Account>{account}</Account></GetCallerIdentityResult>"
        "</GetCallerIdentityResponse>"
    ).encode()


def _verified(*_args: object, **_kwargs: object) -> str:
    return OPERATOR_ARN


def _call(operation: str, arguments: dict[str, Any] | None = None, **extra: Any) -> dict:
    call = {
        "operation": operation,
        "arguments": arguments or {},
        "callerIdentity": SIGNED,
        "agent": "claude-code",
    }
    call.update(extra)
    return entry.handle(
        call,
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        verify=_verified,
        audit_key=lambda: AUDIT_KEY,
    )


def _profile(user_id: str, role: str, number: str, **fields: Any) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "account_number": number,
        "email": f"{user_id}@stoa.test",
        "name": f"Name {user_id}",
        "created_at": "2026-01-01T00:00:00+00:00",
        # Stored fields that must never leave through an operator call.
        "cognito_sub": "sub-secret",
        "activation_token_hash": "hash-secret",
        **fields,
    }


def _audit_rows(table) -> list[dict[str, Any]]:
    return [
        row
        for (pk, _sk), row in table.rows.items()
        if pk == f"SECURITY_AUDIT#{catalog.OPERATOR_ACTOR_ID}"
    ]


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [k for item in value.values() for k in _keys(item)]
    if isinstance(value, list):
        return [k for item in value for k in _keys(item)]
    return []


# -- the list of operations -----------------------------------------------------------


def test_the_operation_list_is_exactly_this() -> None:
    """Adding an operation, or making one write, is a decision this test makes visible."""
    assert {spec.name: spec.effect for spec in catalog.OPERATIONS} == {
        "find_accounts": catalog.Effect.READ,
        "get_account": catalog.Effect.READ,
    }
    assert set(entry.RUNNERS) == set(catalog.OPERATIONS_BY_NAME)


def test_every_write_operation_rehearses_and_asks_first() -> None:
    for spec in catalog.OPERATIONS:
        schema = spec.input_schema()
        if spec.effect is catalog.Effect.WRITE:
            assert "dryRun" in schema["properties"], spec.name
            assert "confirm" in spec.description.lower(), spec.name
        else:
            assert spec.description.startswith("Read only."), spec.name


def test_catalog_vocabulary_matches_the_domain() -> None:
    roles = catalog.FindAccountsArguments.model_json_schema()["properties"]["role"]
    states = catalog.FindAccountsArguments.model_json_schema()["properties"]["status"]
    assert set(roles["anyOf"][0]["enum"]) == {role.value for role in CanonicalRole}
    assert set(states["anyOf"][0]["enum"]) == {status.value for status in AccountStatus}


# -- the Lambda entry -----------------------------------------------------------------


def test_http_events_still_go_to_mangum(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(main, "http_handler", lambda event, context: seen.append(event) or "http")
    event = {"version": "2.0", "rawPath": "/health", "requestContext": {}}

    assert main.handler(event, SimpleNamespace(invoked_function_arn=FUNCTION_ARN)) == "http"
    assert seen == [event]


def test_operator_events_go_to_the_operator_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, Any]] = []
    monkeypatch.setattr(main, "http_handler", lambda *_: pytest.fail("reached Mangum"))
    monkeypatch.setattr(
        entry, "handle", lambda call, **kwargs: calls.append((call, kwargs)) or {"ok": True}
    )

    answer = main.handler(
        {catalog.OPERATOR_CALL_KEY: {"operation": "find_accounts"}},
        SimpleNamespace(invoked_function_arn=FUNCTION_ARN),
    )

    assert answer == {"ok": True}
    assert calls == [({"operation": "find_accounts"}, {"invoked_function_arn": FUNCTION_ARN})]


def test_the_expected_account_is_the_functions_own() -> None:
    assert entry.account_of_function(FUNCTION_ARN) == ACCOUNT_ID
    assert entry.account_of_function("") == ""
    assert entry.account_of_function("arn:aws:lambda:eu-central-2:1:function:x") == ""


# -- verifying the caller ---------------------------------------------------------------


def test_verify_sends_only_the_signature_to_the_fixed_sts_request() -> None:
    sent: list[tuple[str, dict, bytes]] = []

    def post(url, headers, body):
        sent.append((url, dict(headers), body))
        return caller_identity.StsAnswer(200, _sts_xml())

    arn = caller_identity.verify(
        {**SIGNED, "Host": "evil.example", "X-Forwarded-To": "elsewhere"},
        region="eu-central-2",
        expected_account_id=ACCOUNT_ID,
        post=post,
    )

    assert arn == OPERATOR_ARN
    assert sent == [
        (
            "https://sts.eu-central-2.amazonaws.com/",
            {
                "content-type": catalog.STS_CONTENT_TYPE,
                "host": "sts.eu-central-2.amazonaws.com",
                **SIGNED,
            },
            b"Action=GetCallerIdentity&Version=2011-06-15",
        )
    ]


@pytest.mark.parametrize(
    ("signed", "answer"),
    [
        (None, caller_identity.StsAnswer(200, _sts_xml())),
        ({"x-amz-date": "20261110T120000Z"}, caller_identity.StsAnswer(200, _sts_xml())),
        ({**SIGNED, "authorization": "a\r\nInjected: 1"}, caller_identity.StsAnswer(200, _sts_xml())),
        (SIGNED, caller_identity.StsAnswer(403, b"<ErrorResponse>ExpiredToken</ErrorResponse>")),
        (SIGNED, caller_identity.StsAnswer(200, b"not xml")),
        (SIGNED, caller_identity.StsAnswer(200, _sts_xml(account="111122223333"))),
        (
            SIGNED,
            caller_identity.StsAnswer(
                200, _sts_xml(arn=f"arn:aws:iam::{ACCOUNT_ID}:user/someone")
            ),
        ),
    ],
)
def test_verify_refuses_and_says_how_to_log_in(signed, answer) -> None:
    with pytest.raises(caller_identity.CallerNotVerified) as refused:
        caller_identity.verify(
            signed,
            region="eu-central-2",
            expected_account_id=ACCOUNT_ID,
            post=lambda *_: answer,
        )
    message = str(refused.value)
    assert "aws sso login --sso-session stoa" in message or "wrong account" in message
    assert "ExpiredToken" not in message
    assert "session-token" not in message


def test_an_unverified_caller_learns_nothing_and_leaves_nothing(fake_table) -> None:
    def refuse(*_args, **_kwargs):
        raise caller_identity.CallerNotVerified("Refused; run 'aws sso login --sso-session stoa'.")

    answer = entry.handle(
        {"operation": "no_such_thing", "arguments": {}, "callerIdentity": SIGNED},
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        verify=refuse,
        audit_key=lambda: AUDIT_KEY,
    )

    assert answer["ok"] is False
    assert answer["error"]["code"] == "caller_not_verified"
    assert "find_accounts" not in str(answer)
    assert fake_table.rows == {}


def test_a_signed_request_the_operator_makes_is_the_one_sts_receives(time_machine) -> None:
    """The MCP signs; the function replays. The signature must cover what is replayed."""
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    import stoa_admin_mcp

    time_machine.move_to("2026-11-10T12:00:00Z", tick=False)
    credentials = Credentials("ASIAEXAMPLE", "secret-key", "session-token")
    session = SimpleNamespace(get_credentials=lambda: credentials)
    signed = stoa_admin_mcp.sign_caller_identity(session, "eu-central-2")
    sent: list[tuple[str, dict, bytes]] = []

    def post(url, headers, body):
        sent.append((url, dict(headers), body))
        return caller_identity.StsAnswer(200, _sts_xml())

    caller_identity.verify(
        signed, region="eu-central-2", expected_account_id=ACCOUNT_ID, post=post
    )
    url, headers, body = sent[0]
    replay = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={
            name: value
            for name, value in headers.items()
            if name not in ("authorization", "x-amz-date", "x-amz-security-token", "host")
        },
    )
    SigV4Auth(credentials, "sts", "eu-central-2").add_auth(replay)
    assert replay.headers["Authorization"] == headers["authorization"]
    assert "secret-key" not in str(signed)


# -- running operations ---------------------------------------------------------------


def test_find_accounts_answers_the_console_projection_and_records_one_row(fake_table) -> None:
    fake_table.seed(
        _profile("student-1", "student", "S26-0001"),
        _profile("parent-1", "parent", "P26-0001"),
    )

    answer = _call("find_accounts", {"role": "student"})

    assert answer["ok"] is True
    items = answer["result"]["items"]
    assert [item["accountNumber"] for item in items] == ["S26-0001"]
    assert items[0]["email"] == "student-1@stoa.test"
    assert items[0]["accountStatus"] == "active"
    assert not [k for k in _keys(answer) if any(word in k.lower() for word in SECRET_WORDS)]
    assert "sub-secret" not in str(answer) and "hash-secret" not in str(answer)

    rows = _audit_rows(fake_table)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "operator_call"
    assert row["actor_id"] == "operator:agent_mcp"
    assert row["agent_client"] == "claude-code"
    assert row["dry_run"] is False
    assert row["action"] == "find_accounts"
    assert row["result_code"] == "ok"
    assert row["evidence_reference"] == "returned:1"
    assert row["actor_fingerprint"] == security_audit_repo.operator_principal_fingerprint(
        AUDIT_KEY, OPERATOR_ARN
    )
    assert "operator@stoa.test" not in str(row)


def test_a_read_writes_nothing_but_its_audit_row(fake_table) -> None:
    fake_table.seed(_profile("student-1", "student", "S26-0001"))
    before = {key: dict(row) for key, row in fake_table.rows.items()}

    _call("find_accounts", {"query": "S26"})
    _call("get_account", {"accountNumber": "S26-0001"})

    after = {key: row for key, row in fake_table.rows.items() if key not in before}
    assert {key: fake_table.rows[key] for key in before} == before
    assert {pk for pk, _sk in after} == {"SECURITY_AUDIT#operator:agent_mcp"}
    assert len(after) == 2


@pytest.mark.parametrize(
    "arguments",
    [
        {"userId": "student-1"},
        {"accountNumber": "s26-0001"},
        {"email": "Student-1@stoa.test"},
    ],
)
def test_get_account_by_any_one_key(fake_table, arguments) -> None:
    fake_table.seed(
        _profile("student-1", "student", "S26-0001", usage_period_ends_on="2026-12-31"),
        {
            "PK": "ACCOUNT_NUMBER#S26-0001",
            "SK": "ACCOUNT_NUMBER",
            "entity_type": "account_number",
            "account_number": "S26-0001",
            "account_id": "student-1",
        },
    )

    answer = _call("get_account", arguments)

    assert answer["ok"] is True, answer
    account = answer["result"]
    assert account["userId"] == "student-1"
    assert set(account["usagePeriod"]) == {"endsOn", "state", "version", "effective"}
    assert set(account["usagePeriod"]["effective"]) == {"endsOn", "state", "paidBy", "parentId"}
    assert not [k for k in _keys(answer) if any(word in k.lower() for word in SECRET_WORDS)]
    assert _audit_rows(fake_table)[0]["target_id"] == "student-1"


def test_get_account_reads_the_usage_period_the_console_reads(fake_table) -> None:
    fake_table.seed(_profile("parent-1", "parent", "P26-0001"))
    expected = usage_period.read_account("parent-1", table=fake_table)

    account = _call("get_account", {"userId": "parent-1"})["result"]

    assert account["usagePeriod"] == {
        "endsOn": expected.ends_on.isoformat() if expected.ends_on else None,
        "state": expected.state.value,
        "version": expected.version,
    }


def test_a_teacher_has_no_usage_period(fake_table) -> None:
    fake_table.seed(_profile("teacher-1", "teacher", "T26-0001"))

    assert _call("get_account", {"userId": "teacher-1"})["result"]["usagePeriod"] is None


def test_an_address_with_two_accounts_names_their_numbers(fake_table) -> None:
    fake_table.seed(
        _profile("teacher-1", "teacher", "T26-0001", email="shared@stoa.test"),
        _profile("parent-1", "parent", "P26-0001", email="shared@stoa.test"),
    )

    answer = _call("get_account", {"email": "shared@stoa.test"})

    assert answer["error"] == {
        "code": "ambiguous_account",
        "message": "This address holds several accounts (P26-0001, T26-0001); "
        "ask again by accountNumber.",
    }


@pytest.mark.parametrize(
    ("operation", "arguments", "code"),
    [
        ("get_account", {"userId": "nobody"}, "account_not_found"),
        ("get_account", {}, "invalid_arguments"),
        ("get_account", {"userId": "a", "email": "a@b.c"}, "invalid_arguments"),
        ("find_accounts", {"limit": 500}, "invalid_arguments"),
        ("find_accounts", {"password": "hunter2"}, "invalid_arguments"),
        ("delete_account", {"userId": "student-1"}, "unknown_operation"),
        ("provision_privileged_admin", {}, "unknown_operation"),
    ],
)
def test_refusals_are_recorded_and_echo_nothing(fake_table, operation, arguments, code) -> None:
    answer = _call(operation, arguments)

    assert answer["ok"] is False
    assert answer["error"]["code"] == code
    assert "hunter2" not in str(answer)
    rows = _audit_rows(fake_table)
    assert len(rows) == 1
    assert rows[0]["result_code"] == code
    assert rows[0]["action"] in {operation, "unknown_operation"}
    assert "hunter2" not in str(rows)


def test_no_result_without_its_audit_row(fake_table, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_table.seed(_profile("student-1", "student", "S26-0001"))

    def broken(*_args, **_kwargs):
        raise RuntimeError("audit table down")

    monkeypatch.setattr(security_audit_repo, "append_event", broken)

    answer = _call("get_account", {"userId": "student-1"})

    assert answer == {
        "ok": False,
        "error": {
            "code": "audit_unavailable",
            "message": "The call could not be recorded, so no result is given.",
        },
    }


def test_nothing_runs_without_an_audit_key(fake_table) -> None:
    def unavailable():
        raise entry.OperatorCallRefused("audit_unavailable", "no key")

    answer = entry.handle(
        {"operation": "find_accounts", "arguments": {}, "callerIdentity": SIGNED},
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        verify=_verified,
        audit_key=unavailable,
    )

    assert answer["error"]["code"] == "audit_unavailable"
    assert fake_table.calls == {}


def test_a_failure_answers_only_its_correlation_id(fake_table, monkeypatch) -> None:
    def explode(_arguments):
        raise RuntimeError("table detail student-1@stoa.test")

    monkeypatch.setitem(entry.RUNNERS, "find_accounts", explode)

    answer = _call("find_accounts", {})

    assert answer["error"]["code"] == "failed"
    assert "student-1@stoa.test" not in str(answer)
    assert _audit_rows(fake_table)[0]["result_code"] == "failed"


def test_the_agent_name_is_reduced_to_a_plain_label(fake_table) -> None:
    _call("find_accounts", {}, agent="claude code\n<script>")

    assert _audit_rows(fake_table)[0]["agent_client"] == "claudecodescript"


def test_the_default_audit_key_comes_from_the_configured_keyring() -> None:
    key = entry._audit_key()

    assert key.key_id
    assert key.secret
