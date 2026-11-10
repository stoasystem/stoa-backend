"""Fail-closed AWS identity checks for local operator scripts."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class AwsOperatorIdentityError(RuntimeError):
    """Raised when an operator script is not authenticated through approved SSO."""


def require_sso_operator_session(
    *,
    profile_name: str,
    region_name: str,
    expected_account_id: str,
    session: Any | None = None,
) -> Any:
    """Return a verified SSO session or fail before an operator script can mutate AWS."""
    profile_name = profile_name.strip()
    expected_account_id = expected_account_id.strip()
    if not profile_name:
        raise AwsOperatorIdentityError("An explicit AWS SSO profile is required.")
    if not expected_account_id:
        raise AwsOperatorIdentityError("An expected AWS account ID is required.")

    aws_session = session or boto3.Session(
        profile_name=profile_name,
        region_name=region_name,
    )
    try:
        identity = aws_session.client("sts", region_name=region_name).get_caller_identity()
    except (BotoCoreError, ClientError) as exc:
        raise AwsOperatorIdentityError(
            f"Unable to verify AWS SSO identity for profile {profile_name!r}; {SSO_LOGIN_HINT}."
        ) from exc

    check_sso_operator_identity(
        account_id=str(identity.get("Account") or ""),
        caller_arn=str(identity.get("Arn") or ""),
        expected_account_id=expected_account_id,
    )
    return aws_session


SSO_LOGIN_HINT = "run 'aws sso login --sso-session stoa'"


def check_sso_operator_identity(
    *, account_id: str, caller_arn: str, expected_account_id: str
) -> None:
    """The one rule for an operator identity: the expected account, through Identity Center.

    Shared by the local operator scripts, which ask STS themselves, and by the
    operator calls the API function verifies on the caller's behalf (#383).
    """
    expected_account_id = expected_account_id.strip()
    if not expected_account_id:
        raise AwsOperatorIdentityError("An expected AWS account ID is required.")
    expected_arn_prefix = (
        f"arn:aws:sts::{expected_account_id}:assumed-role/AWSReservedSSO_"
    )
    if account_id != expected_account_id:
        raise AwsOperatorIdentityError("AWS SSO identity resolved to the wrong account.")
    if not caller_arn.startswith(expected_arn_prefix):
        raise AwsOperatorIdentityError(
            f"Refusing non-SSO AWS credentials; {SSO_LOGIN_HINT}."
        )
