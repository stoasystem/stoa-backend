"""Which browser origins may call this API, as the application answers them.

The production site and the two preview sites of the frontend redesign must
pass a preflight for every method and request header the frontend sends; any
other origin, including one that merely starts or ends like an allowed one,
must not.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.main import app


ALLOWED_ORIGINS = (
    "https://app.stoaedu.ch",
    "https://app-planet.stoaedu.ch",
)

# Every verb the frontend's httpClient issues against the API.
FRONTEND_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# The request headers the frontend sets: Content-Type and Authorization on every
# call, Accept-Language from the request interceptor and the streaming fetch,
# Idempotency-Key on billing commands.
FRONTEND_HEADERS = ("authorization", "content-type", "accept-language", "idempotency-key")

REJECTED_ORIGINS = (
    "https://evil.example",
    "https://app-planet.stoaedu.ch.evil.example",
    "https://app.stoaedu.ch.evil.example",
    "http://app-planet.stoaedu.ch",
    "http://app.stoaedu.ch",
    "https://app-planet.stoaedu.ch:8443",
    "https://evil.app-planet.stoaedu.ch",
    # A sibling subdomain must not ride on the wildcard certificate into CORS.
    "https://app-cute.stoaedu.ch",
    # Preview hostnames that were planned and then replaced.
    "https://planet.stoaedu.ch",
    "https://cute.stoaedu.ch",
    "https://app.stoaedu-planet.ch",
    "https://app.stoaedu-cute.ch",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _preflight(client: TestClient, origin: str, method: str):
    return client.options(
        "/students/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": ", ".join(FRONTEND_HEADERS),
        },
    )


def test_default_origins_name_production_and_both_previews_exactly() -> None:
    default = Settings.model_fields["cors_origins"].default

    for origin in ALLOWED_ORIGINS:
        assert origin in default
    assert not any("*" in origin for origin in default)


@pytest.mark.parametrize("method", FRONTEND_METHODS)
@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_preflight_from_an_allowed_origin_admits_what_the_frontend_sends(
    client: TestClient, origin: str, method: str
) -> None:
    response = _preflight(client, origin, method)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_methods = {
        value.strip() for value in response.headers["access-control-allow-methods"].split(",")
    }
    assert method in allowed_methods
    allowed_headers = {
        value.strip().lower()
        for value in response.headers["access-control-allow-headers"].split(",")
    }
    assert set(FRONTEND_HEADERS) <= allowed_headers


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_a_plain_request_from_an_allowed_origin_names_that_origin(
    client: TestClient, origin: str
) -> None:
    response = client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", REJECTED_ORIGINS)
def test_preflight_from_any_other_origin_is_refused(client: TestClient, origin: str) -> None:
    response = _preflight(client, origin, "POST")

    assert response.status_code == 400
    assert "origin" in response.text
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", REJECTED_ORIGINS)
def test_a_plain_request_from_any_other_origin_is_not_granted(
    client: TestClient, origin: str
) -> None:
    response = client.get("/health", headers={"Origin": origin})

    assert "access-control-allow-origin" not in response.headers
