# Requirements: v4.0 Adaptive Learning Memory And Assignment

**Milestone:** v4.0
**Status:** Complete locally
**Created:** 2026-06-10

## Goal

Turn learning profile seeds, curriculum progress, question history, AI teacher drafts, and weak-topic evidence into durable student memory and teacher-reviewed assignment workflows. This milestone focuses on product functionality: adaptive memory records, next-practice recommendations, reviewed exercise assignment, student/tutor UX, and parent progress signals.

## Requirements

### ADAPT-01 Adaptive Learning Memory And Assignment Contract

Implementers have a concrete product and data contract before backend/frontend changes.

Acceptance criteria:

- Contract defines durable learning memory fields: strengths, weak topics, recent activity, mastered concepts, struggling concepts, preferred explanation style, curriculum progress, assignment history, and freshness.
- Contract defines memory inputs from questions, feedback, teacher replies, curriculum progress, exercise attempts, AI teacher drafts, and weekly report signals.
- Contract defines reviewed assignment lifecycle: draft, recommended, assigned, started, completed, skipped, archived.
- Contract defines recommendation behavior for next-practice suggestions without claiming fully autonomous tutoring decisions.
- Contract defines parent/tutor/student visibility boundaries and stale data behavior.

### ADAPT-02 Backend Learning Memory And Reviewed Assignment APIs

Backend supports durable student memory, next-practice recommendations, and reviewed assignments.

Acceptance criteria:

- Backend aggregates and stores learning memory snapshots per student and subject/topic.
- Backend exposes student/tutor/parent-readable learning memory summaries with role-appropriate fields.
- Tutor/admin can create reviewed assignments from curriculum exercises or AI exercise drafts.
- Student can list, start, complete, and skip assigned practice items with progress updates.
- Focused tests cover memory aggregation, role visibility, assignment lifecycle, idempotency, and progress compatibility.

### UI-25 Student/Tutor Assignment UX And Parent Progress Signals

Frontend exposes adaptive learning memory and assignment workflows.

Acceptance criteria:

- Student UI shows next-practice recommendations, assigned exercises, status, and completion feedback.
- Tutor UI shows memory signals and can assign/review exercises from curriculum or AI draft context.
- Parent UI shows progress signals, weak areas, assigned/completed practice, and freshness.
- UI distinguishes recommended practice from teacher/admin-assigned practice.
- Targeted browser verification confirms student/tutor/parent assignment workflows.

### VERIFY-23 v4.0 Functional Release Gate And Personalization Audit

v4.0 closes with functional evidence and updated `stoa_docs` gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to adaptive memory and assignments pass.
- Gap audit marks student memory/personalization and reviewed assignment workflows active or closed and records residual fully autonomous sequencing scope.
- Final audit lists remaining product expansions: mobile/multilingual polish, production notification delivery, live payment rollout, support integrations, rich content authoring, and deeper analytics.

## Future Requirements

- Fully autonomous tutoring and assignment decisions.
- Long-term adaptive sequencing engine beyond reviewed assignments and next-practice recommendations.
- Learning analytics dashboards beyond parent/tutor progress signals.
- Native mobile apps.
- Production notification delivery and support integrations.

## Out of Scope

- Fully autonomous student assignment without teacher/admin review.
- Replacing the existing tutor workflow with an AI-only tutor.
- Broad security/compliance program beyond required authorization and functional correctness.
- Native mobile apps or notification provider rollout.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ADAPT-01 | Phase 128 | Complete |
| ADAPT-02 | Phase 129 | Complete |
| UI-25 | Phase 130 | Complete |
| VERIFY-23 | Phase 131 | Complete |
