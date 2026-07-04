# Phase 234 Plan: Backend Content Migration Service And APIs

## Goal

Implement manifest-driven curriculum content migration so operators can validate and apply content changes without manual database writes.

## Work Items

1. Define migration manifest schema.
   - Source metadata, source ID, source version, operator note.
   - Subject/topic/unit mapping.
   - Public lesson IDs and optional target version IDs.
   - Locale/language metadata.
   - Lesson content and exercise rows.
   - Publish intent, dependency order, and rollback hints.

2. Add migration service.
   - Parse and normalize manifest input.
   - Reuse Phase 233 validation logic.
   - Detect create/update/skip/conflict/error rows.
   - Generate stable preview IDs or dry-run tokens for apply confirmation.

3. Add dry-run API.
   - Endpoint target: `POST /admin/curriculum/migrations/dry-run`.
   - Requires migration operator or publisher capability for access.
   - Returns summary counts, row-level actions, validation issues, conflicts, and publish readiness.
   - Writes no curriculum versions, pointers, or projections.

4. Add apply API.
   - Endpoint target: `POST /admin/curriculum/migrations/{migration_id}/apply` or confirmed apply by dry-run token.
   - Requires `migration_operator` plus explicit confirmation token.
   - Writes curriculum versions and optional published pointers.
   - Writes migration evidence, audit events, rollback metadata, and manifest references.

5. Add migration evidence read API.
   - Endpoint target: `GET /admin/curriculum/migrations/{migration_id}`.
   - Shows summary, row results, evidence references, applied pointers, conflicts, and rollback hints.

6. Add focused backend tests.
   - Dry-run no mutation.
   - Apply with confirmation.
   - Missing authorization.
   - Ordinary teacher/tutor refusal.
   - Conflict handling.
   - Validation failures.
   - Idempotent retry behavior.
   - Evidence and audit records.
   - No student/parent draft leakage.

## Verification

- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_curriculum_migration.py -q`
- Targeted Ruff on changed backend source/tests.

## Exit Criteria

- Operators have a repeatable backend migration path.
- Phase 235 can build a migration console from stable API responses.
- Manual DB writes are no longer the expected path for production curriculum imports.
