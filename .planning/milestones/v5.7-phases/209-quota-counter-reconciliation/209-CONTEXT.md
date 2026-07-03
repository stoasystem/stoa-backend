# Phase 209: Quota Counter Reconciliation - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Compare daily quota counter rows with usage ledger totals and report reconciliation state safely and repeatably.
</domain>

<decisions>
## Implementation Decisions

### Reconciliation Model
- Reconcile by student/action/day.
- Classify `matched`, `ledger-missing`, `counter-missing`, and `count-mismatch`.
- Default to read-only preview.
- Permit explicit bounded repair for missing/stale counters by setting the counter to the ledger total.

### the agent's Discretion
Do not attempt to synthesize missing ledger rows from counters; that would fabricate per-event history.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing counter rows live at `USAGE#{student_id}/QUESTION#{day}`.
- Ledger rows are queryable by `USAGE_LEDGER#{student_id}` and action/day prefix.

### Established Patterns
- Admin support endpoints already use read-only service wrappers with explicit mutation routes when needed.

### Integration Points
- `usage_ledger_service.reconcile_question_usage`
- `GET /admin/usage/reconciliation`
</code_context>

<specifics>
## Specific Ideas

Repair is opt-in through `repair=true` and reports whether anything changed.
</specifics>

<deferred>
## Deferred Ideas

Automated scheduled reconciliation and repair queues remain out of scope.
</deferred>
