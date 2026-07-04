# Phase 233 Plan: Backend Special Authorization And Editor APIs

## Goal

Implement the backend permission model and editor API surface needed for a real curriculum editor.

## Work Items

1. Add a curriculum capability resolver.
   - Source capabilities from backend-controlled user/profile metadata.
   - Support `curriculum_author`, `curriculum_reviewer`, `curriculum_publisher`, and future `migration_operator`.
   - Return consistent `403` errors for missing capabilities.

2. Replace broad authoring role checks.
   - Replace `AUTHOR_ROLES = {"admin", "tutor", "teacher"}` style checks with capability checks.
   - Keep read-only analytics/worklist access separate from edit/review/publish permissions.
   - Add tests proving ordinary teacher/tutor accounts cannot create, patch, approve, publish, rollback, archive, or read restricted audit without capability.

3. Add draft patch/update support.
   - Endpoint target: `PATCH /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}`.
   - Support structured lesson fields, exercise add/update/remove/reorder, locale metadata, tags, prerequisites, estimated duration, hints, explanations, and answer keys.
   - Preserve immutable version identity and draft isolation.

4. Add structured validation preview.
   - Endpoint target: `POST /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/validation-preview`.
   - Return `status`, `publishReady`, `issues[]`, severity, field path, message, and remediation hint.
   - Do not mutate state.

5. Add content diff API.
   - Endpoint target: `GET /admin/curriculum/lessons/{public_lesson_id}/diff`.
   - Compare draft/current/published/rollback candidate by version IDs.
   - Return bounded structural diffs for lesson fields and exercise rows without unrelated data.

6. Add bounded audit-read API.
   - Endpoint target: `GET /admin/curriculum/lessons/{public_lesson_id}/audit`.
   - Return version lifecycle events with actor ID/role/capability, operation, from/to state, reason, timestamps, and pagination.
   - Keep scope limited to one public lesson/content item.

7. Add focused backend tests.
   - Capability resolver and ordinary teacher/tutor refusal.
   - Authorized author patch behavior.
   - Reviewer diff/audit access.
   - Publisher-only publish/rollback/archive.
   - Validation preview and published-read compatibility.

## Verification

- `.venv/bin/python -m pytest tests/test_curriculum_ops.py -q`
- Targeted Ruff on changed backend source/tests.

## Exit Criteria

- Backend mutation routes no longer grant edit powers to all teachers/tutors.
- Editor APIs are sufficient for Phase 235 frontend implementation.
- Existing student/parent published curriculum reads remain compatible.
