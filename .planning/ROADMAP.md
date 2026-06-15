# Roadmap: v5.3 Controlled Assignment Automation

**Status:** Active planning
**Created:** 2026-06-15
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Turn v5.2 adaptive sequencing recommendations into controlled assignment automation. v5.3 should let tutors/admins configure automation levels, batch reviewed candidates, create assignments safely from accepted AI drafts or curriculum exercises, expose delivery state to students/parents/tutors, and keep fully unreviewed autonomous tutoring out of scope.

## Execution Bias

Build product capability directly. Keep checks focused on automation policy behavior, candidate selection, duplicate prevention, assignment creation/delivery, role-visible explanations, and release evidence. This is internal development, so avoid broad unrelated security/compliance testing unless a strict safety issue appears.

## Phases

- [x] **Phase 186: Controlled Assignment Automation Contract** - Define automation levels, source eligibility, review gates, duplicate rules, delivery states, role visibility, and rollout boundaries.
- [x] **Phase 187: Automation Policy And Candidate Batch Planner** - Add or define policy-driven candidate selection from v5.2 recommendations, accepted AI drafts, curriculum exercises, and assignment outcomes.
- [x] **Phase 188: Controlled Assignment Creation And Delivery Worker** - Add or define idempotent assignment creation/delivery from approved batches with clear refusal and result evidence.
- [ ] **Phase 189: Tutor Admin Review UX Contracts And Family Visibility** - Define tutor/admin batch review, override, pause, and parent/student explanations for automated assignment delivery.
- [ ] **Phase 190: v5.3 Controlled Assignment Automation Release Gate** - Verify v5.3 docs/contracts/evidence, record rollout state, and select the next feature milestone.

## Phase Details

### Phase 186: Controlled Assignment Automation Contract

**Goal**: Define the v5.3 automation contract before code expands.
**Depends on**: v3.7 AI teacher tools, v4.0 reviewed assignments, v5.1 assignment automation readiness, v5.2 adaptive sequencing and assignment outcome feedback
**Requirements**: AUTOASSIGN-01
**Success Criteria** (what must be TRUE):

  1. Backend, frontend, tutor, admin, student/parent, analytics, and release ownership boundaries are documented.
  2. Autonomy levels are defined: off, suggest-only, tutor-approved batch, auto-create reviewed, and future auto-deliver.
  3. Eligible sources are limited to accepted AI practice drafts, published curriculum exercises, and v5.2 recommendation candidates.
  4. Duplicate, stale, completed, archived, rolled-back, unpublished, and low-confidence candidates are refused or suppressed.
  5. Phase 187 through Phase 190 implementation targets are concrete.

**Plans**: 1/1 plans complete

Plans:

- [x] 186-01: Define controlled assignment automation contract.

### Phase 187: Automation Policy And Candidate Batch Planner

**Goal**: Convert recommendations into policy-bounded assignment candidate batches.
**Depends on**: Phase 186
**Requirements**: AUTOASSIGN-02
**Success Criteria** (what must be TRUE):

  1. Policy settings cover student/cohort scope, subjects/topics, max assignments, source types, confidence thresholds, freshness, due-window defaults, and pause states.
  2. Batch planner explains selected and refused candidates with source, confidence, duplicate reason, review status, and expected student impact.
  3. Planner uses assignment outcomes to avoid immediate repeats and to prioritize remediation where useful.
  4. Tests cover policy filtering, dedupe/refusal, stale candidates, accepted-draft eligibility, and stable batch shape.

**Plans**: 1/1 plans complete

Plans:

- [x] 187-01: Implement automation policy and candidate batch planner.

### Phase 188: Controlled Assignment Creation And Delivery Worker

**Goal**: Create and optionally deliver reviewed assignments from approved batches without duplicate side effects.
**Depends on**: Phase 187
**Requirements**: AUTOASSIGN-03
**Success Criteria** (what must be TRUE):

  1. Approved batches create assignments idempotently with source attribution, automation policy metadata, actor, and result evidence.
  2. Delivery states distinguish created, assigned, delivered, skipped, refused, duplicate, and failed.
  3. Student-visible assignments never expose answer keys; parent-visible state remains summary-safe.
  4. Tests cover idempotency, partial batch results, source attribution, duplicate prevention, and role-visible response shape.

**Plans**: 1/1 plans complete

Plans:

- [x] 188-01: Implement controlled assignment creation and delivery worker.

### Phase 189: Tutor Admin Review UX Contracts And Family Visibility

**Goal**: Make automation review and assignment delivery understandable to operators and families.
**Depends on**: Phase 188
**Requirements**: AUTOASSIGN-04
**Success Criteria** (what must be TRUE):

  1. Tutor/admin review contracts cover preview, approve, reject, override, pause, resume, and audit/result views.
  2. Parent/student explanations show why assignment work appeared without exposing internal ranking internals.
  3. Operator dashboards show automation coverage, acceptance/refusal, delivery results, skips/completions, and intervention candidates.
  4. Frontend/API handoff documents routes, payloads, empty states, and no-automation behavior.

**Plans**: 0/1 plans complete

Plans:

- [ ] 189-01: Define tutor/admin review UX contracts and family visibility.

### Phase 190: v5.3 Controlled Assignment Automation Release Gate

**Goal**: Close v5.3 with focused verification, handoff evidence, and updated remaining-feature planning.
**Depends on**: Phase 189
**Requirements**: VERIFY-36
**Success Criteria** (what must be TRUE):

  1. Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
  2. Automation policy, batch planning, creation/delivery, role visibility, and docs are verified.
  3. Release evidence records rollout state: contract-ready, planner-ready, automation-ready, delivery-ready, blocked, or deferred.
  4. Docs and feature-gap audit reflect completed v5.3 scope and next milestone recommendation.

**Plans**: 0/1 plans complete

Plans:

- [ ] 190-01: Verify v5.3 controlled assignment automation release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 186 Controlled Assignment Automation Contract | v5.3 | 1/1 | Complete | 2026-06-15 |
| 187 Automation Policy And Candidate Batch Planner | v5.3 | 1/1 | Complete | 2026-06-15 |
| 188 Controlled Assignment Creation And Delivery Worker | v5.3 | 1/1 | Complete | 2026-06-15 |
| 189 Tutor Admin Review UX Contracts And Family Visibility | v5.3 | 0/1 | Planned | - |
| 190 v5.3 Controlled Assignment Automation Release Gate | v5.3 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTOASSIGN-01 | Phase 186 | Complete |
| AUTOASSIGN-02 | Phase 187 | Complete |
| AUTOASSIGN-03 | Phase 188 | Complete |
| AUTOASSIGN-04 | Phase 189 | Planned |
| VERIFY-36 | Phase 190 | Planned |

---
*Last updated: 2026-06-15 after selecting v5.3 controlled assignment automation.*
