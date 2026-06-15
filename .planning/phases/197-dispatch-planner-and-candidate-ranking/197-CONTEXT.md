# Phase 197 Context: Dispatch Planner And Candidate Ranking

## Phase Boundary

Build non-mutating teacher/tutor candidate ranking for escalated questions. The planner must explain selected and refused candidates without changing question state.

## Existing Context

- `src/stoa/services/teacher_dispatch_service.py` owns dispatch planning logic.
- Existing question rows provide `subject`, `teacher_requested_at`, `queue_visible_at`, and dispatch metadata.
- Teacher/tutor/admin user profiles provide role, subject capability, availability, load, and SLA metadata.

## Decisions

- Use profile metadata for availability and capabilities before live staffing calendar integration exists.
- Refuse profiles with ineligible role, paused/offline/busy status, max active sessions, missing subject capability, subject mismatch, or prior timeout.
- Rank eligible candidates by load, SLA bucket, last-dispatch fairness, and stable teacher ID.

## Deferred

- Live calendar integration.
- Cross-timezone scheduling.
- Payroll or compensation automation.
