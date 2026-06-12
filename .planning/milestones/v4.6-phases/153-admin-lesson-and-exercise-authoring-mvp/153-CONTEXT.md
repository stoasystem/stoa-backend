# Phase 153 Context

**Phase:** 153 - Admin Lesson And Exercise Authoring MVP
**Milestone:** v4.6 Rich Curriculum Authoring And Analytics Foundation
**Created:** 2026-06-12
**Status:** Ready for execution

## Source Context

Phase 153 implements the Phase 152 contract:

- `.planning/phases/152-curriculum-authoring-contract-and-qa-workflow/152-CURRICULUM-AUTHORING-CONTRACT.md`
- `.planning/phases/152-curriculum-authoring-contract-and-qa-workflow/152-LEGACY-READINESS.md`

Existing compatibility surfaces:

- `src/stoa/services/curriculum_service.py`
- `src/stoa/routers/practice.py`
- `src/stoa/services/adaptive_learning_service.py`
- `tests/test_curriculum_rollout.py`
- `tests/test_adaptive_learning.py`

## Implementation Boundary

Add a dedicated internal curriculum operations layer. Do not make student/parent curriculum routes read draft/review authoring records.

## Required Behavior

- Admin/tutor/teacher can create drafts, submit review, approve/request changes, and preview unpublished versions.
- Admin can publish, roll back, and archive.
- Publish is compare-and-set guarded by the expected published version.
- Drafts do not write published projections until publish succeeds.
- Archive refuses active assignment references.
- Audit evidence is appended for lifecycle transitions and important refusals.
- Existing curriculum/adaptive compatibility tests remain green.

