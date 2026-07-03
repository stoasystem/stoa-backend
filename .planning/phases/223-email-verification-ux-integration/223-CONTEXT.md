# Phase 223: Email Verification UX Integration - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted recommended decisions

<domain>
## Phase Boundary

Make the v5.8 Cognito-backed email verification lifecycle usable in the web frontend. This phase adds typed frontend auth clients and user-visible register/login/confirm/resend states. It does not change backend entitlement, usage, verification, or account operations primitives unless a concrete frontend contract bug is found.

</domain>

<decisions>
## Implementation Decisions

### Registration Flow
- Registration success with `onboardingStatus=email_verification_required` must not set auth state or redirect as a signed-in user.
- Existing multi-step registration stays in place; the final state becomes a verification prompt when the backend requires email verification.
- Tutor `pending_review` behavior remains compatible and distinct from email verification.
- The registration confirmation state should offer code entry, resend, and a route back to login after successful verification.

### Login Blocked State
- Login errors with backend code `email_verification_required` should show a verification action path rather than a generic failure.
- The login form should keep the email value and allow resend/confirm from the same screen to reduce dead ends.
- Generic auth failures must remain sanitized and user-facing.
- Login should still only write the auth store after a real token-bearing response.

### Verification API Contract
- Add typed frontend calls for `/auth/email-verification/resend` and `/auth/email-verification/confirm`.
- Preserve structured backend error detail when available so code-specific UI states can be rendered.
- Handle `sent`, `accepted`, `already_requested`, `already_verified`, `confirmed`, invalid code, expired code, and rate-limited states.
- Do not expose provider internals or delivery implementation details in UI copy.

### Test And Safety Scope
- Focus tests on register pending verification, login blocked until verified, resend, confirm, and sanitized error states.
- Demo fallback may continue for existing demo auth flows, but verification API failures must not silently create auth state.
- Keep changes frontend-first; backend tests should only be run if a backend contract concern appears.
- UI should remain compact, form-like, and consistent with existing auth surfaces.

### the agent's Discretion
- Choose exact component/file boundaries that fit existing frontend patterns.
- Choose minimal English/German/French/Italian translation additions needed for build stability.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/Users/zhdeng/stoa-frontend/src/services/auth/authApi.ts` owns login/register/current-user API calls.
- `/Users/zhdeng/stoa-frontend/src/hooks/auth/useLoginMutation.ts` and `useRegisterMutation.ts` own auth mutation side effects.
- `/Users/zhdeng/stoa-frontend/src/components/auth/RegisterConfirmationStep.tsx` is the existing post-register confirmation surface.
- Existing UI primitives include `Button`, `Input`, `Label`, and card/badge components.

### Established Patterns
- React Query `useMutation` is used for auth writes.
- `useAuthStore.setAuth` is only called after token-bearing responses.
- `toUserFacingError` sanitizes internal terms before rendering.
- Auth pages use i18next namespaces `auth`, `common`, and `errors`.

### Integration Points
- Backend register returns `AuthResponse` with empty `accessToken` and `onboardingStatus=email_verification_required` for new non-teacher accounts.
- Backend login can return 403 detail code `email_verification_required`.
- Backend resend endpoint: `POST /auth/email-verification/resend`.
- Backend confirm endpoint: `POST /auth/email-verification/confirm`.

</code_context>

<specifics>
## Specific Ideas

- Add an email verification panel component that can be reused by registration and login blocked states.
- Preserve the email address from register/login forms and prefill verification actions.
- Add typed error helpers so code-specific states do not depend on string matching only.

</specifics>

<deferred>
## Deferred Ideas

- Passwordless/login-code UX remains deferred until the backend implements Cognito custom auth.
- Native app verification flows remain future work.
- Admin verification support UI belongs to Phase 225, not this phase.

</deferred>
