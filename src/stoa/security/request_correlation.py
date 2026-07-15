"""Server-owned request correlation for authorization and safe errors."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request, Response

from stoa.security.errors import normalize_correlation_id


CORRELATION_HEADER = "X-Correlation-ID"


def get_request_correlation_id(request: Request, response: Response) -> str:
    """Return one canonical ID per request, never trusting an inbound header."""
    existing = getattr(request.state, "stoa_correlation_id", None)
    correlation_id = (
        normalize_correlation_id(str(existing))
        if existing
        else normalize_correlation_id(str(uuid4()))
    )
    request.state.stoa_correlation_id = correlation_id
    response.headers[CORRELATION_HEADER] = correlation_id
    return correlation_id
