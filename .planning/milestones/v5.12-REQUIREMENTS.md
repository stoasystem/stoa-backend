# Requirements: v5.12 Curriculum Editor And Content Migration Buildout

**Milestone:** v5.12
**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.11 Additional Usage Ledger Coverage

## Purpose

Implement the buildable curriculum tooling gaps that v5.1 intentionally left as readiness/deferred scope: rich editor backend/frontend functionality for specially authorized curriculum operators, production content migration service/API/UI, validation/diff/audit evidence, and operator release readiness.

This is an internal development milestone. Prioritize usable curriculum operations over broad unrelated security/compliance testing. Keep checks focused on authoring correctness, content integrity, migration safety, published-read compatibility, and frontend usability.

## Requirements

### CURRBUILD-01 Curriculum Buildout Reality Refresh And Contract

Status: Complete 2026-07-05.

Acceptance criteria:

- v5.1 deferred items are mapped to current backend and frontend files.
- Existing backend authoring, analytics, practice, and adaptive routes are documented as preserved foundations.
- Missing backend APIs are identified: special curriculum authorization, draft patch/update, validation preview, diff, audit-read, migration dry-run/apply, evidence, and rollback metadata.
- Missing frontend surfaces are identified: authorized editor workbench, validation/diff/review UI, migration console, typed clients, hooks, routes, and e2e.
- Remaining-feature docs are corrected so v5.10 and v5.11 are no longer listed as remaining work.

### CURRBUILD-02 Backend Special Authorization Editor Patch Validation Diff And Audit APIs

Acceptance criteria:

- Backend exposes safe draft patch/update behavior for structured lesson and exercise content only to users with backend-granted `curriculum_author` capability.
- Existing ordinary teacher/tutor users cannot create, edit, review, publish, rollback, or archive curriculum unless the backend grants explicit curriculum capability.
- Validation preview returns field-level issues, blocking/warning severity, publish readiness, and remediation hints.
- Diff endpoint compares draft/current/published/rollback candidates without leaking unrelated data.
- Curriculum audit-read endpoint returns bounded version lifecycle and review events only to authorized curriculum reviewers/publishers.
- Tests cover legal edits, missing authorization, ordinary teacher/tutor refusal, validation failures, draft isolation, diff output, audit output, and published-read compatibility.

### CURRBUILD-03 Backend Content Migration Service And APIs

Acceptance criteria:

- Migration manifest schema covers source metadata, subject/topic mapping, public/version IDs, locale metadata, lessons, exercises, dependencies, and operator notes.
- Dry-run API validates manifest input and reports create/update/skip/conflict/error rows without mutation.
- Apply API requires `migration_operator` or equivalent publisher authorization plus explicit confirmation, then writes content versions, optional published pointers, evidence records, and audit references.
- Conflict and rollback metadata are available for operator review and follow-up.
- Tests cover dry-run, apply, missing authorization, ordinary teacher/tutor refusal, idempotency, validation failure, conflict handling, evidence, rollback metadata, and no student/parent draft leakage.

### CURRBUILD-04 Frontend Curriculum Editor And Migration Console

Acceptance criteria:

- Frontend clients, query keys, hooks, and routes cover editor worklist, draft edit, validation preview, diff, review actions, audit view, migration dry-run, and migration apply only for users with backend-granted curriculum capabilities.
- Editor supports lesson sections, objectives, examples, formulas, media references, exercise blocks, answer keys, hints, explanations, tags, prerequisites, estimated duration, and locale metadata.
- Migration console supports manifest input/upload, dry-run summary, row-level validation/conflict output, apply confirmation, evidence references, and rollback hints.
- Loading, empty, invalid, conflict, partial-success, unauthorized, missing-permission, and API-error states are implemented with no demo fallback.
- Focused e2e covers editor happy path, validation errors, diff/review, migration dry-run, migration apply confirmation, ordinary teacher/tutor unauthorized states, and API-error states.

### VERIFY-45 v5.12 Curriculum Buildout Release Gate

Acceptance criteria:

- Focused backend tests pass for special curriculum authorization, editor APIs, migration APIs, published-read compatibility, and authoring audit behavior.
- Frontend lint/build and focused e2e pass for curriculum editor and migration console workflows.
- Docs, roadmap, state, milestone snapshots, and `stoa_docs` gap audit are updated.
- Release evidence records completed implementation, deferred external activation, and any remaining editor/migration limitations.
- Next milestone recommendation is explicit and separates new functional, safety, and stability buildouts from externally blocked activation work.

## Out of Scope

- Native iOS/Android app implementation.
- Live Stripe/TWINT activation or customer charging rollout.
- Live notification provider activation, APNS/FCM production rollout, or email digest scheduling.
- Warehouse/BI deployment.
- Broad collaborative editing, comments, or a full CMS beyond the internal editor/migration workflows.
- Unreviewed AI publication directly to students.
- Production content source import from an unapproved or unavailable external source.

## Future Milestones

- **v5.13 Payment And Entitlement Production Completion**: make paid access actually work end to end with provider callbacks, entitlement reconciliation, user-visible state, admin support evidence, refunds/invoices where applicable, and release gates.
- **v5.14 Verification And Login Reliability**: make email verification and login-code behavior dependable, observable, rate-limited, and supportable across registration, resend, confirmation, login, and account activation edge cases.
- **v5.15 Usage, Quota, And Product Stability**: make usage accounting trustworthy across real student flows, reconcile quota/ledger drift, expose support-safe usage explanations, and add health/smoke/regression gates for core flows.
- External activation milestones remain separate when live provider credentials and rollout approvals unblock.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRBUILD-01 | Phase 232 | Complete |
| CURRBUILD-02 | Phase 233 | Complete |
| CURRBUILD-03 | Phase 234 | Planned |
| CURRBUILD-04 | Phase 235 | Planned |
| VERIFY-45 | Phase 236 | Planned |
