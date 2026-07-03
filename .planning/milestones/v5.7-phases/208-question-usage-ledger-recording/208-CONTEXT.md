# Phase 208: Question Usage Ledger Recording - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Record durable usage ledger events for successful student question quota increments without destabilizing quota enforcement.
</domain>

<decisions>
## Implementation Decisions

### Recording Path
- Generate the question id before quota enforcement so counter and ledger records share one correlation id.
- Keep `question_repo.record_daily_question_usage` as the authoritative quota gate.
- Write a ledger event only after the counter accepts the usage.
- Do not write consumed-usage ledger events for quota exhaustion.

### Retry Handling
- When `idempotencyKey` is provided, check the existing ledger event before incrementing the counter.
- If the prior question exists, return it instead of creating a new counter increment or ledger event.

### the agent's Discretion
Allow rare counter-before-ledger failures to be surfaced by reconciliation instead of weakening the existing atomic counter behavior.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `submit_question` already centralizes question quota, question row creation, OCR, and AI response update.

### Established Patterns
- Focused route tests monkeypatch repositories/services to isolate behavior.

### Integration Points
- `src/stoa/routers/questions.py`
- `tests/test_questions.py`
</code_context>

<specifics>
## Specific Ideas

Store the effective entitlement snapshot used for the quota decision on every successful ledger event.
</specifics>

<deferred>
## Deferred Ideas

Ledger events for other quota-governed actions remain future work.
</deferred>
