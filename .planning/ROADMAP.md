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

## Current Milestone

**v3.7 AI Teacher Tools And Exercise Generation** - Active.

Goal: add teacher-facing automatic summaries, suggested focus, draft explanations, and bounded exercise generation with teacher/admin review.

## Phases

- [x] **Phase 116: AI Teacher Tools Contract And Generation Model** - Complete 2026-06-09.
- [x] **Phase 117: Backend Teacher Summary And Exercise Draft APIs** - Complete 2026-06-09.
- [ ] **Phase 118: Tutor AI Tools And Exercise Draft UI** - Planned.
- [ ] **Phase 119: Functional Release Gate And AI Tools Audit** - Planned.

| Phase | Name | Status | Requirement |
|-------|------|--------|-------------|
| 116 | AI Teacher Tools Contract And Generation Model | Complete | AITOOL-01 |
| 117 | Backend Teacher Summary And Exercise Draft APIs | Complete | AITOOL-02 |
| 118 | Tutor AI Tools And Exercise Draft UI | Planned | UI-22 |
| 119 | v3.7 Functional Release Gate And AI Tools Audit | Planned | VERIFY-20 |

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 116 | v3.7 | 1/1 | Complete | 2026-06-09 |
| 117 | v3.7 | 1/1 | Complete | 2026-06-09 |
| 118 | v3.7 | 0/1 | Planned | - |
| 119 | v3.7 | 0/1 | Planned | - |

## Phase Details

### Phase 116: AI Teacher Tools Contract And Generation Model

**Goal:** Define teacher summaries, suggested focus, draft explanation, bounded exercise generation, input sources, persistence, review lifecycle, and no-auto-send boundaries before implementation.

**Requirement:** AITOOL-01
**Plans:** 1/1 plans complete

**Success Criteria**:
1. Contract defines session summary, misconception summary, suggested teaching focus, draft explanation, and practice exercise draft outputs.
2. Contract defines approved input sources from question, conversation, teacher reply, subject/topic, learning profile, feedback, escalation, and teacher assistance seed data.
3. Contract defines exercise draft shape, difficulty, subject/topic binding, answer key, explanation, and review state.
4. Contract states AI-generated replies and exercises are drafts only until teacher/admin review.
5. Contract defines persistence, regeneration, accept/reject/archive behavior, and verification priorities.

### Phase 117: Backend Teacher Summary And Exercise Draft APIs

**Goal:** Add backend tutor/admin APIs and storage for teacher summary drafts and bounded exercise drafts using existing AI and learning context foundations.

**Requirement:** AITOOL-02
**Plans:** 1/1 plans complete

**Success Criteria**:
1. Tutor/admin can request summary drafts for visible question/session context only.
2. Tutor/admin can request bounded exercise drafts by student, subject, topic, difficulty, and count.
3. Backend stores draft metadata including status, creator, source context, prompt version, generated timestamp, review timestamp, and linked evidence.
4. Backend supports regenerate, accept, reject, and archive lifecycle operations.
5. Focused tests cover authorization, generation shape, lifecycle transitions, topic binding, and no automatic student delivery.

### Phase 118: Tutor AI Tools And Exercise Draft UI

**Goal:** Expose practical tutor/admin UI for AI summaries, suggested focus, draft explanations, and reviewed exercise draft workflows.

**Requirement:** UI-22
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Tutor session UI shows auto summary, misconception summary, suggested focus, and draft explanation controls.
2. Tutor/admin UI can generate practice exercise drafts from selected student, subject, topic, difficulty, and count context.
3. UI clearly distinguishes AI draft content from sent teacher replies or assigned exercises.
4. UI supports accept, reject, archive, and regenerate states with clear status feedback.
5. Targeted browser verification confirms the tutor/admin workflow is usable.

### Phase 119: Functional Release Gate And AI Tools Audit

**Goal:** Close v3.7 with focused backend/frontend evidence and update Phase 2 gap tracking for AI teacher tools and residual expansion scope.

**Requirement:** VERIFY-20
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Backend and frontend focused quality gates relevant to AI teacher tools pass.
2. Gap audit marks AI teacher tools, automatic summaries, and exercise generation active or closed with residual richer personalization/curriculum scope.
3. Final audit lists remaining Phase 2 product expansions including Stripe/TWINT, full curriculum rollout, production WebSocket infrastructure, push/native/email notifications, mobile/multilingual polish, and support integrations.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AITOOL-01 | Phase 116 | Complete |
| AITOOL-02 | Phase 117 | Complete |
| UI-22 | Phase 118 | Planned |
| VERIFY-20 | Phase 119 | Planned |

---
*Last updated: 2026-06-09 after planning v3.7*
