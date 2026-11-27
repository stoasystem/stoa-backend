"""#675: the adaptive memory snapshots are worked out on each read, never stored.

`POST /adaptive/students/{id}/memory/refresh` stored them as `LEARNING_MEMORY#`
rows, and a stored row then stood in for the snapshot worked out on the read.
No client called it. The route, the writer and the reader are gone: every
snapshot is one of the student's weak topics (`weak_topics`, #673), and its
exercise attempts are that topic's wrong answers that still count. Rows stored
before are still reached by an account's deletion (the catalog lists the type
as `no_longer_written`); `scripts/delete_learning_memory_snapshots.py` cleans
them out once.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes import student_evidence as fake_evidence
from fakes.weak_topic_students import NOW, Student, answer, asked, at, catalog
from stoa.main import app
from stoa.services import adaptive_learning_service, weak_topics

ROOT = Path(__file__).resolve().parents[1]


def _snapshots(student: Student, subject: str | None = None) -> tuple[list, list[dict]]:
    evidence = student.evidence()
    weak = weak_topics.for_student(evidence, student.asked, locale="de")
    return weak, adaptive_learning_service._build_memory_snapshots(  # noqa: SLF001
        student=evidence, weak=weak, subject=subject
    )


STUDENT = Student(
    "snapshots",
    "two exercises wrong in one unit, one of them put right since; Ask on two topics",
    answers=(
        answer("c1", False, 30, unit="prozent-u1"),
        answer("c1", True, 10, unit="prozent-u1"),
        answer("c2", False, 5, unit="prozent-u1"),
        answer("c3", False, 4, unit="kraefte-u1"),
    ),
    asked=(asked(3, "Brüche rechnen"), asked(2, "Kopfrechnen im Alltag")),
)


def test_one_snapshot_per_weak_topic_in_the_projections_order() -> None:
    weak, snapshots = _snapshots(STUDENT)

    assert [(s["subject"], s["topic_id"]) for s in snapshots] == [
        (topic.subject, topic.topic_id) for topic in weak
    ]
    assert [s["topic_id"] for s in snapshots] == [
        "kraefte-u1", "prozent-u1", "kopfrechnen im alltag", "brueche-u2"
    ]
    for snapshot, topic in zip(snapshots, weak, strict=True):
        assert snapshot["weak_topics"] == snapshot["struggling_concepts"] == [topic.topic_id]
        assert snapshot["strengths"] == snapshot["mastered_concepts"] == []
        assert snapshot["freshness"]["lastEvidenceAt"] == topic.latest_evidence_at


def test_a_snapshots_attempts_are_the_mistakes_that_still_count() -> None:
    _, snapshots = _snapshots(STUDENT)
    by_topic = {s["topic_id"]: s for s in snapshots}

    # c1 was answered right after its mistake, so only c2 is left.
    assert by_topic["prozent-u1"]["recent_exercise_attempts"] == [
        {"challengeId": "c2", "lessonId": "prozent-l1", "createdAt": at(5)}
    ]
    assert by_topic["kraefte-u1"]["recent_exercise_attempts"] == [
        {"challengeId": "c3", "lessonId": "kraefte-l1", "createdAt": at(4)}
    ]
    assert by_topic["brueche-u2"]["recent_exercise_attempts"] == []


def test_a_subject_keeps_only_its_snapshots() -> None:
    _, snapshots = _snapshots(STUDENT, subject="physics")

    assert [s["topic_id"] for s in snapshots] == ["kraefte-u1"]


def test_a_snapshots_progress_is_its_units_finished_lessons() -> None:
    # A finished lesson of the unit counts; one of another unit does not.
    built = fake_evidence.evidence(
        "student-progress",
        catalog=catalog(),
        attempts=[answer("c2", False, 5, unit="prozent-u1")],
        progress=[
            {
                "lesson_id": "prozent-l1",
                "unit_id": "prozent-u1",
                "subject_id": "math",
                "topic_id": "prozent",
                "status": "completed",
                "completed_at": at(6),
            },
            {
                "lesson_id": "geometrie-l1",
                "unit_id": "geometrie-u1",
                "subject_id": "math",
                "topic_id": "geometrie",
                "status": "completed",
                "completed_at": at(6),
            },
        ],
        now=NOW,
    )
    weak = weak_topics.for_student(built, (), locale="de")
    (snapshot,) = adaptive_learning_service._build_memory_snapshots(  # noqa: SLF001
        student=built, weak=weak, subject=None
    )

    assert snapshot["recent_curriculum_progress"] == [
        {"lessonId": "prozent-l1", "status": "completed", "completedAt": at(6)}
    ]


def test_the_refresh_route_is_gone() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not {path for path in paths if path.endswith("/memory/refresh")}

    saved = dict(app.dependency_overrides)
    install_actor_overrides(app, {"sub": "teacher-1", "role": "teacher"})
    try:
        response = TestClient(app).post("/adaptive/students/student-1/memory/refresh")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)

    assert response.status_code in {404, 405}, response.text


@pytest.mark.parametrize("name", ["put_memory_snapshot", "list_memory_snapshots"])
def test_nothing_reads_or_writes_the_stored_snapshots(name: str) -> None:
    repo = adaptive_learning_service.adaptive_learning_repo
    assert not hasattr(repo, name)
    # The partition is named only where the deletion still reaches old rows.
    naming = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "src" / "stoa").rglob("*.py")
        if "LEARNING_MEMORY#" in path.read_text(encoding="utf-8")
    )
    assert naming == ["src/stoa/db/data_catalog.py", "src/stoa/db/owner_registry.py"]
