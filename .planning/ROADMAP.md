# Roadmap: v5.5 Automatic Teacher Dispatch And SLA Load Balancing

**Status:** Active planning
**Created:** 2026-06-15
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Turn the existing manual teacher queue/takeover workflow into controlled automatic dispatch: route escalated student questions to eligible teachers/tutors, prevent double assignment, reassign timed-out work, and expose SLA/load health.

## Purpose

When a student requests a teacher, the product should not depend only on every teacher manually scanning the shared queue. v5.5 makes the system actively route work while preserving the human teacher reply workflow.

This feature answers: "Which available teacher should see this request first, when should it be reassigned, and how do operators know the queue is healthy?"

## Implementation Strategy

Start from existing backend primitives and add dispatch behavior around them:

- Use `POST /questions/{question_id}/request-teacher` as the source of escalated requests.
- Preserve `GET /teachers/queue` and `POST /teachers/questions/{question_id}/takeover` compatibility.
- Extend question/session metadata with dispatch ID, candidate teacher, dispatch status, deadline, attempt count, and previous assignees.
- Add a planner that ranks teachers/tutors by subject match, availability, active load, recent SLA, queue age, and fairness.
- Add conditional claim/reassignment behavior to prevent duplicate assignment and recover timed-out dispatches.
- Keep implementation focused on product behavior during internal development; avoid broad unrelated security/compliance work.

## Phases

- [x] **Phase 196: Teacher Dispatch And SLA Load Balancing Contract** - Define dispatch purpose, states, matching inputs, claim rules, timeout behavior, and visibility.
- [x] **Phase 197: Dispatch Planner And Candidate Ranking** - Add or define non-mutating candidate ranking for escalated questions.
- [x] **Phase 198: Automatic Dispatch Claim And Reassignment Worker** - Add or define idempotent dispatch claim, timeout, reassignment, and manual takeover compatibility.
- [x] **Phase 199: Teacher Queue And Operator Dispatch Visibility** - Add or define teacher queue/operator dashboard visibility for assigned work, load, and SLA risk.
- [x] **Phase 200: v5.5 Teacher Dispatch Release Gate** - Verify dispatch behavior, docs, evidence, and next milestone recommendation.

## Phase Details

### Phase 196: Teacher Dispatch And SLA Load Balancing Contract

**Goal**: Define dispatch purpose, state model, matching inputs, claim rules, timeout/reassignment behavior, visibility surfaces, and implementation boundaries before automatic teacher dispatch code expands.
**Depends on**: Existing request-teacher, teacher queue, teacher takeover, teacher reply, resolve, notification, and SLA behavior.
**Requirements**: TEACHDISP-01
**Success Criteria** (what must be TRUE):

  1. Teacher/tutor availability, subject capability, role eligibility, load metrics, and pause/offline states are defined.
  2. Dispatch states are defined from unassigned through dispatched, accepted, timed out, reassigned, declined, active, and resolved.
  3. Candidate ranking inputs include subject match, active load, recent SLA, last dispatch, queue age, and escalation priority.
  4. Conflict and claim behavior prevents double assignment while preserving manual takeover compatibility.
  5. Teacher queue, operator dashboard, student status, notification, and rollout-state boundaries are explicit.

**Plans**: 1/1 plans complete

Plans:

- [x] 196-01: Define teacher dispatch and SLA load balancing contract.

### Phase 197: Dispatch Planner And Candidate Ranking

**Goal**: Build or define a non-mutating dispatch planner that ranks eligible teachers/tutors for an escalated question and explains selected/refused candidates.
**Depends on**: Phase 196
**Requirements**: TEACHDISP-02
**Success Criteria** (what must be TRUE):

  1. Planner returns stable selected/refused candidate payloads with reason codes.
  2. Planner respects subject capability, availability, max active sessions, paused/offline state, and role eligibility.
  3. Planner ranks eligible candidates by load, SLA health, queue age, fairness, and last dispatch time.
  4. Focused tests cover eligible candidate selection, refusal reasons, fairness/load ordering, and no-candidate fallback.

**Plans**: 1/1 plans complete

Plans:

- [x] 197-01: Implement dispatch planner and candidate ranking.

### Phase 198: Automatic Dispatch Claim And Reassignment Worker

**Goal**: Add idempotent automatic dispatch claim and timeout/reassignment behavior while preserving the existing manual takeover/reply workflow.
**Depends on**: Phase 197
**Requirements**: TEACHDISP-03
**Success Criteria** (what must be TRUE):

  1. Dispatch worker conditionally claims an escalated question for exactly one selected teacher/tutor.
  2. Dispatch metadata records dispatch ID, candidate teacher, reason, SLA deadline, attempt count, and previous assignees.
  3. Timeout worker releases or reassigns stale dispatched work according to policy.
  4. Manual takeover can accept or override dispatch when allowed without corrupting SLA or assignment state.
  5. Focused tests cover idempotency, double-claim prevention, timeout, reassignment, manual takeover interaction, and no-candidate fallback.

**Plans**: 1/1 plans complete

Plans:

- [x] 198-01: Implement automatic dispatch claim and reassignment worker.

### Phase 199: Teacher Queue And Operator Dispatch Visibility

**Goal**: Make dispatch state visible to teachers and operators without exposing internal ranking details to students.
**Depends on**: Phase 198
**Requirements**: TEACHDISP-04
**Success Criteria** (what must be TRUE):

  1. Teacher queue distinguishes available queue items, dispatched-to-me items, stale dispatches, and manually available items.
  2. Operator dashboard exposes queue age, assigned load, dispatch attempts, timeout/reassignment counts, SLA risk, and no-candidate reasons.
  3. Student-facing status stays simple: waiting, assigned, active, replied, or resolved.
  4. Notification/event handoff is documented for dispatched, accepted, timed out, reassigned, and replied states.
  5. Focused checks verify role-appropriate visibility for teacher, operator, and student surfaces.

**Plans**: 1/1 plans complete

Plans:

- [x] 199-01: Implement teacher queue and operator dispatch visibility.

### Phase 200: v5.5 Teacher Dispatch Release Gate

**Goal**: Close v5.5 with dispatch behavior evidence, documentation updates, feature-gap alignment, and next milestone recommendation.
**Depends on**: Phase 199
**Requirements**: VERIFY-38
**Success Criteria** (what must be TRUE):

  1. Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
  2. Dispatch planner, claim/reassignment worker, teacher queue visibility, operator dashboard, and docs are verified.
  3. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.5 work.
  4. Final audit records rollout state: contract-ready, planner-ready, dispatch-ready, queue-ready, blocked, or deferred.
  5. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 1/1 plans complete

Plans:

- [x] 200-01: Verify v5.5 teacher dispatch release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 196 Teacher Dispatch And SLA Load Balancing Contract | v5.5 | 1/1 | Complete | 2026-06-15 |
| 197 Dispatch Planner And Candidate Ranking | v5.5 | 1/1 | Complete | 2026-06-15 |
| 198 Automatic Dispatch Claim And Reassignment Worker | v5.5 | 1/1 | Complete | 2026-06-15 |
| 199 Teacher Queue And Operator Dispatch Visibility | v5.5 | 1/1 | Complete | 2026-06-15 |
| 200 v5.5 Teacher Dispatch Release Gate | v5.5 | 1/1 | Complete | 2026-06-15 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEACHDISP-01 | Phase 196 | Complete |
| TEACHDISP-02 | Phase 197 | Complete |
| TEACHDISP-03 | Phase 198 | Complete |
| TEACHDISP-04 | Phase 199 | Complete |
| VERIFY-38 | Phase 200 | Complete |

---
*Last updated: 2026-06-15 after completing v5.5 teacher dispatch release gate.*
