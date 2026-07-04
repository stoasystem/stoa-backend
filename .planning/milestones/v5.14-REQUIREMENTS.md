# Requirements: v5.14 Verification And Login Reliability

**Milestone:** v5.14
**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.13 Payment And Entitlement Production Completion

## Purpose

Make email verification, login policy, account activation, resend/confirm behavior, and support recovery reliable for real users. v5.14 must resolve half-enabled login-code/passwordless behavior, tighten verification state consistency across Cognito/local profiles/frontend views, and provide bounded support evidence without exposing sensitive authentication data.

This is a reliability and production-readiness milestone, not a broad authentication redesign. The milestone should audit current reality first, then complete the smallest dependable verification/login loop.

## Requirements

### AUTHREL-01 Verification And Login Reality Audit

Status: Complete.

Acceptance criteria:

- Current Cognito sign-up confirmation, local profile verification fields, token-return behavior, resend/confirm endpoints, frontend verification screens, and admin/account-operations support views are mapped to concrete files/routes/services.
- Implemented, partially implemented, demo-only, stale, and externally blocked behavior is separated in an evidence table.
- Login-code/passwordless references are located and classified as supported, hidden, or deferred.
- v5.14 implementation contract identifies the canonical login/verification policy and release-gate evidence expectations.

### VERIFY-01 Email Verification Resend Confirm Reliability

Status: Complete.

Acceptance criteria:

- User can register, receive verification-required state, resend verification, confirm email, and then log in without inconsistent local/Cognito state.
- Expired, already-confirmed, wrong-code, rate-limited, disabled-user, and missing-profile cases return clear support-safe errors.
- Local profile verification fields remain consistent with Cognito confirmation and frontend account operations state.
- Focused tests cover success, retries, expiry/rate-limit, already-confirmed, and failed confirmation paths.

### LOGIN-01 Canonical Login Code And Passwordless Policy

Status: Complete.

Acceptance criteria:

- Half-enabled login-code/passwordless behavior is either completed with a real Cognito custom-auth contract or removed/hidden from product surfaces.
- Email/password login remains a dependable canonical path unless a complete custom-auth path is implemented.
- Token return is blocked for unverified accounts according to the canonical policy, with clear frontend messaging.
- Tests cover unsupported login-code attempts, canonical login success, unverified login refusal, and policy documentation.

### SUPPORT-01 Verification Support Visibility And Recovery

Status: Complete.

Acceptance criteria:

- Parent/admin account operations expose bounded verification/login recovery state, including verification status, resend eligibility, last request/confirm metadata, and support action.
- Support/admin recovery actions are explicit, audited, and do not expose raw Cognito secrets, codes, or sensitive token material.
- Frontend admin/support surfaces render verification blockers, warnings, next actions, and recovery evidence clearly.
- Focused tests cover support visibility for pending, expired, verified, locked/rate-limited, and support-recovered accounts.

### VERIFY-48 v5.14 Release Gate

Status: Active.

Acceptance criteria:

- Focused backend tests pass for registration confirmation, resend/confirm, login refusal/success, policy enforcement, support visibility, and recovery audit.
- Frontend lint/build and focused e2e pass for verification/login recovery workflows.
- Live Cognito/email delivery smoke is recorded as blocked or completed based on credential/environment availability.
- Docs, roadmap, state, milestone snapshots, and release evidence are updated.
- Remaining externally blocked delivery/custom-auth items are explicit future work, not hidden in completion notes.

## Out of Scope

- Switching identity providers.
- Broad OAuth/social login.
- Native app auth flows.
- Full passwordless rollout unless the real Cognito custom-auth flow is implemented end to end in this milestone.
- Exposing raw verification codes, Cognito secrets, refresh tokens, or sensitive auth payloads in support/admin views.
- Production email-provider deliverability certification beyond explicit smoke/blocker documentation.

## Future Milestones

- **v5.15 Usage, Quota, And Product Stability**: usage accounting, quota reconciliation, user-visible usage explanations, support views, health checks, and regression gates.
- External live delivery/custom-auth activation remains separate when provider credentials, Cognito trigger deployment, and rollout approvals unblock.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTHREL-01 | Phase 242 | Complete |
| VERIFY-01 | Phase 243 | Complete |
| LOGIN-01 | Phase 244 | Complete |
| SUPPORT-01 | Phase 245 | Complete |
| VERIFY-48 | Phase 246 | Active |
