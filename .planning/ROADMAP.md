# Roadmap: v4.6 Rich Curriculum Authoring And Analytics Foundation

**Status:** Active research-first planning
**Created:** 2026-06-12
**Research:** `.planning/research/SUMMARY.md`

## Goal

Build an internal curriculum operations layer on top of the v3.8 catalog and v4.0 adaptive-learning signals: authoring, QA, publication lifecycle, rollback/archive safety, and bounded content analytics.

## Execution Bias

Keep the existing FastAPI/Pydantic/DynamoDB stack. Do not build a broad CMS, BI platform, workflow engine, search stack, collaborative editor, or auto-publish automation. Protect existing student/parent/tutor published curriculum, progress, assignments, and adaptive-memory flows before adding analytics.

## Phases

- [ ] **Phase 152: Curriculum Authoring Contract And QA Workflow** - Define stable public IDs versus immutable versions, lifecycle state machines, validation rules, publish manifests, role boundaries, and legacy-readiness rules.
- [ ] **Phase 153: Admin Lesson And Exercise Authoring MVP** - Implement draft/review/publish/archive/rollback authoring workflows with published-only student reads, immutable versions, worklist visibility, and append-only audit evidence.
- [ ] **Phase 154: Learning Analytics And Content Quality Signals** - Add bounded analytics signal capture and aggregate views for confusing exercises, weak topics, stale lessons, content gaps, and assignment-to-content feedback.
- [ ] **Phase 155: v4.6 Curriculum Operations Release Gate** - Verify lifecycle safety, draft isolation, publish/rollback/archive behavior, analytics stability, docs, and next-milestone recommendation.

## Phase Details

### Phase 152: Curriculum Authoring Contract And QA Workflow

**Goal**: Define the curriculum operations contract before any published curriculum mutation is implemented.
**Depends on**: v3.8 curriculum catalog/exercise bank; v4.0 adaptive-learning memory and assignments
**Requirements**: CURROPS-01
**Success Criteria** (what must be TRUE):

  1. Stable public `lesson_id` / `exercise_id` values are separated from immutable authoring `version_id` values.
  2. Curriculum content, QA review outcomes, assignment state, and AI draft acceptance have separate allowed-transition matrices with role requirements and refusal reasons.
  3. Publish units and manifests define how lesson/exercise bundles publish, roll back, archive, and preserve audit evidence without partial mixed states.
  4. Validation rules cover required content fields, answer keys, hints, difficulty, language metadata, subject/topic bindings, and legacy v3.8 readiness.
  5. Student/parent published-only visibility and admin/tutor preview boundaries are explicit.

**Plans**: 0/1 plans complete

Plans:

- [ ] 152-01: Define curriculum authoring contract and QA workflow.

### Phase 153: Admin Lesson And Exercise Authoring MVP

**Goal**: Implement internal authoring workflows that can safely create, review, publish, archive, and roll back lessons/exercises without leaking drafts or breaking published reads.
**Depends on**: Phase 152
**Requirements**: CURROPS-02
**Success Criteria** (what must be TRUE):

  1. Dedicated curriculum ops models, repository, service, and admin/tutor router exist for draft/review/publish/archive/rollback flows.
  2. Immutable version snapshots, mutable summary/published pointers, append-only audit events, and worklist visibility are persisted in the existing DynamoDB table.
  3. Publish and rollback use compare-and-set semantics and update published projections while preserving stable public IDs.
  4. Student/parent catalog, lesson, exercise, progress, and assignment reads remain published-only while draft/review content exists.
  5. Archive is guarded against active assignments and required historical references unless a safe migration/repoint path exists.
  6. Focused tests prove legal/illegal transitions, draft isolation, publish idempotency, rollback/archive behavior, audit evidence, and no student/parent draft leakage.

**Plans**: 0/1 plans complete

Plans:

- [ ] 153-01: Implement admin curriculum authoring and publish safety MVP.

### Phase 154: Learning Analytics And Content Quality Signals

**Goal**: Add bounded operational analytics that help staff prioritize curriculum QA without adding a warehouse or exposing student-sensitive detail.
**Depends on**: Phase 153
**Requirements**: CURROPS-03
**Success Criteria** (what must be TRUE):

  1. Curriculum analytics signals are recorded or materialized from practice attempts, wrong answers, lesson completion, assignment outcomes, skips, adaptive memory, and publish/archive lifecycle events.
  2. Analytics rows are keyed by stable public content IDs and immutable version IDs so edits and rollback do not rewrite historical interpretation.
  3. Admin/tutor aggregate views expose weak topics, confusing exercises, stale lessons, content gaps, assignment-to-content feedback, and high-impact review priorities.
  4. Metrics are segmented by source type, including self-practice, reviewed assignment, AI-draft assignment, skip, retry, and lesson completion.
  5. Analytics avoid request-time full table scans through bounded aggregate rows, windows, pagination, and recompute/backfill helpers where needed.
  6. Responses preserve aggregate privacy boundaries and do not expose raw student answers, answer keys, or per-student surveillance data.

**Plans**: 0/1 plans complete

Plans:

- [ ] 154-01: Add curriculum analytics and content quality signals.

### Phase 155: v4.6 Curriculum Operations Release Gate

**Goal**: Close v4.6 with verification that authoring, publish safety, archive/rollback, analytics, and compatibility with existing curriculum/adaptive flows are locally release-ready.
**Depends on**: Phase 154
**Requirements**: VERIFY-29
**Success Criteria** (what must be TRUE):

  1. Focused backend gates pass for authoring lifecycle, draft isolation, publish/rollback/archive safety, and analytics aggregation.
  2. Existing student/parent/tutor curriculum, practice, progress, and adaptive assignment flows remain compatible with published projections.
  3. Release evidence captures role boundaries, privacy controls, publish idempotency, rollback correctness, archive refusal/guard behavior, analytics stability, and no draft leakage.
  4. Requirements, roadmap, state, feature-gap audit, and remaining-feature queue reflect completed v4.6 scope and deferred CMS/BI/automation work.
  5. Next-milestone recommendation is documented with options across adaptive sequencing, native/mobile expansion, notification production rollout, payment activation, support provider expansion, and deeper analytics.

**Plans**: 0/1 plans complete

Plans:

- [ ] 155-01: Verify v4.6 curriculum operations release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 152 Curriculum Authoring Contract And QA Workflow | v4.6 | 0/1 | Planned | — |
| 153 Admin Lesson And Exercise Authoring MVP | v4.6 | 0/1 | Planned | — |
| 154 Learning Analytics And Content Quality Signals | v4.6 | 0/1 | Planned | — |
| 155 v4.6 Curriculum Operations Release Gate | v4.6 | 0/1 | Planned | — |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURROPS-01 | Phase 152 | Planned |
| CURROPS-02 | Phase 153 | Planned |
| CURROPS-03 | Phase 154 | Planned |
| VERIFY-29 | Phase 155 | Planned |

---
*Last updated: 2026-06-12 after v4.6 research-first roadmap refresh.*
