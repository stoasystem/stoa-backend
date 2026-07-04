---
phase: 228
name: Chat And Teacher-Help Ledger Instrumentation
status: planned
---

# Phase 228 Plan: Chat And Teacher-Help Ledger Instrumentation

## Goal

Record privacy-safe, idempotent ledger events for existing successful chat and teacher-help flows.

## Tasks

1. Add a reusable generic ledger write helper.
   - Use the Phase 227 taxonomy.
   - Accept optional counter info and bounded metadata.
   - Fail closed for unsupported actions.

2. Return counter details from chat rate limiting.
   - Preserve existing 429 behavior.
   - Return period, key, value, limit, and TTL for successful increments.

3. Instrument chat/conversation routes.
   - Normal message send.
   - Pseudo-stream message send.
   - Initial message on conversation creation.

4. Instrument teacher-help routes.
   - Question escalation.
   - Conversation escalation.

5. Add focused tests.
   - Generic support-visible event write.
   - Chat event metadata/privacy.
   - Question teacher-help event.
   - Conversation teacher-help event.

## Verification

- `.venv/bin/python -m pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py -q`
- `.venv/bin/python -m ruff check src/stoa/services/usage_ledger_service.py src/stoa/services/rate_limit.py src/stoa/routers/questions.py src/stoa/routers/conversations.py tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py`
