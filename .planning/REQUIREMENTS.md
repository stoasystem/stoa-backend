# Requirements: v5.3 Controlled Assignment Automation

**Milestone:** v5.3
**Status:** Active planning
**Created:** 2026-06-15

## Goal

Use STOA's reviewed AI drafts, adaptive sequencing recommendations, assignment lifecycle, and warehouse-ready analytics foundations to support controlled assignment automation. v5.3 focuses on policy-bounded candidate batching, reviewed assignment creation, optional delivery states, operator review, and family-visible explanations.

This is an internal development milestone. Prioritize functional learning product capability. Keep checks focused on automation behavior, duplicate prevention, assignment lifecycle correctness, role-visible explanation quality, and operator evidence.

## Requirements

### AUTOASSIGN-01 Controlled Automation Contract

Implementers have a concrete contract before autonomous tutoring or assignment automation expands.

Acceptance criteria:

- Contract identifies backend, frontend, tutor/admin, student/parent, analytics, and release ownership boundaries.
- Contract defines autonomy levels: off, suggest-only, tutor-approved batch, auto-create reviewed, and future auto-deliver.
- Contract limits eligible sources to accepted AI practice drafts, published curriculum exercises, and v5.2 recommendation candidates.
- Contract defines duplicate, stale, completed, archived, rolled-back, unpublished, low-confidence, and paused-policy refusal rules.
- Contract defines rollout states, release evidence, and deferred fully autonomous tutoring scope.

### AUTOASSIGN-02 Automation Policy And Candidate Batch Planner

Tutors/admins can create policy-bounded candidate batches from sequencing recommendations without immediately creating student work.

Acceptance criteria:

- Policy settings cover student/cohort scope, subject/topic filters, source types, max assignment count, confidence threshold, freshness, due-window defaults, and pause state.
- Planner selects and refuses candidates with clear source, confidence, rationale, duplicate reason, review status, and expected student impact.
- Planner uses assignment outcomes to avoid immediate repeats and prioritize remediation when useful.
- Batch response shape is stable for tutor/admin review and frontend preview.
- Tests cover policy filtering, dedupe/refusal, stale candidates, accepted-draft eligibility, low-confidence refusal, and empty states.

### AUTOASSIGN-03 Controlled Assignment Creation And Delivery Worker

Approved batches can create assignments idempotently and optionally move them into delivery-visible states.

Acceptance criteria:

- Approved batches create reviewed assignments with source attribution, policy metadata, actor, batch ID, and result evidence.
- Worker is idempotent by batch/candidate/source and returns per-item created, assigned, delivered, skipped, refused, duplicate, or failed results.
- Student-visible assignments do not expose answer keys, and parent-visible data remains summary-safe.
- Assignment outcome feedback and analytics can attribute work to automation policy and batch metadata.
- Tests cover idempotency, partial batch results, duplicate prevention, source attribution, student/parent visibility, and role-specific payload shape.

### AUTOASSIGN-04 Tutor/Admin Review UX Contracts And Family Visibility

Automation is reviewable and explainable before broader rollout.

Acceptance criteria:

- Tutor/admin review contract covers preview, approve, reject, override, pause, resume, result history, and intervention views.
- Parent/student explanations show why assignment work appeared, what it targets, and whether it was tutor-approved or automated.
- Operator analytics expose automation coverage, accepted/refused candidates, delivery results, skips/completions, and intervention opportunities.
- Frontend/API handoff documents routes, payloads, empty states, error states, and no-automation behavior.
- Tests or focused checks cover route contracts, explanation shape, no-automation empty states, and operator summary shape.

### VERIFY-36 v5.3 Controlled Assignment Automation Release Gate

v5.3 closes with controlled assignment automation evidence.

Acceptance criteria:

- Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
- Automation policy, candidate batching, assignment creation/delivery, review UX contracts, family visibility, and docs are verified.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.3 work.
- Final audit records rollout state: contract-ready, planner-ready, automation-ready, delivery-ready, blocked, or deferred.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Fully autonomous tutoring decisions without tutor/admin approval.
- Automatic generation and publication of new AI assignments without review.
- Live notification/push delivery for automated assignments.
- Frontend rich curriculum editor implementation and production content import.
- Final live payment/support external activation when prerequisites are ready.
- Native app implementation and app-store release.

## Out of Scope

- Unreviewed AI-generated assignment publication.
- Replacing teacher/tutor judgment for high-stakes intervention decisions.
- Live payment/support provider activation.
- Native app implementation.
- Live warehouse/BI deployment.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTOASSIGN-01 | Phase 186 | Complete |
| AUTOASSIGN-02 | Phase 187 | Complete |
| AUTOASSIGN-03 | Phase 188 | Complete |
| AUTOASSIGN-04 | Phase 189 | Complete |
| VERIFY-36 | Phase 190 | Complete |
