"""The deletion comparison (#640) only reads: the table, S3 and every other AWS call.

`scripts/compare_deletion_plan.py` runs the old deletion branches for real, so
everything they would write has to land in its in-memory copy and nowhere else.
These tests hold it to that: run over a table holding one account's rows of
every kind a branch deletes, the live table is asked for nothing but a scan and
is unchanged afterwards, S3 is only read, and any botocore call that is not a
read is refused before it is sent.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

from fakes.dynamodb import FakeTable
from scripts import compare_deletion_plan as compare
from stoa.config import Settings
from stoa.db import table as db_table
from test_account_deletion_branch_coverage import ACCOUNT, WRITER, deleted_by_branch


class LiveTable:
    """The production table as the comparison sees it: a scan, and nothing else."""

    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.calls: list[str] = []

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("scan")
        return self.table.scan(**kwargs)

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        raise AssertionError(f"the comparison asked the live table for {name}")


class LiveS3:
    """S3 with nothing stored; any call that is not a read fails the test."""

    READS = frozenset({"list_object_versions", "head_object"})
    exceptions = None

    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_object_versions(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("list_object_versions")
        return {"Versions": [], "DeleteMarkers": [], "IsTruncated": False}

    def head_object(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("head_object")
        raise compare._not_found("HeadObject")

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        raise AssertionError(f"the comparison sent s3:{name}")


def _production_like_table() -> FakeTable:
    """One account with a profile and a row of every kind a branch deletes, registered."""
    table = FakeTable()
    table.seed_active_account(ACCOUNT)
    table.seed_active_account(WRITER)
    profile = {
        "PK": f"USER#{ACCOUNT}",
        "SK": "PROFILE",
        "user_id": ACCOUNT,
        "role": "student",
        "email": "student@example.test",
        "display_name": "Student",
    }
    for row in [profile, *(row for _, row in deleted_by_branch().values())]:
        db_table.fenced(WRITER, [{"Put": {"Item": row}}], table=table)
    return table


def test_the_comparison_only_reads_the_table_and_s3():
    stored = _production_like_table()
    before = deepcopy(stored.rows)
    live, s3 = LiveTable(stored), LiveS3()

    with compare.read_only_aws():
        report = compare.run(live, s3, settings=Settings())

    assert set(live.calls) == {"scan"}
    assert stored.rows == before
    assert set(s3.calls) <= LiveS3.READS
    assert report["accounts_compared"] == 1
    assert report["rows_compared"] >= len(deleted_by_branch())
    # The in-memory run is taken down again: the suite's table is not left installed.
    assert db_table._installed is None


def test_every_difference_names_its_row_and_both_actions():
    with compare.read_only_aws():
        report = compare.run(LiveTable(_production_like_table()), LiveS3(), settings=Settings())

    for row in report["difference_rows"]:
        assert {"PK", "SK", "type", "old", "new", "reason"} <= row.keys()
        # Account ids are aliased unless asked for.
        assert ACCOUNT not in row["PK"] + row["SK"]


@pytest.mark.parametrize(
    ("service", "call", "params"),
    [
        ("dynamodb", "put_item", {"TableName": "t", "Item": {"PK": {"S": "a"}, "SK": {"S": "b"}}}),
        ("dynamodb", "delete_item", {"TableName": "t", "Key": {"PK": {"S": "a"}, "SK": {"S": "b"}}}),
        ("dynamodb", "update_item", {"TableName": "t", "Key": {"PK": {"S": "a"}, "SK": {"S": "b"}}}),
        ("dynamodb", "transact_write_items", {"TransactItems": []}),
        ("s3", "delete_object", {"Bucket": "b", "Key": "k"}),
        ("s3", "put_object", {"Bucket": "b", "Key": "k"}),
        ("cognito-idp", "admin_delete_user", {"UserPoolId": "p", "Username": "u"}),
        ("cognito-idp", "admin_user_global_sign_out", {"UserPoolId": "p", "Username": "u"}),
        ("ses", "send_email", {"Source": "a", "Destination": {}, "Message": {}}),
    ],
)
def test_the_guard_refuses_every_call_that_is_not_a_read(service, call, params):
    client = boto3.client(
        service,
        region_name="eu-central-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    # No stub and no network: were the guard to let it through, the call would
    # fail on the socket, not with `RefusedCall`.
    with compare.read_only_aws(), pytest.raises(compare.RefusedCall):
        getattr(client, call)(**params)


def test_the_guard_lets_a_read_through_and_is_taken_down_afterwards():
    client = boto3.client(
        "dynamodb",
        region_name="eu-central-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stubber:
        stubber.add_response("query", {"Items": []})
        stubber.add_response("put_item", {})
        with compare.read_only_aws():
            assert client.query(TableName="t", KeyConditionExpression="PK = :p")["Items"] == []
        # Outside the guard the stubbed write goes through again.
        client.put_item(TableName="t", Item={"PK": {"S": "a"}, "SK": {"S": "b"}})


def test_the_sandbox_doubles_refuse_what_they_do_not_record():
    sandbox = compare.SandboxTable(compare.Snapshot([]))
    with pytest.raises(compare.RefusedCall):
        compare.SandboxS3(LiveS3(), sandbox).put_object(Bucket="b", Key="k")
    with pytest.raises(compare.RefusedCall):
        compare.SandboxProvider().admin_create_user(UserPoolId="p", Username="u")
    with pytest.raises(compare.RefusedCall):
        compare.Refusing(compare.Kind.SES).send_email()
