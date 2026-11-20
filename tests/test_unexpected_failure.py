"""An unhandled exception answers 500 with the standard body and a traceable id."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import pytest

from rule_violation_helpers import assert_violation
from stoa import config
from stoa.main import app as stoa_app
from stoa.rule_violation import (
    CorrelationMiddleware,
    install_rule_violation_handler,
    render_message,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.unexpected_failure import ServerErrorCode, UnexpectedFailureMiddleware

BROKEN_PATH = "/__test__/unexpected-failure"


class _Broken(RuntimeError):
    pass


@pytest.fixture
def broken_route() -> Iterator[str]:
    """A route on the real application that raises what nothing handles."""

    def broken():
        raise _Broken("draft accept fell over")

    route = APIRoute(BROKEN_PATH, broken, methods=["POST"])
    stoa_app.router.routes.append(route)
    try:
        yield BROKEN_PATH
    finally:
        stoa_app.router.routes.remove(route)


def _failure_records(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "stoa.unexpected_failure"]


def test_an_unhandled_exception_answers_500_with_the_logged_correlation_id(
    broken_route, caplog
):
    caplog.set_level(logging.ERROR, logger="stoa.unexpected_failure")

    response = TestClient(stoa_app).post(broken_route)

    assert response.status_code == 500
    detail = assert_violation(response, ServerErrorCode.INTERNAL_ERROR)
    assert set(detail) == {"code", "message", "correlationId"}
    assert detail["code"] == "internal_error"
    assert "draft accept fell over" not in response.text

    [record] = _failure_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None and record.exc_info[0] is _Broken
    assert record.correlation_id == detail["correlationId"]
    assert detail["correlationId"] in record.getMessage()
    assert BROKEN_PATH in record.getMessage()


def test_the_500_is_in_the_requested_language_and_keeps_cors(broken_route):
    origin = config.settings().cors_origins[0]
    response = TestClient(stoa_app).post(
        broken_route, headers={"Accept-Language": "fr", "Origin": origin}
    )

    detail = assert_violation(response, ServerErrorCode.INTERNAL_ERROR)
    assert detail["message"] == render_message(ServerErrorCode.INTERNAL_ERROR, "fr")
    assert response.headers["access-control-allow-origin"] == origin


def test_each_failure_names_its_own_request(broken_route):
    client = TestClient(stoa_app)
    first = client.post(broken_route).json()["detail"]["correlationId"]
    second = client.post(broken_route).json()["detail"]["correlationId"]
    assert first != second


def test_a_rule_violation_and_a_422_keep_their_shapes(caplog):
    caplog.set_level(logging.ERROR, logger="stoa.unexpected_failure")
    application = FastAPI()
    application.add_middleware(UnexpectedFailureMiddleware)
    application.add_middleware(CorrelationMiddleware)
    install_rule_violation_handler(application)

    @application.get("/refuse")
    def refuse():
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)

    @application.get("/count")
    def count(n: int):
        return {"n": n}

    client = TestClient(application)
    assert_violation(client.get("/refuse"), SecurityErrorCode.ACTION_NOT_ALLOWED)
    invalid = client.get("/count", params={"n": "many"})
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)
    assert _failure_records(caplog) == []


def test_the_real_422_is_still_the_redacted_list():
    response = TestClient(stoa_app).post("/auth/login", json={})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_a_failure_after_the_response_started_is_raised_on():
    application = FastAPI()
    application.add_middleware(UnexpectedFailureMiddleware)
    application.add_middleware(CorrelationMiddleware)

    def chunks():
        yield b"partial"
        raise _Broken("mid-stream")

    @application.get("/stream")
    def stream():
        return StreamingResponse(chunks())

    with pytest.raises(_Broken):
        TestClient(application).get("/stream")


def test_the_application_runs_the_catch_all_inside_the_correlation_middleware():
    order = [item.cls for item in stoa_app.user_middleware]
    # user_middleware lists the outermost first.
    assert order.index(CorrelationMiddleware) < order.index(UnexpectedFailureMiddleware)
