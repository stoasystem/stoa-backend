# Phase 279: AI Cost Latency Provider Observability - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, conservative defaults

<domain>
## Phase Boundary

Summarize AI provider cost, latency, refusal, fallback, and failure metadata without raw prompt exposure.
</domain>

<decisions>
## Implementation Decisions

- Provider observability remains metadata-only.
- Budget and provider-blocked states are explicit.
</decisions>

<code_context>
## Existing Code Insights

v5.18 BI patterns require low-cardinality, support-safe evidence.
</code_context>

<specifics>
## Specific Ideas

Add provider event summary and forbidden evidence validation.
</specifics>

<deferred>
## Deferred Ideas

Live provider cost feed remains blocked until provider telemetry is configured.
</deferred>
