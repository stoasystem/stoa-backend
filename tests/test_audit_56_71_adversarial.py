"""INDEPENDENT AUDIT probes for stoa-backend#56 / #71. Not part of the shipped suite.

Written by the audit agent to attack the two new routes rather than to
describe them. Delete with the audit if it is not kept.
"""

from __future__ import annotations

from typing import Any

import pytest
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable

from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.routers import admin, practice
from stoa.security import route_authorization
from stoa.services import knowledge_map_service as km
from stoa.services import knowledge_mastery_service as mastery


# ───────────────────────── #56  PATCH /admin/curriculum/units/{unit_id}


UNITS = [
    {
        "unit_id": "u-a",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "title": "A",
        "order": 1,
        "prerequisite_unit_ids": [],
    },
    {
        "unit_id": "u-b",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "title": "B",
        "order": 2,
        "prerequisite_unit_ids": ["u-a"],
    },
    {
        "unit_id": "u-c",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "title": "C",
        "order": 3,
        "prerequisite_unit_ids": ["u-b"],
    },
    {
        "unit_id": "u-de",
        "topic_id": "topic-b",
        "subject_id": "german",
        "title": "German one",
        "order": 1,
        "prerequisite_unit_ids": [],
    },
    {
        "unit_id": "u-noless",
        "topic_id": "topic-c",
        "subject_id": "",
        "title": "No subject",
        "order": 1,
        "prerequisite_unit_ids": [],
    },
    {
        "unit_id": "u-noless-2",
        "topic_id": "topic-c",
        "subject_id": "",
        "title": "No subject two",
        "order": 2,
        "prerequisite_unit_ids": [],
    },
]


def _units_table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    table = FakeTable()
    table.seed(*[{"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in UNITS])
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(curriculum_ops_repo, "get_table", lambda: table)
    return table


def _admin_client(user: dict[str, Any]) -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    return TestClient(app)


def _author(role: str = "teacher", sub: str = "t-1") -> dict[str, Any]:
    return {"sub": sub, "role": role, "capabilities": {"curriculum_author": "granted"}}


def _patch(client: TestClient, unit_id: str, refs: list[str], **extra: Any):
    return client.patch(
        f"/admin/curriculum/units/{unit_id}",
        json={"prerequisiteUnitIds": refs, **extra},
    )


def test_patch_cannot_create_a_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _units_table(monkeypatch)
    client = _admin_client(_author())

    response = _patch(client, "u-brand-new", ["u-a"])

    assert response.status_code == 404, response.text
    assert ("PRACTICE", "UNIT#u-brand-new") not in table.rows


def test_patch_refuses_a_three_hop_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """a -> b -> c, then c as a's prerequisite closes a loop two hops away."""
    table = _units_table(monkeypatch)
    client = _admin_client(_author())

    response = _patch(client, "u-a", ["u-c"])

    assert response.status_code == 422, response.text
    assert table.rows[("PRACTICE", "UNIT#u-a")]["prerequisite_unit_ids"] == []


def test_patch_refuses_duplicate_references(monkeypatch: pytest.MonkeyPatch) -> None:
    _units_table(monkeypatch)
    client = _admin_client(_author())

    assert _patch(client, "u-c", ["u-a", "u-a"]).status_code == 422


def test_patch_refuses_more_than_fifty_references(monkeypatch: pytest.MonkeyPatch) -> None:
    _units_table(monkeypatch)
    client = _admin_client(_author())

    assert _patch(client, "u-c", [f"u-{i}" for i in range(51)]).status_code == 422


def test_patch_refuses_a_cross_subject_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    _units_table(monkeypatch)
    client = _admin_client(_author())

    assert _patch(client, "u-c", ["u-de"]).status_code == 422


def test_units_without_a_subject_can_be_wired_to_each_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`same_subject('', '')` is true, so a blank subject is its own bucket."""
    _units_table(monkeypatch)
    client = _admin_client(_author())

    response = _patch(client, "u-noless-2", ["u-noless"])

    assert response.status_code == 200, response.text


def test_an_author_teacher_may_rewire_any_subject_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No per-subject scoping exists: one `curriculum_author` grant is global."""
    table = _units_table(monkeypatch)
    client = _admin_client(_author(sub="maths-teacher"))

    german = _patch(client, "u-de", [])
    maths = _patch(client, "u-c", ["u-a"])

    assert german.status_code == 200, german.text
    assert maths.status_code == 200, maths.text
    assert table.rows[("PRACTICE", "UNIT#u-de")]["updated_by"] == "maths-teacher"


def test_patch_cannot_rename_or_remap_the_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _units_table(monkeypatch)
    client = _admin_client(_author())

    response = _patch(
        client, "u-c", [], title="Hijacked", subjectId="german", topicId="topic-b"
    )

    assert response.status_code == 200, response.text
    row = table.rows[("PRACTICE", "UNIT#u-c")]
    assert row["title"] == "C"
    assert row["subject_id"] == "mathematics"
    assert row["topic_id"] == "topic-a"


@pytest.mark.parametrize("role", ["student", "parent"])
def test_a_learner_role_never_reaches_the_unit_patch(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    _units_table(monkeypatch)
    client = _admin_client({"sub": "x-1", "role": role})

    assert _patch(client, "u-c", []).status_code == 403


def test_a_teacher_without_the_author_capability_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _units_table(monkeypatch)
    client = _admin_client({"sub": "t-2", "role": "teacher"})

    assert _patch(client, "u-c", []).status_code == 403


def test_a_reviewer_capability_is_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    _units_table(monkeypatch)
    client = _admin_client(
        {"sub": "t-3", "role": "teacher", "capabilities": {"curriculum_reviewer": "granted"}}
    )

    assert _patch(client, "u-c", []).status_code == 403


# ───────────────────────── #71  POST /practice/knowledge-map/acknowledged-lit


CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "T", "order": 0}],
    "units": [
        {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "One", "order": 0},
        {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "Two", "order": 1},
    ],
    "lessons": [],
}


def _judged(unit_id: str, state: mastery.LearningState) -> mastery.UnitMastery:
    lit = state is mastery.LearningState.LIT
    return mastery.UnitMastery(
        unit_id=unit_id,
        topic_id="t1",
        subject_id="math",
        state=state,
        progress=1.0 if lit else 0.0,
        unmet_exercises=0,
        lesson_count=1,
        lessons_done=1 if lit else 0,
        next_lesson=None,
    )


class Sky:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, *students: str) -> None:
        self.table = FakeTable()
        for student in students:
            self.table.seed_active_account(student)
        self.states = {
            "u1": _judged("u1", mastery.LearningState.READY),
            "u2": _judged("u2", mastery.LearningState.READY),
        }
        monkeypatch.setattr(practice_repo, "get_table", lambda: self.table)
        monkeypatch.setattr(km.curriculum_service, "list_catalog", lambda **_k: CATALOG)
        monkeypatch.setattr(km.curriculum_service, "get_progress_summary", lambda *_a, **_k: {})
        monkeypatch.setattr(km, "_review_due_by_unit", lambda *_a, **_k: {})
        monkeypatch.setattr(
            km.knowledge_mastery_service, "unit_states", lambda *_a, **_k: dict(self.states)
        )

    def light(self, unit_id: str) -> None:
        self.states[unit_id] = _judged(unit_id, mastery.LearningState.LIT)

    def read(self, student_id: str) -> dict[str, Any]:
        return km.knowledge_map(student_id)

    def rows(self, student_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"ACTIVITY#{student_id}") & Key("SK").begins_with("LIT")
            )
        )
        return list(response.get("Items", []))


def _practice_client(
    monkeypatch: pytest.MonkeyPatch, user: dict[str, Any]
) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, user)
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda user_id, **_kw: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        },
    )
    return TestClient(app)


def test_a_named_student_in_the_body_is_ignored_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route + service + table, no stand-in for the write."""
    sky = Sky(monkeypatch, "student-a", "student-b")
    sky.read("student-a")
    sky.read("student-b")
    sky.light("u1")
    sky.read("student-a")
    sky.read("student-b")

    client = _practice_client(monkeypatch, {"sub": "student-a", "role": "student"})
    response = client.post(
        "/practice/knowledge-map/acknowledged-lit",
        json={
            "unitIds": ["u1"],
            "studentId": "student-b",
            "userId": "student-b",
            "owner_id": "student-b",
            "student_id": "student-b",
            "PK": "ACTIVITY#student-b",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["acknowledged"] == ["u1"]
    mine = [r for r in sky.rows("student-a") if r.get("unit_id") == "u1"]
    theirs = [r for r in sky.rows("student-b") if r.get("unit_id") == "u1"]
    assert mine and mine[0].get("acknowledged_at")
    assert theirs and not theirs[0].get("acknowledged_at")
    assert sky.read("student-b")["unacknowledgedLit"] == ["u1"]


def test_an_unknown_unit_id_creates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    sky = Sky(monkeypatch, "student-a")
    sky.read("student-a")

    client = _practice_client(monkeypatch, {"sub": "student-a", "role": "student"})
    response = client.post(
        "/practice/knowledge-map/acknowledged-lit",
        json={"unitIds": ["u-not-real", "LIT_LEDGER", "../u1", ""]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["acknowledged"] == []
    assert [r["SK"] for r in sky.rows("student-a")] == ["LIT_LEDGER"]


def test_acknowledging_before_the_lighting_does_not_swallow_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sky = Sky(monkeypatch, "student-a")
    sky.read("student-a")

    km.acknowledge_lit("student-a", ["u1"])
    sky.light("u1")

    assert sky.read("student-a")["unacknowledgedLit"] == ["u1"]


@pytest.mark.parametrize("role", ["parent", "teacher"])
def test_nobody_but_the_student_may_confirm(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    Sky(monkeypatch, "student-a")
    client = _practice_client(monkeypatch, {"sub": f"{role}-1", "role": role})

    response = client.post(
        "/practice/knowledge-map/acknowledged-lit", json={"unitIds": ["u1"]}
    )

    assert response.status_code in (403, 404), response.text


def test_one_post_cannot_cost_more_writes_than_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upper bound on what one confirmation call asks the table to do.

    Every id costs a conditional write whether or not it names a lighting,
    and a refused write is billed like any other. The cap was two hundred
    against ten knowledge points; the audit that found this is why it is not.
    """
    sky = Sky(monkeypatch, "student-a")
    sky.read("student-a")
    before = len(sky.table.requests)

    client = _practice_client(monkeypatch, {"sub": "student-a", "role": "student"})
    response = client.post(
        "/practice/knowledge-map/acknowledged-lit",
        json={"unitIds": [f"u-{i}" for i in range(50)]},
    )
    refused = client.post(
        "/practice/knowledge-map/acknowledged-lit",
        json={"unitIds": [f"u-{i}" for i in range(51)]},
    )

    assert response.status_code == 200, response.text
    # One over the cap is refused outright rather than trimmed quietly.
    assert refused.status_code == 422, refused.text
    writes = [
        c
        for c in sky.table.requests[before:]
        if c[0] in {"update_item", "put_item", "transact_write_items"}
    ]
    assert len(writes) == 50, f"{len(writes)} write attempts for one call"


# ───────────────────────── #71  the read that writes


def test_a_settled_sky_costs_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    sky = Sky(monkeypatch, "student-a")
    sky.light("u1")
    sky.read("student-a")

    before = len(sky.table.requests)
    for _ in range(5):
        sky.read("student-a")
    writes = [
        c[0]
        for c in sky.table.requests[before:]
        if c[0] in {"put_item", "update_item", "transact_write_items"}
    ]
    assert writes == [], f"a settled sky still wrote: {writes}"


def test_a_parent_s_get_writes_into_the_student_s_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driven through the real route by a bound parent, not by calling the service."""
    sky = Sky(monkeypatch, "student-a")
    sky.light("u1")

    client = _practice_client(
        monkeypatch, {"sub": "parent-1", "role": "parent", "bound": True}
    )
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "de")

    response = client.get("/practice/knowledge-map", params={"studentId": "student-a"})

    assert response.status_code == 200, response.text
    rows = sky.rows("student-a")
    assert {r["SK"] for r in rows} == {"LIT_LEDGER", "LIT#u1"}
    assert all(r.get("owner_id") == "student-a" for r in rows)
    assert sky.rows("parent-1") == []


def test_a_swallowed_write_replays_the_celebration_forever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the lighting row cannot be written, the signal never settles."""
    sky = Sky(monkeypatch, "student-a")
    sky.read("student-a")  # ledger opens
    sky.light("u1")

    monkeypatch.setattr(
        practice_repo,
        "record_lit_unit",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("table down")),
    )

    first = sky.read("student-a")
    second = sky.read("student-a")

    assert first["unacknowledgedLit"] == ["u1"]
    assert second["unacknowledgedLit"] == ["u1"]
    # And confirming it does nothing, because there is no row to confirm.
    assert km.acknowledge_lit("student-a", ["u1"])["acknowledged"] == []
    assert sky.read("student-a")["unacknowledgedLit"] == ["u1"]


def test_a_read_failure_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading the ledger is outside the try: a broken read breaks the sky."""
    sky = Sky(monkeypatch, "student-a")
    monkeypatch.setattr(
        practice_repo,
        "read_lit_ledger",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("table down")),
    )

    with pytest.raises(RuntimeError):
        sky.read("student-a")
