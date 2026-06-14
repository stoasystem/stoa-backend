# Requirements: v5.1 Rich Curriculum Editor And Production Content Migration

**Milestone:** v5.1
**Status:** Active planning
**Created:** 2026-06-14

## Goal

Move the v3.8 curriculum catalog and v4.6 authoring/analytics foundation into product-ready curriculum operations: rich editor UX contract, production content migration pipeline, reviewed/generated exercise assignment readiness, adaptive sequencing readiness, and release evidence.

This is an internal development milestone. Prioritize functional curriculum tooling and migration readiness. Keep checks focused on content integrity, authoring workflow correctness, migration validation, and assignment behavior; avoid broad unrelated security/compliance work.

## Requirements

### CURRICULUMXP-01 Rich Curriculum Editor And Migration Contract

Implementers have a concrete v5.1 contract before editor UI or content migration work expands.

Acceptance criteria:

- Contract identifies backend, frontend, content, curriculum QA, and release ownership boundaries.
- Contract defines rich lesson/exercise editing expectations, formula/media/code-block handling, preview behavior, validation, and review lifecycle.
- Contract defines production content import/export, migration manifest, dry-run, validation, rollback, and publish sequencing.
- Contract defines assignment automation and adaptive sequencing readiness using existing curriculum, AI draft, memory, and analytics signals.
- Contract defines release evidence and deferred scope for frontend implementation, native app consumption, and warehouse analytics.

### CURRICULUMXP-02 Admin Rich Curriculum Editor UI And API Readiness

Admin/tutor curriculum authors have a usable editor handoff and backend contract for rich lesson/exercise content.

Acceptance criteria:

- Rich editor handoff defines sections, objectives, examples, formulas, media references, exercise blocks, answer keys, hints, explanations, tags, prerequisites, and estimated duration.
- Backend API readiness covers draft create/update, preview, validation, submit review, approve/request changes, publish, rollback, archive, and audit behavior.
- Frontend handoff identifies `/Users/zhdeng/stoa-frontend` implementation points for editor layout, review queue, diff/preview, and validation errors.
- Existing published-only student/parent reads remain stable while authoring drafts evolve.
- Focused checks cover route contract stability and content validation behavior when backend changes are needed.

### CURRICULUMXP-03 Production Content Migration Pipeline And Validation

Curriculum content can move from source material into STOA-managed curriculum records with repeatable validation.

Acceptance criteria:

- Migration pipeline contract supports source manifests, subject/topic mapping, public IDs, version IDs, locale metadata, exercise mapping, and dependency ordering.
- Dry-run mode reports created/updated/skipped/conflicted rows, validation errors, and publish readiness without mutating production content.
- Apply mode is gated by explicit operator approval and writes migration evidence, version metadata, and audit records.
- Rollback/undo path is defined for failed or incorrect migrations without breaking existing published content.
- Tests or focused checks cover dry-run, conflict detection, validation failures, apply evidence, and rollback metadata.

### CURRICULUMXP-04 Assignment Automation And Adaptive Sequencing Readiness

Reviewed curriculum and generated exercises are ready for controlled assignment automation and future adaptive sequencing.

Acceptance criteria:

- Assignment automation readiness defines when reviewed/generated exercises may be proposed, assigned, skipped, completed, or archived.
- Sequencing signals use curriculum progress, mistakes, AI draft outcomes, assignment outcomes, content-quality analytics, and tutor review state.
- Student/parent/tutor visibility boundaries are documented for automated recommendations versus assigned work.
- Automation remains review-gated where required and does not bypass tutor/admin approval for generated content.
- Tests or focused checks cover assignment eligibility, duplicate prevention, progression signals, and archived/rolled-back content behavior.

### VERIFY-34 v5.1 Curriculum Product Release Gate And Handoff

v5.1 closes with curriculum product readiness evidence and updated remaining-feature planning.

Acceptance criteria:

- Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
- Rich editor handoff, production migration pipeline, validation, rollback, assignment readiness, and adaptive sequencing readiness are verified.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.1 work.
- Final audit records rollout state: contract-ready, editor-ready, migration-ready, assignment-ready, blocked, or deferred.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Frontend rich editor implementation if not completed in this backend planning cycle.
- Production content import from approved source material.
- Warehouse-backed analytics and BI.
- Fully autonomous tutoring and adaptive sequencing.
- Final live payment/support external activation when prerequisites are ready.

## Out of Scope

- Broad rewrite of the curriculum data model without migration need.
- Unreviewed AI publication to students.
- Warehouse/BI implementation unless selected later.
- Final payment/support provider external activation.
- Full native app release.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRICULUMXP-01 | Phase 176 | Planned |
| CURRICULUMXP-02 | Phase 177 | Planned |
| CURRICULUMXP-03 | Phase 178 | Planned |
| CURRICULUMXP-04 | Phase 179 | Planned |
| VERIFY-34 | Phase 180 | Planned |
