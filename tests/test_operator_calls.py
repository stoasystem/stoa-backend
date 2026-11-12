"""#383, #384: operator calls - an agent's admin operations on an operator's SSO identity."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from stoa import main
from stoa.db.repositories import account_email_claim_repo, security_audit_repo
from stoa.operator_calls import caller_identity, catalog, entry
from stoa.security.identity import AccountStatus, CanonicalRole
from stoa.services import account_provisioning_service, notify_service, usage_period


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
        "invite_account": catalog.Effect.WRITE,
        "reissue_invitation": catalog.Effect.WRITE,
        "revoke_invitation": catalog.Effect.WRITE,
        "delete_account": catalog.Effect.WRITE,
        "list_teacher_applications": catalog.Effect.READ,
        "count_review_queues": catalog.Effect.READ,
        "report_email_stats": catalog.Effect.READ,
    }
    assert set(entry.RUNNERS) == set(catalog.OPERATIONS_BY_NAME)


def test_every_write_operation_rehearses_and_asks_first() -> None:
    for spec in catalog.OPERATIONS:
        schema = spec.input_schema()
        if spec.effect is catalog.Effect.WRITE:
            assert "dryRun" in schema["properties"], spec.name
            # Never defaulted: every write call says which of the two it is.
            assert "dryRun" in schema["required"], spec.name
            assert schema["properties"]["dryRun"]["type"] == "boolean", spec.name
            assert "confirm" in spec.description.lower(), spec.name
            assert spec.description.startswith("Changes data."), spec.name
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
        ("archive_account", {"userId": "student-1"}, "unknown_operation"),
        ("delete_account", {"userId": "student-1"}, "invalid_arguments"),
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


# -- invitations (#384) ---------------------------------------------------------------


ADDRESS = "new.student@stoa.test"
ADMIN_ACTOR = {
    "user_id": "admin-1",
    "role": "admin",
    "account_status": "active",
    "capabilities": {"admin_identity_manager": True},
}


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every activation email the console's own delivery was asked to send."""
    sent: list[dict[str, Any]] = []

    def send(recipient: str, **kwargs: Any) -> None:
        sent.append({"recipient": recipient, **kwargs})

    monkeypatch.setattr(notify_service, "send_account_invitation_email", send)
    return sent


def _rows(table) -> dict[tuple[str, str], dict[str, Any]]:
    return {key: dict(row) for key, row in table.rows.items()}


def _business_rows_added(table, before) -> set[tuple[str, str]]:
    return {
        key
        for key in table.rows
        if key not in before and key[0] != f"SECURITY_AUDIT#{catalog.OPERATOR_ACTOR_ID}"
    }


def _invitations(table) -> list[dict[str, Any]]:
    return [
        row for (pk, _sk), row in table.rows.items() if pk.startswith("ACCOUNT_INVITATION#")
    ]


def _assert_no_secrets(answer: dict, table) -> None:
    assert not [k for k in _keys(answer) if any(word in k.lower() for word in SECRET_WORDS)]
    text = str(answer)
    for row in _invitations(table):
        assert str(row["token_digest"]) not in text


def _invite(**overrides: Any) -> dict:
    arguments = {"role": "student", "email": ADDRESS, "fullName": "Alex Muster", "dryRun": False}
    arguments.update(overrides)
    answer = _call("invite_account", arguments)
    assert answer["ok"] is True, answer
    return answer["result"]


def test_admin_is_not_an_invitable_role() -> None:
    roles = catalog.InviteAccountArguments.model_json_schema()["properties"]["role"]["enum"]
    assert set(roles) == {"student", "parent", "teacher"}


def test_a_dry_run_invitation_writes_and_sends_nothing(fake_table, mailbox) -> None:
    before = _rows(fake_table)

    answer = _call(
        "invite_account", {"role": "student", "email": " New.Student@stoa.test ", "dryRun": True}
    )

    assert answer["ok"] is True, answer
    assert answer["result"] == {
        "dryRun": True,
        "summary": (
            "Would create a student account in state invited and send a German activation "
            f"email to {ADDRESS}. Its account number is allocated when it runs. Nothing was "
            "created or sent."
        ),
        "role": "student",
        "email": ADDRESS,
        "accountStatus": "invited",
        "emailLanguage": "de",
        "expirySeconds": account_provisioning_service.DEFAULT_INVITATION_SECONDS,
    }
    assert mailbox == []
    assert {key: fake_table.rows[key] for key in before} == before
    assert _business_rows_added(fake_table, before) == set()
    (row,) = _audit_rows(fake_table)
    assert row["action"] == "invite_account"
    assert row["dry_run"] is True
    assert row["result_code"] == "ok"
    assert ADDRESS not in str(row)
    _assert_no_secrets(answer, fake_table)


def test_a_real_invitation_opens_the_account_and_mails_it_as_the_console_does(
    fake_table, mailbox
) -> None:
    result = _invite(locale="fr")

    assert set(result) == {
        "dryRun",
        "summary",
        "userId",
        "accountNumber",
        "role",
        "accountStatus",
        "invitationId",
        "invitationStatus",
        "invitationDelivered",
        "emailLanguage",
        "expiresAt",
    }
    assert result["dryRun"] is False
    assert result["role"] == "student"
    assert result["accountStatus"] == "invited"
    assert result["accountNumber"].startswith("S")
    assert result["invitationStatus"] == "issued"
    assert result["invitationDelivered"] is True
    assert result["summary"] == (
        f"Created student account {result['accountNumber']} in state invited and sent a "
        "French activation email."
    )
    (mail,) = mailbox
    assert mail["recipient"] == ADDRESS
    assert mail["locale"] == "fr"
    assert mail["role"] == "student"
    assert mail["activation_token"] not in str(result)

    profile = fake_table.rows[(f"USER#{result['userId']}", "PROFILE")]
    assert profile["created_by"] == "operator:agent_mcp"
    assert profile["account_status"] == "invited"
    (invitation,) = _invitations(fake_table)
    assert invitation["invited_by"] == "operator:agent_mcp"
    assert invitation["invitation_id"] == result["invitationId"]
    service_rows = [
        row
        for (pk, _sk), row in fake_table.rows.items()
        if pk == f"SECURITY_AUDIT#{result['userId']}"
    ]
    assert {row["event_type"] for row in service_rows} == {"account_invitation_issued"}
    assert {row["actor_id"] for row in service_rows} == {"operator:agent_mcp"}
    (row,) = _audit_rows(fake_table)
    assert row["dry_run"] is False
    assert row["target_id"] == result["userId"]
    assert row["evidence_reference"] == f"account-invitation:{result['invitationId']}"
    _assert_no_secrets({"result": result}, fake_table)


def test_get_account_then_shows_the_invited_account(fake_table, mailbox) -> None:
    result = _invite()

    account = _call("get_account", {"accountNumber": result["accountNumber"]})["result"]

    assert account["userId"] == result["userId"]
    assert account["accountStatus"] == "invited"
    assert account["invitationId"] == result["invitationId"]


def test_a_delivery_failure_is_said_not_hidden(fake_table, monkeypatch) -> None:
    def down(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("SES unavailable")

    monkeypatch.setattr(notify_service, "send_account_invitation_email", down)

    result = _invite()

    assert result["invitationDelivered"] is False
    assert "could not send the activation email" in result["summary"]


@pytest.mark.parametrize("dry_run", [True, False])
def test_an_address_already_held_in_that_role_is_refused_by_number(
    fake_table, mailbox, dry_run
) -> None:
    fake_table.seed(_profile("parent-2", "parent", "P26-0002", email="held@stoa.test"))
    before = _rows(fake_table)

    answer = _call(
        "invite_account", {"role": "parent", "email": "Held@stoa.test", "dryRun": dry_run}
    )

    verb = "Would be refused" if dry_run else "Refused"
    tense = "would be" if dry_run else "was"
    assert answer == {
        "ok": False,
        "error": {
            "code": "account_exists",
            "message": f"{verb}: this address already holds a parent account (P26-0002, "
            f"active). Nothing {tense} created or sent.",
        },
    }
    assert mailbox == []
    assert _business_rows_added(fake_table, before) == set()
    (row,) = _audit_rows(fake_table)
    assert row["result_code"] == "account_exists"
    assert row["dry_run"] is dry_run
    assert row["target_id"] == "parent-2"


def test_the_claim_row_refuses_even_before_the_address_index_has_caught_up(
    fake_table, mailbox
) -> None:
    # The profile does not carry the address in the index yet; the claim row does.
    profile = _profile("student-9", "student", "S26-0009")
    profile.pop("email")
    fake_table.seed(
        profile,
        account_email_claim_repo.claim_item(
            email=ADDRESS, role="student", account_id="student-9", created_at="2026-01-01"
        ),
    )

    answer = _call("invite_account", {"role": "student", "email": ADDRESS, "dryRun": True})

    assert answer["error"]["code"] == "account_exists"
    assert "(S26-0009, active)" in answer["error"]["message"]
    assert mailbox == []


def test_the_same_address_in_another_role_is_free(fake_table, mailbox) -> None:
    fake_table.seed(_profile("parent-2", "parent", "P26-0002", email="held@stoa.test"))

    answer = _call("invite_account", {"role": "teacher", "email": "held@stoa.test", "dryRun": True})

    assert answer["ok"] is True
    assert answer["result"]["role"] == "teacher"


@pytest.mark.parametrize(
    "arguments",
    [
        {"role": "student", "email": ADDRESS},
        {"role": "student", "email": ADDRESS, "dryRun": "true"},
        {"role": "student", "email": ADDRESS, "dryRun": 1},
        {"role": "admin", "email": ADDRESS, "dryRun": True},
        {"role": "student", "email": ADDRESS, "dryRun": True, "locale": "es"},
        {"role": "student", "email": ADDRESS, "dryRun": True, "activationToken": "x"},
    ],
)
def test_an_invitation_must_say_dry_run_or_not_and_stay_in_its_lane(
    fake_table, mailbox, arguments
) -> None:
    answer = _call("invite_account", arguments)

    assert answer["error"]["code"] == "invalid_arguments"
    assert ADDRESS not in str(answer)
    assert mailbox == []
    assert _business_rows_added(fake_table, {}) == set()


def test_an_invalid_birthday_is_refused_in_the_dry_run_too(fake_table, mailbox) -> None:
    answer = _call(
        "invite_account",
        {"role": "student", "email": ADDRESS, "dateOfBirth": "2026-02-30", "dryRun": True},
    )

    assert answer["error"] == {
        "code": "date_of_birth_invalid",
        "message": "Refused: date_of_birth_invalid.",
    }


@pytest.mark.parametrize("key", ["invitationId", "accountNumber"])
def test_a_dry_run_reissue_reports_the_invitation_and_changes_nothing(
    fake_table, mailbox, key
) -> None:
    invited = _invite()
    mailbox.clear()
    before = _rows(fake_table)

    answer = _call("reissue_invitation", {key: invited[key], "dryRun": True})

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["dryRun"] is True
    assert result["invitationId"] == invited["invitationId"]
    assert result["invitationStatus"] == "issued"
    assert result["expired"] is False
    assert result["accountNumber"] == invited["accountNumber"]
    assert result["accountStatus"] == "invited"
    assert result["emailLanguage"] == "de"
    assert result["summary"].startswith(
        f"Now: invitation {invited['invitationId']} is issued; student account "
        f"{invited['accountNumber']} is invited. Would retire this invitation"
    )
    assert mailbox == []
    assert {key: fake_table.rows[key] for key in before} == before
    assert _business_rows_added(fake_table, before) == set()
    assert _audit_rows(fake_table)[-1]["dry_run"] is True
    _assert_no_secrets(answer, fake_table)


def test_a_real_reissue_retires_the_old_link_and_mails_a_new_one(fake_table, mailbox) -> None:
    invited = _invite()
    mailbox.clear()

    answer = _call(
        "reissue_invitation",
        {"accountNumber": invited["accountNumber"], "locale": "it", "dryRun": False},
    )

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["replacedInvitationId"] == invited["invitationId"]
    assert result["invitationId"] != invited["invitationId"]
    assert result["accountNumber"] == invited["accountNumber"]
    assert result["userId"] == invited["userId"]
    assert result["invitationDelivered"] is True
    (mail,) = mailbox
    assert mail["recipient"] == ADDRESS and mail["locale"] == "it"
    assert mail["activation_token"] not in str(answer)
    statuses = {row["invitation_id"]: row["status"] for row in _invitations(fake_table)}
    assert statuses == {invited["invitationId"]: "revoked", result["invitationId"]: "issued"}
    new_row = next(
        row for row in _invitations(fake_table) if row["invitation_id"] == result["invitationId"]
    )
    assert new_row["invited_by"] == "operator:agent_mcp"
    _assert_no_secrets(answer, fake_table)


def test_a_used_invitation_is_not_reissued(fake_table, mailbox) -> None:
    invited = _invite()
    (row,) = _invitations(fake_table)
    row["status"] = "used"
    mailbox.clear()

    answer = _call("reissue_invitation", {"invitationId": invited["invitationId"], "dryRun": True})

    assert answer["error"]["code"] == "invitation_already_used"
    assert answer["error"]["message"] == (
        f"Would be refused: invitation {invited['invitationId']} is used; student account "
        f"{invited['accountNumber']} is invited. A used invitation cannot be reissued."
    )
    assert mailbox == []


def test_an_administrator_invitation_is_not_reissued_by_an_agent(fake_table, mailbox) -> None:
    issued = account_provisioning_service.invite_account(
        actor=ADMIN_ACTOR, role="admin", email="new.admin@stoa.test"
    )

    for dry_run in (True, False):
        answer = _call(
            "reissue_invitation", {"invitationId": issued["invitationId"], "dryRun": dry_run}
        )
        assert answer["error"]["code"] == "role_not_provisionable"
    assert {row["status"] for row in _invitations(fake_table)} == {"issued"}


def test_a_dry_run_revoke_reports_the_invitation_and_changes_nothing(fake_table, mailbox) -> None:
    invited = _invite()
    before = _rows(fake_table)

    answer = _call("revoke_invitation", {"invitationId": invited["invitationId"], "dryRun": True})

    assert answer["ok"] is True, answer
    assert answer["result"]["dryRun"] is True
    assert answer["result"]["invitationStatus"] == "issued"
    assert answer["result"]["accountNumber"] == invited["accountNumber"]
    assert "Would revoke this invitation" in answer["result"]["summary"]
    assert {key: fake_table.rows[key] for key in before} == before
    assert _business_rows_added(fake_table, before) == set()
    _assert_no_secrets(answer, fake_table)


def test_a_real_revoke_retires_the_invitation_and_keeps_the_account(fake_table, mailbox) -> None:
    invited = _invite()

    answer = _call(
        "revoke_invitation", {"accountNumber": invited["accountNumber"].lower(), "dryRun": False}
    )

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["invitationId"] == invited["invitationId"]
    assert result["invitationStatus"] == "revoked"
    assert result["accountStatus"] == "invited"
    (row,) = _invitations(fake_table)
    assert row["status"] == "revoked"
    revoked = [
        event
        for (pk, _sk), event in fake_table.rows.items()
        if pk == f"SECURITY_AUDIT#{invited['userId']}"
        and event["event_type"] == "account_invitation_revoked"
    ]
    assert [event["actor_id"] for event in revoked] == ["operator:agent_mcp"]
    assert _audit_rows(fake_table)[-1]["target_id"] == invited["userId"]
    _assert_no_secrets(answer, fake_table)

    again = _call("revoke_invitation", {"invitationId": invited["invitationId"], "dryRun": True})
    assert again["error"]["code"] == "invitation_not_revocable"
    assert f"invitation {invited['invitationId']} is revoked" in again["error"]["message"]
    by_number = _call(
        "revoke_invitation", {"accountNumber": invited["accountNumber"], "dryRun": True}
    )
    assert by_number["error"] == {
        "code": "invitation_not_found",
        "message": f"Account {invited['accountNumber']} (invited) has no open invitation.",
    }


@pytest.mark.parametrize(
    ("operation", "arguments", "code"),
    [
        (
            "revoke_invitation",
            {"invitationId": "accountinvite_nope", "dryRun": True},
            "invitation_not_found",
        ),
        ("reissue_invitation", {"accountNumber": "S26-9999", "dryRun": True}, "account_not_found"),
        ("revoke_invitation", {"dryRun": True}, "invalid_arguments"),
        (
            "revoke_invitation",
            {"invitationId": "a", "accountNumber": "S26-0001", "dryRun": True},
            "invalid_arguments",
        ),
    ],
)
def test_invitation_refusals_are_recorded(fake_table, operation, arguments, code) -> None:
    answer = _call(operation, arguments)

    assert answer["error"]["code"] == code
    assert _audit_rows(fake_table)[0]["result_code"] == code


def test_a_real_write_whose_row_fails_says_it_ran(fake_table, mailbox, monkeypatch) -> None:
    real_append = security_audit_repo.append_event

    def operator_rows_fail(stream_id, event, **kwargs):
        if stream_id == catalog.OPERATOR_ACTOR_ID:
            raise RuntimeError("audit table down")
        return real_append(stream_id, event, **kwargs)

    monkeypatch.setattr(security_audit_repo, "append_event", operator_rows_fail)

    answer = _call("invite_account", {"role": "student", "email": ADDRESS, "dryRun": False})

    assert answer["error"]["code"] == "audit_unavailable"
    assert "ran but could not be recorded" in answer["error"]["message"]
    assert len(mailbox) == 1


# -- delete_account (#396) -------------------------------------------------------------


REASON = "Parent asked by email to close the trial account."


def _fence(user_id: str, status: str = "active", **fields: Any) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "ACCOUNT_FENCE",
        "entity_type": "account_fence",
        "schema_version": "account-fence.v1",
        "user_id": user_id,
        "status": status,
        "generation": 1,
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        **fields,
    }


def _number_claim(user_id: str, number: str) -> dict[str, Any]:
    return {
        "PK": f"ACCOUNT_NUMBER#{number}",
        "SK": "ACCOUNT_NUMBER",
        "entity_type": "account_number",
        "account_number": number,
        "account_id": user_id,
    }


def _seed_account(table, user_id: str, role: str, number: str, **fields: Any) -> None:
    table.seed(
        _profile(user_id, role, number, **fields),
        _fence(user_id),
        _number_claim(user_id, number),
    )


def _delete(number: str, *, dry: bool, confirm: str | None = None, **extra: Any) -> dict:
    arguments: dict[str, Any] = {"accountNumber": number, "reason": REASON, "dryRun": dry}
    if confirm is not None:
        arguments["confirmAccountNumber"] = confirm
    arguments.update(extra)
    return _call("delete_account", arguments)


def _deletion_commands(table) -> list[dict[str, Any]]:
    return [
        row
        for (_pk, sk), row in table.rows.items()
        if sk.startswith("DELETE_COMMAND#")
    ]


def test_delete_account_is_destructive_and_says_it_cannot_be_undone() -> None:
    spec = catalog.OPERATIONS_BY_NAME["delete_account"]
    assert spec.destructive is True
    assert spec.description.startswith("Changes data. Irreversible.")
    assert "dryRun=true first" in spec.description
    schema = spec.input_schema()
    assert set(schema["required"]) == {"accountNumber", "reason", "dryRun"}
    assert "confirmAccountNumber" in schema["properties"]
    import stoa_admin_mcp

    (tool,) = [
        tool for tool in stoa_admin_mcp.tool_definitions() if tool["name"] == "delete_account"
    ]
    assert tool["annotations"]["destructiveHint"] is True
    assert tool["annotations"]["readOnlyHint"] is False


def test_a_dry_run_deletion_shows_the_student_and_writes_no_business_row(
    fake_table, link_rows
) -> None:
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    _seed_account(
        fake_table, "parent-1", "parent", "P26-0001", usage_period_ends_at="2026-12-31"
    )
    link_rows.link("parent-1", "student-1")
    before = _rows(fake_table)

    answer = _delete("S26-0001", dry=True)

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["canDelete"] is True
    assert result["refusal"] is None
    assert result["accountNumber"] == "S26-0001"
    assert result["role"] == "student"
    assert result["accountStatus"] == "active"
    assert [item["accountNumber"] for item in result["linkedAccounts"]] == ["P26-0001"]
    assert result["usagePeriod"]["effective"]["paidBy"] == "parent"
    assert result["usagePeriodPaidBy"] == "parent P26-0001"
    assert result["usagePeriod"]["effective"]["endsOn"] == "2026-12-31"
    assert "Irreversible" in result["summary"]
    assert "email address is released when the deletion completes" in result["irreversible"]
    assert "Links that end: P26-0001." in result["summary"]
    assert {key: fake_table.rows[key] for key in before} == before
    assert _business_rows_added(fake_table, before) == set()
    (row,) = _audit_rows(fake_table)
    assert row["action"] == "delete_account"
    assert row["dry_run"] is True
    assert row["actor_id"] == "operator:agent_mcp"
    assert row["target_id"] == "student-1"
    assert row["evidence_reference"] == f"would_delete:S26-0001;reason:{REASON}"
    assert "sub-secret" not in str(answer) and "hash-secret" not in str(answer)


def test_a_dry_run_names_why_an_account_cannot_be_deleted(fake_table) -> None:
    _seed_account(fake_table, "teacher-1", "teacher", "T26-0001")
    before = _rows(fake_table)

    answer = _delete("T26-0001", dry=True)

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["canDelete"] is False
    assert result["refusal"]["code"] == "teacher_not_deletable"
    assert result["summary"].startswith("Would be refused: account T26-0001.")
    assert _business_rows_added(fake_table, before) == set()
    assert _audit_rows(fake_table)[0]["evidence_reference"].startswith(
        "would_refuse:teacher_not_deletable;reason:"
    )


@pytest.mark.parametrize("confirm", [None, "S26-0002", "s26-0001", " S26-0001"])
def test_a_real_deletion_needs_the_number_confirmed_exactly(fake_table, confirm) -> None:
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    before = _rows(fake_table)

    answer = _delete("S26-0001", dry=False, confirm=confirm)

    assert answer["error"]["code"] == "confirmation_mismatch"
    assert "Nothing was deleted." in answer["error"]["message"]
    assert _business_rows_added(fake_table, before) == set()
    assert fake_table.rows[("USER#student-1", "ACCOUNT_FENCE")]["status"] == "active"
    (row,) = _audit_rows(fake_table)
    assert row["result_code"] == "confirmation_mismatch"
    assert row["dry_run"] is False
    assert row["evidence_reference"] == f"refused:confirmation_mismatch;reason:{REASON}"


@pytest.mark.parametrize(
    ("role", "status", "code"),
    [
        ("teacher", "active", "teacher_not_deletable"),
        ("teacher", "suspended", "teacher_not_deletable"),
        ("admin", "active", "account_role_not_deletable"),
        ("admin", "invited", "account_role_not_deletable"),
        ("student", "archived", "account_status_not_deletable"),
        ("parent", "provisioning_failed", "account_status_not_deletable"),
    ],
)
def test_accounts_an_agent_may_not_delete_are_refused(fake_table, role, status, code) -> None:
    _seed_account(fake_table, "account-1", role, "X26-0001", account_status=status)
    before = _rows(fake_table)

    for dry in (True, False):
        answer = _delete("X26-0001", dry=dry, confirm="X26-0001")
        if dry:
            assert answer["result"]["refusal"]["code"] == code
        else:
            assert answer["error"]["code"] == code
            assert answer["error"]["message"].startswith("Refused: account X26-0001.")

    assert _business_rows_added(fake_table, before) == set()
    assert fake_table.rows[("USER#account-1", "ACCOUNT_FENCE")]["status"] == "active"


def test_an_invited_teacher_may_be_deleted(fake_table) -> None:
    _seed_account(fake_table, "teacher-1", "teacher", "T26-0001", account_status="invited")

    assert _delete("T26-0001", dry=True)["result"]["canDelete"] is True


def test_an_active_subscription_is_refused_until_billing_is_settled(fake_table) -> None:
    _seed_account(fake_table, "parent-1", "parent", "P26-0001")
    fake_table.seed(
        {
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "entity_type": "subscription_billing",
            "billing_status": "active",
        }
    )
    before = _rows(fake_table)

    dry = _delete("P26-0001", dry=True)["result"]
    real = _delete("P26-0001", dry=False, confirm="P26-0001")

    assert dry["refusal"]["code"] == "billing_active"
    assert "subscription billing is active" in dry["refusal"]["message"]
    assert "Settle billing first" in dry["refusal"]["message"]
    assert real["error"]["code"] == "billing_active"
    assert _business_rows_added(fake_table, before) == set()


def test_a_student_covered_by_a_paid_plan_is_refused(fake_table, link_rows) -> None:
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    _seed_account(fake_table, "parent-1", "parent", "P26-0001")
    link_rows.link("parent-1", "student-1")
    fake_table.seed(
        {
            "PK": "PAID_GRANT#parent-1",
            "SK": "BENEFICIARY#student-1",
            "entity_type": "beneficiary_grant",
            "grant_status": "active",
            "plan_id": "family",
            "parent_id": "parent-1",
            "beneficiary_id": "student-1",
        }
    )

    result = _delete("S26-0001", dry=True)["result"]

    assert result["refusal"]["code"] == "billing_active"
    assert "a parent's paid plan covers this account" in result["refusal"]["message"]


def test_a_usage_period_alone_does_not_hold_a_deletion_up(fake_table) -> None:
    _seed_account(
        fake_table, "parent-1", "parent", "P26-0001", usage_period_ends_at="2027-06-30"
    )
    fake_table.seed(
        {
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "entity_type": "subscription_billing",
            "billing_status": "canceled",
        }
    )

    result = _delete("P26-0001", dry=True)["result"]

    assert result["canDelete"] is True
    assert result["usagePeriod"]["endsOn"] == "2027-06-30"
    assert result["usagePeriodPaidBy"] == "the parent's own period"


def test_a_real_deletion_enters_the_one_pipeline_and_records_who_and_why(
    fake_table,
) -> None:
    from stoa.db.repositories import account_deletion_repo
    from stoa.services import account_deletion_service

    _seed_account(fake_table, "student-1", "student", "S26-0001")

    answer = _delete("S26-0001", dry=False, confirm="S26-0001")

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert set(result) == {
        "dryRun",
        "summary",
        "accountNumber",
        "deletionCommandId",
        "acceptedAt",
        "status",
        "revokedInvitationId",
    }
    assert result["status"] == "deletion_pending"
    assert result["accountNumber"] == "S26-0001"
    assert result["revokedInvitationId"] is None
    fence = fake_table.rows[("USER#student-1", "ACCOUNT_FENCE")]
    assert fence["status"] == "deletion_pending"
    assert fence["command_id"] == result["deletionCommandId"]
    (command,) = _deletion_commands(fake_table)
    assert command["command_id"] == result["deletionCommandId"]
    assert command["status"] == "pending"
    assert command["initiated_by"] == "operator:agent_mcp"
    assert command["reason"] == REASON
    assert command["fingerprint"] == account_deletion_service.operator_deletion_command_fingerprint(
        initiated_by="operator:agent_mcp", user_id="student-1", generation=1
    )
    assert "issuer_hash" not in command and "subject_hash" not in command
    assert command["branch_ids"] == list(account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS)
    (row,) = _audit_rows(fake_table)
    assert row["dry_run"] is False
    assert row["actor_id"] == "operator:agent_mcp"
    assert row["evidence_reference"] == (
        f"account-deletion:{result['deletionCommandId']};reason:{REASON}"
    )
    _assert_no_secrets(answer, fake_table)
    assert "fingerprint" not in str(answer) and "PK" not in str(answer)

    # The scheduled job's sweep finds it, as it finds a self-deletion.
    page = account_deletion_repo.scan_pending_deletion_commands(table=fake_table)
    assert [item["command_id"] for item in page.items] == [result["deletionCommandId"]]

    # And it is not accepted twice.
    again = _delete("S26-0001", dry=False, confirm="S26-0001")
    assert again["error"]["code"] == "account_deletion_in_progress"
    assert result["deletionCommandId"] in again["error"]["message"]
    assert len(_deletion_commands(fake_table)) == 1


def test_an_invited_parents_invitation_is_revoked_and_its_dry_run_says_so(
    fake_table, mailbox
) -> None:
    invited = _invite(role="parent", email="invited.parent@stoa.test")
    number = invited["accountNumber"]

    dry = _delete(number, dry=True)
    assert dry["ok"] is True, dry
    preview = dry["result"]
    assert preview["role"] == "parent"
    assert preview["accountStatus"] == "invited"
    assert preview["canDelete"] is True
    assert preview["openInvitationId"] == invited["invitationId"]
    assert preview["linkedAccounts"] == []
    assert f"Its open invitation {invited['invitationId']} is revoked first." in preview["summary"]
    (invitation,) = _invitations(fake_table)
    assert invitation["status"] == "issued"

    answer = _delete(number, dry=False, confirm=number)

    assert answer["ok"] is True, answer
    assert answer["result"]["revokedInvitationId"] == invited["invitationId"]
    (invitation,) = _invitations(fake_table)
    assert invitation["status"] == "revoked"
    fence = fake_table.rows[(f"USER#{invited['userId']}", "ACCOUNT_FENCE")]
    assert fence["status"] == "deletion_pending"
    _assert_no_secrets(answer, fake_table)


def test_get_account_shows_a_deletion_in_progress_then_completed(fake_table) -> None:
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    assert _call("get_account", {"accountNumber": "S26-0001"})["result"]["deletion"] == {
        "state": "none"
    }

    accepted = _delete("S26-0001", dry=False, confirm="S26-0001")["result"]
    shown = _call("get_account", {"accountNumber": "S26-0001"})["result"]

    assert shown["accountStatus"] == "active"
    assert shown["deletion"] == {
        "state": "in_progress",
        "commandId": accepted["deletionCommandId"],
        "acceptedAt": accepted["acceptedAt"],
        "initiatedBy": "operator:agent_mcp",
    }

    # What the pipeline leaves once it has finished: a tombstone profile, a
    # terminal fence and a terminal command.
    command_key = ("USER#student-1", f"DELETE_COMMAND#{accepted['deletionCommandId']}")
    fake_table.seed(
        {
            "PK": "USER#student-1",
            "SK": "PROFILE",
            "entity_type": "user_deletion_tombstone",
            "schema_version": "account-deletion-tombstone.v1",
            "status": "deleted",
            "owner_deletion_generation": 1,
            "deleted_at": "2026-11-11T12:10:00+00:00",
        },
        {
            **fake_table.rows[("USER#student-1", "ACCOUNT_FENCE")],
            "status": "deleted",
            "deleted_at": "2026-11-11T12:10:00+00:00",
        },
        {**fake_table.rows[command_key], "status": "complete"},
    )

    done = _call("get_account", {"accountNumber": "S26-0001"})

    assert done["ok"] is True, done
    assert done["result"]["role"] is None
    assert done["result"]["deletion"]["state"] == "completed"
    assert done["result"]["deletion"]["completedAt"] == "2026-11-11T12:10:00+00:00"
    assert "student-1@stoa.test" not in str(done)
    refused = _delete("S26-0001", dry=True)
    assert refused["error"]["code"] == "account_already_deleted"


def test_a_self_deletion_still_records_the_account_and_meets_no_operator_command(
    fake_table,
) -> None:
    from stoa.db.repositories import account_deletion_repo
    from stoa.security.tokens import VerifiedAccessToken
    from stoa.services import account_deletion_service

    token = VerifiedAccessToken(
        issuer="https://identity.example/pool",
        subject="subject-1",
        client_id="student-client",
        groups=("students",),
    )
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    _seed_account(fake_table, "student-2", "student", "S26-0002")

    receipt = account_deletion_service.accept_account_deletion(
        user_id="student-1",
        initiator=account_deletion_service.SelfInitiated(verified=token),
        now_iso="2026-11-11T12:00:00+00:00",
    )
    (command,) = _deletion_commands(fake_table)
    assert command["initiated_by"] == "student-1"
    assert "reason" not in command
    assert command["path"] == "/auth/me"
    assert command["fingerprint"] == account_deletion_service.deletion_command_fingerprint(
        verified=token,
        user_id="student-1",
        method="DELETE",
        path="/auth/me",
        body=b"",
        generation=1,
    )
    assert account_deletion_service.begin_or_replay_deletion(
        verified=token,
        user_id="student-1",
        method="DELETE",
        path="/auth/me",
        body=b"",
        now_iso="2026-11-11T12:05:00+00:00",
    ) == receipt
    assert _call("get_account", {"userId": "student-1"})["result"]["deletion"][
        "initiatedBy"
    ] == "self"
    # An operator cannot take over a deletion the account started.
    assert _delete("S26-0001", dry=True)["error"]["code"] == "account_deletion_in_progress"

    # And the other way round: an operator's command is not the account's to replay.
    _delete("S26-0002", dry=False, confirm="S26-0002")
    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_service.accept_account_deletion(
            user_id="student-2",
            initiator=account_deletion_service.SelfInitiated(verified=token),
            now_iso="2026-11-11T12:05:00+00:00",
        )
