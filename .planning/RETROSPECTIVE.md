# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v5.0 — Native Mobile And Full Localization Governance

**Shipped:** 2026-06-14
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- Native mobile and localization governance contract across backend, frontend/PWA, future native, localization, content, and release ownership.
- Mobile API readiness and client handoff guidance for core role flows, including no-demo-fallback expectations.
- Native notification token lifecycle and offline/read-through state handoff.
- Localization governance, English/German catalog parity evidence, broad copy QA scope, and future-locale/RTL readiness.
- Release gate evidence recording rollout state as `contract-ready`.

### What Worked

- Keeping v5.0 explicitly contract-ready made deferred frontend/native/provider work visible without blocking the milestone.
- Reusing v4.1, v4.3, and v4.9 evidence kept mobile/localization planning aligned with existing backend and frontend foundations.
- The release gate separated backend documentation readiness from frontend-ready, native-ready, and live-activation claims.

### What Was Inefficient

- The archive helper created milestone archives but left several project-level references stale, requiring manual closeout cleanup.
- Summary extraction did not populate top-level milestone accomplishments automatically.
- No phase-level `*-VALIDATION.md` artifacts were produced for this docs-only milestone, leaving Nyquist validation marked as missing.

### Patterns Established

- Use explicit rollout states (`contract-ready`, `frontend-ready`, `native-ready`, `blocked`, `deferred`) for cross-workspace milestones.
- Record frontend/native/provider prerequisites as deferred follow-up work when the current workspace cannot complete them directly.
- Keep mobile client handoff documents tied to route groups, state behavior, fallback rules, and release evidence.

### Key Lessons

1. Cross-workspace milestones need a clear readiness label so documentation contracts do not get mistaken for implemented client releases.
2. Localization governance should distinguish key parity from semantic review, hardcoded-string inventory, and mobile visual QA.
3. Milestone closeout still needs manual inspection after helper automation, especially for `PROJECT.md`, top-level accomplishments, and active-file cleanup.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous closeout session.
- Notable: The milestone was documentation-heavy; verification cost centered on artifact traceability and archive hygiene rather than source test runtime.

---

## Milestone: v5.1 — Rich Curriculum Editor And Production Content Migration

**Shipped:** 2026-06-14
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- Rich curriculum editor and migration ownership contract.
- Admin/tutor rich editor UI/API readiness handoff and UI-SPEC.
- Production content migration manifest, dry-run, apply, evidence, conflict, validation, and rollback contract.
- Assignment automation eligibility, duplicate prevention, sequencing signal, and visibility readiness.
- Release gate evidence recording readiness-complete rollout state.

### What Worked

- The milestone reused v3.8, v4.0, and v4.6 foundations instead of reopening already-settled curriculum architecture.
- Separating readiness from implementation kept frontend, production source content, and automation prerequisites visible.
- Integration audit made the main risk explicit: readiness is coherent, but the product flows are not shipped implementations.

### What Was Inefficient

- The archive helper again left stale active references and placeholder accomplishments that required manual closeout.
- Phase summaries do not include frontmatter, so audit summary extraction remains manual.
- Nyquist validation artifacts are still missing for docs/readiness-only phases.

### Patterns Established

- Use `readiness-complete` for milestones that prepare a product surface without shipping the full UI/service implementation.
- State deferred implementation work in release gate, audit, feature queue, and milestone ledger.
- Treat editor, migration, and automation as separate rollout states rather than one ambiguous curriculum milestone state.

### Key Lessons

1. A readiness milestone should explicitly name non-shipped E2E flows so future work does not assume APIs/UI exist.
2. Migration plans need source ownership and approval gates before implementation; otherwise the backend can only define contracts safely.
3. Assignment automation should start with deterministic eligibility and duplicate prevention before ranking sophistication.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous execution and closeout session.
- Notable: Verification cost centered on cross-phase integration and deferred-scope clarity, not runtime test execution.

---

## Milestone: v5.2 — Adaptive Sequencing And Warehouse Analytics

**Shipped:** 2026-06-15
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- Adaptive sequencing and warehouse analytics contract across backend, frontend, curriculum/tutor, analytics, and release ownership.
- Multi-signal recommendation generation for remediation topics, curriculum exercises, reviewed AI drafts, and continuation lessons.
- Assignment outcome feedback metadata, idempotent transition handling, aggregate analytics signals, and parent/tutor sequencing summaries.
- Admin warehouse readiness, aggregate export schemas, and operator dashboard contracts.
- Release gate evidence recording rollout state as `warehouse-ready`.

### What Worked

- The implementation phases stayed narrowly scoped to backend/API behavior and avoided reopening frontend/native/provider work.
- Code review iterations caught duplicate side-effect and visibility risks before the release gate.
- The integration audit confirmed the phase chain from recommendation flow to assignment feedback to operator analytics without adding broad unrelated checks.

### What Was Inefficient

- The milestone archive helper still required manual cleanup for duplicate `MILESTONES.md` entries, living roadmap state, and stale project references.
- Phase summaries still do not expose structured frontmatter accomplishments, so top-level accomplishment extraction remained manual.
- Nyquist validation artifacts were not generated, leaving validation coverage recorded as missing despite focused tests and integration review passing.

### Patterns Established

- Use `warehouse-ready` for backend/API analytics milestones that provide readiness/export contracts without live warehouse deployment.
- Preserve review gates and explicitly set `autonomousDecision` false while improving recommendation ranking.
- Keep analytics responses aggregate/operator-focused and make no-live-warehouse behavior explicit.

### Key Lessons

1. Assignment transition side effects need idempotency tokens or state-machine claiming before analytics and progress updates are safe.
2. Recommendation visibility must treat reviewed AI drafts as manager-visible by default unless role-specific review gates are explicit.
3. Warehouse readiness is clearer when source schemas and live export rows are distinguished in both code and release evidence.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous execution and closeout session.
- Notable: Verification cost was mostly focused pytest, targeted Ruff, and cross-phase wiring review after code review drove the risky fixes.

---

## Milestone: v5.3 — Controlled Assignment Automation

**Shipped:** 2026-06-15
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- Controlled assignment automation contract with reviewed-source boundaries, autonomy levels, refusal rules, and rollout states.
- Policy-bounded candidate preview from adaptive recommendations, accepted AI drafts, curriculum exercises, and assignment outcomes.
- Approved-batch assignment execution with explicit approval, current-preview binding, deterministic source IDs, conditional insert, and per-item result evidence.
- Role-safe automation metadata in assignment responses and AI draft visibility enforcement before materialization.
- Tutor/admin review UX and family visibility handoff, plus release gate evidence recording rollout state as `automation-ready`.

### What Worked

- Code review caught major assignment idempotency, forged-candidate, and visibility risks before Phase 188 was committed.
- The milestone audit caught a cross-phase subject-scoped preview/execute gap that focused unit tests had missed.
- Keeping live provider, frontend, native, and warehouse work out of scope let the backend automation path become concrete without broadening the release gate.

### What Was Inefficient

- The execute route initially diverged from the preview route by omitting `subject`, showing that route-pair contracts need paired request tests.
- Idempotency required several iterations: pre-read dedupe, deterministic automation keys, deterministic source IDs, and finally conditional insert.
- Archive cleanup still required manual consistency work across roadmap snapshots, live requirements, milestone indexes, and phase directory moves.

### Patterns Established

- Preview-bound execution should recompute the same scoped preview and reject stale or forged candidates.
- Automation-created assignment rows need source-based uniqueness plus conditional writes to avoid duplicate rows and data loss.
- Family visibility tests should cover automation-created assignments, not only legacy assignment privacy.

### Key Lessons

1. Any preview/execute pair must carry identical scoping fields or the server-side replay binding will fail real frontend flows.
2. Deterministic IDs are not enough for idempotency; writes must be conditional to avoid overwriting existing progress.
3. Integration audit is most valuable after apparently passing tests, because it checks the documented E2E flow rather than only the coded happy path.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous execution and closeout session.
- Notable: Most cost was spent in review/fix loops around idempotency and cross-phase route binding, not broad test runtime.

---

## Milestone: v5.4 — Frontend Learning Operations And Automation Dashboards

**Shipped:** 2026-06-15
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- No-demo-fallback frontend learning operations API/types/hooks for automation, assignment history, analytics dashboard, warehouse readiness/export, and parent progress.
- Tutor/admin automation review console routes for preview, refusal review, approved execution, results, and assignment history.
- Operator learning operations dashboards for sequencing coverage, assignment outcomes, quality hotspots, interventions, warehouse readiness, and export summary.
- Student and parent assignment explanation surfaces that hide answer keys and internal ranking internals.
- Focused Playwright e2e coverage for the Open Design finish pass across automation, dashboard, student, and parent role flows.

### What Worked

- Reusing the v5.2/v5.3 backend APIs kept the frontend work product-focused and avoided unnecessary backend scope.
- Role-safe explanation checks made the family-facing privacy boundary executable instead of only documented.
- Separating the Open Design finish-pass test commit from the implementation commit made verification evidence easier to review.

### What Was Inefficient

- The requested `open-design` skill set existed only as catalog entries plus an `agent-browser` workflow; the `agent-browser` CLI was not installed locally, so verification fell back to Playwright.
- The archive helper again left stale active milestone references in `PROJECT.md`, `STATE.md`, `ROADMAP.md`, and `REQUIREMENTS.md`.
- Phase directory archiving still needed manual movement after milestone completion.

### Patterns Established

- Frontend learning operations should use explicit no-demo-fallback clients and visible empty/error states when backend data is absent.
- Student/parent assignment explanations need tests that assert absence of sensitive markers, not just presence of friendly copy.
- Cross-workspace milestones should record both implementation and verification commits from the frontend repo.

### Key Lessons

1. A frontend-ready release gate should include role-flow e2e coverage, not only build and lint.
2. Optional design-review/browser tooling needs a local availability check before relying on it for release evidence.
3. Learning operations dashboards are more useful when no-live-warehouse states are first-class, not treated as missing data.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous execution and closeout session.
- Notable: Verification cost was concentrated in frontend build/lint and a focused Playwright e2e spec rather than broad backend testing.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v5.0 | 1 | 5 | Introduced explicit mobile/localization contract-ready release classification across backend, frontend, native, and localization ownership. |
| v5.1 | 1 | 5 | Extended rollout-state discipline to curriculum readiness: editor-ready, migration-ready, assignment-ready, and deferred sequencing. |
| v5.2 | 1 | 5 | Promoted readiness planning into backend/API implementation while preserving review gates and explicit warehouse-ready boundaries. |
| v5.3 | 1 | 5 | Closed the loop from recommendations to controlled assignment automation with preview-bound execution and source-idempotent assignment creation. |
| v5.4 | 1 | 5 | Brought the backend learning operations capabilities into usable frontend role flows with no-demo-fallback behavior and focused Open Design e2e verification. |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v5.0 | `git diff --check`; artifact traceability; English/German key parity evidence | Contract coverage for 5/5 requirements | 0 |
| v5.1 | `git diff --check`; artifact traceability; integration audit | Readiness coverage for 5/5 requirements | 0 |
| v5.2 | 20 focused backend tests; targeted Ruff; integration audit | Backend/API coverage for 5/5 requirements | 0 |
| v5.3 | 15 focused adaptive backend tests; targeted Ruff; code review; integration audit | Automation-ready coverage for 5/5 requirements | 0 |
| v5.4 | Frontend build; frontend lint; focused Playwright e2e | Frontend role-flow coverage for 5/5 requirements | 0 |

### Top Lessons (Verified Across Milestones)

1. Release gates should name the exact rollout state, especially when external credentials, frontend workspaces, or native clients remain out of scope.
2. Archive helpers reduce mechanical work but do not replace a final consistency pass across ROADMAP, REQUIREMENTS, PROJECT, STATE, and MILESTONES.
3. Readiness milestones need a prominent list of intentionally incomplete E2E product flows.
4. Implementation milestones need idempotent transition side effects before analytics and progress projections can be trusted.
5. Preview/execute route pairs need explicit tests for every shared scope field, especially when the execute path recomputes server-side state.
