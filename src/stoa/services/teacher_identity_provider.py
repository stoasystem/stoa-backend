"""Cognito adapter for invitation-gated teacher account creation.

Account creation lives behind an adapter so the activation lifecycle stays free of
provider details and can be driven by a double in tests. The adapter never chooses who
may become a teacher; it only executes a decision already authorised by a single-use
invitation.
"""

from __future__ import annotations

from typing import Any, Protocol

from botocore.exceptions import ClientError


class TeacherAccountExists(RuntimeError):
    """An identity already exists for the invited address."""


class TeacherAccountPasswordRejected(RuntimeError):
    """The provider refused the supplied password."""


class TeacherAccountUnavailable(RuntimeError):
    """The provider could not complete account setup."""


class TeacherIdentityProvider(Protocol):
    def create_teacher_account(self, *, email: str, password: str) -> str: ...

    def ensure_teacher_identity(self, *, email: str, user_id: str, group: str) -> None: ...


class CognitoTeacherIdentityProvider:
    def __init__(self, client: Any, *, user_pool_id: str) -> None:
        if not user_pool_id:
            raise TeacherAccountUnavailable("teacher identity pool is not configured")
        self._client = client
        self._user_pool_id = user_pool_id

    def create_teacher_account(self, *, email: str, password: str) -> str:
        """Create one confirmed account for the invited address and return its subject.

        The address comes from the invitation rather than from client input, and the
        account is created with `MessageAction=SUPPRESS` so Cognito does not send a
        competing temporary-password email alongside our activation link.
        """
        try:
            created = self._client.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                ],
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "UsernameExistsException":
                raise TeacherAccountExists(email) from exc
            raise TeacherAccountUnavailable(str(code or "admin_create_user failed")) from exc

        subject = _subject_of(created)
        try:
            self._client.admin_set_user_password(
                UserPoolId=self._user_pool_id,
                Username=email,
                Password=password,
                Permanent=True,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"InvalidPasswordException", "InvalidParameterException"}:
                raise TeacherAccountPasswordRejected(str(code)) from exc
            raise TeacherAccountUnavailable(str(code or "admin_set_user_password failed")) from exc
        return subject

    def ensure_teacher_identity(self, *, email: str, user_id: str, group: str) -> None:
        del user_id
        try:
            self._client.admin_add_user_to_group(
                UserPoolId=self._user_pool_id,
                Username=email,
                GroupName=group,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            raise TeacherAccountUnavailable(str(code or "admin_add_user_to_group failed")) from exc


def _subject_of(created: Any) -> str:
    user = created.get("User") if isinstance(created, dict) else None
    attributes = user.get("Attributes") if isinstance(user, dict) else None
    if not isinstance(attributes, list):
        raise TeacherAccountUnavailable("provider response is missing user attributes")
    for attribute in attributes:
        if isinstance(attribute, dict) and attribute.get("Name") == "sub":
            subject = str(attribute.get("Value") or "").strip()
            if subject:
                return subject
    raise TeacherAccountUnavailable("provider response is missing the account subject")
