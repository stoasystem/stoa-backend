"""Assert a response is a rule violation (#211), by its code rather than its prose."""

from __future__ import annotations

from typing import Any

from stoa.rule_violation import CORRELATION_HEADER, registered_code, render_message
from stoa.services import locale_service

_ALWAYS = frozenset({"code", "message", "correlationId"})


def assert_violation(response: Any, code: object, **public: object) -> dict[str, Any]:
    """`response` refuses with `code`, carrying exactly the public fields given.

    Checks the status the code's contract names, that the message is the
    catalog's in the language the request asked for (German without one), that
    the body's correlation id is the one in the header, and that no public
    field appears beyond `public`. Returns the body's `detail`.
    """
    registered = registered_code(str(getattr(code, "value", code)))
    contract = registered.contract
    assert response.status_code == contract.http_status, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert detail["code"] == registered.value, response.text
    message = render_message(registered, _request_locale(response))
    if "{" not in message:  # a message with params is filled by the raise site
        assert detail["message"] == message, response.text
    else:
        assert isinstance(detail["message"], str) and detail["message"], response.text
    assert detail["correlationId"] == response.headers[CORRELATION_HEADER]
    assert {key: value for key, value in detail.items() if key not in _ALWAYS} == public
    return detail


def _request_locale(response: Any) -> str:
    try:
        headers = response.request.headers
    except (AttributeError, RuntimeError):
        return locale_service.DEFAULT_LOCALE
    return (
        locale_service.locale_from_accept_language(headers.get("accept-language"))
        or locale_service.DEFAULT_LOCALE
    )
