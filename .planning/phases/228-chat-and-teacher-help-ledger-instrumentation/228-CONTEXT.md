# Phase 228: Chat And Teacher-Help Ledger Instrumentation - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Instrument existing successful chat/conversation and teacher-help request flows with privacy-safe, idempotent usage ledger events. This phase uses the Phase 227 taxonomy and should not change parent/admin summary aggregation yet.

</domain>

<decisions>
## Implementation Decisions

### Chat Coverage
- Cover existing conversation send endpoints: normal messages, pseudo-streamed messages, and initial conversation messages.
- Record chat ledger only after the student message and assistant response are persisted.
- Reuse existing chat counter behavior and attach counter metadata to ledger events.
- Idempotency should use the persisted student message ID unless a future route adds request keys.

### Teacher-Help Coverage
- Cover both question escalation (`/questions/{id}/request-teacher`) and conversation escalation (`/teacher-help/request`).
- Record teacher-help as support-visible, not quota-enforced.
- Record only after the question/conversation is accepted for escalation.
- Duplicate or rejected requests should not consume additional usage.

### Privacy Boundary
- Store bounded metadata only: conversation ID, question ID, subject, grade, request ID, status, and counter linkage.
- Do not store chat content, teacher message text, assistant content, prompt text, or provider payloads.
- Keep raw system messages as an existing product behavior, but do not copy them into usage ledger metadata.

### the agent's Discretion
The agent may introduce helper functions in route modules to keep instrumentation local and testable.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `usage_ledger_service` now exposes action constants, idempotency helpers, safe metadata, and privacy flags.
- `rate_limit.check_and_record_chat` already increments `USAGE#{student}/CHAT#{day}` but currently returns no counter info.
- `questions.request_teacher` already marks questions escalated and emits notification/dispatch events.
- `conversations._send_message_impl` persists student and assistant messages and returns their IDs.

### Established Patterns
- Question ledger writes happen after successful quota/counter work.
- Route tests monkeypatch service helpers rather than hitting real DynamoDB.
- Failed route validation raises `HTTPException` before mutation.

### Integration Points
- `src/stoa/routers/conversations.py`
- `src/stoa/routers/questions.py`
- `src/stoa/services/rate_limit.py`
- `tests/test_usage_ledger.py` and focused route tests.

</code_context>

<specifics>
## Specific Ideas

- Add a generic `record_usage_event` helper that later phases can reuse.
- Make `check_and_record_chat` return counter period/key/value so chat events can include reconciliation hints.

</specifics>

<deferred>
## Deferred Ideas

- Hint and practice route instrumentation remains Phase 229.
- Multi-action parent/admin summaries remain Phase 230.

</deferred>
