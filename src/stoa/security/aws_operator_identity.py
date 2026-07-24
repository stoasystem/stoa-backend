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
            f"Unable to verify AWS SSO identity for profile {profile_name!r}."
        ) from exc

    account_id = str(identity.get("Account") or "")
    caller_arn = str(identity.get("Arn") or "")
    expected_arn_prefix = (
        f"arn:aws:sts::{expected_account_id}:assumed-role/AWSReservedSSO_"
    )
    if account_id != expected_account_id:
        raise AwsOperatorIdentityError("AWS SSO identity resolved to the wrong account.")
    if not caller_arn.startswith(expected_arn_prefix):
        raise AwsOperatorIdentityError(
            "Refusing non-SSO AWS credentials; run 'aws sso login --profile stoa'."
        )
    return aws_session
