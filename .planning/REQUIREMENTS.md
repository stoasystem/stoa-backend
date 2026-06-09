# Requirements: v3.8 Full Curriculum Rollout

**Milestone:** v3.8
**Status:** Active
**Created:** 2026-06-09

## Goal

Turn the v3.4 subject/topic foundation and v3.7 exercise draft foundation into a usable full curriculum rollout for math, physics, German, and English. This milestone focuses on curriculum structure, lesson/exercise bank coverage, student/parent curriculum UX, and tutor/admin visibility.

## Requirements

### CURRIC-01 Full Curriculum Rollout Contract And Content Model

Implementers have a precise curriculum rollout contract before backend and frontend changes.

Acceptance criteria:

- Contract defines curriculum hierarchy: subject, grade/band, unit, topic, lesson, exercise, assessment/checkpoint, and rollout state.
- Contract defines minimum content fields for lessons and exercises, including title, objective, explanation, examples, difficulty, estimated time, answer key, and topic binding.
- Contract defines supported subjects for rollout: math, physics, German, and English, with language and grade-level metadata.
- Contract defines content source and review states: seed, draft, reviewed, active, archived.
- Contract defines migration/backfill behavior from existing practice subjects/topics/lessons/challenges without breaking current practice routes.

### CURRIC-02 Backend Curriculum Catalog And Exercise Bank APIs

Backend exposes curriculum catalog and exercise bank data through real APIs.

Acceptance criteria:

- Student/tutor/admin can list curriculum subjects, units, topics, lessons, and exercises with rollout-aware filters.
- Backend supports curriculum content seed/backfill from existing practice data and new curriculum metadata.
- Backend preserves existing practice progress, mistake, lesson completion, and challenge attempt behavior.
- Backend can return lesson detail with explanation, examples, exercises, answer keys where authorized, and next-step metadata.
- Focused tests cover catalog shape, subject/grade/topic filtering, exercise bank shape, progress compatibility, and inactive/archived content exclusion.

### UI-23 Student/Parent Curriculum UX And Tutor Signals

Frontend exposes the curriculum rollout as usable product surfaces.

Acceptance criteria:

- Student practice/curriculum UI shows subject, unit, topic, lesson, exercise, progress, and next-step states for rolled-out subjects.
- Parent child profile/report surfaces show curriculum progress and weak curriculum areas without claiming unsupported subjects are complete.
- Tutor/admin surfaces can inspect a student's curriculum context while answering questions or reviewing AI exercise drafts.
- UI distinguishes active curriculum content from draft/preview/archived content.
- Targeted browser verification confirms core curriculum navigation and progress states.

### VERIFY-21 Functional Release Gate And Curriculum Audit

v3.8 closes with functional evidence and updated `stoa_docs` gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to curriculum rollout pass.
- Gap audit marks full multi-subject curriculum rollout active or closed and records residual adaptive sequencing/automatic assignment scope.
- Final audit lists remaining Phase 2 product expansions: payment-provider integration, long-term personalization, production WebSocket infrastructure, push/native/email notifications, mobile/multilingual polish, and support integrations.

## Future Requirements

- Long-term adaptive sequencing beyond current progress and weak-topic signals.
- Automatic student assignment/delivery of generated exercises.
- Full content authoring workflow with rich editor, approval queues, and versioned publishing.
- Payment-provider implementation.
- Push/native/email notification delivery.
- Full mobile/multilingual polish.

## Out of Scope

- Automatically assigning generated exercises to students.
- Full adaptive tutoring engine.
- Payment-provider implementation.
- Production WebSocket infrastructure rollout.
- Broad security/compliance program beyond required authorization and functional correctness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRIC-01 | Phase 120 | Complete |
| CURRIC-02 | Phase 121 | Complete |
| UI-23 | Phase 122 | Complete |
| VERIFY-21 | Phase 123 | Planned |
