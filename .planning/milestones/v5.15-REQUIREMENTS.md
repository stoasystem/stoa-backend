# Requirements: v5.15 Usage, Quota, And Product Stability

**Milestone:** v5.15
**Status:** Complete
**Created:** 2026-07-05
**Prior milestone:** v5.14 Verification And Login Reliability

## Purpose

Make usage accounting, quota reconciliation, support explanations, and core product smoke checks trustworthy across real STOA flows. v5.15 should verify actual behavior before adding code, then close the highest-risk gaps in usage recording, idempotency, drift detection, and local stability gates.

This is a product stability milestone, not a BI/analytics expansion. It should preserve privacy boundaries and use support-safe metadata instead of raw learning content.

## Requirements

### STABILITY-01 Usage Reality Audit

Status: Complete.

Acceptance criteria:

- All current usage-bearing flows are mapped to concrete backend/frontend files and classified as ledger event, aggregate counter, both, intentionally skipped, missing, future-only, or externally blocked.
- Question submit, chat, hints, teacher help, practice, lesson completion, assignment generation, assignment lifecycle, curriculum read, billing entitlement, and account operations paths are included.
- Each skip rule is explicit for previews, failed operations, admin-triggered retries, dry-runs, duplicate submissions, provider-blocked paths, and read-only flows.
- Priority fixes are identified for paid access, student quota behavior, parent explanations, and admin support decisions.

### LEDGER-01 Ledger Coverage And Idempotency Closure

Status: Complete.

Acceptance criteria:

- Major successful usage flows emit privacy-safe, governed, idempotent ledger events or have an explicit non-consuming skip decision.
- Duplicate request/action identifiers are handled consistently and semantically equivalent retries do not double-charge quota.
- Mismatched duplicate intents are rejected, flagged, or surfaced as support-safe conflicts.
- Focused tests cover duplicate request IDs, repeated submissions, failed operations, partial failures, and action metadata privacy.

### QUOTA-01 Quota Reconciliation And Support Explanations

Status: Complete.

Acceptance criteria:

- Ledger rows, aggregate counters, entitlement limits, and user/admin summaries can be reconciled for a student/action/day.
- Drift is detected and surfaced with support-safe status, counts, request IDs, quota period, action, and recommended support action.
- Parent/admin account operations explain remaining quota and unreconciled usage without raw learning content or provider payloads.
- Focused tests cover matched, drifted, stale, partial, over-limit, and no-usage states.

### HEALTH-01 Core Health And Smoke Gates

Status: Complete.

Acceptance criteria:

- Local smoke or health checks cover login, entitlement resolution, curriculum read, question submit, teacher help, and admin/account support surfaces.
- Checks separate service availability from product-flow readiness and return actionable route/status/request metadata.
- Smoke outputs are deterministic enough for local release gates and support-safe enough to share internally.
- Tests cover smoke success, expected auth/provider blocks, and failure classification.

### VERIFY-49 v5.15 Usage Stability Gate

Status: Complete.

Acceptance criteria:

- Focused backend tests pass for usage coverage, idempotency, reconciliation, support summaries, and smoke checks.
- Frontend build and focused account-operations/usage visibility checks pass when execution permission is available.
- v5.14 residual focused frontend e2e blocker is recorded separately and not hidden in v5.15 completion.
- Docs, roadmap, state, milestone snapshots, research summary, and release evidence are updated.
- Remaining BI/APM/live-provider dependencies are explicit future work.

## Out of Scope

- Full BI warehouse deployment.
- Long-term analytics modeling beyond operational usage reliability.
- External APM/vendor rollout unless explicitly approved.
- New payment, Cognito, notification, or support-provider activation.
- Raw learning content, prompt bodies, Cognito token material, provider payloads, or private report artifacts in support evidence.
- Broad frontend redesign beyond focused usage/quota visibility needed by this milestone.

## Research Summary

Research files:

- `.planning/research/STACK.md`
- `.planning/research/FEATURES.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`
- `.planning/research/SUMMARY.md`

Key guidance:

- Use existing STOA stack and support-safe metadata.
- Prefer explicit request/action idempotency keys over payload equality.
- Keep error/status codes low-cardinality and documented.
- Separate product-flow smoke checks from generic service liveness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STABILITY-01 | Phase 247 | Complete |
| LEDGER-01 | Phase 248 | Complete |
| QUOTA-01 | Phase 249 | Complete |
| HEALTH-01 | Phase 250 | Complete |
| VERIFY-49 | Phase 251 | Complete |
