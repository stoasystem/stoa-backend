"""Who made an operator call, as STS says and not as the caller says (#383).

The caller sends the signature of a GetCallerIdentity request made with its own
SSO credentials. This module sends that request to STS from inside the function
and applies the operator rule of `security.aws_operator_identity` to the answer.
Only the signature headers are taken from the caller; the endpoint, the body and
the content type are fixed in `catalog`, so the request cannot be pointed
anywhere else or made to ask anything else. A signature is good for about fifteen
minutes, and only someone allowed to invoke the function can hand one in.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from xml.etree import ElementTree

import httpx

from stoa.operator_calls import catalog
from stoa.security.aws_operator_identity import (
    SSO_LOGIN_HINT,
    AwsOperatorIdentityError,
    check_sso_operator_identity,
)


STS_TIMEOUT_SECONDS = 5.0
MAX_HEADER_LENGTH = 4096
_STS_NAMESPACE = "{https://sts.amazonaws.com/doc/2011-06-15/}"


class CallerNotVerified(RuntimeError):
    """The caller's identity could not be verified; the message is safe to return."""


@dataclass(frozen=True, slots=True)
class StsAnswer:
    status: int
    body: bytes


Post = Callable[[str, Mapping[str, str], bytes], StsAnswer]


def _post(url: str, headers: Mapping[str, str], body: bytes) -> StsAnswer:
    response = httpx.post(url, headers=dict(headers), content=body, timeout=STS_TIMEOUT_SECONDS)
    return StsAnswer(response.status_code, response.content)


def _refused(reason: str) -> CallerNotVerified:
    return CallerNotVerified(f"{reason}; {SSO_LOGIN_HINT} and call again.")


def _signed_headers(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise _refused("The call carries no signed identity")
    headers: dict[str, str] = {}
    for name, header in value.items():
        key = str(name).lower()
        if key not in catalog.SIGNED_HEADERS:
            continue
        if (
            not isinstance(header, str)
            or not header
            or len(header) > MAX_HEADER_LENGTH
            or "\r" in header
            or "\n" in header
        ):
            raise _refused("The signed identity is malformed")
        headers[key] = header
    if "authorization" not in headers or "x-amz-date" not in headers:
        raise _refused("The call carries no signed identity")
    return headers


def _identity(body: bytes) -> tuple[str, str]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise _refused("STS gave an unreadable answer") from exc
    account = root.findtext(f".//{_STS_NAMESPACE}Account") or ""
    arn = root.findtext(f".//{_STS_NAMESPACE}Arn") or ""
    if not account or not arn:
        raise _refused("STS gave an unreadable answer")
    return account, arn


def verify(
    signed: object,
    *,
    region: str,
    expected_account_id: str,
    post: Post = _post,
) -> str:
    """The verified SSO session ARN of the caller, or `CallerNotVerified`."""
    headers = _signed_headers(signed)
    url = catalog.sts_endpoint(region)
    request_headers = {
        "content-type": catalog.STS_CONTENT_TYPE,
        "host": url.split("/")[2],
        **headers,
    }
    try:
        answer = post(url, request_headers, catalog.STS_BODY.encode("utf-8"))
    except httpx.HTTPError as exc:
        raise _refused("STS could not be reached to verify the caller") from exc
    if answer.status != 200:
        # Expired or forged signatures both land here; STS says which, and
        # neither detail is the caller's business.
        raise _refused("STS did not accept the signed identity (expired SSO session?)")
    account_id, arn = _identity(answer.body)
    try:
        check_sso_operator_identity(
            account_id=account_id, caller_arn=arn, expected_account_id=expected_account_id
        )
    except AwsOperatorIdentityError as exc:
        raise CallerNotVerified(str(exc)) from exc
    return arn
