# Requirements: v5.8 Email Verification And Login Code Policy

**Milestone:** v5.8
**Status:** Active planning
**Created:** 2026-07-03
**Prior milestone:** v5.7 Usage Ledger And Quota Reconciliation

## Purpose

Make account verification behavior explicit and enforceable. Registration, email verification, resend/expiry, and any login-code/passwordless behavior must have a clear backend policy instead of placeholder or ambiguous flows.

v5.8 protects the parent/student account lifecycle before the broader v5.9 operations visibility milestone. It should preserve existing role onboarding, parent-student binding, and Cognito token compatibility while clarifying what is supported now and what is intentionally deferred.

## Requirements

### EMAIL-01 Email Verification Contract And State Model

Acceptance criteria:

- Account verification states are defined for registered, unverified, pending verification, verified, expired verification, resend-limited, and blocked states.
- Registration output and stored user profile metadata expose verification status without leaking Cognito internals.
- Parent/student binding behavior is explicit when one or both accounts are unverified.
- Verification policy identifies which routes require verified email immediately and which remain allowed for onboarding/support.
- Test matrix is documented before enforcement changes.

### EMAIL-02 Registration Verification Enforcement

Acceptance criteria:

- New registrations record email verification policy metadata and initial verification state.
- Login or token-return behavior after registration follows the chosen verification policy.
- Existing student, parent, teacher, and admin role onboarding remains compatible.
- Parent-student binding creation does not silently grant fully active access when verification policy blocks it.
- Focused tests cover parent registration, student registration with parent email, unverified states, verified states, and role aliases.

### EMAIL-03 Verification Resend And Expiry Operations

Acceptance criteria:

- Backend exposes a safe resend-verification operation or explicitly documents the Cognito-compatible equivalent.
- Resend behavior is rate-limited or idempotency-safe enough for repeated user attempts.
- Expired or stale verification states produce actionable responses without exposing provider internals.
- Admin/support can inspect verification status at a bounded level suitable for account support.
- Tests cover resend success, resend throttling/idempotency, expired state handling, and support visibility.

### LOGIN-01 Login Code Policy And Token Compatibility

Acceptance criteria:

- Login-code/passwordless behavior is explicitly classified as supported, provider-gated, or deferred.
- If supported in this milestone, the implementation produces Cognito-compatible authenticated sessions and has expiry, replay, and rate-limit protections.
- If deferred, existing placeholder login-code behavior is gated so clients cannot mistake it for production authentication.
- Forgot-password and standard Cognito login flows remain backward compatible.
- Tests cover the chosen policy, unsupported/deferred responses, and existing auth lifecycle flows.

### VERIFY-41 v5.8 Verification Release Gate

Acceptance criteria:

- Email verification contract, enforcement, resend/expiry operations, login-code policy, and focused tests are complete.
- Requirements, roadmap, state, and milestone history reflect v5.8 completion.
- Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
- Final audit records rollout state: `verification-ready`, `policy-deferred`, `blocked`, or `deferred`.
- v5.9 parent/admin operations visibility handoff is updated.

## Future Milestones

- v5.9 Parent Admin Operations Visibility.
- Native iOS/Android app buildout after core account/payment/usage correctness.

## Out of Scope

- Full parent/admin operations console.
- Native app implementation.
- Final live Stripe/TWINT activation.
- Replacing Cognito with a custom identity provider.
- Storing raw verification codes or provider secrets in DynamoDB.
- Broad fraud/risk scoring beyond verification rate limits and replay protection.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EMAIL-01 | Phase 212 | Planned |
| EMAIL-02 | Phase 213 | Planned |
| EMAIL-03 | Phase 214 | Planned |
| LOGIN-01 | Phase 215 | Planned |
| VERIFY-41 | Phase 216 | Planned |
