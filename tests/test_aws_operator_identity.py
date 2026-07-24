from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from stoa.security.aws_operator_identity import (
    AwsOperatorIdentityError,
    require_sso_operator_session,
)


ACCOUNT_ID = "562923011260"


class FakeSts:
    def __init__(self, identity=None, error=None):
        self.identity = identity
        self.error = error

    def get_caller_identity(self):
        if self.error:
            raise self.error
        return self.identity


class FakeSession:
    def __init__(self, identity=None, error=None):
        self.sts = FakeSts(identity=identity, error=error)

    def client(self, service_name, **_kwargs):
        assert service_name == "sts"
        return self.sts


def _identity(arn: str, account_id: str = ACCOUNT_ID):
    return {"Account": account_id, "Arn": arn, "UserId": "session-user"}


def test_accepts_expected_identity_center_role():
    session = FakeSession(
        identity=_identity(
            f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/"
            "AWSReservedSSO_AdministratorAccess_example/Deng_Zhiyuan"
        )
    )

    assert require_sso_operator_session(
        profile_name="stoa",
        region_name="eu-central-2",
        expected_account_id=ACCOUNT_ID,
        session=session,
    ) is session


@pytest.mark.parametrize(
    "arn",
    [
        f"arn:aws:iam::{ACCOUNT_ID}:user/Deng_Zhiyuan",
        f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/custom-admin/session",
        f"arn:aws:iam::{ACCOUNT_ID}:root",
    ],
)
def test_rejects_static_user_root_and_non_sso_roles(arn):
    with pytest.raises(AwsOperatorIdentityError, match="Refusing non-SSO"):
        require_sso_operator_session(
            profile_name="stoa-prod-admin",
            region_name="eu-central-2",
            expected_account_id=ACCOUNT_ID,
            session=FakeSession(identity=_identity(arn)),
        )


def test_rejects_wrong_account():
    with pytest.raises(AwsOperatorIdentityError, match="wrong account"):
        require_sso_operator_session(
            profile_name="stoa",
            region_name="eu-central-2",
            expected_account_id=ACCOUNT_ID,
            session=FakeSession(
                identity=_identity(
                    "arn:aws:sts::111122223333:assumed-role/"
                    "AWSReservedSSO_AdministratorAccess_example/session",
                    account_id="111122223333",
                )
            ),
        )


def test_provider_failure_is_redacted():
    error = ClientError(
        {"Error": {"Code": "ExpiredToken", "Message": "provider detail"}},
        "GetCallerIdentity",
    )
    with pytest.raises(AwsOperatorIdentityError, match="Unable to verify AWS SSO identity") as exc:
        require_sso_operator_session(
            profile_name="stoa",
            region_name="eu-central-2",
            expected_account_id=ACCOUNT_ID,
            session=FakeSession(error=error),
        )
    assert "provider detail" not in str(exc.value)
