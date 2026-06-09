# Requirements: v3.7 AI Teacher Tools And Exercise Generation

**Milestone:** v3.7
**Status:** Active
**Created:** 2026-06-09

## Goal

Build AI teacher tools on top of the existing question, teacher reply, learning profile, topic seed, notification, and realtime foundations. This milestone focuses on practical teacher-facing productivity: automatic session summaries, suggested teaching focus, draft follow-up explanations, and bounded practice exercise generation.

## Requirements

### AITOOL-01 AI Teacher Tools Contract And Generation Model

Implementers have a precise contract for teacher summaries, suggested focus, draft follow-up explanations, and bounded exercise generation.

Acceptance criteria:

- Contract defines tool outputs: session summary, misconception summary, suggested teaching focus, draft explanation, and generated practice exercises.
- Contract defines input sources: question content, AI answer, teacher replies, conversation context, subject/topic taxonomy, learning profile seeds, feedback, and escalation history.
- Contract defines exercise output shape, difficulty levels, subject/topic binding, answer key, explanation, and review state.
- Contract defines human-in-the-loop workflow: AI drafts are never automatically sent to students without teacher/admin action.
- Contract defines persistence and regeneration behavior for drafts, summaries, and exercises.

### AITOOL-02 Backend Teacher Summary And Exercise Draft APIs

Backend supports teacher summary and practice exercise draft generation.

Acceptance criteria:

- Tutor/admin can request a summary draft for visible question/session context.
- Tutor/admin can request bounded exercise drafts by student, subject, topic, difficulty, and count.
- Backend stores generated drafts with status, creator, source context, prompt version, generated_at, reviewed_at, accepted/rejected state, and optional linked question/profile evidence.
- Backend supports regenerate, accept, reject, and archive operations for drafts.
- Focused tests cover authorization, generation shape, draft lifecycle, topic binding, and no automatic student delivery.

### UI-22 Tutor AI Tools And Exercise Draft UI

Frontend exposes practical AI teacher tools for tutors/admins.

Acceptance criteria:

- Tutor session UI shows auto summary, misconception summary, suggested focus, and draft explanation controls.
- Tutor/admin UI supports generating practice exercise drafts from selected subject/topic/student context.
- UI clearly distinguishes AI draft content from sent teacher replies or assigned exercises.
- UI supports accept/reject/archive/regenerate states.
- Targeted browser verification confirms the workflow is usable.

### VERIFY-20 v3.7 Functional Release Gate And AI Tools Audit

v3.7 closes with functional evidence and updated Phase 2 gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to AI teacher tools pass.
- Gap audit marks AI teacher tools / automatic summaries / exercise generation as active or closed and records residual richer personalization/curriculum scope.
- Final audit lists remaining Phase 2 product expansions: Stripe/TWINT, full curriculum rollout, production WebSocket infrastructure live rollout, push/native/email notifications, mobile/multilingual polish, and support integrations.

## Future Requirements

- Student-facing automatic assignment/delivery of generated exercises.
- Full curriculum-aligned exercise banks.
- Long-term personalization beyond current learning profile seeds.
- Payment-provider implementation.
- Push/native/email notification delivery.
- Full mobile/multilingual polish.

## Out of Scope

- Automatically sending AI-generated replies to students.
- Automatically assigning generated exercises without teacher/admin review.
- Full curriculum content authoring.
- Payment-provider implementation.
- Broad security/compliance program beyond required authorization and functional correctness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AITOOL-01 | Phase 116 | Complete |
| AITOOL-02 | Phase 117 | Complete |
| UI-22 | Phase 118 | Planned |
| VERIFY-20 | Phase 119 | Planned |
