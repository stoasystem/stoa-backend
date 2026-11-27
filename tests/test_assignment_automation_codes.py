"""#495: the automation's reasons carry codes a client translates.

A candidate's rationale (`rationaleCode`), a refusal (`refusalCode`) and an
execution result (`reasonCode`) each carry a stable code; the four-language
sentences are in the message catalog under `assignment_automation.<kind>.<code>`.
The English sentence is still sent beside the code, for a client that does not
know the code yet, and it is the catalog's English.
"""

from __future__ import annotations

import pytest

from stoa.services import adaptive_learning_service, message_catalog
from stoa.services.adaptive_learning_service import (
    AutomationRefusalCode,
    AutomationResultCode,
    RationaleCode,
    automation_catalog_key,
)
from fakes import student_evidence as fake_evidence
from test_adaptive_learning import (  # noqa: F401 - the autouse fixtures
    _app,
    _canonical_student_profiles,
    _evidence_read_on_the_same_day,
    _install_learning_sources,
    _install_memory_repo,
)

LOCALES = ("de", "en", "fr", "it")

ALL_CODES = [
    *(("rationale", code) for code in RationaleCode),
    *(("refusal", code) for code in AutomationRefusalCode),
    *(("result", code) for code in AutomationResultCode),
]


@pytest.mark.parametrize(("kind", "code"), ALL_CODES)
def test_every_code_has_a_sentence_in_four_languages(kind, code) -> None:
    variants = message_catalog.TEXT[automation_catalog_key(kind, code)]

    assert set(variants) == set(LOCALES)
    assert all(variants[locale].strip() for locale in LOCALES)


def test_the_rationale_codes_are_the_candidate_types() -> None:
    assert {code.value for code in RationaleCode} == {
        "remediation_topic",
        "curriculum_exercise",
        "reviewed_ai_draft",
        "continuation_lesson",
    }


def _english(kind: str, code: str) -> str:
    return message_catalog.text(automation_catalog_key(kind, code), "en")


def _sources(monkeypatch, *, drafts: list[dict] | None = None) -> None:
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.curriculum_service,
        "topic_exercise_reader",
        lambda **kwargs: lambda _subject, _topic: [
            {"id": "challenge-1", "prompt": "Solve a linear equation"}
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: drafts
        if drafts is not None
        else [
            {
                "draft_id": "draft-1",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "teacher-1",
            }
        ],
    )


def _two_topics(monkeypatch) -> None:
    """Questions on two topics; the reviewed draft is on the first."""
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500, **_kwargs: {
            "Items": [
                {
                    "PK": f"QUESTION#question-{name}",
                    "SK": "META",
                    "question_id": f"question-{name}",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": [point],
                    "student_feedback": 2,
                    "created_at": created_at,
                }
                for name, point, created_at in (
                    ("linear", "Linear equations", "2026-06-09T10:00:00+00:00"),
                    ("fractions", "Fractions", "2026-06-09T11:00:00+00:00"),
                )
            ]
        },
    )
    fake_evidence.install(monkeypatch)


def test_every_recommendation_names_its_rationale_by_code(monkeypatch) -> None:
    _sources(monkeypatch)

    response = _app({"sub": "teacher-1", "role": "teacher"}).get(
        "/adaptive/students/student-1/recommendations"
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert {item["rationaleCode"] for item in items} >= {
        "curriculum_exercise",
        "reviewed_ai_draft",
        "remediation_topic",
    }
    for item in items:
        assert item["rationaleCode"] == item["type"]
        assert item["rationale"] == _english("rationale", item["rationaleCode"])


def test_the_memory_summary_carries_the_rationale_code(monkeypatch) -> None:
    _sources(monkeypatch)

    response = _app({"sub": "teacher-1", "role": "teacher"}).get(
        "/adaptive/students/student-1/memory"
    )

    assert response.status_code == 200, response.text
    assert all(item["rationaleCode"] for item in response.json()["recommendations"])


def test_preview_candidates_and_refusals_carry_codes(monkeypatch) -> None:
    _sources(monkeypatch)

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"sourceTypes": ["ai_draft"], "maxAssignmentsPerStudent": 1}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected"]
    for candidate in body["selected"]:
        assert candidate["rationaleCode"] in {code.value for code in RationaleCode}
        assert candidate["rationale"] == _english("rationale", candidate["rationaleCode"])
    assert body["refused"]
    for refused in body["refused"]:
        assert refused["rationaleCode"]
        assert refused["refusalCode"] in {code.value for code in AutomationRefusalCode}
        assert refused["refusalReason"] == _english("refusal", refused["refusalCode"])


def test_a_paused_policy_keeps_its_own_reason_beside_the_code(monkeypatch) -> None:
    _sources(monkeypatch)

    response = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"status": "paused", "pausedReason": "Exams this week."}},
    )

    assert response.status_code == 200, response.text
    refused = response.json()["refused"]
    assert refused
    assert {item["refusalCode"] for item in refused} == {"policy_paused"}
    assert {item["refusalReason"] for item in refused} == {"Exams this week."}


def test_the_maximum_refusal_carries_its_code(monkeypatch) -> None:
    _sources(monkeypatch)
    _two_topics(monkeypatch)

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={
            "policy": {
                "sourceTypes": ["ai_draft", "curriculum_exercise", "memory_snapshot"],
                "maxAssignmentsPerStudent": 1,
                "confidenceThreshold": "low",
            }
        },
    )

    assert response.status_code == 200, response.text
    maxed = [
        item
        for item in response.json()["refused"]
        if item["refusalCode"] == "max_assignments_reached"
    ]
    assert maxed
    assert maxed[0]["refusalReason"] == _english("refusal", "max_assignments_reached")


def _execute(policy: dict, candidates: list[dict], batch_id: str):
    return _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={"batchId": batch_id, "approved": True, "policy": policy, "candidates": candidates},
    )


def test_execution_results_carry_reason_codes(monkeypatch) -> None:
    _sources(monkeypatch)
    _two_topics(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["linear-equations"],
            "created_by": "teacher-1",
            "items": [{"prompt": "Solve x + 2 = 5"}],
            "answer_key": [{"answer": "3"}],
        },
    )
    policy = {
        "policyId": "policy-codes",
        "sourceTypes": ["ai_draft", "memory_snapshot"],
        "maxAssignmentsPerStudent": 3,
    }
    preview = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": policy},
    )
    assert preview.status_code == 200, preview.text
    batch_id = preview.json()["batchId"]
    selected = preview.json()["selected"]
    draft = next(item for item in selected if item["sourceType"] == "ai_draft")
    memory = next(item for item in selected if item["sourceType"] == "memory_snapshot")

    held_back = _execute(policy, [{**draft, "approved": False}, memory], batch_id)
    executed = _execute(policy, [draft], batch_id)
    again = _execute(policy, [draft], batch_id)

    assert held_back.status_code == 200, held_back.text
    results = {item["candidateId"]: item for item in held_back.json()["results"]}
    not_approved = results[draft["candidateId"]]
    assert not_approved["reasonCode"] == "not_approved"
    assert not_approved["reason"] == _english("result", "not_approved")
    refused = results[memory["candidateId"]]
    assert refused["reasonCode"] == "refused"
    assert refused["refusalCode"] == "unsupported_assignment_source"
    assert refused["reason"] == _english("refusal", "unsupported_assignment_source")
    assert executed.status_code == 200, executed.text
    (created,) = executed.json()["results"]
    assert created["reasonCode"] == "created"
    assert created["reason"] == _english("result", "created")
    assert again.status_code == 200, again.text
    (duplicate,) = again.json()["results"]
    assert duplicate["reasonCode"] == "already_created"
    assert duplicate["reason"] == _english("result", "already_created")
