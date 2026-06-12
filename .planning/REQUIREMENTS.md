# v4.6 Requirements: Rich Curriculum Authoring And Analytics Foundation

**Status:** Active research-first planning
**Created:** 2026-06-12
**Source:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`, v4.6 research artifacts

## Goal

Turn STOA's curriculum catalog and exercise-bank foundation into an operable authoring, QA, and analytics workflow for internal curriculum improvement.

## Requirements

### CURROPS-01 Curriculum Authoring Contract And QA Workflow

- Define authoring lifecycle states for lessons, exercises, tags, subject/topic metadata, and review outcomes.
- Define role responsibilities for author, reviewer, tutor/admin operator, and student-visible publication.
- Define validation requirements for curriculum content completeness, language coverage, answer keys, hints, and difficulty metadata.
- Preserve compatibility with existing v3.8 curriculum catalog/progress APIs.

### CURROPS-02 Admin Lesson And Exercise Authoring MVP

- Add admin/tutor authoring workflows for lesson and exercise creation or editing.
- Support draft, review, publish, archive, and rollback metadata.
- Keep student-visible catalog stable while draft content is under review.
- Add focused tests for lifecycle transitions and published-content visibility.

### CURROPS-03 Learning Analytics And Content Quality Signals

- Aggregate content quality signals from practice completion, skips, wrong answers, assignment outcomes, tutor feedback, and adaptive memory.
- Expose admin/tutor analytics for weak topics, confusing exercises, stale lessons, and high-impact content gaps.
- Keep analytics actionable and bounded before broader data warehouse or BI automation.
- Preserve role boundaries and avoid exposing individual student-sensitive detail in aggregate views.

### VERIFY-29 v4.6 Curriculum Operations Release Gate

- Run focused backend/frontend checks for authoring, lifecycle, and analytics behavior.
- Capture evidence for draft-to-publish behavior, rollback/archive safety, and analytics correctness.
- Update roadmap, state, feature-gap audit, and remaining-feature queue after v4.6.
- Recommend whether the next milestone should be adaptive sequencing, native/mobile expansion, notification production rollout, or deeper analytics.

## Future Requirements

- Full content management system.
- Collaborative authoring and comments.
- Automated content generation into published catalog without review.
- Long-term adaptive sequencing across all curriculum content.
- Full BI/data warehouse integration.

## Out of Scope

- Publishing AI-generated exercises without review.
- Replacing existing curriculum catalog/progress APIs wholesale.
- Broad compliance analytics unrelated to learning operations.
- Native mobile authoring.
- Large-scale data warehouse work before operational analytics prove value.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURROPS-01 | Phase 152 | Planned |
| CURROPS-02 | Phase 153 | Planned |
| CURROPS-03 | Phase 154 | Planned |
| VERIFY-29 | Phase 155 | Planned |
