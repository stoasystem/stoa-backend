# Email Verification Contract

## State Model

| State | Meaning | Token Return |
|-------|---------|--------------|
| `registered` | Account registration record exists and verification has been requested. | No |
| `unverified` | Fallback state when an account is known but has no confirmed verification. | No |
| `pending_verification` | Cognito sign-up confirmation is pending. | No |
| `verified` | Cognito sign-up confirmation succeeded and backend profile is active. | Yes |
| `expired_verification` | Cognito reported an expired confirmation code. | No |
| `resend_limited` | Provider/rate limit prevents another resend attempt now. | No |
| `blocked` | Support or policy has blocked activation. | No |
| `admin_marked_verified` | Legacy state from earlier backend-created users; treated as verified for compatibility. | Yes |

## Public Response Shape

Auth profile and auth responses expose:

- `emailVerificationStatus`
- `emailVerificationRequired`
- `accountActivationStatus`

Support responses additionally expose:

- `emailVerificationPolicy`
- `emailVerifiedAt`
- `emailVerificationRequestedAt`
- `emailVerificationLastResendAt`
- `emailVerificationResendCount`
- `resendAllowed`
- `parentBindingStatus`

These fields intentionally avoid raw Cognito status strings, verification codes, provider request IDs, and secrets.

## Route Policy

Allowed before verification:

- `POST /auth/register`
- `POST /auth/email-verification/resend`
- `POST /auth/email-verification/confirm`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

Blocked before verification:

- `POST /auth/login` token return.
- Any authenticated product route that depends on a Cognito access token from this backend login flow.

Deferred:

- `POST /auth/login-code/request`
- `POST /auth/login-code/confirm`

The login-code routes return explicit `deferred` policy responses and never return `accessToken`.

## Parent Student Binding

When a matching parent/student relationship is discovered during registration:

- If both accounts are verified or legacy verified, binding status is `active`.
- If either account is pending verification, binding status is `active_pending_verification`.
- If counterpart profile or reciprocal email confirmation is missing, existing pending statuses remain: `pending_parent_profile`, `pending_parent_confirmation`, `pending_student_profile`, or `pending_student_confirmation`.

## Test Matrix

| Scenario | Expected |
|----------|----------|
| Student registration with matching parent email | Pending verification, no token, `active_pending_verification` binding |
| One-sided parent email mismatch | Pending binding status, no binding row |
| Confirm verification | Profile becomes `verified` and active |
| Login before verification | 403 with `email_verification_required` |
| Login after verification | Cognito token returned |
| Resend during cooldown | Idempotent `already_requested`, no provider call |
| Provider resend | Delivery metadata only, resend count updated |
| Expired confirm code | `expired_verification`, actionable 400 response |
| Login code request/confirm | `deferred`, no token |
| Admin support visibility | Bounded verification state, no provider internals |
