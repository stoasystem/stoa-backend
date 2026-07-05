# Phase 274: Device QA Matrix And Mobile Smoke - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, conservative defaults

<domain>
## Phase Boundary

Define physical-device QA targets, required mobile smoke coverage, redacted evidence expectations, and blocked local device state.
</domain>

<decisions>
## Implementation Decisions

- Require at least one supported iOS phone and one supported Android phone before claiming device readiness.
- Evidence must be redacted screenshots/logs/notes only.
- Push smoke remains blocked without push credentials.
</decisions>

<code_context>
## Existing Code Insights

v5.19 implemented route/auth/push/offline contracts but no physical devices or signed builds were recorded.
</code_context>

<specifics>
## Specific Ideas

Add `mobile/src/release/deviceQa.ts`.
</specifics>

<deferred>
## Deferred Ideas

Actual device execution is blocked until credentials, installable builds, and physical devices exist.
</deferred>
