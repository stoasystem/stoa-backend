---
phase: 153
plan: 153-01
subsystem: curriculum-operations
tags:
  - curriculum
  - authoring
  - admin
  - publish
key-files:
  - src/stoa/db/repositories/curriculum_ops_repo.py
  - src/stoa/services/curriculum_ops_service.py
  - src/stoa/routers/admin.py
  - tests/test_curriculum_ops.py
metrics:
  tests_added: 6
---

# Phase 153 Summary

**Phase:** 153 - Admin Lesson And Exercise Authoring MVP
**Status:** Complete
**Completed:** 2026-06-12T11:46:05+02:00

## Completed

- Added `curriculum_ops_repo` for same-table version, pointer, manifest, audit, published projection, worklist, and active-assignment guard access patterns.
- Added `curriculum_ops_service` for draft, review, approve, request-changes, publish, rollback, archive, preview, validation, role, and audit behavior.
- Added admin/tutor/teacher endpoints for draft/review/preview/worklist and admin-only publish/rollback/archive endpoints.
- Added focused lifecycle tests for role guard, draft isolation, publish flow, illegal publish, stale pointer refusal, archive refusal, and rollback.
- Confirmed existing curriculum, adaptive-learning, and admin operations tests still pass.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 153-01 | current phase commit | Implement admin curriculum authoring and publish safety MVP. |

## Deviations

- The first worklist is repository-derived from version rows rather than a separate materialized worklist row family. This keeps the MVP smaller while preserving the service boundary for later materialization.
- Published projection updates are encapsulated in repository helpers; broader DynamoDB transaction hardening can be revisited if live concurrent publishing becomes a real operator workflow.

## Self-Check

PASSED. CURROPS-02 behavior is implemented with focused tests and compatibility coverage.

