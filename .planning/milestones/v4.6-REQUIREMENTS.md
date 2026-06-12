# v4.6 Requirements: Rich Curriculum Authoring And Analytics Foundation

**Status:** Active research-first planning
**Created:** 2026-06-12
**Source:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`, v4.6 research artifacts

## Goal

Turn STOA's curriculum catalog and exercise-bank foundation into an operable authoring, QA, and analytics workflow for internal curriculum improvement.

## Requirements

### CURROPS-01 Curriculum Authoring Contract And QA Workflow

Internal curriculum operators have a precise contract for editing lessons and exercises without breaking published catalog, progress, assignment, or adaptive-memory semantics.

Acceptance criteria:

- Define stable public `lesson_id` / `exercise_id` semantics separately from immutable authoring `version_id` values.
- Define lifecycle states and allowed transitions for curriculum content, QA review outcomes, assignment state, and AI draft acceptance without overloading one generic state machine.
- Define author, reviewer, publisher/admin, tutor, and student-visible permission boundaries.
- Define publish-unit and manifest rules for lesson-plus-exercise bundles, including conditional publish, rollback, archive, and audit requirements.
- Define validation requirements for content completeness, answer keys, hints, difficulty, locale/language metadata, subject/topic bindings, and legacy v3.8 content readiness.
- Require student/parent routes to read published projections only; draft/review preview remains admin/tutor-only.
- Preserve compatibility with existing v3.8 curriculum catalog/progress APIs and v4.0 assignments/adaptive memory.

### CURROPS-02 Admin Lesson And Exercise Authoring MVP

Admins and authorized tutors can create, review, publish, archive, and roll back lesson/exercise content safely.

Acceptance criteria:

- Add dedicated curriculum ops models, repository, and service layers rather than expanding published curriculum read logic directly.
- Add role-guarded admin/tutor endpoints for worklist, create/edit draft, submit review, approve/request changes, publish, archive, rollback, and preview.
- Persist immutable version snapshots, mutable summary/published pointers, append-only audit events, and optional worklist feed rows in the existing DynamoDB table.
- Publish and rollback use compare-and-set semantics and update published projections without changing stable public IDs.
- Student-visible catalog, lesson, exercise, progress, and assignment reads remain stable while draft/review content exists.
- Archive refuses or guards content with active assignments or required historical references unless a safe migration/repoint path exists.
- Focused tests prove legal/illegal transitions, draft isolation, publish idempotency, rollback/archive behavior, audit evidence, and no student/parent draft leakage.

### CURROPS-03 Learning Analytics And Content Quality Signals

Operators can see bounded content-health signals that prioritize curriculum QA without adding a warehouse or exposing student-sensitive details.

Acceptance criteria:

- Record or materialize curriculum analytics signals from practice attempts, wrong answers, lesson completion, assignment outcomes, skips, adaptive memory, and publish/archive lifecycle events.
- Keep analytics keyed by stable public content IDs and immutable version IDs so edits and rollback do not rewrite historical interpretation.
- Provide bounded aggregate views for weak topics, confusing exercises, stale lessons, content coverage gaps, assignment-to-content feedback, and high-impact review priorities.
- Segment metrics by source type, such as catalog self-practice, reviewed assignment, AI-draft assignment, skip, retry, and lesson completion.
- Avoid request-time full table scans by using same-table aggregate rows, bounded windows, pagination, and recompute/backfill helpers where needed.
- Preserve role boundaries with aggregate-only responses, cohort thresholds where relevant, and no raw student answers or answer-key leaks.

### VERIFY-29 v4.6 Curriculum Operations Release Gate

v4.6 closes with verification that curriculum authoring and analytics are safe for local backend release.

Acceptance criteria:

- Focused backend checks pass for authoring lifecycle, draft isolation, publish/rollback/archive safety, and analytics aggregation.
- Existing student/parent/tutor curriculum, practice, progress, and adaptive assignment flows remain compatible with published projections.
- Release evidence captures role boundaries, privacy controls, publish idempotency, rollback correctness, archive refusal/guard behavior, analytics stability, and no draft leakage.
- Requirements, roadmap, state, feature-gap audit, and remaining-feature queue reflect completed v4.6 scope and deferred broader CMS/BI/automation work.
- Recommend whether the next milestone should target adaptive sequencing, native/mobile expansion, notification production rollout, payment activation, support provider expansion, or deeper analytics.

## Future Requirements

- Full content management system.
- Collaborative authoring and comments.
- Automated content generation into published catalog without review.
- Long-term adaptive sequencing across all curriculum content.
- Full BI/data warehouse integration.
- Workflow engine, broad search stack, or warehouse-backed analytics platform.
- Rich WYSIWYG authoring and collaborative editing.
- Staged rollout/experimentation platform beyond simple preview/publish safety.

## Out of Scope

- Publishing AI-generated exercises without review.
- Replacing existing curriculum catalog/progress APIs wholesale.
- Broad compliance analytics unrelated to learning operations.
- Native mobile authoring.
- Large-scale data warehouse work before operational analytics prove value.
- Hard deletion of published lessons/exercises.
- Per-student surveillance dashboards for curriculum authors.
- Generic report-builder or BI dashboard scope.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURROPS-01 | Phase 152 | Planned |
| CURROPS-02 | Phase 153 | Planned |
| CURROPS-03 | Phase 154 | Planned |
| VERIFY-29 | Phase 155 | Planned |
