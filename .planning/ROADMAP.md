# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05.
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05.
- [x] **v1.9 Recovery Resume And Support Evidence Packages** - Shipped 2026-06-05.
- [x] **v2.0 Controlled Report Editing MVP** - Shipped 2026-06-05.
- [x] **v2.1 Report Artifact Versioning And Safe Edit Preview** - Shipped 2026-06-06.
- [x] **v2.2 Report Artifact Rollback And Safe Fixture Verification** - Shipped 2026-06-06.
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07.
- [x] **v2.6 Audit Retention And Immutable Evidence Readiness** - Shipped 2026-06-07.
- [x] **v2.7 Immutable Audit Storage And Legal Hold Foundation** - Shipped 2026-06-07.
- [x] **v2.8 CDK-Managed Immutable Evidence Storage Deployment** - Shipped 2026-06-07.
- [x] **v2.9 Retention Governance And Legal Hold Operations** - Complete local-only 2026-06-07; production verification closed by v3.0.
- [x] **v3.0 STOA Docs Gap Closeout And Account Intake Hardening** - Shipped 2026-06-08.
- [x] **v3.1 Teacher Reply Quality And SLA Operations** - Shipped 2026-06-08.
- [x] **v3.2 Content Moderation And Internal Operations** - Shipped 2026-06-08.
- [x] **v3.3 Subscription Operations MVP** - Completed local release gate 2026-06-08.
- [x] **v3.4 Learning Expansion Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.5 Realtime And Teacher Assistance Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.6 Full WebSocket Realtime Notifications** - Completed local release gate 2026-06-09.
- [x] **v3.7 AI Teacher Tools And Exercise Generation** - Completed local release gate 2026-06-09.

## Current Milestone

**v3.8 Full Curriculum Rollout** - Active.

Goal: roll out full curriculum structure and exercise bank coverage for math, physics, German, and English on top of the existing subject/topic/practice foundations.

## Phases

- [x] **Phase 120: Full Curriculum Rollout Contract And Content Model** - Complete 2026-06-09.
- [ ] **Phase 121: Backend Curriculum Catalog And Exercise Bank APIs** - Planned.
- [ ] **Phase 122: Student/Parent Curriculum UX And Tutor Signals** - Planned.
- [ ] **Phase 123: Functional Release Gate And Curriculum Audit** - Planned.

| Phase | Name | Status | Requirement |
|-------|------|--------|-------------|
| 120 | Full Curriculum Rollout Contract And Content Model | Complete | CURRIC-01 |
| 121 | Backend Curriculum Catalog And Exercise Bank APIs | Planned | CURRIC-02 |
| 122 | Student/Parent Curriculum UX And Tutor Signals | Planned | UI-23 |
| 123 | Functional Release Gate And Curriculum Audit | Planned | VERIFY-21 |

## Phase Details

### Phase 120: Full Curriculum Rollout Contract And Content Model

**Goal:** Define the curriculum hierarchy, content states, lesson/exercise fields, supported subjects, and migration/backfill behavior before backend and frontend implementation.

**Requirement:** CURRIC-01
**Plans:** 1/1 plans complete

**Success Criteria**:
1. Contract defines subject, grade/band, unit, topic, lesson, exercise, assessment/checkpoint, and rollout state hierarchy.
2. Contract defines lesson and exercise fields including objective, explanation, examples, difficulty, estimated time, answer key, and topic binding.
3. Contract defines math, physics, German, and English rollout metadata, including language and grade-level handling.
4. Contract defines seed, draft, reviewed, active, and archived content lifecycle states.
5. Contract defines migration/backfill behavior from existing practice data without breaking current practice routes.

### Phase 121: Backend Curriculum Catalog And Exercise Bank APIs

**Goal:** Add backend curriculum catalog and exercise bank APIs that expose active curriculum data while preserving existing practice progress behavior.

**Requirement:** CURRIC-02
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Student/tutor/admin can list curriculum subjects, units, topics, lessons, and exercises with rollout-aware filters.
2. Backend supports seed/backfill from existing practice subjects, topics, lessons, and challenges into curriculum metadata.
3. Existing practice progress, mistakes, lesson completion, and challenge attempts remain compatible.
4. Lesson detail returns explanation, examples, exercises, authorized answer keys, and next-step metadata.
5. Focused tests cover catalog shape, subject/grade/topic filtering, exercise bank shape, progress compatibility, and inactive/archived exclusion.

### Phase 122: Student/Parent Curriculum UX And Tutor Signals

**Goal:** Expose curriculum rollout through student, parent, tutor, and admin surfaces using real curriculum data and clear rollout states.

**Requirement:** UI-23
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Student practice/curriculum UI shows subject, unit, topic, lesson, exercise, progress, and next-step states.
2. Parent child profile/report surfaces show curriculum progress and weak curriculum areas without claiming unsupported subjects are complete.
3. Tutor/admin surfaces expose student curriculum context while answering questions or reviewing AI exercise drafts.
4. UI distinguishes active curriculum content from draft, preview, and archived content.
5. Targeted browser verification confirms core curriculum navigation and progress states.

### Phase 123: Functional Release Gate And Curriculum Audit

**Goal:** Close v3.8 with focused backend/frontend evidence and update Phase 2 gap tracking for curriculum rollout and residual adaptive scope.

**Requirement:** VERIFY-21
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Backend and frontend focused quality gates relevant to curriculum rollout pass.
2. Gap audit marks full multi-subject curriculum rollout active or closed and records residual adaptive sequencing/automatic assignment scope.
3. Final audit lists remaining Phase 2 product expansions including payment-provider integration, long-term personalization, production WebSocket infrastructure, push/native/email notifications, mobile/multilingual polish, and support integrations.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 120 | v3.8 | 1/1 | Complete | 2026-06-09 |
| 121 | v3.8 | 0/1 | Planned | - |
| 122 | v3.8 | 0/1 | Planned | - |
| 123 | v3.8 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRIC-01 | Phase 120 | Complete |
| CURRIC-02 | Phase 121 | Planned |
| UI-23 | Phase 122 | Planned |
| VERIFY-21 | Phase 123 | Planned |

---
*Last updated: 2026-06-09 after completing Phase 120*
