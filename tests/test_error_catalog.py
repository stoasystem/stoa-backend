"""A rule violation's message comes from the catalog, in the reader's language (#273)."""

from __future__ import annotations

from string import Formatter

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from rule_violation_helpers import assert_violation
from stoa.main import app as stoa_app
from stoa.rule_violation import (
    CorrelationMiddleware,
    RuleViolation,
    catalog_key,
    install_rule_violation_handler,
    registered_codes,
    render_message,
)
from stoa.security.errors import (
    VALIDATION_MESSAGE_CODES,
    SecurityErrorCode,
    redacted_validation_errors,
)
from stoa.services import locale_service, message_catalog
from stoa.services.message_catalog import errors as error_catalog

LOCALES = sorted(locale_service.SUPPORTED_LOCALES)
ERROR_KEYS = sorted(error_catalog.TEXT)


def _params(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


# ── completeness ─────────────────────────────────────────────────────────────


def test_every_registered_code_has_a_catalog_key():
    missing = sorted(
        value for value in registered_codes() if catalog_key(value) not in message_catalog.TEXT
    )
    assert missing == []


def test_every_validation_code_has_a_catalog_key():
    assert {catalog_key(code) for code in VALIDATION_MESSAGE_CODES} <= set(error_catalog.TEXT)


def test_every_error_key_names_a_code():
    known = {catalog_key(value) for value in registered_codes()}
    known |= {catalog_key(code) for code in VALIDATION_MESSAGE_CODES}
    assert sorted(set(ERROR_KEYS) - known) == []


@pytest.mark.parametrize("key", ERROR_KEYS)
def test_every_error_key_has_all_four_languages_with_the_same_params(key):
    variants = error_catalog.TEXT[key]
    assert set(variants) == set(LOCALES), key
    assert all(variants[locale].strip() for locale in LOCALES), key
    names = {locale: _params(variants[locale]) for locale in LOCALES}
    assert len({frozenset(found) for found in names.values()}) == 1, names


@pytest.mark.parametrize("key", ERROR_KEYS)
def test_swiss_german_writes_ss(key):
    assert "ß" not in error_catalog.TEXT[key]["de"]


def test_english_keeps_the_sentences_clients_already_show():
    assert render_message(SecurityErrorCode.AUTHENTICATION_REQUIRED, "en") == (
        "Please sign in to continue."
    )
    assert render_message("upload_too_large", "en") == (
        "This file is too large. Choose a smaller file."
    )


# ── rendering in the request's language ──────────────────────────────────────


def _bare_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(CorrelationMiddleware)
    install_rule_violation_handler(application)

    @application.get("/refuse")
    def refuse():
        raise RuleViolation(SecurityErrorCode.ACTION_NOT_ALLOWED)

    return application


@pytest.mark.parametrize(
    ("header", "locale"),
    [
        ({"Accept-Language": "fr-CH"}, "fr"),
        ({"Accept-Language": "en"}, "en"),
        ({"Accept-Language": "it;q=0.9, en;q=0.5"}, "it"),
        ({"Accept-Language": "es"}, "de"),
        ({}, "de"),
    ],
)
def test_the_same_violation_speaks_the_request_language(header, locale):
    response = TestClient(_bare_app()).get("/refuse", headers=header)

    detail = assert_violation(response, SecurityErrorCode.ACTION_NOT_ALLOWED)
    assert detail["code"] == "action_not_allowed"
    assert detail["message"] == message_catalog.TEXT["error.action_not_allowed"][locale]


@pytest.mark.parametrize(
    ("header", "locale"), [({"Accept-Language": "fr"}, "fr"), ({"Accept-Language": "en"}, "en"), ({}, "de")]
)
def test_the_application_renders_a_coded_422_in_the_request_language(header, locale):
    # The application's own middleware binds the request's language.
    response = TestClient(stoa_app).post(
        "/auth/register",
        headers=header,
        json={
            "role": "student",
            "name": "Probe",
            "email": "probe@example.com",
            "password": "PlaintextSecret123!",
            "profile": {"age": 222222, "school": "X", "grade": "8"},
        },
    )

    assert response.status_code == 422
    (entry,) = [e for e in response.json()["detail"] if e.get("code") == "age_out_of_range"]
    assert entry["msg"] == message_catalog.text(
        "error.age_out_of_range", locale, min_age=1, max_age=120
    )


def test_a_coded_validation_message_is_rendered_in_the_request_language():
    english = message_catalog.text("error.age_out_of_range", "en", min_age=1, max_age=120)
    errors = [{"type": "value_error", "loc": ["body", "age"], "msg": f"Value error, {english}"}]

    locale_service.set_request_locale("fr")
    try:
        (entry,) = redacted_validation_errors(errors)
    finally:
        locale_service.set_request_locale(None)

    assert entry["code"] == "age_out_of_range"
    assert entry["msg"] == message_catalog.text(
        "error.age_out_of_range", "fr", min_age=1, max_age=120
    )


def test_an_uncoded_validation_message_stays_as_pydantic_wrote_it():
    errors = [{"type": "missing", "loc": ["body", "email"], "msg": "Field required"}]
    assert redacted_validation_errors(errors) == [
        {"type": "missing", "loc": ["body", "email"], "msg": "Field required"}
    ]
