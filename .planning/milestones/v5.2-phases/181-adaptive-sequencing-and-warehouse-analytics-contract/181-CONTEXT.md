# Phase 181 Context: Adaptive Sequencing And Warehouse Analytics Contract

## Why This Phase Exists

STOA has adaptive learning memory, reviewed assignments, curriculum analytics, and curriculum product readiness. The remaining `stoa_docs` product expansion gap is deeper sequencing and analytics: better next-work recommendations, assignment outcome feedback, warehouse-ready exports, and operator dashboards.

v5.2 starts with a contract phase so recommendation behavior, review gates, analytics schemas, and release expectations are explicit before implementation expands.

## Current Foundation

- v4.0 completed adaptive memory snapshots, next-practice recommendations, reviewed assignment workflows, student/tutor assignment routes, and parent progress signals.
- v4.6 completed bounded curriculum analytics and aggregate content-quality operator views.
- v5.1 completed rich curriculum editor readiness, content migration readiness, assignment automation readiness, and adaptive sequencing readiness.
- `src/stoa/services/adaptive_learning_service.py` and `src/stoa/db/repositories/adaptive_learning_repo.py` contain current memory and assignment behavior.
- `src/stoa/services/curriculum_analytics_service.py` and `src/stoa/db/repositories/curriculum_analytics_repo.py` contain current curriculum analytics behavior.
- `tests/test_adaptive_learning.py` and `tests/test_curriculum_analytics.py` cover existing adaptive/analytics behavior.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 182 through Phase 185 implement. It should not enable fully autonomous tutoring, unreviewed generated assignments, or live warehouse deployment.

## Key Files To Inspect

- `src/stoa/routers/adaptive.py`
- `src/stoa/routers/admin.py`
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/db/repositories/adaptive_learning_repo.py`
- `src/stoa/db/repositories/curriculum_analytics_repo.py`
- `tests/test_adaptive_learning.py`
- `tests/test_curriculum_analytics.py`
- `.planning/phases/128-adaptive-learning-memory-and-assignment-contract/`
- `.planning/phases/129-backend-learning-memory-and-reviewed-assignment-apis/`
- `.planning/phases/130-student-tutor-assignment-ux-and-parent-progress-signals/`
- `.planning/phases/131-v4-0-functional-release-gate-and-personalization-audit/`
- `.planning/phases/154-learning-analytics-and-content-quality-signals/`
- `.planning/phases/179-assignment-automation-and-adaptive-sequencing-readiness/`

## Constraints

- Fully autonomous tutoring remains out of scope unless selected later.
- Generated content remains review-gated.
- Live warehouse/BI deployment may require future infrastructure work.
- Published/rolled-back/archived curriculum content rules must be honored.
- Recommendation outputs should be explainable to tutors/students without exposing raw internal scoring internals.
