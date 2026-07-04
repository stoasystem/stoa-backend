# Phase 235 Plan: Frontend Curriculum Editor And Migration Console

## Goal

Build usable frontend tooling for authorized curriculum operators to edit, validate, review, migrate, and audit curriculum content.

## Work Items

1. Add typed frontend API clients and query keys.
   - Worklist, draft read/patch, validation preview, diff, review actions, publish/rollback/archive, audit.
   - Migration dry-run, apply, evidence read.
   - Capability-aware current-user or operator-capabilities data if not already exposed.

2. Add authorized curriculum operator route.
   - Candidate route: `/admin/curriculum`.
   - Child routes for worklist, editor detail, diff/review, audit, and migration console.
   - Missing-permission state for ordinary teacher/tutor direct navigation.

3. Build editor workbench.
   - Lesson fields: title, objective, description, subject/topic/unit, grade, difficulty, duration, locale.
   - Rich sections: examples, formulas, media references, tags, prerequisites.
   - Exercises: prompt, type, difficulty, order, answer key, hint, explanation, skills.
   - Save draft, validation preview, submit review, approve/request changes.

4. Build diff/review/audit views.
   - Compare draft versus published or selected version.
   - Show validation blockers/warnings.
   - Show bounded audit events.

5. Build migration console.
   - Manifest input/upload.
   - Dry-run summary and row-level issues.
   - Conflict review.
   - Apply confirmation.
   - Evidence references and rollback hints.

6. Add focused e2e.
   - Authorized editor happy path.
   - Validation error path.
   - Diff/review path.
   - Migration dry-run.
   - Migration apply confirmation.
   - Ordinary teacher/tutor unauthorized state.
   - API-error state with no demo fallback.

## Verification

- Frontend lint and build from `/Users/zhdeng/stoa-frontend`.
- Focused Playwright e2e for curriculum editor/migration routes.
- Backend focused compatibility tests if frontend integration reveals contract issues.

## Exit Criteria

- Authorized operators can use the editor and migration console without manual API calls.
- Ordinary teachers/tutors cannot edit through the UI.
- No demo fallback hides curriculum authoring or migration API failures.
