"""Server-owned request correlation for authorization and safe errors."""

from __future__ import annotations

from fastapi import Request, Response

from stoa.rule_violation import CORRELATION_HEADER, request_correlation_id

__all__ = ["CORRELATION_HEADER", "get_request_correlation_id"]


def get_request_correlation_id(request: Request, response: Response) -> str:
    """Return the request's one id, minted at the door; an inbound header is never trusted.

    `stoa.rule_violation.CorrelationMiddleware` mints it and sets the response
    header; setting it here as well keeps a test's bare application, which has
    no middleware, sending the same id it audited.
    """
    correlation_id = request_correlation_id(request)
    response.headers[CORRELATION_HEADER] = correlation_id
    return correlation_id
