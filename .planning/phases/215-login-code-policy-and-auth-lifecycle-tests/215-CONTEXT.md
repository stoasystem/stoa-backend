# Phase 215: Login Code Policy And Auth Lifecycle Tests - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 215 resolves passwordless login-code behavior and verifies that standard Cognito auth lifecycle flows still work.

</domain>

<decisions>
## Implementation Decisions

### Login Code Policy
- Login-code/passwordless is deferred because production support requires Cognito custom auth triggers capable of minting real Cognito tokens.
- Placeholder login-code endpoints may exist only to return explicit non-production policy responses.
- No endpoint stores or validates local login codes.
- No login-code response includes `accessToken`.

### Compatibility
- Forgot-password and reset-password continue to use Cognito forgot/confirm APIs.
- Standard verified password login remains supported.
- Unverified password login remains blocked by email verification policy.

### the agent's Discretion
Use HTTP 200 policy responses with `status=deferred` because the important production boundary is that no token is minted or implied.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Forgot/reset tests already verify no token return.
- Auth response tests can assert absence of `accessToken` in login-code policy responses.

### Established Patterns
- Frontend-facing auth responses use camelCase and bounded policy strings.

### Integration Points
- `/auth/login-code/request`
- `/auth/login-code/confirm`
- Existing `/auth/forgot-password`, `/auth/reset-password`, `/auth/login`

</code_context>

<specifics>
## Specific Ideas

State the required future implementation path: Cognito custom auth triggers.

</specifics>

<deferred>
## Deferred Ideas

Actual passwordless login-code support is deferred until Cognito trigger infrastructure and replay/rate-limit storage are explicitly designed.

</deferred>
