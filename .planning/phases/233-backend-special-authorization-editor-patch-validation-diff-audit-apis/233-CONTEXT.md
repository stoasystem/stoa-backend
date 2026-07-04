---
phase: 233
name: Backend Special Authorization Editor Patch Validation Diff And Audit APIs
status: planned
created: 2026-07-05
---

# Phase 233 Context: Backend Special Authorization And Editor APIs

## Milestone

v5.12 Curriculum Editor And Content Migration Buildout

## Why This Phase Exists

The existing curriculum authoring foundation is role-guarded with broad `admin`, `tutor`, and `teacher` access. That is too permissive for real curriculum editing. v5.12 must make curriculum editing a backend-granted capability before adding richer editor APIs.

Phase 233 is the backend contract and implementation phase that makes the frontend editor possible without giving every teacher/tutor edit permission.

## Current Backend Reality

- `curriculum_ops_service.AUTHOR_ROLES = {"admin", "tutor", "teacher"}` currently allows broad teacher/tutor authoring.
- Existing routes under `/admin/curriculum/...` support draft create, preview, submit review, approve/request changes, publish, rollback, archive, and worklist.
- Existing validation is exception-only and not shaped as a reusable validation preview.
- Existing preview returns one version, but there is no structured diff endpoint.
- `curriculum_ops_repo.list_audit_events` exists, but there is no dedicated bounded audit-read API for the editor.
- Existing tests prove lifecycle and role guard behavior, but not special capability authorization.

## Required Authorization Model

Backend should recognize explicit curriculum capabilities from user profile metadata or equivalent backend-controlled assignment:

- `curriculum_author`: create/update drafts, request validation, submit review.
- `curriculum_reviewer`: inspect drafts, read diffs/audit, approve, request changes.
- `curriculum_publisher`: publish, rollback, archive.
- `migration_operator`: dry-run/apply migration workflows in Phase 234.

Admins should not automatically bypass every curriculum edit action unless they also have an explicit curriculum capability or a documented backend superuser override. Ordinary teachers/tutors must receive `403` for editor mutation routes without granted capability.

## Boundaries

- Do not change student/parent published curriculum reads.
- Do not implement migration dry-run/apply in this phase; Phase 234 owns migration service/API.
- Do not implement frontend pages in this phase; Phase 235 owns frontend tooling.
