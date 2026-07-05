# Phase 268: Auth Session And Account State - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted conservative defaults

<domain>
## Phase Boundary

Implement native auth/session contracts for the mobile client. This includes Amplify/Cognito wrapping, secure storage boundaries, API token injection, account-state mapping, and sign-out cleanup hooks.
</domain>

<decisions>
## Implementation Decisions

- Use Amplify Auth as the only Cognito session source.
- Do not persist raw tokens anywhere in mobile code.
- Use SecureStore only for small metadata, not token material.
- Keep backend support-safe account state authoritative and map generic 401/403 only as fallback states.
- Add static tests because mobile dependencies are declared but not installed.
</decisions>

<code_context>
## Existing Code Insights

The adjacent web app uses `fetchAuthSession()` for bearer tokens but also has localStorage access-token storage. The native client must preserve the former and reject the latter.
</code_context>

<specifics>
## Specific Ideas

- Add `amplifyAuth.ts`, `authTypes.ts`, `secureSessionMetadata.ts`, `accountState.ts`, `signOutCleanup.ts`, and `mobileApiClient.ts`.
- Add `mobile/docs/AUTH.md` and focused static tests.
</specifics>

<deferred>
## Deferred Ideas

- Actual screen controls remain shell-level until data journeys are wired in Phase 269.
- Push token revoke implementation is supplied by Phase 270 and consumed by the cleanup hook.
</deferred>
