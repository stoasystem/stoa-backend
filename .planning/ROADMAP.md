# Roadmap: v5.4 Frontend Learning Operations And Automation Dashboards

**Status:** Active planning
**Created:** 2026-06-15
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Turn v5.2/v5.3 backend learning operations into product-usable frontend workflows: tutor/admin automation review, learning operations dashboards, and student/parent explanations for automated assignments.

## Purpose

v5.4 makes completed backend capabilities usable by real operators and families. It is not teacher auto-dispatch. The feature answers: "What work should this student do next, why, who approved it, what happened after delivery, and where should tutors intervene?"

## Implementation Strategy

Start from existing backend APIs and keep new backend scope minimal:

- Use `/adaptive/students/{student_id}/assignment-automation/batches/preview`.
- Use `/adaptive/students/{student_id}/assignment-automation/batches/execute`.
- Use adaptive assignment list/detail/progress routes for student and parent explanations.
- Use `/admin/curriculum/analytics/dashboard`, `/warehouse-readiness`, and `/warehouse-export` for operator analytics.
- Add frontend contracts, no-demo-fallback behavior, empty/error states, and focused checks before considering new backend endpoints.

## Execution Bias

Build product workflows directly. During internal development, prioritize end-to-end usability and contract correctness over broad security/compliance testing. Keep strict role-safe display boundaries for answer keys and internal ranking details.

## Phases

- [x] **Phase 191: Frontend Learning Operations And Automation Dashboard Contract** - Define purpose, UI surfaces, API dependencies, role-safe data boundaries, and implementation handoff.
- [x] **Phase 192: Tutor Admin Automation Review Console** - Build or define preview/approve/execute/result UI for controlled assignment automation.
- [x] **Phase 193: Learning Operations Dashboard Integration** - Build or define dashboard UI for sequencing coverage, assignment outcomes, warehouse readiness, and interventions.
- [x] **Phase 194: Student Parent Assignment Explanation UX** - Build or define family-safe assignment explanations and progress views.
- [ ] **Phase 195: v5.4 Frontend Learning Operations Release Gate** - Verify UI/API contracts, evidence, docs, and next milestone recommendation.

## Phase Details

### Phase 191: Frontend Learning Operations And Automation Dashboard Contract

**Goal**: Define purpose, UI surfaces, API dependencies, role-safe data boundaries, state handling, and implementation handoff before frontend learning operations work expands.
**Depends on**: v5.2 adaptive sequencing analytics, v5.3 controlled assignment automation
**Requirements**: FRONTOPS-01
**Success Criteria** (what must be TRUE):

  1. Tutor, admin, student, and parent surfaces are identified with API dependencies.
  2. v5.4 is clearly scoped to learning operations and assignment automation dashboards, not automatic teacher/tutor dispatch.
  3. Automation preview, execute, result history, analytics dashboard, student assignment, and parent progress flows are mapped.
  4. No-demo-fallback, loading, empty, refusal, partial-success, and error states are defined.
  5. Backend planning and frontend workspace ownership boundaries are explicit.

**Plans**: 1/1 plans complete

Plans:

- [x] 191-01: Define frontend learning operations and automation dashboard contract.

### Phase 192: Tutor Admin Automation Review Console

**Goal**: Build or define a tutor/admin console for previewing, approving, executing, and reviewing controlled assignment automation batches.
**Depends on**: Phase 191
**Requirements**: FRONTOPS-02
**Success Criteria** (what must be TRUE):

  1. Student selection, automation policy controls, preview, approval, execute, and result views are available or concretely handed off.
  2. Preview and execute payloads follow the v5.3 backend API shape.
  3. Duplicate, refused, low-confidence, stale, and paused-policy states are visible without exposing internal ranking internals.
  4. Focused checks cover preview, execute, partial results, empty states, and backend error states.

**Plans**: 1/1 plans complete

Plans:

- [x] 192-01: Build or define tutor/admin automation review console.

### Phase 193: Learning Operations Dashboard Integration

**Goal**: Build or define learning operations dashboards for sequencing coverage, assignment outcomes, warehouse readiness, and intervention candidates.
**Depends on**: Phase 192
**Requirements**: FRONTOPS-03
**Success Criteria** (what must be TRUE):

  1. Dashboard consumes curriculum analytics dashboard, warehouse readiness/export summaries, and assignment automation result metadata.
  2. Dashboard highlights cohort progress, sequencing coverage, assignment starts/completions/skips/archives, quality signals, and intervention candidates.
  3. Empty and no-live-warehouse states are explicit and useful during internal development.
  4. Focused checks cover dashboard rendering and no-live-warehouse behavior.

**Plans**: 1/1 plans complete

Plans:

- [x] 193-01: Build or define learning operations dashboard integration.

### Phase 194: Student Parent Assignment Explanation UX

**Goal**: Build or define family-safe assignment explanation UX for students and parents.
**Depends on**: Phase 193
**Requirements**: FRONTOPS-04
**Success Criteria** (what must be TRUE):

  1. Student assignment views show source label, target topic, tutor-approved or automation-created marker, due state, and next action.
  2. Parent progress views show family-safe explanations for why assignment work appeared and what it targets.
  3. Answer keys and internal ranking internals remain hidden from student and parent surfaces.
  4. Focused checks cover role-safe payload rendering and no-assignment states.

**Plans**: 1/1 plans complete

Plans:

- [x] 194-01: Build or define student/parent assignment explanation UX.

### Phase 195: v5.4 Frontend Learning Operations Release Gate

**Goal**: Close v5.4 with focused verification, release evidence, documentation updates, and next milestone recommendation.
**Depends on**: Phase 194
**Requirements**: VERIFY-37
**Success Criteria** (what must be TRUE):

  1. Focused frontend/backend contract checks pass or isolate documented pre-existing failures.
  2. Automation console, dashboard integration, student/parent explanations, no-demo-fallback behavior, and docs are verified.
  3. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.4 work.
  4. Final audit records rollout state: contract-ready, frontend-ready, dashboard-ready, blocked, or deferred.
  5. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans complete

Plans:

- [ ] 195-01: Verify v5.4 frontend learning operations release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 191 Frontend Learning Operations And Automation Dashboard Contract | v5.4 | 1/1 | Complete | 2026-06-15 |
| 192 Tutor Admin Automation Review Console | v5.4 | 1/1 | Complete | 2026-06-15 |
| 193 Learning Operations Dashboard Integration | v5.4 | 1/1 | Complete | 2026-06-15 |
| 194 Student Parent Assignment Explanation UX | v5.4 | 1/1 | Complete | 2026-06-15 |
| 195 v5.4 Frontend Learning Operations Release Gate | v5.4 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FRONTOPS-01 | Phase 191 | Complete |
| FRONTOPS-02 | Phase 192 | Complete |
| FRONTOPS-03 | Phase 193 | Complete |
| FRONTOPS-04 | Phase 194 | Complete |
| VERIFY-37 | Phase 195 | Planned |

---
*Last updated: 2026-06-15 after selecting v5.4 frontend learning operations and automation dashboards.*
