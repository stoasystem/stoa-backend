from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from stoa.config import Settings
from stoa.routers.parents import ParentCheckoutSessionCreate
from stoa.services import subscription_service
from stoa.services.billing_callback_service import (
    BillingWebOriginPolicy,
    build_checkout_return_urls,
    parse_exact_web_origin,
)


@pytest.mark.parametrize(
    ("environment", "origin", "expected"),
    [
        ("production", "https://app.stoaedu.ch", "https://app.stoaedu.ch"),
        ("staging", "https://staging.stoaedu.ch", "https://staging.stoaedu.ch"),
        ("development", "http://localhost:5173", "http://localhost:5173"),
        ("development", "http://127.0.0.1:5173", "http://127.0.0.1:5173"),
        ("development", "http://[::1]:5173", "http://[::1]:5173"),
    ],
)
def test_exact_origin_positive_matrix(
    environment: str,
    origin: str,
    expected: str,
) -> None:
    assert parse_exact_web_origin(origin, environment=environment) == expected


@pytest.mark.parametrize(
    ("environment", "origin"),
    [
        ("production", "http://app.stoaedu.ch"),
        ("production", "https://localhost:5173"),
        ("production", "https://app.stoaedu.ch:444"),
        ("staging", "https://staging.stoaedu.ch/path"),
        ("staging", "https://staging.stoaedu.ch/"),
        ("staging", "https://staging.stoaedu.ch?next=evil"),
        ("staging", "https://staging.stoaedu.ch#fragment"),
        ("staging", "https://user@staging.stoaedu.ch"),
        ("staging", "https://user:secret@staging.stoaedu.ch"),
        ("staging", "https://*.stoaedu.ch"),
        ("staging", "//staging.stoaedu.ch"),
        ("staging", r"https://staging.stoaedu.ch\@evil.example"),
        ("staging", "https://staging.stoaedu.ch%2fevil.example"),
        ("staging", "https://staging.stoaedu.ch%5cevil.example"),
        ("staging", "https://staging.stoaedu.ch%40evil.example"),
        ("staging", "https://staging.stoaedu.ch:"),
        ("development", "http://localhost"),
        ("development", "http://127.0.0.1"),
        ("development", "http://[::1]"),
        ("development", "http://localhost:5173:80"),
        ("development", "http://localhost.evil.example:5173"),
        ("development", "http://127.0.0.1.evil.example:5173"),
        ("development", "http://0.0.0.0:5173"),
        ("development", "http://192.168.1.10:5173"),
        ("development", "http://localhost:0"),
        ("development", "http://localhost:65536"),
        ("unknown", "https://app.stoaedu.ch"),
    ],
)
def test_exact_origin_parser_rejects_ambiguous_or_unsafe_configuration(
    environment: str,
    origin: str,
) -> None:
    with pytest.raises(ValueError, match=r"^billing_web_origin_"):
        parse_exact_web_origin(origin, environment=environment)


@pytest.mark.parametrize(
    "candidate",
    [
        "https://evil.example",
        "https://app.stoaedu.ch.evil.example",
        "https://app.stoaedu.ch:444",
        "https://user@app.stoaedu.ch",
        "https://app.stoaedu.ch/path",
        "https://app.stoaedu.ch?checkoutRef=attacker",
        "https://app.stoaedu.ch#fragment",
        r"https://app.stoaedu.ch\@evil.example",
        "https://app.stoaedu.ch%2fevil.example",
        "//app.stoaedu.ch",
    ],
)
def test_policy_rejects_every_unconfigured_candidate(candidate: str) -> None:
    policy = BillingWebOriginPolicy(
        environment="production",
        configured_origins=("https://app.stoaedu.ch",),
        result_path="/billing/checkout/result",
    )

    with pytest.raises(ValueError, match=r"^billing_web_origin_"):
        policy.require_configured_origin(candidate)


def test_policy_rejects_duplicate_or_ambiguous_startup_configuration() -> None:
    with pytest.raises(ValueError, match="billing_web_origin_duplicate"):
        BillingWebOriginPolicy(
            environment="development",
            configured_origins=(
                "http://localhost:5173",
                "http://LOCALHOST:5173",
            ),
            result_path="/billing/checkout/result",
        )

    with pytest.raises(ValueError, match="billing_checkout_result_path_invalid"):
        BillingWebOriginPolicy(
            environment="production",
            configured_origins=("https://app.stoaedu.ch",),
            result_path="/parent/subscription?checkout=success",
        )

    with pytest.raises(ValueError, match="billing_web_origin_missing"):
        BillingWebOriginPolicy(
            environment="production",
            configured_origins=(),
            result_path="/billing/checkout/result",
        )


def test_settings_validate_current_environment_policy_at_startup() -> None:
    development = Settings(_env_file=None)
    assert development.stripe_checkout_web_origins == ["http://localhost:5173"]
    assert development.stripe_checkout_result_path == "/billing/checkout/result"

    staging = Settings(
        _env_file=None,
        environment="staging",
        stripe_checkout_web_origins=["https://staging.stoaedu.ch"],
    )
    assert staging.stripe_checkout_web_origins == ["https://staging.stoaedu.ch"]

    with pytest.raises(
        ValidationError,
        match="billing_web_origin_https_required",
    ):
        Settings(_env_file=None, environment="staging")


def test_return_urls_use_only_configured_origin_fixed_path_and_safe_query() -> None:
    settings = SimpleNamespace(
        environment="production",
        stripe_checkout_web_origins=["https://app.stoaedu.ch"],
        stripe_checkout_result_path="/billing/checkout/result",
    )

    success_url, cancel_url = build_checkout_return_urls(
        "checkout-public-ref_123",
        settings,
    )

    success = urlsplit(success_url)
    cancel = urlsplit(cancel_url)
    assert (success.scheme, success.netloc, success.path) == (
        "https",
        "app.stoaedu.ch",
        "/billing/checkout/result",
    )
    assert (cancel.scheme, cancel.netloc, cancel.path) == (
        "https",
        "app.stoaedu.ch",
        "/billing/checkout/result",
    )
    assert parse_qs(success.query) == {
        "checkoutRef": ["checkout-public-ref_123"],
        "flow": ["return"],
    }
    assert parse_qs(cancel.query) == {
        "checkoutRef": ["checkout-public-ref_123"],
        "flow": ["cancel"],
    }
    assert success.fragment == cancel.fragment == ""


@pytest.mark.parametrize(
    "checkout_ref",
    [
        "",
        " ",
        "short",
        "contains space",
        "contains/slash",
        "contains?query",
        "contains#fragment",
        "ü" * 16,
        "a" * 129,
    ],
)
def test_return_url_builder_rejects_non_opaque_checkout_references(
    checkout_ref: str,
) -> None:
    settings = SimpleNamespace(
        environment="production",
        stripe_checkout_web_origins=["https://app.stoaedu.ch"],
        stripe_checkout_result_path="/billing/checkout/result",
    )

    with pytest.raises(ValueError, match="billing_checkout_reference_invalid"):
        build_checkout_return_urls(checkout_ref, settings)


def test_builder_api_has_no_browser_or_request_authority_parameters() -> None:
    assert tuple(inspect.signature(build_checkout_return_urls).parameters) == (
        "checkout_ref",
        "settings",
    )

    service_source = Path(
        "src/stoa/services/billing_callback_service.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "successUrl",
        "cancelUrl",
        "window.location.origin",
        "request.headers",
        "forwarded-host",
        "x-forwarded-host",
    )
    assert all(marker not in service_source for marker in forbidden)


def test_checkout_service_and_route_reject_browser_callback_authority() -> None:
    assert "success_url" not in inspect.signature(
        subscription_service.create_checkout_session
    ).parameters
    assert "cancel_url" not in inspect.signature(
        subscription_service.create_checkout_session
    ).parameters

    with pytest.raises(ValidationError):
        ParentCheckoutSessionCreate.model_validate(
            {
                "requestedTier": "student",
                "successUrl": "https://evil.example",
                "cancelUrl": "https://evil.example",
            }
        )
