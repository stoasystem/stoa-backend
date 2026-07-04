# Phase 236 Plan: v5.12 Curriculum Buildout Release Gate

## Goal

Close v5.12 with evidence that curriculum editor and migration tooling are implemented and ready for internal use.

## Work Items

1. Run backend focused tests.
   - Special curriculum authorization.
   - Editor patch/update.
   - Validation preview.
   - Diff and audit.
   - Migration dry-run/apply/evidence.
   - Published student/parent read compatibility.

2. Run frontend checks.
   - Lint.
   - Build.
   - Focused Playwright e2e for editor and migration console.
   - Missing-permission state for ordinary teacher/tutor.

3. Write release evidence.
   - Backend command evidence.
   - Frontend command evidence.
   - Authorization matrix.
   - Migration dry-run/apply behavior summary.
   - Known limitations and deferred items.

4. Update docs.
   - `ROADMAP.md`, `REQUIREMENTS.md`, `STATE.md`, `MILESTONES.md`, `PROJECT.md`, `NEXT-MILESTONES.md`.
   - `STOA_DOCS_FEATURE_GAP_AUDIT.md` and `STOA_DOCS_REMAINING_FEATURES.md`.
   - v5.12 milestone audit.

5. Recommend next milestone.
   - Separate externally blocked activation from internally buildable product work.
   - Candidate options: content-quality dashboards, usage summary visual polish, warehouse/BI, native app, or external activation when unblocked.

## Verification

- Backend focused pytest passes or failures are isolated with a clear non-v5.12 reason.
- Targeted Ruff passes.
- Frontend lint/build/e2e passes or environment blockers are documented.
- Docs and state accurately reflect completion.

## Exit Criteria

- v5.12 can be marked complete only if authorized curriculum operators can edit/review/migrate through implemented workflows and ordinary teachers/tutors cannot edit without special authorization.
