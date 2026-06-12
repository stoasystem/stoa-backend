# Phase 152 Context

**Phase:** 152 - Curriculum Authoring Contract And QA Workflow
**Milestone:** v4.6 Rich Curriculum Authoring And Analytics Foundation
**Created:** 2026-06-12
**Status:** Ready for execution

## Source Context

Phase 152 uses the v4.6 research synthesis in `.planning/research/SUMMARY.md` and the current backend implementation:

- Published curriculum catalog/progress reads are built from `src/stoa/services/curriculum_service.py`.
- Published content storage currently lives behind `src/stoa/db/repositories/practice_repo.py`.
- Student/parent/tutor curriculum routes are exposed from `src/stoa/routers/practice.py`.
- Reviewed assignments and adaptive memory use `src/stoa/services/adaptive_learning_service.py`.
- Existing regression coverage is in `tests/test_curriculum_rollout.py` and `tests/test_adaptive_learning.py`.

## Phase Boundary

This phase defines the contract that Phase 153 must implement. It does not add routes, repositories, data migrations, or student-visible behavior changes.

## Locked Decisions

- Stable public IDs remain the canonical API identifiers for lessons and exercises.
- Immutable authoring versions are separate from stable public IDs.
- Draft/review records must not be read by existing student or parent routes.
- Student-visible curriculum reads continue to use published projections only.
- Admin/tutor preview is explicit and role-gated.
- Assignment lifecycle, AI draft acceptance, QA review outcome, and content lifecycle remain separate state machines.
- The first implementation uses the existing FastAPI/Pydantic/DynamoDB stack and avoids a broad CMS, warehouse, workflow engine, or auto-publish system.

## Open Implementation Discretion For Phase 153

- Exact Pydantic class names and router module split.
- Whether worklist rows are materialized immediately or derived from summary rows.
- Exact DynamoDB sort-key strings, provided the contract's identity and lifecycle guarantees hold.
- The smallest viable endpoint set that satisfies the authoring MVP.

