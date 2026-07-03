# Phase 214: Verification Resend And Expiry Operations - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 214 adds safe verification recovery operations and bounded admin support visibility for verification state.

</domain>

<decisions>
## Implementation Decisions

### Resend Operation
- Use Cognito `resend_confirmation_code`; do not generate or store local codes.
- Unknown emails return an accepted-style response to avoid account enumeration.
- Repeated attempts inside the cooldown return `already_requested` without another provider call.
- Provider throttling maps to `resend_limited` state and HTTP 429.

### Expiry Handling
- Cognito `ExpiredCodeException` sets local `expired_verification`.
- Expired responses are actionable and do not expose provider internals.

### Support Visibility
- Admin support can inspect bounded verification metadata by user ID.
- Support response omits raw codes, provider secrets, and Cognito request IDs.

### the agent's Discretion
The exact cooldown duration can be policy-owned in the helper; v5.8 only requires deterministic repeated-attempt behavior.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Auth routes already normalize Cognito errors.
- Admin routes already expose bounded support endpoints for billing and usage.

### Established Patterns
- Support endpoints use `require_role("admin")`.
- Repository updates use explicit `UpdateExpression` fields.

### Integration Points
- `user_repo.update_email_verification_state`
- `/auth/email-verification/resend`
- `/auth/email-verification/confirm`
- `/admin/account-verification/{user_id}`

</code_context>

<specifics>
## Specific Ideas

Keep the admin endpoint read-only and profile-scoped; broader account search remains v5.9.

</specifics>

<deferred>
## Deferred Ideas

Bulk verification operations and support-side activation controls remain out of scope.

</deferred>
