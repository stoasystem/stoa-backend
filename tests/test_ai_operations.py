import pytest

from stoa.services import ai_operations_service


def test_workflow_audit_maps_ai_surfaces_and_blocks_full_autonomy():
    audit = ai_operations_service.workflow_audit()

    workflow_ids = {item["workflow_id"] for item in audit}
    assert "teacher_summary_draft" in workflow_ids
    assert "practice_exercise_draft" in workflow_ids
    assert "student_question_answer" in workflow_ids
    assert "fully_autonomous_teaching" in workflow_ids

    validation = ai_operations_service.validate_autonomy_boundaries()
    assert validation["status"] == "passed"
    assert "fully_autonomous_teaching" in validation["blockedAutonomy"]


def test_quality_rubric_requires_all_dimensions_and_safe_output():
    passing = ai_operations_service.score_fixture(
        {
            "correctness": 4,
            "age_appropriateness": 4,
            "curriculum_alignment": 4,
            "language_quality": 4,
            "hallucination_risk": 4,
            "teacher_actionability": 4,
        }
    )
    assert passing["status"] == "passed"

    failing = ai_operations_service.score_fixture(
        {
            "correctness": 2,
            "age_appropriateness": 4,
            "curriculum_alignment": 4,
            "language_quality": 4,
            "hallucination_risk": 4,
            "teacher_actionability": 4,
        },
        unsafe_output=True,
    )
    assert failing["status"] == "failed"
    assert failing["unsafeOutput"] is True
    assert "correctness" in failing["lowScoreDimensions"]


def test_golden_fixtures_cover_required_ai_behaviors():
    kinds = {fixture["kind"] for fixture in ai_operations_service.GOLDEN_FIXTURES}

    assert {
        "summary",
        "explanation",
        "exercise_generation",
        "assignment_suggestion",
        "refusal",
        "fallback",
        "multilingual",
    }.issubset(kinds)


def test_provider_observability_summary_is_support_safe_and_budget_aware():
    summary = ai_operations_service.summarize_provider_events(
        [
            {
                "provider": "bedrock",
                "model": "model-a",
                "workflow": "teacher_summary_draft",
                "latency_ms": 1200,
                "cost_cents": 12,
                "fallback": False,
                "refusal": False,
                "failure_class": None,
            },
            {
                "provider": "bedrock",
                "model": "model-a",
                "workflow": "student_question_answer",
                "latency_ms": 1800,
                "cost_cents": 20,
                "fallback": True,
                "refusal": True,
                "failure_class": "provider_blocked",
            },
        ],
        budget_cents=25,
    )

    assert summary["budgetStatus"] == "over_budget"
    assert summary["fallbackRate"] == 0.5
    assert summary["providerBlocked"] is True


def test_provider_observability_rejects_raw_private_evidence():
    with pytest.raises(ValueError):
        ai_operations_service.summarize_provider_events(
            [{"raw_prompt": "private", "cost_cents": 1}],
            budget_cents=10,
        )


def test_safety_teacher_review_states_and_parent_copy_are_explicit():
    assert ai_operations_service.teacher_review_state("draft") == "needs_review"
    assert ai_operations_service.teacher_review_state("refused") == "refused"
    assert ai_operations_service.teacher_review_state("provider_blocked") == "provider_blocked"

    copy = ai_operations_service.student_parent_ai_limit_copy("provider_blocked")
    assert "teacher or support" in copy


def test_release_gate_evidence_records_blockers_without_enabling_autonomy():
    evidence = ai_operations_service.release_gate_evidence()

    assert evidence["releaseState"] == "ai-operations-ready-local-contracts"
    assert evidence["fixtureCount"] >= 7
    assert "fully_autonomous_teaching" in evidence["remainingBlockers"]
    assert evidence["autonomyValidation"]["status"] == "passed"
