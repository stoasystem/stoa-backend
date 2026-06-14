# Phase 176 Context: Rich Curriculum Editor And Migration Contract

## Why This Phase Exists

STOA has a full curriculum catalog, exercise bank, authoring lifecycle, publish/rollback/archive controls, and aggregate curriculum analytics. The remaining `stoa_docs` curriculum product gap is turning those foundations into product-ready operations: rich editor UX, production content migration, assignment automation readiness, and deeper adaptive sequencing readiness.

v5.1 starts with a contract phase so backend, frontend, content, QA, and release ownership are explicit before implementation expands across the curriculum surface.

## Current Foundation

- v3.8 completed curriculum hierarchy, lesson/exercise bank coverage, student/parent curriculum UX, and tutor/admin curriculum signals.
- v4.0 completed adaptive learning memory and reviewed assignment workflows.
- v4.6 completed curriculum authoring, QA lifecycle, publish/rollback/archive safety, and bounded content-quality analytics.
- `src/stoa/services/curriculum_service.py`, `src/stoa/services/curriculum_ops_service.py`, and `src/stoa/services/curriculum_analytics_service.py` contain the current backend curriculum behavior.
- `tests/test_curriculum_rollout.py`, `tests/test_curriculum_ops.py`, and `tests/test_curriculum_analytics.py` cover existing curriculum behavior.
- `stoa_docs` remaining-feature queue now points to product expansion when external activation prerequisites are blocked.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 177 through Phase 180 implement and what remains external. It should not migrate production content or publish unreviewed generated material.

## Key Files To Inspect

- `src/stoa/routers/admin.py`
- `src/stoa/routers/practice.py`
- `src/stoa/routers/adaptive.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/services/curriculum_ops_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/db/repositories/curriculum_ops_repo.py`
- `src/stoa/db/repositories/curriculum_analytics_repo.py`
- `tests/test_curriculum_rollout.py`
- `tests/test_curriculum_ops.py`
- `tests/test_curriculum_analytics.py`
- `.planning/phases/120-curriculum-hierarchy-and-content-contract/`
- `.planning/phases/121-backend-curriculum-catalog-and-exercise-bank/`
- `.planning/phases/122-curriculum-ux-and-tutor-admin-signals/`
- `.planning/phases/123-v3-8-curriculum-release-gate-and-product-expansion-audit/`
- `.planning/phases/152-curriculum-authoring-contract-and-qa-workflow/`
- `.planning/phases/153-admin-lesson-and-exercise-authoring-mvp/`
- `.planning/phases/154-learning-analytics-and-content-quality-signals/`
- `.planning/phases/155-v4-6-curriculum-operations-release-gate/`

## Constraints

- Frontend rich editor work may require `/Users/zhdeng/stoa-frontend`.
- Production source content and migration approval may be external.
- Published student/parent curriculum reads must remain stable while drafts and migrations evolve.
- Generated exercise assignment must remain reviewed/gated unless a later milestone explicitly selects autonomous publication.
- Verification should focus on functional editor/migration/assignment readiness.
