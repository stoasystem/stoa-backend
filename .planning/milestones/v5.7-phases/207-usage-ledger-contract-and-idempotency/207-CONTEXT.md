# Phase 207: Usage Ledger Contract And Idempotency - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Define a durable, privacy-safe usage ledger contract for quota-governed actions, starting with student question submissions.
</domain>

<decisions>
## Implementation Decisions

### Ledger Contract
- Store one event per consumed quota action under `USAGE_LEDGER#{student_id}` with deterministic `EVENT#{action}#{quota_period}#{idempotency_key}` sort keys.
- Use `question_submission` as the first action and align `quota_period` to the existing UTC daily question counter.
- Include actor/student, parent context, action, quantity, counter key, request/question correlation, entitlement snapshot, timestamps, and privacy flags.
- Exclude raw question content, answer content, private image/S3 keys, provider secrets, invoice internals, and unredacted billing payloads.

### Idempotency
- Accept optional client `idempotencyKey`; otherwise generate a per-question key.
- Treat duplicate ledger writes as idempotent duplicates, not new consumed usage events.
- For explicit retries, look up the existing ledger event before incrementing the counter and return the existing question when available.

### the agent's Discretion
Use existing repository/service patterns and keep the atomic daily counter as the quota enforcement primitive.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `question_repo.record_daily_question_usage` owns atomic quota enforcement.
- `entitlement_service.resolve_student_entitlement` returns effective plan/source/limits.
- Parent/admin subscription surfaces already expose effective entitlement summaries.

### Established Patterns
- Single-table DynamoDB rows use explicit `PK`/`SK` prefixes and small repository helpers.
- API responses use camelCase where they are frontend/support-facing.

### Integration Points
- `src/stoa/routers/questions.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/services/entitlement_service.py`
</code_context>

<specifics>
## Specific Ideas

Write ordering is `counter_then_ledger`; reconciliation is responsible for detecting rare ledger/counter drift.
</specifics>

<deferred>
## Deferred Ideas

Full v5.9 operations console and analytics warehouse export remain out of scope.
</deferred>
