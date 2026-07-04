# Phase 244 Plan: Login Code And Passwordless Policy Resolution

## Goal

Remove ambiguity around login-code/passwordless behavior and ensure unsupported login-code attempts cannot produce tokens.

## Steps

1. Verify product-visible frontend login surfaces do not expose passwordless login.
2. Verify backend login-code endpoints remain explicit deferred policy responses.
3. Tighten backend tests so request and confirm responses include deferred status, policy, reason, and no `accessToken`.
4. Document the canonical policy and remaining out-of-scope custom-auth work.

## Non-Goals

- Do not implement Cognito custom auth.
- Do not add a frontend passwordless entry point.
- Do not remove the backend policy endpoints; they are useful as explicit unsupported-contract guards.
