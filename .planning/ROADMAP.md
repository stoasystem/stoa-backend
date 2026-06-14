# Roadmap: v5.1 Rich Curriculum Editor And Production Content Migration

**Status:** Active planning
**Created:** 2026-06-14
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Move STOA's curriculum foundation into product-ready curriculum operations: rich editor UI/API handoff, production content migration pipeline, validation/rollback evidence, reviewed exercise assignment readiness, and adaptive sequencing readiness.

## Execution Bias

Build curriculum product functionality directly. Keep verification focused on editor workflow, content validation, migration safety, assignment behavior, and handoff evidence. Do not spend this milestone on broad unrelated security/compliance testing during internal development.

## Phases

- [x] **Phase 176: Rich Curriculum Editor And Migration Contract** - Define editor, migration, QA, assignment, adaptive sequencing, and release handoff contract.
- [x] **Phase 177: Admin Rich Curriculum Editor UI And API Readiness** - Prepare backend/frontend handoff for rich lesson/exercise editing, validation, preview, diff, review, publish, rollback, and archive.
- [ ] **Phase 178: Production Content Migration Pipeline And Validation** - Define and/or build source manifests, dry-run/apply behavior, validation, conflict detection, migration evidence, and rollback metadata.
- [ ] **Phase 179: Assignment Automation And Adaptive Sequencing Readiness** - Define controlled assignment automation and sequencing signals using curriculum progress, AI drafts, memory, and analytics.
- [ ] **Phase 180: v5.1 Curriculum Product Release Gate And Handoff** - Verify v5.1 docs/contracts/evidence, record rollout state, and select the next feature milestone.

## Phase Details

### Phase 176: Rich Curriculum Editor And Migration Contract

**Goal**: Define the v5.1 curriculum product expansion contract before editor UI, migration, or assignment automation work expands.
**Depends on**: v3.8 full curriculum rollout, v4.0 adaptive assignment foundation, v4.6 curriculum authoring/analytics foundation, and `stoa_docs` remaining-feature audit
**Requirements**: CURRICULUMXP-01
**Success Criteria** (what must be TRUE):

  1. Backend, frontend, content, curriculum QA, and release ownership boundaries are documented.
  2. Rich lesson/exercise editing expectations, preview behavior, validation, and review lifecycle are defined.
  3. Production content import/export, migration manifest, dry-run, validation, rollback, and publish sequencing are defined.
  4. Assignment automation and adaptive sequencing readiness are mapped to existing curriculum, AI draft, memory, and analytics signals.
  5. Phase 177 through Phase 180 implementation targets are concrete.

**Plans**: 1/1 plans complete

Plans:

- [x] 176-01: Define rich curriculum editor and migration contract.

### Phase 177: Admin Rich Curriculum Editor UI And API Readiness

**Goal**: Prepare editor UX and backend contract for rich curriculum authoring.
**Depends on**: Phase 176
**Requirements**: CURRICULUMXP-02
**Success Criteria** (what must be TRUE):

  1. Rich editor handoff covers lesson sections, formulas, media references, exercise blocks, answer keys, hints, explanations, tags, prerequisites, and duration.
  2. Backend readiness covers draft update, preview, validation, submit review, approve/request changes, publish, rollback, archive, and audit behavior.
  3. Frontend handoff identifies editor layout, review queue, diff/preview, and validation error implementation points.
  4. Published-only student/parent reads remain stable.

**Plans**: 1/1 plans complete

Plans:

- [x] 177-01: Define rich editor UI and API readiness.

### Phase 178: Production Content Migration Pipeline And Validation

**Goal**: Make production curriculum content migration repeatable and validated.
**Depends on**: Phase 177
**Requirements**: CURRICULUMXP-03
**Success Criteria** (what must be TRUE):

  1. Migration manifests cover source, subject/topic mapping, public/version IDs, locale metadata, exercises, and dependencies.
  2. Dry-run reports created/updated/skipped/conflicted rows and validation errors without mutation.
  3. Apply mode writes migration evidence, version metadata, and audit records under explicit approval.
  4. Rollback/undo metadata protects existing published content.

**Plans**: 0/1 plans complete

Plans:

- [ ] 178-01: Define production content migration pipeline and validation.

### Phase 179: Assignment Automation And Adaptive Sequencing Readiness

**Goal**: Prepare reviewed curriculum and generated exercises for controlled assignment automation and sequencing.
**Depends on**: Phase 178
**Requirements**: CURRICULUMXP-04
**Success Criteria** (what must be TRUE):

  1. Assignment automation eligibility and lifecycle are defined for reviewed/generated exercises.
  2. Sequencing signals use curriculum progress, mistakes, AI drafts, assignment outcomes, analytics, and tutor review state.
  3. Student/parent/tutor visibility boundaries are documented.
  4. Automation remains review-gated where required.

**Plans**: 0/1 plans complete

Plans:

- [ ] 179-01: Define assignment automation and adaptive sequencing readiness.

### Phase 180: v5.1 Curriculum Product Release Gate And Handoff

**Goal**: Close v5.1 with focused verification, handoff evidence, and updated remaining-feature planning.
**Depends on**: Phase 179
**Requirements**: VERIFY-34
**Success Criteria** (what must be TRUE):

  1. Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
  2. Editor handoff, migration pipeline, validation, rollback, assignment readiness, and adaptive sequencing readiness are verified.
  3. Release evidence records rollout state: contract-ready, editor-ready, migration-ready, assignment-ready, blocked, or deferred.
  4. Docs and feature-gap audit reflect completed v5.1 scope and next milestone recommendation.

**Plans**: 0/1 plans complete

Plans:

- [ ] 180-01: Verify v5.1 curriculum product release gate and handoff.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 176 Rich Curriculum Editor And Migration Contract | v5.1 | 1/1 | Complete | 2026-06-14 |
| 177 Admin Rich Curriculum Editor UI And API Readiness | v5.1 | 1/1 | Complete | 2026-06-14 |
| 178 Production Content Migration Pipeline And Validation | v5.1 | 0/1 | Planned | - |
| 179 Assignment Automation And Adaptive Sequencing Readiness | v5.1 | 0/1 | Planned | - |
| 180 v5.1 Curriculum Product Release Gate And Handoff | v5.1 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRICULUMXP-01 | Phase 176 | Complete |
| CURRICULUMXP-02 | Phase 177 | Complete |
| CURRICULUMXP-03 | Phase 178 | Planned |
| CURRICULUMXP-04 | Phase 179 | Planned |
| VERIFY-34 | Phase 180 | Planned |

---
*Last updated: 2026-06-14 after completing Phase 177 admin rich curriculum editor UI and API readiness.*
