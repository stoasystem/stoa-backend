# Phase 186 Context: Controlled Assignment Automation Contract

## Milestone

v5.3 Controlled Assignment Automation

## Why This Phase Exists

`stoa_docs` Phase 2 growth work calls for AI teacher tools, personalized practice, and subscription-backed learning expansion. STOA now has the required foundations:

- v3.7 reviewed AI teacher tool drafts and practice exercise drafts.
- v4.0 adaptive memory and reviewed assignment lifecycle.
- v5.1 assignment automation readiness and duplicate-prevention boundaries.
- v5.2 adaptive sequencing recommendations, assignment outcome feedback, warehouse-ready analytics, and operator dashboards.

The remaining buildable product gap is controlled automation: converting reviewed recommendations into useful assignments without enabling unreviewed autonomous tutoring.

## Code Context

- `src/stoa/services/adaptive_learning_service.py` creates reviewed assignments, ranks sequencing recommendations, records assignment transitions, and builds parent/tutor progress signals.
- `src/stoa/routers/adaptive.py` exposes memory, recommendation, assignment create/list/get, transition, and parent progress routes.
- `src/stoa/services/ai_teacher_tools_service.py` creates and reviews AI teacher tool drafts, including accepted practice exercise drafts.
- `src/stoa/services/curriculum_analytics_service.py` records assignment outcomes and operator analytics.
- `tests/test_adaptive_learning.py` and `tests/test_curriculum_analytics.py` cover recommendation ranking, assignment lifecycle, outcome feedback, and warehouse/operator analytics.

## Planning Boundary

Phase 186 is a contract phase. It should define autonomy levels, policy boundaries, source eligibility, duplicate/refusal rules, delivery states, review UX handoff, and release evidence. Implementation belongs to Phases 187-190.
