# Phase 269: Student And Parent Core Mobile Journeys - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted conservative defaults

<domain>
## Phase Boundary

Implement typed mobile adapters and screen contracts for student and parent journeys using real backend endpoints. This phase does not attempt full native visual completion or offline implementation.
</domain>

<decisions>
## Implementation Decisions

- Keep backend endpoints authoritative.
- Model screen states explicitly: loading, ready, empty, blocked, stale, and error.
- Keep question, billing, teacher-help, and quota-consuming mutations online-only.
- Add English/Chinese label fixtures for mobile text-fit coverage.
</decisions>

<code_context>
## Existing Code Insights

Backend router paths are available for `/students`, `/practice`, `/questions`, `/parents`, and `/notifications`. The mobile client should use these paths directly through the authenticated API client from Phase 268.
</code_context>

<specifics>
## Specific Ideas

- Add `studentApi.ts`, `parentApi.ts`, `studentScreens.ts`, `parentScreens.ts`, `journeyState.ts`, journey docs, and static tests.
</specifics>

<deferred>
## Deferred Ideas

- Runtime UI data fetching hooks can be added after mobile dependencies are installed.
- Offline cache storage is implemented in Phase 270.
</deferred>
