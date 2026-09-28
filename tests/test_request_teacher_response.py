"""What a student is told after asking for a teacher: stoasystem/stoa-backend#76.

`POST /questions/{id}/request-teacher` returned the dispatch service's result
as it was, and that result carries the dispatch plan: every candidate
teacher's id, role, account state, profile version, fence generation,
subjects, availability, load, SLA bucket, rank and refusal reason, and on
success the chosen teacher's id. A student is told only whether a teacher
has been found.
"""

from __future__ import annotations

import json

import pytest
from fakes.dynamodb import FakeTable

from stoa.routers import questions
from test_index_key_writes_omit_none import _escalation_scaffold

_PLAN = {
    "questionId": "question-1",
    "status": "ready",
    "selected": [
        {
            "teacherId": "teacher-secret-1",
            "role": "teacher",
            "accountStatus": "active",
            "profileVersion": 7,
            "accountFenceGeneration": 3,
            "subjects": ["math"],
            "availability": "available",
            "activeCount": 1,
            "maxActiveSessions": 3,
            "recentSlaBucket": "within_target",
            "rankScore": 12.0,
        }
    ],
    "refused": [
        {
            "teacherId": "teacher-secret-2",
            "refusalCode": "not_available",
            "refusalReason": "Teacher is paused, offline, busy, or inactive.",
        }
    ],
    "summary": {"topCandidateId": "teacher-secret-1", "noCandidateReason": None},
}


@pytest.mark.parametrize(
    ("service_result", "told"),
    [
        (
            {
                "questionId": "question-1",
                "status": "dispatched",
                "dispatchId": "dispatch-1",
                "teacherId": "teacher-secret-1",
                "deadlineAt": "2026-09-28T12:10:00+00:00",
                "attemptCount": 1,
                "plan": _PLAN,
            },
            "assigned",
        ),
        (
            {
                "questionId": "question-1",
                "status": "already_dispatched",
                "teacherId": "teacher-secret-1",
                "dispatchId": "dispatch-1",
            },
            "assigned",
        ),
        ({"questionId": "question-1", "status": "no_candidate", "plan": _PLAN}, "waiting"),
        ({"questionId": "question-1", "status": "claim_conflict", "plan": _PLAN}, "waiting"),
        ({"questionId": "question-1", "status": "deferred", "reason": "dispatch_failed"}, "waiting"),
    ],
    ids=["dispatched", "already_dispatched", "no_candidate", "claim_conflict", "deferred"],
)
def test_the_student_is_told_only_whether_a_teacher_was_found(monkeypatch, service_result, told):
    client, _question, _dispatches = _escalation_scaffold(monkeypatch, FakeTable())
    monkeypatch.setattr(
        questions.teacher_dispatch_service,
        "dispatch_question",
        lambda question_id, **_kwargs: dict(service_result),
    )

    response = client.post("/questions/question-1/request-teacher")

    assert response.status_code == 202, response.text
    assert response.json()["dispatch"] == {"questionId": "question-1", "status": told}
    served = json.dumps(response.json())
    for secret in ("teacher-secret", "plan", "rankScore", "refusal", "dispatch-1", "deadlineAt"):
        assert secret not in served, secret
