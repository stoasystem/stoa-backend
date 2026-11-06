"""One exception, one renderer: how a rule violation reaches a client (#272)."""

from __future__ import annotations

from enum import StrEnum

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from rule_violation_helpers import assert_violation
from stoa import rule_violation
from stoa.main import app as stoa_app
from stoa.rule_violation import (
    CORRELATION_HEADER,
    CorrelationMiddleware,
    RuleContract,
    RuleViolation,
    register_codes,
    registered_codes,
)
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.request_correlation import get_request_correlation_id
from stoa.services.ask_question import AskQuestionErrorCode
from stoa.services.ask_question._admission import AdmissionError

ALL_CODES = sorted(registered_codes().items())


def _app(raise_it) -> FastAPI:
    application = FastAPI()
    application.add_middleware(CorrelationMiddleware)
    rule_violation.install_rule_violation_handler(application)

    @application.get("/refuse")
    def refuse():
        raise raise_it()

    @application.get("/ok")
    def ok(request: Request, audited: str = Depends(get_request_correlation_id)):
        return {"state": request.state.stoa_correlation_id, "audited": audited}

    @application.get("/refuse-after-audit")
    def refuse_after_audit(audited: str = Depends(get_request_correlation_id)):
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, audited)

    return application


@pytest.mark.parametrize(("value", "entry"), ALL_CODES, ids=[value for value, _ in ALL_CODES])
def test_every_registered_code_renders_under_its_contract(value, entry):
    _domain, code = entry
    response = TestClient(_app(lambda: RuleViolation(code))).get("/refuse")

    detail = assert_violation(response, value)
    assert set(detail) == {"code", "message", "correlationId"}
    retry_after = code.contract.retry_after_seconds
    if retry_after is None:
        assert "Retry-After" not in response.headers
    else:
        assert response.headers["Retry-After"] == str(retry_after)


def test_the_domain_errors_are_rule_violations_with_their_constructors():
    assert isinstance(SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN, "c", "why"), RuleViolation)
    assert isinstance(AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID, "why", "c"), RuleViolation)
    assert isinstance(AdmissionError(AskQuestionErrorCode.ALLOWANCE_EXHAUSTED), RuleViolation)


def test_a_declared_public_field_is_sent_and_an_undeclared_one_is_refused():
    def refused():
        return AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_DAILY_LIMIT).with_public(
            conversationId="conv-1"
        )

    response = TestClient(_app(refused)).get("/refuse")
    assert_violation(response, "message_daily_limit", conversationId="conv-1")

    with pytest.raises(ValueError):
        SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED).with_public(conversationId="x")


def test_params_fill_the_message_and_never_reach_the_body():
    def refused():
        return SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND).with_params(
            student_name="params-canary"
        )

    response = TestClient(_app(refused)).get("/refuse")
    assert_violation(response, SecurityErrorCode.RESOURCE_NOT_FOUND)
    assert "params-canary" not in response.text


def test_internal_detail_never_reaches_the_body():
    response = TestClient(
        _app(lambda: SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, None, "detail-canary"))
    ).get("/refuse")
    assert "detail-canary" not in response.text


def test_a_raise_site_may_give_its_own_retry_time_only_where_the_contract_retries():
    response = TestClient(
        _app(lambda: AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED).retrying_after(42))
    ).get("/refuse")
    assert_violation(response, AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED)
    assert response.headers["Retry-After"] == "42"

    with pytest.raises(ValueError):
        SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED).retrying_after(5)


def test_success_and_refusal_carry_the_request_id_and_ignore_the_clients():
    client = TestClient(_app(lambda: SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)))
    sent = {CORRELATION_HEADER: "client-chosen-id"}

    ok = client.get("/ok", headers=sent)
    assert ok.headers[CORRELATION_HEADER] == ok.json()["state"] == ok.json()["audited"]
    assert ok.headers[CORRELATION_HEADER] != "client-chosen-id"

    refused = client.get("/refuse-after-audit", headers=sent)
    detail = assert_violation(refused, SecurityErrorCode.ACTION_NOT_ALLOWED)
    assert detail["correlationId"] != "client-chosen-id"

    other = client.get("/ok")
    assert other.headers[CORRELATION_HEADER] != ok.headers[CORRELATION_HEADER]


def test_a_refusal_is_sent_with_the_id_the_request_was_audited_under():
    seen: list[str] = []
    application = _app(lambda: SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED))

    @application.get("/audited-then-refused")
    def audited_then_refused(audited: str = Depends(get_request_correlation_id)):
        seen.append(audited)
        raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, "some-other-id")

    response = TestClient(application).get("/audited-then-refused")
    detail = assert_violation(response, SecurityErrorCode.RESOURCE_NOT_FOUND)
    assert detail["correlationId"] == seen[0]


def test_the_application_installs_the_handler_and_the_middleware():
    assert RuleViolation in stoa_app.exception_handlers
    assert any(item.cls is CorrelationMiddleware for item in stoa_app.user_middleware)


def test_a_code_string_names_one_code_across_every_domain(monkeypatch):
    monkeypatch.setattr(rule_violation, "_REGISTRY", dict(rule_violation._REGISTRY))

    class Colliding(StrEnum):
        SAME = "upload_not_found"

    with pytest.raises(RuntimeError, match="registered by both"):
        register_codes("elsewhere", Colliding, {Colliding.SAME: RuleContract(404, "x")})


def test_a_domain_must_give_every_code_a_contract(monkeypatch):
    monkeypatch.setattr(rule_violation, "_REGISTRY", dict(rule_violation._REGISTRY))

    class Partial(StrEnum):
        ONE = "test_only_one"
        TWO = "test_only_two"

    with pytest.raises(RuntimeError, match="not exhaustive"):
        register_codes("partial", Partial, {Partial.ONE: RuleContract(400, "x")})


def test_a_contract_declares_only_known_public_fields():
    with pytest.raises(ValueError):
        RuleContract(400, "x", public_fields=frozenset({"studentName"}))
    with pytest.raises(ValueError):
        RuleContract(200, "x")
