# Phase 223 UI Spec: Email Verification UX Integration

**Status:** Approved
**Date:** 2026-07-03

## Product Surface

Phase 223 changes the existing auth surfaces:

- Registration completion state after backend-required email verification.
- Login error state when the account exists but email is not verified.
- Shared verification code and resend interaction.

## Layout Contract

- Keep auth flows inside the existing auth page/form footprint.
- Use a single compact panel for verification with:
  - small status icon,
  - concise heading,
  - one explanatory paragraph,
  - email field if editable or email summary if fixed,
  - confirmation code input,
  - primary confirm button,
  - secondary resend button,
  - tertiary login/register navigation link.
- Avoid marketing/hero additions. This is an operational account state, not a landing page.
- Buttons must not resize the layout when loading labels change.

## State Contract

Render distinct states:

- `pending_verification`: account created or login blocked, code required.
- `sent` / `accepted`: resend request accepted.
- `already_requested`: cooldown/rate-safe resend result.
- `already_verified`: account is verified; user should return to login.
- `confirmed`: verification complete; user can sign in.
- `expired_verification`: code expired; show resend path.
- invalid code/request: show retryable error without provider language.
- rate-limited: tell the user to wait before retrying.

## Copy Contract

- Use user-facing language: "Verify your email", "Enter the code we sent", "Send code again", "Email verified".
- Do not show internal words such as provider, backend, Cognito, token, endpoint, API, stack trace, or exception.
- Login blocked copy should say verification is required before sign-in and provide the same action path.
- Registration pending copy should make clear that account creation is not the same as being signed in.

## Accessibility Contract

- Code input has a label and `autoComplete="one-time-code"`.
- Status and error messages use `role="status"` or `role="alert"` as appropriate.
- Primary action remains reachable by form submit.
- Focus order stays email/code/actions, with no hidden keyboard traps.

## Visual Contract

- Use existing auth form typography and spacing.
- Use restrained success/warning/destructive colors already present in the design system.
- Use lucide icons where useful; do not add custom SVGs.
- No nested cards beyond the existing auth panel structure.

## Test Contract

- E2E or component-level browser tests must cover:
  - registration pending verification state,
  - login blocked state,
  - resend success/cooldown state,
  - confirm success state,
  - expired/invalid/rate-limited error copy.

