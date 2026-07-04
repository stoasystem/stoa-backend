# Phase 242 Audit: Verification And Login Reality

## Backend Verification Lifecycle

| Area | Status | Evidence | Notes |
|------|--------|----------|-------|
| Registration creates Cognito user | Implemented | `src/stoa/routers/auth.py` `/auth/register` calls `cognito.sign_up` with role client id. | Local profile is written after Cognito sign-up. |
| Registration returns no access token | Implemented | `_auth_response_for_profile(access_token="")` in `/auth/register`; `tests/test_auth_account_lifecycle.py::test_register_records_email_verification_policy_and_parent_binding`. | User is created but not signed in until verification completes. |
| Local verification fields | Implemented | `account_verification_service.registration_profile_fields`, `verified_fields`, `expired_fields`, `resend_limited_fields`. | Policy is `cognito_sign_up_confirm_sign_up`. |
| Login blocks unverified profiles | Implemented | `/auth/login` checks `can_return_tokens(profile)` after Cognito auth; tests cover 403 `email_verification_required`. | Cognito `UserNotConfirmedException` is also normalized to verification-required. |
| Resend verification code | Implemented, needs reliability hardening | `/auth/email-verification/resend`; tests cover cooldown and provider delivery. | Already covers missing profile enumeration safety and provider rate limit. Phase 243 should add already-confirmed/provider mismatch cases. |
| Confirm verification code | Implemented, needs reliability hardening | `/auth/email-verification/confirm`; tests cover success and expired code. | Phase 243 should add already-confirmed, wrong code, missing profile, disabled user, and local/Cognito consistency checks. |
| Admin verification support lookup | Implemented basic support view | `/admin/account-verification/{user_id}` returns `support_summary`. | Exposes bounded status/policy/timestamps/count/binding state; no raw codes. |
| Parent/admin account operations verification | Implemented basic support state | `account_operations_service._profile_summary`, child verification, and `_support_state`. | Parent unverified becomes blocker; child unverified/binding issue becomes warning. |
| Password reset code flow | Implemented as Cognito forgot-password | `/auth/forgot-password`, `/auth/reset-password`; tests verify no token return. | Separate from account verification and not passwordless login. |

## Login-Code And Passwordless Classification

| Surface | Status | Evidence | v5.14 Policy |
|---------|--------|----------|--------------|
| Backend `/auth/login-code/request` | Deferred, explicit | Returns `LoginCodePolicyResponse` with `deferred_cognito_custom_auth_required`. | Keep non-token-producing unless real Cognito custom auth is implemented end to end. |
| Backend `/auth/login-code/confirm` | Deferred, explicit | Returns policy response and does not include `accessToken`. | Keep visible only as API contract/debug behavior, not a product login path. |
| Backend tests | Implemented guard | `test_login_code_policy_is_deferred_without_tokens`. | Add/keep tests that unsupported login-code attempts cannot mint tokens. |
| Frontend product login | No visible passwordless path found | `LoginForm` and auth E2E use email/password plus verification recovery. | Canonical product path remains email/password plus email verification. |

## Frontend Verification Reality

| Area | Status | Evidence | Notes |
|------|--------|----------|-------|
| Auth API calls real verification endpoints | Implemented | `authApi.ts` `resendEmailVerification` and `confirmEmailVerification`. | These functions do not use demo fallback. |
| Login verification block detection | Implemented | `isEmailVerificationRequiredError` checks 403 plus `email_verification_required`. | `LoginForm` renders `EmailVerificationPanel` when blocked. |
| Registration verification panel | Implemented | `RegisterConfirmationStep` and auth E2E show code/resend actions after register returns no token. | User sees "not signed in yet" copy. |
| Expired and rate-limited messaging | Implemented basic UX | `EmailVerificationPanel` maps expired/rate-limited errors; E2E covers both. | Phase 245 can refine support-needed states and admin visibility. |
| Demo fallback | Demo-only, bounded by env | `authApi.ts` uses `allowDemoFallback` for login/register/current-user failures only. | Verification endpoints do not silently demo-fallback. Phase 244 should ensure demo fallback cannot mask production auth policy. |

## Externally Blocked Evidence

| Evidence | Status | Blocker |
|----------|--------|---------|
| Live Cognito sign-up email delivery | Externally blocked | Requires approved deployment credentials, configured Cognito clients, delivery domain, and environment access. |
| Live resend/confirm smoke | Externally blocked | Requires real test account lifecycle and email inbox access. |
| Custom auth/passwordless rollout | Out of scope unless explicitly approved | Requires Cognito custom auth triggers, secure challenge storage, frontend UX, and release gate. |

## Canonical v5.14 Contract

- Email/password remains the canonical product login path.
- Registration creates a Cognito account and local profile, then returns no access token while email verification is required.
- Unverified accounts must not receive tokens from login or registration responses.
- Resend and confirm operate through Cognito sign-up confirmation and update bounded local verification state.
- Login-code/passwordless remains deferred and must not mint tokens or appear as a product-supported login path.
- Support/admin views may expose status, policy, timestamps, resend eligibility, counters, binding state, and audited support actions only.
- Release evidence must separate local deterministic tests from externally blocked live Cognito/email smoke.

## Phase 243 Backlog From Audit

- Add backend coverage for already-confirmed confirmation, wrong code, missing profile, disabled/rate-limited users, and provider/local consistency.
- Make resend/confirm responses consistently support-safe and machine-readable where needed by frontend/admin support.
- Ensure account operations verification state exposes enough bounded evidence for support without leaking secrets.
