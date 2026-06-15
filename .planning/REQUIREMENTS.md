# Requirements: v5.4 Frontend Learning Operations And Automation Dashboards

**Milestone:** v5.4
**Status:** Active planning
**Created:** 2026-06-15

## Purpose

Make the completed v5.2/v5.3 backend learning operations usable in the product UI. v5.4 is not automatic teacher dispatch. Its purpose is to let tutors/admins review adaptive recommendations, preview/execute controlled assignment automation, inspect learning/automation dashboards, and let students/parents understand why automated assignments appeared.

## Implementation Strategy

Use existing backend capabilities first:

- Automation preview/execute APIs in `src/stoa/routers/adaptive.py`.
- Student assignment and parent progress APIs in `src/stoa/routers/adaptive.py`.
- Curriculum analytics dashboard and warehouse-readiness APIs in `src/stoa/routers/admin.py`.
- Existing v5.3 automation metadata on assignments.

Build frontend-facing contracts and UI handoff before adding new backend scope. Any backend work should be limited to missing response-shape fields, no-demo-fallback support, empty/error states, and route contract stabilization.

## Requirements

### FRONTOPS-01 Frontend Learning Operations Contract

Implementers have a concrete UI/API contract for v5.4 before frontend work expands.

Acceptance criteria:

- Contract identifies tutor/admin/student/parent surfaces and their API dependencies.
- Contract explains that v5.4 surfaces automated assignment operations, not automatic teacher dispatch.
- Contract maps automation preview, execute, result history, analytics dashboard, student assignment, and parent progress flows.
- Contract defines no-demo-fallback, loading, empty, refusal, partial-success, and error states.
- Contract defines implementation ownership between backend planning docs and frontend workspace.

### FRONTOPS-02 Tutor/Admin Automation Review Console

Tutors/admins can operate controlled assignment automation from UI.

Acceptance criteria:

- UI contract covers student selector, policy controls, preview, selected/refused candidates, approval, execute, and result rendering.
- Preview and execute payloads use the v5.3 backend API shape.
- Duplicate/refused/low-confidence/paused-policy states are visible without exposing internal ranking internals.
- Tests or focused checks cover preview, execute, partial results, empty states, and backend error states.

### FRONTOPS-03 Learning Operations Dashboard Integration

Operators can inspect learning and automation health from frontend dashboards.

Acceptance criteria:

- UI contract consumes curriculum analytics dashboard, warehouse readiness/export summaries, and assignment automation result metadata.
- Dashboard highlights cohort progress, sequencing coverage, assignment starts/completions/skips/archives, quality signals, and intervention candidates.
- Empty/no-warehouse states are explicit and useful during internal development.
- Tests or focused checks cover dashboard rendering and no-live-warehouse behavior.

### FRONTOPS-04 Student/Parent Assignment Explanation UX

Students and parents can understand automated assignments without seeing private answer keys or internal ranking details.

Acceptance criteria:

- Student assignment views show assignment source label, target topic, tutor-approved/automated marker, due state, and next action.
- Parent progress views show family-safe explanations for why assignment work appeared and what it targets.
- Answer keys and internal ranking internals remain hidden from student/parent surfaces.
- Tests or focused checks cover role-safe payload rendering and no-assignment states.

### VERIFY-37 v5.4 Frontend Learning Operations Release Gate

v5.4 closes with frontend learning operations evidence.

Acceptance criteria:

- Focused frontend/backend contract checks pass or isolate documented pre-existing failures.
- Automation console, dashboard integration, student/parent explanations, no-demo-fallback behavior, and docs are verified.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.4 work.
- Final audit records rollout state: contract-ready, frontend-ready, dashboard-ready, blocked, or deferred.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Automatic teacher/tutor dispatch for student teacher-request queues.
- Fully unreviewed autonomous tutoring.
- Native app implementation and app-store release.
- Live warehouse/BI deployment and scheduled exports.
- Final live payment/support external activation when prerequisites are ready.
- Frontend rich curriculum editor implementation and production content import.

## Out of Scope

- Automatic assignment of human teachers/tutors to student requests.
- Replacing tutor/admin judgment for high-stakes interventions.
- Live provider activation for payments/support.
- Native app implementation.
- Live warehouse deployment.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FRONTOPS-01 | Phase 191 | Complete |
| FRONTOPS-02 | Phase 192 | Complete |
| FRONTOPS-03 | Phase 193 | Complete |
| FRONTOPS-04 | Phase 194 | Complete |
| VERIFY-37 | Phase 195 | Planned |
