# Phase 273: Internal Build Distribution Pipeline - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, conservative defaults

<domain>
## Phase Boundary

Define internal EAS build commands, artifact evidence schema, and rollback instructions without claiming that builds ran locally.
</domain>

<decisions>
## Implementation Decisions

- Development and preview EAS builds are internal-distribution profiles.
- Build evidence must include commit/profile/platform/environment metadata and stay secret-safe.
</decisions>

<code_context>
## Existing Code Insights

`mobile/eas.json` already contains development and preview internal profiles.
</code_context>

<specifics>
## Specific Ideas

Add `mobile/src/release/buildDistribution.ts`.
</specifics>

<deferred>
## Deferred Ideas

Actual EAS build artifacts require configured credentials and are blocked in local source-only execution.
</deferred>
