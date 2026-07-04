---
phase: 228
name: Chat And Teacher-Help Ledger Instrumentation
status: complete
completed: 2026-07-04
---

# Phase 228 Summary: Chat And Teacher-Help Ledger Instrumentation

## Completed

- Added generic `record_usage_event` for governed non-question usage actions.
- Made chat/hint rate-limit helpers return counter period/key/value metadata while preserving existing rejection behavior.
- Instrumented conversation chat messages for normal sends, pseudo-stream sends, and initial conversation messages.
- Instrumented question teacher-help escalation with support-visible ledger events.
- Instrumented conversation teacher-help escalation with support-visible ledger events.
- Added focused tests for generic event privacy, question teacher-help, chat message instrumentation, and conversation teacher-help instrumentation.

## Files Changed

- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/services/rate_limit.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/conversations.py`
- `tests/test_usage_ledger.py`
- `tests/test_questions.py`
- `tests/test_conversations.py`
- `tests/test_teacher_reply_sla.py`
- `tests/test_notifications.py`

## Verification

- `.venv/bin/python -m pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py tests/test_teacher_reply_sla.py::test_request_teacher_records_request_and_queue_timestamps tests/test_notifications.py::test_request_teacher_emits_tutor_and_admin_events -q` — passed, 22 tests.
- `.venv/bin/python -m ruff check src/stoa/services/usage_ledger_service.py src/stoa/services/rate_limit.py src/stoa/routers/questions.py src/stoa/routers/conversations.py tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py tests/test_teacher_reply_sla.py tests/test_notifications.py` — passed.

## Deferred

- Hint, practice, lesson, assignment, and generation instrumentation remain Phase 229.
- Multi-action summaries and account operations aggregation remain Phase 230.
