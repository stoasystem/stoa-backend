# Roadmap: v5.12 Curriculum Editor And Content Migration Buildout

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.11 Additional Usage Ledger Coverage
**Research:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`, `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Turn the v5.1 curriculum editor and production content migration readiness work into implemented internal tooling: backend draft patch/validation/diff/migration APIs, frontend authorized-curriculum-operator authoring UI, migration operator console, and focused release evidence.

## Why This Is The Current Milestone

v5.10 and v5.11 closed the account-operations and usage-ledger polish chain at the local planning/test level. The remaining product queue now splits into two categories:

- Externally blocked activation: live Stripe/TWINT charging, live notification providers, external support provider credentials, production warehouse deployment.
- Internally buildable functionality: rich curriculum editor implementation, production content import/migration UI/API, and operator content QA workflows.

The v5.1 audit explicitly left these implementation gaps visible:

- Full frontend rich curriculum editor implementation is still deferred to `/Users/zhdeng/stoa-frontend`.
- Backend draft update/patch, structured validation preview, diff endpoint, and audit-read endpoint remain future implementation work.
- Production migration service, manifest parsing, dry-run/apply APIs, evidence persistence, rollback metadata implementation, and operator UI remain future work.
- No production content source has been imported or published through a repeatable migration workflow.

v5.12 therefore remains the active curriculum tooling milestone. Future milestones should be new product, safety, or stability buildouts rather than renaming v5.12 phases.

## Current Reality

Backend evidence:

- `src/stoa/services/curriculum_ops_service.py` and `src/stoa/db/repositories/curriculum_ops_repo.py` provide authoring lifecycle foundations.
- `src/stoa/services/curriculum_analytics_service.py` and `src/stoa/db/repositories/curriculum_analytics_repo.py` provide bounded content-quality analytics.
- `src/stoa/routers/admin.py` already contains admin curriculum operations surfaces and content-quality routes.
- Student/parent published curriculum reads are served through `src/stoa/routers/practice.py`.
- Adaptive assignment and sequencing surfaces exist in `src/stoa/routers/adaptive.py` and `src/stoa/services/adaptive_learning_service.py`.
- Current curriculum edit permissions are still too broad in code: `AUTHOR_ROLES = {"admin", "tutor", "teacher"}` and multiple admin curriculum routes allow `admin`, `tutor`, and `teacher`.

Frontend evidence:

- `/Users/zhdeng/stoa-frontend/src/pages/admin/` has admin operations, analytics, usage, support, subscription, and report operations pages, but no dedicated curriculum authoring workbench page.
- `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts` and query hooks exist for many admin workflows, but rich curriculum editor/migration clients are not yet a complete implemented surface.
- `/Users/zhdeng/stoa-frontend/src/pages/practice/` and `src/components/practice/` provide student-facing curriculum/practice UX, not authoring or migration operator UX.

Planning evidence:

- v5.1 was readiness-complete, not implementation-complete.
- v5.11 is complete as `multi-action-usage-ledger-ready`.
- Before this update, `STOA_DOCS_REMAINING_FEATURES.md` still listed v5.10/v5.11 as remaining work; v5.12 corrects that queue and promotes this buildable curriculum gap.

## Implementation Strategy

- Start with a reality refresh and contract update so v5.12 is not confused with the older v5.1 readiness milestone.
- Build backend API gaps before frontend authoring screens.
- Treat curriculum editing as a special backend-granted capability, not a default teacher/tutor permission.
- Add explicit authorization checks for `curriculum_author`, `curriculum_reviewer`, and `curriculum_publisher`/`migration_operator` capabilities before draft edit, review, publish, rollback, or migration apply actions.
- Keep published student/parent curriculum reads stable while draft/migration workflows evolve.
- Treat migration dry-run as non-mutating and apply as explicitly confirmed.
- Store migration evidence and audit references, but do not broaden this milestone into warehouse/BI or external production activation.
- Implement frontend authorized-operator tooling against real API clients with no demo fallback for authoring/migration state.
- Close with focused backend tests, frontend lint/build/e2e, docs, and a next-milestone recommendation.

## Phases

- [x] **Phase 232: Curriculum Buildout Reality Refresh And Contract** - Reconcile v5.1 deferred implementation, current backend/frontend code, `stoa_docs`, and v5.12 scope.
- [x] **Phase 233: Backend Special Authorization Editor Patch Validation Diff And Audit APIs** - Implement backend special-authorization model, draft patch/update, structured validation preview, content diff, audit-read, and focused tests.
- [ ] **Phase 234: Backend Content Migration Service And APIs** - Implement manifest parsing, dry-run, apply, evidence, conflict reporting, rollback metadata, and tests.
- [ ] **Phase 235: Frontend Curriculum Editor And Migration Console** - Implement authorized curriculum operator workbench, review/preview/diff UX, migration dry-run/apply console, and focused e2e.
- [ ] **Phase 236: v5.12 Curriculum Buildout Release Gate** - Verify backend/frontend behavior, docs, state, release evidence, and next milestone decision.

## Phase Details

### Phase 232: Curriculum Buildout Reality Refresh And Contract

**Goal**: Define the exact v5.12 implementation contract from current code and stale planning docs.
**Depends on**: v5.1 readiness audit, v5.11 completion.
**Requirements**: CURRBUILD-01
**Status**: Complete 2026-07-05.
**Evidence**: `.planning/phases/232-curriculum-buildout-reality-refresh-and-contract/232-SUMMARY.md`, `.planning/phases/232-curriculum-buildout-reality-refresh-and-contract/232-VERIFICATION.md`.
**Success Criteria**:

1. v5.1 deferred implementation gaps are mapped to current backend/frontend files.
2. Current backend routes/services are checked for existing authoring lifecycle support, missing API capabilities, and current role/capability boundaries.
3. Current frontend is checked for missing editor/migration pages, typed clients, hooks, routes, and tests.
4. `stoa_docs` remaining-feature docs no longer list v5.10/v5.11 as remaining work.
5. v5.12 scope, phase order, out-of-scope items, and release evidence are documented.

### Phase 233: Backend Special Authorization Editor Patch Validation Diff And Audit APIs

**Goal**: Make curriculum draft editing and review workflow implementable by a frontend editor.
**Depends on**: Phase 232.
**Requirements**: CURRBUILD-02
**Status**: Active.
**Success Criteria**:

1. Draft update/patch endpoint requires a backend-granted curriculum author capability and supports structured lesson and exercise edits without changing published projections.
2. Validation preview returns field-level issues, publish readiness, and blocking versus warning severity.
3. Diff endpoint compares draft/current/published/rollback candidates in bounded metadata-safe form.
4. Audit-read endpoint exposes curriculum version events only to authorized curriculum reviewers/publishers without raw private data or unrelated audit streams.
5. Focused backend tests cover legal edits, invalid content, draft isolation, validation output, diff output, audit output, ordinary teacher/tutor refusal, and published-read compatibility.

### Phase 234: Backend Content Migration Service And APIs

**Goal**: Make repeatable production content import possible without manual database writes.
**Depends on**: Phase 233.
**Requirements**: CURRBUILD-03
**Success Criteria**:

1. Migration manifest schema supports source metadata, subject/topic mapping, public IDs, version IDs, locale metadata, lessons, exercises, dependencies, and operator notes.
2. Dry-run endpoint reports create/update/skip/conflict/validation results without mutation.
3. Apply endpoint requires migration-operator authorization plus explicit confirmation, then writes versions, published pointers when requested, evidence, and audit references.
4. Conflict and rollback metadata are persisted enough for operator review and safe follow-up.
5. Focused backend tests cover dry-run, apply, conflicts, validation failures, idempotency, evidence, and no accidental student/parent draft leakage.

### Phase 235: Frontend Curriculum Editor And Migration Console

**Goal**: Give internal operators usable curriculum tooling instead of backend-only readiness.
**Depends on**: Phase 234.
**Requirements**: CURRBUILD-04
**Success Criteria**:

1. Frontend clients, query keys, hooks, and routes cover editor worklist, draft edit, validation preview, diff, review actions, audit view, migration dry-run, and migration apply only for users with backend-granted curriculum capabilities.
2. Editor supports lesson sections, objectives, examples, formulas, media references, exercise blocks, answer keys, hints, explanations, tags, prerequisites, duration, and locale metadata.
3. Migration console shows manifest validation, conflicts, dry-run summary, apply confirmation, evidence references, and rollback hints.
4. Loading, empty, invalid, conflict, partial-success, unauthorized, and API-error states are implemented without demo fallback.
5. Focused frontend e2e covers editor happy path, validation errors, diff/review, migration dry-run, migration apply confirmation, unauthorized ordinary teacher/tutor states, and API-error states.

### Phase 236: v5.12 Curriculum Buildout Release Gate

**Goal**: Close v5.12 with evidence that curriculum editor and migration tooling are usable for internal development.
**Depends on**: Phase 235.
**Requirements**: VERIFY-45
**Success Criteria**:

1. Focused backend tests pass for editor patch/validation/diff/audit and migration service/API behavior.
2. Frontend lint/build and focused e2e pass for editor and migration console workflows.
3. Published student/parent curriculum reads remain compatible, and ordinary teacher/tutor accounts cannot edit curriculum without special authorization.
4. Docs, roadmap, requirements, state, remaining-feature audit, and milestone evidence are updated.
5. Next milestone recommendation is explicit and separates new functional, safety, and stability buildouts from externally blocked activation work.

## Future Milestone Directions

The next milestones after v5.12 should be new buildable feature, safety, or stability efforts, not renamed v5.12 phases:

- **v5.13 Payment And Entitlement Production Completion**: finish real payment access, entitlement activation, webhook reconciliation, refund/invoice support state, and admin-visible billing evidence.
- **v5.14 Verification And Login Reliability**: finish email verification, login-code/passwordless policy, delivery observability, resend limits, abuse controls, and account activation edge cases.
- **v5.15 Usage, Quota, And Product Stability**: close real usage metering gaps, quota reconciliation, user-visible usage explanations, admin support views, health checks, smoke monitors, and regression gates.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 232 Curriculum Buildout Reality Refresh And Contract | v5.12 | 1/1 | Complete | 2026-07-05 |
| 233 Backend Special Authorization Editor Patch Validation Diff And Audit APIs | v5.12 | 1/1 | Complete | 2026-07-05 |
| 234 Backend Content Migration Service And APIs | v5.12 | 0/1 | Active | - |
| 235 Frontend Curriculum Editor And Migration Console | v5.12 | 0/1 | Planned | - |
| 236 v5.12 Curriculum Buildout Release Gate | v5.12 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CURRBUILD-01 | Phase 232 | Complete |
| CURRBUILD-02 | Phase 233 | Complete |
| CURRBUILD-03 | Phase 234 | Planned |
| CURRBUILD-04 | Phase 235 | Planned |
| VERIFY-45 | Phase 236 | Planned |
