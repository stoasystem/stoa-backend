"""The first-lighting signal the star map hands the frontend (#71).

Two things are being proved here, and they are different things.

`litAt` / `litAtSource` say *that* a knowledge point is lit and where that fact
came from. `unacknowledgedLit` says a lighting happened that this student has
not been shown yet, which is the only one the celebration may fire on. A
lighting that was already true before this ledger existed is history, not an
event, so it is written down as `backfilled` and never reaches the signal.

The acknowledgement is kept per student on the server. Keeping it in the
browser would replay the celebration on every new device and swallow it after a
cleared cache, and neither failure is visible from a test that only looks at
one response.
"""

from __future__ import annotations

from typing import Any

import pytest
from boto3.dynamodb.conditions import Key

from fakes.dynamodb import FakeTable

from stoa.db.repositories import practice_repo
from stoa.services import knowledge_map_service as km
from stoa.services import knowledge_mastery_service as mastery


CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 0},
        {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "Erweitern", "order": 1},
    ],
    "lessons": [],
}


def judged(unit_id: str, state: mastery.LearningState) -> mastery.UnitMastery:
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
    """The star map over a table double, with the content held still."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *students: str) -> None:
        self.table = FakeTable()
        for student in students:
            self.table.seed_active_account(student)
        self.states: dict[str, mastery.UnitMastery] = {
            "u1": judged("u1", mastery.LearningState.READY),
            "u2": judged("u2", mastery.LearningState.READY),
        }
        monkeypatch.setattr(practice_repo, "get_table", lambda: self.table)
        monkeypatch.setattr(km.curriculum_service, "list_catalog", lambda **_k: CATALOG)
        monkeypatch.setattr(
            km.curriculum_service, "get_progress_summary", lambda *_a, **_k: {}
        )
        monkeypatch.setattr(km, "_review_due_by_unit", lambda *_a, **_k: {})
        monkeypatch.setattr(
            km.knowledge_mastery_service,
            "unit_states",
            lambda *_a, **_k: dict(self.states),
        )

    def light(self, unit_id: str) -> None:
        self.states[unit_id] = judged(unit_id, mastery.LearningState.LIT)

    def read(self, student_id: str) -> dict[str, Any]:
        return km.knowledge_map(student_id)

    def star(self, sky: dict[str, Any], unit_id: str) -> dict[str, Any]:
        return next(star for star in sky["stars"] if star["unitId"] == unit_id)

    def stored_rows(self, student_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"ACTIVITY#{student_id}") & Key("SK").begins_with("LIT")
            )
        )
        return list(response.get("Items", []))


def test_a_first_lighting_is_signalled_once_and_then_stays_quiet(monkeypatch) -> None:
    sky = Sky(monkeypatch, "student-a")

    opening = sky.read("student-a")
    assert opening["unacknowledgedLit"] == []

    sky.light("u1")
    after = sky.read("student-a")
    assert after["unacknowledgedLit"] == ["u1"]
    star = sky.star(after, "u1")
    assert star["litAtSource"] == "observed"
    assert star["litAt"]

    # Reading again without confirming keeps the signal: a refresh must not
    # swallow a celebration that was never shown.
    assert sky.read("student-a")["unacknowledgedLit"] == ["u1"]

    km.acknowledge_lit("student-a", ["u1"])

    settled = sky.read("student-a")
    assert settled["unacknowledgedLit"] == []
    assert sky.star(settled, "u1")["litAtSource"] == "observed"


def test_the_acknowledgement_is_kept_on_the_server_not_on_the_device(monkeypatch) -> None:
    sky = Sky(monkeypatch, "student-a")
    sky.read("student-a")
    sky.light("u1")
    sky.read("student-a")

    km.acknowledge_lit("student-a", ["u1"])

    acknowledged = [
        row
        for row in sky.stored_rows("student-a")
        if row.get("unit_id") == "u1" and row.get("acknowledged_at")
    ]
    assert acknowledged, "the confirmation left no row behind, so a new device replays it"
    assert acknowledged[0]["student_id"] == "student-a"
    assert sky.read("student-a")["unacknowledgedLit"] == []


def test_a_backfilled_lighting_never_reaches_the_signal(monkeypatch) -> None:
    """A unit already lit when the ledger opened is history, not an event."""
    sky = Sky(monkeypatch, "student-a")
    sky.light("u1")

    first = sky.read("student-a")

    assert first["unacknowledgedLit"] == []
    assert sky.star(first, "u1")["litAtSource"] == "backfilled"
    # And it stays out of the signal on every later read.
    assert sky.read("student-a")["unacknowledgedLit"] == []


def test_one_student_s_confirmation_leaves_another_student_s_alone(monkeypatch) -> None:
    sky = Sky(monkeypatch, "student-a", "student-b")
    sky.read("student-a")
    sky.read("student-b")

    sky.light("u1")
    assert sky.read("student-a")["unacknowledgedLit"] == ["u1"]
    assert sky.read("student-b")["unacknowledgedLit"] == ["u1"]

    km.acknowledge_lit("student-a", ["u1"])

    assert sky.read("student-a")["unacknowledgedLit"] == []
    assert sky.read("student-b")["unacknowledgedLit"] == ["u1"]


def test_a_student_cannot_confirm_a_lighting_that_is_not_in_their_own_sky(monkeypatch) -> None:
    """The partition is the student's. Naming another's unit confirms nothing."""
    sky = Sky(monkeypatch, "student-a", "student-b")
    sky.read("student-b")
    sky.light("u1")
    sky.read("student-b")

    # student-a has no row for u1 at all; nothing may be written under b's key.
    assert km.acknowledge_lit("student-a", ["u1"])["acknowledged"] == []
    assert sky.read("student-b")["unacknowledgedLit"] == ["u1"]


def test_an_unlit_knowledge_point_carries_no_lighting_time(monkeypatch) -> None:
    sky = Sky(monkeypatch, "student-a")

    star = sky.star(sky.read("student-a"), "u2")
    assert star["litAt"] is None
    assert star["litAtSource"] is None


def test_the_signal_is_decided_in_the_pure_core() -> None:
    """`resolve_lit_facts` is where observed and backfilled are told apart."""
    facts, fresh = mastery.resolve_lit_facts(
        lit_unit_ids=["u1"], stored={}, ledger_open=False, now="2026-10-08T00:00:00+00:00"
    )
    assert facts["u1"].source is mastery.LitSource.BACKFILLED
    assert [fact.unit_id for fact in fresh] == ["u1"]
    assert mastery.unacknowledged_lit(facts) == ()

    later, newly = mastery.resolve_lit_facts(
        lit_unit_ids=["u1", "u2"],
        stored=facts,
        ledger_open=True,
        now="2026-10-09T00:00:00+00:00",
    )
    assert [fact.unit_id for fact in newly] == ["u2"]
    assert mastery.unacknowledged_lit(later) == ("u2",)
