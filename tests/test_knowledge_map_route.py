"""Who the star map route answers for, as behaviour rather than declaration.

The read model's own tests are pure-function tests, which is right for the
judgement but leaves the thing a red-line card actually cares about unproven:
that the student whose sky comes back is the one authorization resolved, and
not whoever the caller named in the query string.

The handler takes no `studentId` of its own — the authorization dependency
declares and checks that parameter. These tests are what would go red if
somebody ever read it directly instead.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides

from stoa.routers import practice
from stoa.security import route_authorization


def _client(user: dict[str, Any]) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, user)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _sky(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which student the service was asked about, and answer emptily."""
    asked: list[str] = []

    def knowledge_map(student_id: str, **_kwargs: Any) -> dict[str, Any]:
        asked.append(student_id)
        return {
            "subjectId": "math",
            "galaxies": [],
            "nebulae": [],
            "stars": [],
            "prerequisites": [],
            "summary": {"lit": 0, "total": 0, "streakDays": 0, "score": 0},
            "source": "test",
        }

    monkeypatch.setattr(practice.knowledge_map_service, "knowledge_map", knowledge_map)
    # The handler resolves the reader's language through the profile; without a
    # stand-in that is a live table read, and the socket guard turns it into a
    # failure that looks like an authorization outage.
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "de")
    # The authorization dependency resolves the student through the profile
    # (`route_authorization.py:144`); without a stand-in that is a live table
    # read, which the socket guard turns into an authorization outage.
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        },
    )
    return asked


def test_a_student_gets_their_own_sky_without_naming_themselves(_sky: list[str]) -> None:
    response = _client({"sub": "student-1", "role": "student"}).get("/practice/knowledge-map")

    assert response.status_code == 200, response.text
    assert _sky == ["student-1"]


def test_a_student_cannot_ask_for_somebody_else_s_sky(_sky: list[str]) -> None:
    """The one that matters. `studentId` is checked, not trusted."""
    response = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/knowledge-map", params={"studentId": "student-2"}
    )

    assert response.status_code in (403, 404), response.text
    assert _sky == [], "the service must not be reached at all for a refused student"


def test_a_parent_bound_to_the_student_may_read_it(_sky: list[str]) -> None:
    response = _client({"sub": "parent-1", "role": "parent", "bound": True}).get(
        "/practice/knowledge-map", params={"studentId": "student-1"}
    )

    assert response.status_code == 200, response.text
    assert _sky == ["student-1"]


def test_a_parent_bound_to_nobody_is_refused(_sky: list[str]) -> None:
    response = _client({"sub": "parent-1", "role": "parent", "bound": False}).get(
        "/practice/knowledge-map", params={"studentId": "student-1"}
    )

    assert response.status_code in (403, 404), response.text
    assert _sky == []


def test_the_language_is_not_taken_from_the_query_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Curriculum titles follow the request's language, as every other
    curriculum read here does — not a query parameter with German wired in."""
    seen: list[str] = []
    monkeypatch.setattr(
        practice.knowledge_map_service,
        "knowledge_map",
        lambda _student, **kwargs: seen.append(str(kwargs.get("locale"))) or {"stars": []},
    )
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "fr")

    response = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/knowledge-map", params={"locale": "de"}
    )

    assert response.status_code == 200, response.text
    assert seen == ["fr"], "the request's language wins; `?locale=` is not read"
