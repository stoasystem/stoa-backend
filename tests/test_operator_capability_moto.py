"""#84 against moto: the real capability transaction, not a stub of it.

Adapted from the external audit's offline probes (2026-09-30). The stubbed
tests in test_operator_capability.py cannot show which credentials sign the
store's transaction, nor what a revoke does to the rows a rerun reads.
"""

import boto3
from botocore.stub import Stubber
from moto import mock_aws
import pytest

import operator_capability as script
from stoa.db.repositories import capability_repo
from stoa.security.aws_operator_identity import require_sso_operator_session

ADMIN = "audit-admin"
CAPABILITY = capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER
WHEN = "2020-01-01T12:00:00+00:00"


def make_table(session):
    table = session.resource("dynamodb", region_name="eu-central-2").create_table(
        TableName="audit-only",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                              {"AttributeName": "SK", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(Item={"PK": f"USER#{ADMIN}", "SK": "PROFILE", "user_id": ADMIN,
                         "role": "admin", "account_status": "active"})
    table.put_item(Item={"PK": f"USER#{ADMIN}", "SK": "ACCOUNT_FENCE",
                         "status": "active", "generation": 1})
    return table


def issue(table, capability=CAPABILITY, dry_run=False):
    status, _repaired = script.grant(table, user_id=ADMIN, capability=capability, scope="global",
                        incident_reason="offline audit probe", dry_run=dry_run,
                        now=lambda: WHEN)
    return status


@mock_aws
def test_the_grant_transaction_signs_with_the_verified_operator_key(monkeypatch):
    operator = boto3.Session(aws_access_key_id="VERIFIED_OPERATOR_KEY",
                             aws_secret_access_key="fake-operator-secret")
    sts = operator.client("sts", region_name="eu-central-2")
    stub = Stubber(sts)
    stub.add_response("get_caller_identity", {
        "Account": "123456789012", "UserId": "operator",
        "Arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_Admin/operator",
    })
    original_operator_client = operator.client
    monkeypatch.setattr(operator, "client", lambda name, **kw:
                        sts if name == "sts" else original_operator_client(name, **kw))
    with stub:
        verified = require_sso_operator_session(profile_name="operator", region_name="eu-central-2",
                                                expected_account_id="123456789012", session=operator)
    table = script.SessionTable(
        make_table(verified), verified.client("dynamodb", region_name="eu-central-2")
    )
    boto3.setup_default_session(aws_access_key_id="UNVERIFIED_DEFAULT_KEY",
                               aws_secret_access_key="fake-default-secret")
    original_client = boto3.client
    transaction_keys = []

    def capture(name, **kwargs):
        client = original_client(name, **kwargs)
        transaction_keys.append(client._request_signer._credentials.access_key)
        return client

    monkeypatch.setattr(boto3, "client", capture)
    assert issue(table) == "issued"
    assert table.meta.client._request_signer._credentials.access_key == "VERIFIED_OPERATOR_KEY"
    assert table._client._request_signer._credentials.access_key == "VERIFIED_OPERATOR_KEY"
    assert transaction_keys == []  # no ambient client was opened for the transaction


@mock_aws
def test_a_grant_revoked_after_its_row_was_lost_is_recorded_on_rerun(monkeypatch):
    boto3.setup_default_session(aws_access_key_id="testing", aws_secret_access_key="testing")
    table = make_table(boto3.DEFAULT_SESSION)
    append = script._append_audit

    def unavailable(*args, **kwargs):
        raise RuntimeError("simulated crash after grant transaction")

    monkeypatch.setattr(script, "_append_audit", unavailable)
    with pytest.raises(RuntimeError, match="simulated crash"):
        issue(table)
    original, = capability_repo.get_current_grants(ADMIN, table_factory=lambda: table)
    capability_repo.revoke_capability(
        user_id=ADMIN, grant_id=original["grant_id"], capability=CAPABILITY, scope="global",
        expected_generation=int(original["generation"]), expected_version=int(original["version"]),
        actor_id="second-admin", reason="revoked", changed_at=WHEN, action_id="revoke-probe",
        table_factory=lambda: table,
    )
    monkeypatch.setattr(script, "_append_audit", append)
    assert issue(table) == "issued"
    old_audit = {"PK": f"SECURITY_AUDIT#{ADMIN}",
                 "SK": f"EVENT#{script._grant_event_id(original['grant_id'])}"}
    assert "Item" in table.get_item(Key=old_audit, ConsistentRead=True)
    replacement, = capability_repo.get_current_grants(ADMIN, table_factory=lambda: table)
    assert replacement["grant_id"] != original["grant_id"]
