# Phase 154 Context

**Phase:** 154 - Learning Analytics And Content Quality Signals
**Milestone:** v4.6 Rich Curriculum Authoring And Analytics Foundation
**Created:** 2026-06-12
**Status:** Ready for execution

## Source Context

Phase 154 builds on Phase 153's public-ID/version-ID authoring layer and existing practice/adaptive events.

Relevant files:

- `src/stoa/services/curriculum_ops_service.py`
- `src/stoa/routers/practice.py`
- `src/stoa/services/adaptive_learning_service.py`
- `tests/test_curriculum_ops.py`
- `tests/test_curriculum_rollout.py`
- `tests/test_adaptive_learning.py`

## Implementation Boundary

Add bounded same-table analytics signals and aggregate views. Do not add a warehouse, BI platform, raw student-answer dashboard, or request-time full table scans across learning history.

## Required Behavior

- Record aggregate-safe signals for practice attempts, wrong answers, lesson completions, assignment completions/skips, and publish/archive lifecycle events.
- Key analytics by stable public IDs and immutable version IDs when available.
- Segment source types such as catalog self-practice, reviewed assignment, AI draft assignment, lesson completion, and curriculum authoring.
- Expose aggregate-only content quality metrics to authorized operators.
- Preserve existing student/parent/tutor curriculum and adaptive behavior.

