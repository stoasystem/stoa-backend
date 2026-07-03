# Phase 212: Email Verification Contract And Account State Policy - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 212 defines the account verification contract before enforcement: verification states, public response fields, route policy, parent/student binding semantics, and test matrix.

</domain>

<decisions>
## Implementation Decisions

### Verification State Model
- Use Cognito `sign_up` and `confirm_sign_up` as the canonical verification mechanism for new registrations.
- Store backend-visible state as product metadata, not provider internals.
- Treat legacy `admin_marked_verified` profiles as verified for backward compatibility.
- Do not store raw verification codes or provider secrets in DynamoDB.

### Route Policy
- New registration is allowed without an existing token but returns no authenticated access token until email is verified.
- Login may call Cognito password auth, but backend must refuse to return a token for profiles that still require verification.
- Forgot/reset password remains compatible with Cognito and does not become login-code behavior.
- Verification resend/confirm routes are the only unauthenticated verification operations in scope.

### Parent Student Binding
- Parent/student binding may be created during onboarding, but if either side is unverified the binding status is `active_pending_verification`.
- Pending one-sided parent/student email matches remain pending and do not create a binding.
- Verified legacy profiles still count as verified for binding compatibility.

### Login Code Policy
- Passwordless login code is deferred until a Cognito custom auth trigger flow exists.
- Placeholder login-code routes must not mint or imply production tokens.

### the agent's Discretion
Exact helper names, response-model placement, and focused test grouping are implementation details as long as the public contract remains explicit and provider-redacted.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/auth.py` already owns registration, login, forgot/reset password, role aliases, locale response fields, and parent/student binding helpers.
- `src/stoa/db/repositories/user_repo.py` owns profile writes and parent/student binding rows.
- `tests/test_auth_account_lifecycle.py` already covers registration policy, binding behavior, forgot/reset password, and admin binding repair.

### Established Patterns
- Route-local Pydantic request/response models use camelCase fields for frontend contract compatibility.
- Cognito `ClientError` values are normalized to bounded HTTP responses.
- Existing profile metadata is stored in the DynamoDB profile row under `PK=USER#{user_id}`, `SK=PROFILE`.

### Integration Points
- Auth response profile shape is `_build_user_out`.
- Parent/student binding creation is `_bind_parent_student_if_possible` and `_bind_existing_child_if_possible`.
- Admin support visibility belongs in `src/stoa/routers/admin.py` next to usage/account support endpoints.

</code_context>

<specifics>
## Specific Ideas

Use a small service helper for account verification policy so auth and admin routes share state semantics.

</specifics>

<deferred>
## Deferred Ideas

Full parent/admin account operations console remains v5.9 scope. Native app verification UX remains future client scope.

</deferred>
