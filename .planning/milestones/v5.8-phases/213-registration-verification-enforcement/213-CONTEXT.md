# Phase 213: Registration Verification Enforcement - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 213 enforces the Phase 212 verification contract through registration, login, profile response, and parent/student binding behavior.

</domain>

<decisions>
## Implementation Decisions

### Registration Enforcement
- Use Cognito `sign_up` so Cognito owns confirmation code generation and verification.
- Persist initial backend state as `pending_verification`.
- Registration returns no `accessToken` until verification is confirmed.
- Existing role aliases and onboarding payload fields remain compatible.

### Login Enforcement
- Standard password login remains the only production login flow.
- Successful Cognito password auth still cannot return a token if the profile requires email verification.
- Cognito `UserNotConfirmedException` maps to a bounded `email_verification_required` response.

### Binding Enforcement
- Matching parent/student registration creates a binding with `active_pending_verification` when either side is unverified.
- Mismatched one-sided onboarding remains pending and creates no binding row.

### the agent's Discretion
The implementation may keep legacy verified profiles compatible as long as all new registrations follow the enforced pending-verification path.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/auth.py` registration flow already extracts frontend onboarding payloads.
- `user_repo.put_parent_student_binding` already writes both parent and student lookup rows.

### Established Patterns
- Cognito errors are normalized near route boundaries.
- Tests monkeypatch Cognito and user repository helpers for deterministic lifecycle assertions.

### Integration Points
- Register, login, `_build_user_out`, and binding helpers are the integration points.

</code_context>

<specifics>
## Specific Ideas

Keep forgot/reset password unchanged while changing registration and login token-return semantics.

</specifics>

<deferred>
## Deferred Ideas

Automatic promotion of pending binding rows after both accounts verify can be expanded in v5.9 operations visibility if needed.

</deferred>
