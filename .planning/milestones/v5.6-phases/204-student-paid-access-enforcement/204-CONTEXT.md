# Phase 204: Student Paid Access Enforcement - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Make student question submission quota use effective entitlement instead of only the student's local `subscription_tier`.

</domain>

<decisions>
## Implementation Decisions

### Quota Integration
- Resolve entitlement during question submission after loading the student profile.
- Keep `_check_daily_limit` backward compatible for existing tests and callers.
- Use entitlement limits when provided; otherwise fall back to the existing tier-to-limit mapping.

### Denial Behavior
- Preserve the existing 429 status and message shape.
- Append blocking reason only when entitlement supplies one.

### Persistence
- Store the entitlement snapshot on the question item for support/debug context.

### the agent's Discretion
- Do not introduce a usage ledger in this phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `question_repo.record_daily_question_usage` is already atomic.
- `Settings` already exposes free, standard, and premium daily question limits.

### Established Patterns
- Question submission stores broad metadata on the question item.

### Integration Points
- `src/stoa/routers/questions.py`.

</code_context>

<specifics>
## Specific Ideas

Quota behavior should remain stable for existing free-tier students.

</specifics>

<deferred>
## Deferred Ideas

Ledger/reconciliation events remain v5.7 scope.

</deferred>
