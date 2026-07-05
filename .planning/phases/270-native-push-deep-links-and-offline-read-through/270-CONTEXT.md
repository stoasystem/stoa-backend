# Phase 270: Native Push Deep Links And Offline Read-Through - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted conservative defaults

<domain>
## Phase Boundary

Implement native push, notification deep-link, and offline read-through contracts. This phase covers provider token registration/revocation models, route validation, TTL cache policy, and privacy guards.
</domain>

<decisions>
## Implementation Decisions

- Use Expo Notifications first.
- Register and revoke push tokens through existing backend `/notifications/push-tokens` APIs.
- Treat notification route targets as hints, never authorization.
- Offline cache is read-only and TTL-bounded.
- Keep question, teacher-help, billing, subscription, and challenge mutations online-only.
</decisions>

<code_context>
## Existing Code Insights

Backend notification routes already support list, preferences, push-token registration/revocation, read, and archive. Phase 269 defined which student and parent surfaces can be read-through cache candidates.
</code_context>

<specifics>
## Specific Ideas

- Add notification API, push permission/token service, deep-link validation service, offline cache policy, read-through cache helper, docs, and tests.
</specifics>

<deferred>
## Deferred Ideas

- Physical-device push smoke requires Expo project IDs plus FCM/APNs/EAS credentials and is recorded as a release blocker.
</deferred>
