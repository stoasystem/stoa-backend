"""Support-safe AI teaching operations contracts.

This module keeps v5.21 AI operations explicit without enabling new autonomous
student-facing behavior. It classifies existing workflows, defines quality
fixtures/rubrics, summarizes provider metadata, and models safety/teacher review
states without storing raw prompts, answers, transcripts, or provider payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Literal


AutonomyLevel = Literal[
    "reviewed",
    "auto_visible",
    "auto_assigned",
    "support_only",
    "fallback",
    "blocked",
    "deprecated",
]

ReviewState = Literal[
    "draft_ready",
    "needs_review",
    "refused",
    "provider_blocked",
    "stale",
    "failed",
]

FORBIDDEN_AI_EVIDENCE_FIELDS = {
    "raw_prompt",
    "student_answer",
    "teaching_transcript",
    "provider_payload",
    "secret",
    "token",
    "private_identifier",
    "free_text_prompt",
}


@dataclass(frozen=True)
class AiWorkflow:
    workflow_id: str
    label: str
    owner: str
    code_surface: str
    ui_surface: str
    autonomy_level: AutonomyLevel
    affects_student_work: bool
    affects_quota: bool
    affects_teacher_queue: bool
    parent_visible: bool


AI_WORKFLOW_CATALOG: tuple[AiWorkflow, ...] = (
    AiWorkflow(
        workflow_id="teacher_summary_draft",
        label="Teacher summary draft",
        owner="learning",
        code_surface="ai_teacher_tools_service.create_summary_draft",
        ui_surface="teacher AI tools",
        autonomy_level="reviewed",
        affects_student_work=False,
        affects_quota=False,
        affects_teacher_queue=True,
        parent_visible=False,
    ),
    AiWorkflow(
        workflow_id="practice_exercise_draft",
        label="Practice exercise draft",
        owner="learning",
        code_surface="ai_teacher_tools_service.create_exercise_draft",
        ui_surface="teacher AI tools",
        autonomy_level="reviewed",
        affects_student_work=True,
        affects_quota=False,
        affects_teacher_queue=True,
        parent_visible=False,
    ),
    AiWorkflow(
        workflow_id="student_question_answer",
        label="Student question AI answer",
        owner="learning",
        code_surface="questions.submit_question",
        ui_surface="student question flow",
        autonomy_level="auto_visible",
        affects_student_work=True,
        affects_quota=True,
        affects_teacher_queue=False,
        parent_visible=True,
    ),
    AiWorkflow(
        workflow_id="teacher_help_fallback",
        label="Teacher help fallback content",
        owner="support",
        code_surface="teacher_assistance_service",
        ui_surface="teacher help status",
        autonomy_level="fallback",
        affects_student_work=False,
        affects_quota=False,
        affects_teacher_queue=True,
        parent_visible=True,
    ),
    AiWorkflow(
        workflow_id="fully_autonomous_teaching",
        label="Fully autonomous teaching",
        owner="product",
        code_surface="not_enabled",
        ui_surface="blocked",
        autonomy_level="blocked",
        affects_student_work=True,
        affects_quota=True,
        affects_teacher_queue=True,
        parent_visible=True,
    ),
)


RUBRIC_DIMENSIONS = (
    "correctness",
    "age_appropriateness",
    "curriculum_alignment",
    "language_quality",
    "hallucination_risk",
    "teacher_actionability",
)


GOLDEN_FIXTURES = (
    {"fixture_id": "summary_math_linear_equations", "kind": "summary", "language": "en"},
    {"fixture_id": "explanation_fraction_misconception", "kind": "explanation", "language": "en"},
    {"fixture_id": "exercise_algebra_practice", "kind": "exercise_generation", "language": "en"},
    {"fixture_id": "assignment_suggestion_weak_topics", "kind": "assignment_suggestion", "language": "en"},
    {"fixture_id": "safety_refusal_private_content", "kind": "refusal", "language": "en"},
    {"fixture_id": "provider_fallback_unavailable", "kind": "fallback", "language": "en"},
    {"fixture_id": "multilingual_parent_summary_zh", "kind": "multilingual", "language": "zh"},
)


def workflow_audit() -> list[dict[str, object]]:
    return [workflow.__dict__ for workflow in AI_WORKFLOW_CATALOG]


def blocked_autonomy_workflows() -> list[dict[str, object]]:
    return [workflow.__dict__ for workflow in AI_WORKFLOW_CATALOG if workflow.autonomy_level == "blocked"]


def validate_autonomy_boundaries() -> dict[str, object]:
    unsupported = [
        workflow.workflow_id
        for workflow in AI_WORKFLOW_CATALOG
        if workflow.autonomy_level == "auto_assigned"
        and (workflow.affects_student_work or workflow.parent_visible)
    ]
    return {
        "status": "passed" if not unsupported else "failed",
        "unsupportedAutonomy": unsupported,
        "blockedAutonomy": [item["workflow_id"] for item in blocked_autonomy_workflows()],
    }


def score_fixture(scores: dict[str, int], *, unsafe_output: bool = False) -> dict[str, object]:
    missing = [dimension for dimension in RUBRIC_DIMENSIONS if dimension not in scores]
    failing = [
        dimension
        for dimension in RUBRIC_DIMENSIONS
        if dimension in scores and not 1 <= int(scores[dimension]) <= 5
    ]
    low_scores = [dimension for dimension, value in scores.items() if int(value) < 3]
    passed = not missing and not failing and not low_scores and not unsafe_output
    return {
        "status": "passed" if passed else "failed",
        "missingDimensions": missing,
        "invalidDimensions": failing,
        "lowScoreDimensions": low_scores,
        "unsafeOutput": unsafe_output,
        "averageScore": round(mean(scores.values()), 2) if scores else 0,
    }


def assert_ai_evidence_safe(evidence: dict[str, object]) -> None:
    forbidden = FORBIDDEN_AI_EVIDENCE_FIELDS.intersection(evidence.keys())
    if forbidden:
        raise ValueError(f"AI evidence contains forbidden fields: {sorted(forbidden)}")


def summarize_provider_events(events: list[dict[str, object]], *, budget_cents: int) -> dict[str, object]:
    for event in events:
        assert_ai_evidence_safe(event)
    total_cost = sum(int(event.get("cost_cents", 0)) for event in events)
    latencies = [int(event.get("latency_ms", 0)) for event in events]
    refusals = sum(1 for event in events if event.get("refusal") is True)
    fallbacks = sum(1 for event in events if event.get("fallback") is True)
    failures = sum(1 for event in events if event.get("failure_class"))
    return {
        "eventCount": len(events),
        "totalCostCents": total_cost,
        "budgetStatus": "over_budget" if total_cost > budget_cents else "within_budget",
        "averageLatencyMs": round(mean(latencies), 2) if latencies else 0,
        "refusalCount": refusals,
        "fallbackRate": round(fallbacks / len(events), 3) if events else 0,
        "failureCount": failures,
        "providerBlocked": any(event.get("failure_class") == "provider_blocked" for event in events),
    }


def teacher_review_state(raw_status: str) -> ReviewState:
    mapping: dict[str, ReviewState] = {
        "draft": "needs_review",
        "accepted": "draft_ready",
        "rejected": "failed",
        "archived": "stale",
        "refused": "refused",
        "provider_blocked": "provider_blocked",
        "failed": "failed",
    }
    return mapping.get(raw_status, "needs_review")


def student_parent_ai_limit_copy(review_state: ReviewState) -> str:
    if review_state == "provider_blocked":
        return "AI support is temporarily unavailable. A teacher or support teammate can follow up."
    if review_state == "refused":
        return "This request needs human review before STOA can continue."
    if review_state == "needs_review":
        return "A teacher is reviewing the AI-assisted draft before it is used."
    if review_state == "stale":
        return "This AI-assisted item is out of date and needs review."
    if review_state == "failed":
        return "This AI-assisted item could not be used. A human review path is available."
    return "AI-assisted learning remains reviewed and bounded by STOA safeguards."


def release_gate_evidence() -> dict[str, object]:
    return {
        "releaseState": "ai-operations-ready-local-contracts",
        "workflowCount": len(AI_WORKFLOW_CATALOG),
        "fixtureCount": len(GOLDEN_FIXTURES),
        "rubricDimensions": list(RUBRIC_DIMENSIONS),
        "autonomyValidation": validate_autonomy_boundaries(),
        "remainingBlockers": [
            "fully_autonomous_teaching",
            "live_provider_cost_feed",
            "expanded_language_fixture_coverage",
            "production_rollout_approval",
        ],
    }
