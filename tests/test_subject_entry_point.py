"""One entry point for subject ids (#354, shape in #317).

`curriculum_service` holds the only alias table and the only
`SUPPORTED_SUBJECTS`. Everything outside it says the canonical id (`math`),
however the content rows store it (`mathematics`): what a client writes into
a profile or a conversation is normalised and checked on the way in, and what
was stored before is normalised on the way out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from audit_helpers import MemoryAuthorizationAuditSink
from fakes.ask_question import _actor as _student
from fakes.ask_question import bucket as bucket  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.admission import seed_period_active
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations, practice, students
from stoa.security import route_authorization
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import curriculum_service, message_catalog
from stoa.services.ask_question import _answering
from test_curriculum_catalog_shows_seeded_topics import _seeded_table

SRC = Path(__file__).resolve().parents[1] / "src"


# ── The entry point ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("sent", "canonical"),
    [
        ("math", "math"),
        ("mathematics", "math"),
        ("Mathematik", "math"),
        (" MATHEMATICS ", "math"),
        ("Physik", "physics"),
        ("deutsch", "german"),
        ("Deutsch", "german"),
        ("Englisch", "english"),
        ("english", "english"),
    ],
)
def test_every_known_spelling_names_its_canonical_subject(sent, canonical):
    assert curriculum_service.subject_id(sent) == canonical


@pytest.mark.parametrize("sent", ["chemistry", "French", "", "   ", None, 7, "math-ish"])
def test_a_subject_nobody_teaches_is_unknown_not_math(sent):
    assert curriculum_service.subject_id(sent) is None


def test_the_supported_subjects_keep_their_rollout_marks():
    assert set(curriculum_service.SUPPORTED_SUBJECTS) == {"math", "physics", "german", "english"}
    states = {key: meta["rollout_state"] for key, meta in curriculum_service.SUPPORTED_SUBJECTS.items()}
    assert states == {
        "math": "active",
        "physics": "foundation",
        "german": "foundation",
        "english": "foundation",
    }


def test_there_is_one_alias_table_in_the_source():
    """`mathematik` is spelled as a key in exactly one module of `src`."""
    holders = sorted(
        str(path.relative_to(SRC)).replace("\\", "/")
        for path in SRC.rglob("*.py")
        if re.search(r"""["']mathematik["']\s*:""", path.read_text(encoding="utf-8"), re.IGNORECASE)
    )
    assert holders == ["stoa/services/curriculum_service.py"]


def test_there_is_one_supported_subjects_table_in_the_source():
    holders = sorted(
        str(path.relative_to(SRC)).replace("\\", "/")
        for path in SRC.rglob("*.py")
        if re.search(r"^SUPPORTED_SUBJECTS\b.*=", path.read_text(encoding="utf-8"), re.MULTILINE)
    )
    assert holders == ["stoa/services/curriculum_service.py"]


# ── The profile's `primary_subjects` ─────────────────────────────────────────


def _profile_actor():
    return Actor(
        "student-1",
        "https://identity.test",
        "student-1-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        "student",
        (),
    )


@pytest.fixture
def profile_client(monkeypatch):
    profile = {
        "user_id": "student-1",
        "role": "student",
        "account_status": "active",
        "name": "Student One",
        "grade": "grade_6_primary",
        "primary_subjects": ["mathematics", "Deutsch"],
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    writes: list[dict] = []
    monkeypatch.setattr(route_authorization.user_repo, "get_user", lambda user_id, **_k: dict(profile))
    monkeypatch.setattr(students.user_repo, "get_user", lambda user_id, **_k: dict(profile))

    def _update(user_id, **kwargs):
        writes.append(kwargs)
        stored = dict(profile)
        values = kwargs.get("expression_attribute_values") or {}
        if ":s" in values:
            stored["primary_subjects"] = values[":s"]
        return stored

    monkeypatch.setattr(students.user_repo, "update_profile_fields", _update)
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = _profile_actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app), writes


def test_profile_subjects_are_stored_as_canonical_ids(profile_client):
    client, writes = profile_client

    response = client.patch(
        "/students/me/profile", json={"primarySubjects": ["mathematics", "Mathematik", "Englisch"]}
    )

    assert response.status_code == 200, response.text
    assert [write["expression_attribute_values"][":s"] for write in writes] == [["math", "english"]]
    assert response.json()["primarySubjects"] == ["math", "english"]


def test_an_unknown_profile_subject_is_refused_and_nothing_is_written(profile_client):
    client, writes = profile_client

    response = client.patch(
        "/students/me/profile",
        json={"primarySubjects": ["math", "chemistry"]},
        headers={"Accept-Language": "fr"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "subject_unknown"
    assert detail["fields"] == ["primarySubjects"]
    assert writes == []


def test_profile_subjects_stored_before_are_read_as_canonical_ids(profile_client):
    client, _writes = profile_client

    response = client.get("/students/me/profile")

    assert response.status_code == 200, response.text
    assert response.json()["primarySubjects"] == ["math", "german"]


def test_the_refusal_is_in_all_four_languages():
    text = message_catalog.TEXT["error.subject_unknown"]
    assert set(text) == {"de", "en", "fr", "it"}
    assert all(sentence.strip() for sentence in text.values())


# ── A conversation's `subject` ───────────────────────────────────────────────


def _conversation_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    app.dependency_overrides[get_actor] = _student
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _stored_conversations(table) -> list[dict]:
    return [row for row in table.rows.values() if row.get("SK") == "CONV"]


def test_a_conversation_subject_is_stored_as_its_canonical_id(table, monkeypatch, stub_memory_summary):
    seed_period_active(monkeypatch)

    created = _conversation_client().post("/conversations", json={"subject": "Mathematik", "grade": "Sek1"})

    assert created.status_code == 201, created.text
    assert created.json()["subject"] == "math"
    [row] = [row for row in _stored_conversations(table) if row["conversation_id"] == created.json()["id"]]
    assert row["subject"] == "math"


def test_an_unknown_conversation_subject_is_refused_and_nothing_is_opened(table, monkeypatch, stub_memory_summary):
    seed_period_active(monkeypatch)
    before = len(_stored_conversations(table))

    refused = _conversation_client().post("/conversations", json={"subject": "Alchemy", "grade": "Sek1"})

    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["code"] == "subject_unknown"
    assert detail["fields"] == ["subject"]
    assert len(_stored_conversations(table)) == before


@pytest.mark.parametrize(("stored", "context"), [("deutsch", "german"), ("Mathematics", "math"), ("english", "english")])
def test_the_answer_context_names_the_stored_subject_without_guessing_math(stored, context):
    assert _answering._generation_context_without_request("student-x", {"subject": stored})["subject"] == context


def test_an_unknown_stored_subject_is_not_answered_as_math():
    assert _answering._generation_context_without_request("student-x", {"subject": "Alchemy"})["subject"] != "math"


# ── The topic roadmap ────────────────────────────────────────────────────────


def _roadmap_client() -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    return TestClient(app)


def _live_topic(table) -> str:
    return next(
        row["topic_id"]
        for (_pk, sk), row in sorted(table.rows.items())
        if sk.startswith("TOPIC#") and row.get("rollout_state") != "archived"
    )


def test_the_roadmap_speaks_the_canonical_subject_id(monkeypatch):
    table = _seeded_table(monkeypatch)
    topic_id = _live_topic(table)

    for spelling in ("math", "mathematics"):
        body = _roadmap_client().get(f"/practice/{spelling}/{topic_id}/roadmap").json()
        assert body["subjectId"] == "math"
        assert body["topic"]["subjectId"] == "math"
        assert {lesson["subjectId"] for unit in body["units"] for lesson in unit["lessons"]} == {"math"}


def test_an_archived_topic_has_no_roadmap(monkeypatch):
    table = _seeded_table(monkeypatch)
    archived = [
        row["topic_id"]
        for (_pk, sk), row in table.rows.items()
        if sk.startswith("TOPIC#") and row.get("rollout_state") == "archived"
    ]
    assert archived, "the seed is expected to keep a retired topic"

    response = _roadmap_client().get(f"/practice/math/{archived[0]}/roadmap")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"


@pytest.mark.parametrize("state", ["archived", "preview"])
def test_archived_and_preview_units_and_lessons_leave_the_roadmap(monkeypatch, state):
    table = _seeded_table(monkeypatch)
    topic_id = _live_topic(table)
    client = _roadmap_client()
    before = client.get(f"/practice/math/{topic_id}/roadmap").json()
    hidden_unit = before["units"][0]["id"]
    kept = [unit for unit in before["units"] if unit["id"] != hidden_unit]
    assert kept and kept[0]["lessons"], "the topic needs a second unit with lessons"
    hidden_lesson = kept[0]["lessons"][0]["id"]
    for (_pk, sk), row in table.rows.items():
        if (sk.startswith("UNIT#") and row.get("unit_id") == hidden_unit) or (
            sk.startswith("LESSON#") and row.get("lesson_id") == hidden_lesson
        ):
            row["rollout_state"] = state

    after = client.get(f"/practice/math/{topic_id}/roadmap").json()

    unit_ids = [unit["id"] for unit in after["units"]]
    lesson_ids = [lesson["id"] for unit in after["units"] for lesson in unit["lessons"]]
    assert hidden_unit not in unit_ids
    assert hidden_lesson not in lesson_ids
    assert unit_ids == [unit["id"] for unit in kept]


# ── What clients read never says `mathematics` ──────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/practice/curriculum/catalog",
        "/practice/curriculum/catalog?subjectId=mathematics",
        "/practice/curriculum/progress?subjectId=mathematics",
        "/practice/knowledge-map",
        "/practice/knowledge-map?subjectId=mathematics",
    ],
)
def test_catalog_progress_and_star_map_speak_the_canonical_subject_id(monkeypatch, path):
    """The rows are seeded with `mathematics`; the responses say `math`."""
    _seeded_table(monkeypatch)
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "de")
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {"user_id": user_id, "role": "student", "account_status": "active"},
    )

    response = _roadmap_client().get(path)

    assert response.status_code == 200, response.text
    assert "mathematics" not in response.text.lower()
    assert '"math"' in response.text


# ── The three exercise endpoints nobody calls ────────────────────────────────


@pytest.mark.parametrize(
    "path",
    ["/practice/overview", "/practice/subjects", "/practice/math/some-topic/path"],
)
def test_the_old_exercise_endpoints_are_gone(monkeypatch, path):
    _seeded_table(monkeypatch)
    assert _roadmap_client().get(path).status_code == 404
    routes = {(route.path, tuple(sorted(route.methods))) for route in practice.router.routes}
    assert not {p for p, _m in routes} & {
        "/practice/overview",
        "/practice/subjects",
        "/practice/{subject_id}/{topic_id}/path",
        "/overview",
        "/subjects",
        "/{subject_id}/{topic_id}/path",
    }
