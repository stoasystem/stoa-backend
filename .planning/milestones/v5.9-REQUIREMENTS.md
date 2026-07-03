# Requirements: v5.9 Parent Admin Operations Visibility

**Milestone:** v5.9
**Status:** Complete
**Created:** 2026-07-03
**Prior milestone:** v5.8 Email Verification And Login Code Policy

## Purpose

Give parents and admins one support-grade view of account operations state across entitlement, billing, usage, verification, and parent/student binding health.

v5.6 made effective entitlement enforceable, v5.7 made usage durable/reconcilable, and v5.8 made email verification explicit. v5.9 composes those slices into bounded operations visibility without building a broad CRM, analytics warehouse, or frontend console.

## Requirements

### OPSVIS-01 Operations Visibility Contract

Acceptance criteria:

- A shared account operations contract defines parent profile, billing state, child binding state, effective entitlement, usage summary, verification state, and support state.
- The contract reuses v5.6/v5.7/v5.8 data and does not introduce new tables, indexes, or provider payload exposure.
- Support state classifies ready, attention, and blocked conditions with bounded blocker/warning codes.
- Contract documentation identifies privacy boundaries and v5.10/native/frontend handoff.

### PARENTOPS-01 Parent Account Operations Summary

Acceptance criteria:

- Parent users can retrieve a consolidated `/parents/me/account-operations` summary.
- Summary includes parent verification, billing status, linked child rows, effective entitlement, usage summary, and support state.
- Parent access remains ownership-scoped and does not expose provider internals, raw learning content, private artifact keys, or admin-only event detail.
- Focused tests cover billing, entitlement, usage, verification, and ready support state.

### ADMINOPS-01 Admin Account Operations Detail

Acceptance criteria:

- Admins can retrieve one parent account operations detail by parent ID.
- Detail includes parent verification, billing summary with bounded events, child binding states, entitlement, usage, verification, and support state.
- Missing/non-parent accounts return bounded 404 behavior.
- Attention states surface unverified parent/child, non-active binding, billing inactive, no-linked-child, and unreconciled usage signals.
- Focused tests cover admin detail and support-state warnings/blockers.

### OPSVERIFY-01 Privacy And Regression Verification

Acceptance criteria:

- Focused tests prove parent/admin account operations views compose existing billing, entitlement, usage, and verification helpers.
- Adjacent subscription, usage, entitlement, auth lifecycle, and parent authorization tests remain compatible.
- Ruff passes for new/modified account operations modules and routes.
- Release evidence records residual production deploy/live smoke status.

### VERIFY-42 v5.9 Operations Visibility Release Gate

Acceptance criteria:

- Contract, parent summary, admin detail, privacy/regression tests, docs, and audit are complete.
- Requirements, roadmap, state, milestone history, and phase artifacts reflect v5.9 completion.
- Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
- Final audit records rollout state: `operations-visible`, `blocked`, or `deferred`.
- Future handoff identifies frontend/native console integration and production smoke as separate work.

## Future Milestones

- Frontend/native account operations UI integration.
- Production deploy and live smoke for account operations endpoints.
- Actual Cognito custom-auth passwordless login-code implementation if product chooses to support it.

## Out of Scope

- Broad CRM/customer messaging workflows.
- New analytics warehouse, BI dashboards, or cross-account search.
- New DynamoDB indexes, tables, or provider storage.
- Raw question content, answer content, invoice internals, provider payloads, auth tokens, private S3 keys, or verification codes in operations responses.
- Native app implementation.
- Final live Stripe/TWINT activation.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPSVIS-01 | Phase 217 | Complete |
| PARENTOPS-01 | Phase 218 | Complete |
| ADMINOPS-01 | Phase 219 | Complete |
| OPSVERIFY-01 | Phase 220 | Complete |
| VERIFY-42 | Phase 221 | Complete |
