"""Assert a response is a rule violation (#211), by its code rather than its prose."""

from __future__ import annotations

from typing import Any

from stoa.rule_violation import CORRELATION_HEADER, registered_code

_ALWAYS = frozenset({"code", "message", "correlationId"})


def assert_violation(response: Any, code: object, **public: object) -> dict[str, Any]:
    """`response` refuses with `code`, carrying exactly the public fields given.

    Checks the status the code's contract names, the message it is sent with,
    that the body's correlation id is the one in the header, and that no public
    field appears beyond `public`. Returns the body's `detail`.
    """
    registered = registered_code(str(getattr(code, "value", code)))
    contract = registered.contract
    assert response.status_code == contract.http_status, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert detail["code"] == registered.value, response.text
    assert detail["message"] == contract.safe_message
    assert detail["correlationId"] == response.headers[CORRELATION_HEADER]
    assert {key: value for key, value in detail.items() if key not in _ALWAYS} == public
    return detail
