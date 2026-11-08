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

    def knowledge_map(evidence: Any, **_kwargs: Any) -> dict[str, Any]:
        asked.append(evidence.student_id)
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
        # The language travels on the evidence, which also builds the catalog in it.
        lambda evidence, **_kwargs: seen.append(evidence.content.locale) or {"stars": []},
    )
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "fr")

    response = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/knowledge-map", params={"locale": "de"}
    )

    assert response.status_code == 200, response.text
    assert seen == ["fr"], "the request's language wins; `?locale=` is not read"


def test_a_subject_the_curriculum_does_not_have_is_refused_at_the_route(
    monkeypatch: pytest.MonkeyPatch, _sky: list[str]
) -> None:
    """The read model's refusal reaches the client as a 422 (#124).

    Both directions in one test: the names the service refuses all come back
    422, the names it accepts all come back 200. Without the second half an
    endpoint that refused everything would pass.
    """
    refused = {"chemistry", "biology", "latin"}

    def knowledge_map(_evidence: Any, *, subject_id: str | None = None, **_kw: Any):
        if subject_id in refused:
            raise practice.knowledge_map_service.UnknownSubject(subject_id)
        return {"subjectId": subject_id or "math", "stars": []}

    monkeypatch.setattr(practice.knowledge_map_service, "knowledge_map", knowledge_map)
    client = _client({"sub": "student-1", "role": "student"})

    codes = {
        subject: client.get("/practice/knowledge-map", params={"subjectId": subject}).status_code
        for subject in refused | {"math", "physics"}
    }

    assert {subject for subject, code in codes.items() if code == 422} == refused
    assert {subject for subject, code in codes.items() if code == 200} == {"math", "physics"}


@pytest.fixture
def _confirmations(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Record who confirmed which lightings, and write nothing."""
    seen: list[tuple[str, list[str]]] = []

    def acknowledge_lit(student_id: str, unit_ids: Any) -> dict[str, Any]:
        seen.append((student_id, list(unit_ids)))
        return {"acknowledged": list(unit_ids)}

    monkeypatch.setattr(practice.knowledge_map_service, "acknowledge_lit", acknowledge_lit)
    return seen


def test_a_student_confirms_their_own_lighting(
    _sky: list[str], _confirmations: list[tuple[str, list[str]]]
) -> None:
    response = _client({"sub": "student-1", "role": "student"}).post(
        "/practice/knowledge-map/acknowledged-lit", json={"unitIds": ["u1"]}
    )

    assert response.status_code == 200, response.text
    assert _confirmations == [("student-1", ["u1"])]


def test_a_confirmation_can_only_ever_be_for_the_caller(
    _sky: list[str], _confirmations: list[tuple[str, list[str]]]
) -> None:
    """The route takes no student identifier, so none can be smuggled in.

    A body key naming somebody else is ignored rather than honoured: the
    student the write lands on is the authenticated actor and nothing else.
    """
    response = _client({"sub": "student-1", "role": "student"}).post(
        "/practice/knowledge-map/acknowledged-lit",
        json={"unitIds": ["u1"], "studentId": "student-2", "userId": "student-2"},
    )

    assert response.status_code == 200, response.text
    assert _confirmations == [("student-1", ["u1"])]


def test_the_neighbourhood_answers_for_the_authorized_student_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The few stars in full come under the same check as the whole sky."""
    asked: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        practice.knowledge_map_service,
        "neighbourhood",
        lambda evidence, **kwargs: asked.append((evidence.student_id, kwargs.get("around")))
        or {"stars": []},
    )

    own = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/knowledge-map/stars", params={"around": "zahlen-einmaleins"}
    )
    other = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/knowledge-map/stars", params={"studentId": "student-2"}
    )

    assert own.status_code == 200, own.text
    assert other.status_code in (403, 404), other.text
    assert asked == [("student-1", "zahlen-einmaleins")]


def test_the_skeleton_view_reaches_the_read_model(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        practice.knowledge_map_service,
        "knowledge_map",
        lambda _student, **kwargs: seen.append(str(kwargs.get("view"))) or {"stars": []},
    )

    client = _client({"sub": "student-1", "role": "student"})
    assert client.get("/practice/knowledge-map", params={"view": "skeleton"}).status_code == 200
    assert client.get("/practice/knowledge-map").status_code == 200
    assert client.get("/practice/knowledge-map", params={"view": "everything"}).status_code == 422
    assert seen == ["skeleton", "full"]


def test_the_year_group_on_the_student_s_profile_reaches_the_read_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The profile the authorization dependency already read; no second read (#310)."""
    seen: list[Any] = []
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "grade": "grade_9_secondary",
        },
    )
    monkeypatch.setattr(
        practice.knowledge_map_service,
        "knowledge_map",
        lambda _student, **kwargs: seen.append(kwargs.get("student_grade")) or {"stars": []},
    )

    response = _client({"sub": "student-1", "role": "student"}).get("/practice/knowledge-map")

    assert response.status_code == 200, response.text
    assert seen == ["grade_9_secondary"]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({"primary_subjects": ["math", "physics"]}, ("math", "physics")),
        ({"subjects": ["mathematics"]}, ("mathematics",)),
        ({}, ()),
    ],
)
def test_the_subjects_ticked_on_the_profile_reach_the_read_model_from_the_same_read(
    monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any], expected: tuple[str, ...]
) -> None:
    """Taken as much as a subject with progress (#321), from the profile the
    authorization dependency already read: one profile read, as before."""
    reads: list[str] = []
    seen: list[Any] = []

    def get_user(user_id: str, **_kwargs: Any) -> dict[str, Any]:
        reads.append(user_id)
        return {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "grade": "grade_9_secondary",
            **stored,
        }

    monkeypatch.setattr(route_authorization.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        practice.knowledge_map_service,
        "knowledge_map",
        lambda _student, **kwargs: seen.append(
            (kwargs.get("student_grade"), kwargs.get("chosen_subject_ids"))
        )
        or {"stars": []},
    )

    response = _client({"sub": "student-1", "role": "student"}).get("/practice/knowledge-map")

    assert response.status_code == 200, response.text
    assert seen == [("grade_9_secondary", expected)]
    assert reads == ["student-1"]
