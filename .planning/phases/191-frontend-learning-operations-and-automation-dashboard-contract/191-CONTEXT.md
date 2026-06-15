# Phase 191 Context: Frontend Learning Operations And Automation Dashboard Contract

## Milestone

v5.4 Frontend Learning Operations And Automation Dashboards

## Why This Phase Exists

v5.2 and v5.3 created backend/API readiness for learning operations:

- Adaptive sequencing recommendations.
- Assignment outcome feedback.
- Warehouse-ready analytics and operator dashboard contracts.
- Controlled assignment automation preview/execute APIs.
- Role-safe automation metadata for student, parent, tutor, and admin surfaces.

The next product gap is frontend usability. Operators need a real console to preview and approve automated assignments, inspect analytics/interventions, and explain assigned work to families.

## Not This Feature

This phase is not automatic teacher/tutor dispatch. The existing `stoa_docs` teacher request flow is student question escalation into teacher queue/takeover. v5.4 is about frontend learning operations for automated practice assignment and analytics.

## Code Context

- `src/stoa/routers/adaptive.py` exposes assignment automation preview/execute plus assignment/progress routes.
- `src/stoa/services/adaptive_learning_service.py` contains automation preview/execute, recommendation, assignment, and role-safe response behavior.
- `src/stoa/routers/admin.py` exposes curriculum analytics dashboard, warehouse readiness, and warehouse export endpoints.
- `src/stoa/services/curriculum_analytics_service.py` builds aggregate dashboard/intervention metrics.
- Frontend implementation likely belongs in `/Users/zhdeng/stoa-frontend`; this backend repo records the contract and handoff.

## Planning Boundary

Phase 191 defines purpose, API dependencies, UI surfaces, route contracts, state handling, and implementation handoff. It should avoid broad security/compliance work and avoid new backend scope unless needed for frontend contract stability.
