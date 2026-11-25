"""Answers leave gzipped when the client accepts it, through Mangum too (card 133)."""

from __future__ import annotations

import base64
import gzip
import json

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient
from mangum import Mangum

from stoa.main import app


def _large_app() -> FastAPI:
    small = FastAPI()
    small.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

    @small.get("/big")
    def big() -> dict[str, list[str]]:
        return {"rows": [f"lesson-{index}" for index in range(2000)]}

    return small


def test_the_application_compresses_what_it_answers() -> None:
    assert any(middleware.cls is GZipMiddleware for middleware in app.user_middleware)


def test_a_large_json_answer_is_gzipped_for_a_client_that_accepts_it() -> None:
    response = TestClient(_large_app()).get("/big", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
    assert len(response.json()["rows"]) == 2000


def test_mangum_hands_api_gateway_the_compressed_body_in_base64() -> None:
    event = {
        "version": "2.0",
        "routeKey": "GET /big",
        "rawPath": "/big",
        "rawQueryString": "",
        "headers": {"accept-encoding": "gzip", "host": "api.test"},
        "requestContext": {
            "http": {"method": "GET", "path": "/big", "sourceIp": "1.2.3.4", "protocol": "HTTP/1.1", "userAgent": "t"},
            "requestId": "r",
            "stage": "$default",
            "domainName": "api.test",
            "accountId": "1",
            "apiId": "a",
            "time": "25/Nov/2026:00:00:00 +0000",
            "timeEpoch": 0,
        },
        "isBase64Encoded": False,
    }
    result = Mangum(_large_app(), lifespan="off")(event, None)
    assert result["isBase64Encoded"] is True
    assert result["headers"]["content-encoding"] == "gzip"
    body = json.loads(gzip.decompress(base64.b64decode(result["body"])))
    assert len(body["rows"]) == 2000
