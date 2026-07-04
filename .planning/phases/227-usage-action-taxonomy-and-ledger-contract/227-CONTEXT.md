# Phase 227: Usage Action Taxonomy And Ledger Contract - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Define the governed usage action taxonomy and ledger contract for v5.11 before adding new usage writes. This phase should make action names, usage types, quota semantics, success/skip rules, idempotency, and privacy metadata explicit while preserving the existing `question_submission` ledger behavior.

</domain>

<decisions>
## Implementation Decisions

### Action Taxonomy Shape
- Keep `question_submission` as the canonical backward-compatible question action.
- Add centralized action definitions in `usage_ledger_service` so later instrumentation phases reuse one contract instead of scattered literals.
- Distinguish quota-enforced actions from support-visible-only actions through explicit counter key/type metadata.
- Include current backend action candidates: chat message, hint request, question teacher-help request, conversation teacher-help request, practice answer, lesson completion, assignment lifecycle, and reviewed generation.

### Idempotency And Success Rules
- Use deterministic action-specific idempotency key builders instead of raw client payloads.
- Existing question idempotency remains request-key-or-question-id based.
- Chat/hint/teacher-help/practice/generation keys should be based on generated IDs, challenge IDs, assignment IDs, or stable request tokens when available.
- Failed, read-only, preview, draft, passive catalog, and administrative support reads are excluded from consuming ledger writes.

### Privacy Boundary
- Ledger events and summaries must never store raw prompts, answers, teacher messages, generated content, provider payloads, verification codes, tokens, or private artifact keys.
- Store bounded metadata only: subject, source type, resource IDs, outcome/status, counter linkage, entitlement context, and request correlation IDs.
- Mark privacy flags consistently across all events.
- Event response helpers should expose safe fields only.

### Compatibility
- Existing parent/admin usage response fields remain available for question quota compatibility.
- Multi-action additions should be additive through `actions`, `groups`, or metadata rather than replacing current top-level question fields.
- Reconciliation should preserve the current question counter behavior and add read-only ledger totals for support-visible actions.
- Later phases can wire routes after this contract exists.

### the agent's Discretion
The agent may choose exact helper names and dataclass/TypedDict shape, but the contract must be simple enough for existing tests and routers to adopt incrementally.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/usage_ledger_service.py` already owns question ledger event construction, idempotency, reconciliation, parent summaries, and redacted event responses.
- `src/stoa/db/repositories/usage_ledger_repo.py` already supports `put_usage_event`, `get_usage_event`, and action/period event listing.
- `src/stoa/services/rate_limit.py` already increments daily chat and hint counters.
- Existing routes include `questions.request_teacher`, `conversations.send_message`, `conversations.teacher_help_router`, `practice.get_hint`, `practice.submit_answer`, and `practice.complete_lesson`.

### Established Patterns
- Ledger events use DynamoDB single-table rows under `USAGE_LEDGER#{student_id}` with `EVENT#{action}#{quota_period}#{idempotency_key}` sort keys.
- Question counter enforcement remains separate under `USAGE#{student_id}/QUESTION#{day}`.
- Parent/admin account operations consume `build_student_usage_summary`.
- Tests use an in-memory `FakeTable` monkeypatched through `usage_ledger_repo.get_table`.

### Integration Points
- Phase 228 should instrument chat/conversation and teacher-help routes.
- Phase 229 should instrument practice/hint/lesson/assignment/generation routes.
- Phase 230 should extend summaries and reconciliation responses after new events are written.

</code_context>

<specifics>
## Specific Ideas

- Prefer a small `UsageActionDefinition` dataclass and exported constants over broad framework changes.
- Add tests that inspect taxonomy fields, idempotency helpers, safe metadata filtering, and question backward compatibility.

</specifics>

<deferred>
## Deferred Ideas

- Actual route instrumentation is deferred to Phases 228 and 229.
- Multi-action summary aggregation is deferred to Phase 230.
- Any brand-new chat/hint product surface is out of scope unless it already exists as a backend route.

</deferred>
