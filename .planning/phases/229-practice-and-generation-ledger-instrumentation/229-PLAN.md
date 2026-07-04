---
phase: 229
name: Practice And Generation Ledger Instrumentation
status: planned
---

# Phase 229 Plan: Practice And Generation Ledger Instrumentation

## Goal

Record privacy-safe ledger events for eligible practice, lesson, assignment, and reviewed generation flows.

## Tasks

1. Instrument practice routes.
   - Hint request after counter and hint success.
   - Practice answer after attempt persistence.
   - Lesson completion after progress persistence.

2. Instrument adaptive assignment/generation service.
   - Manual reviewed assignment creation.
   - Automation-created assignment creation.
   - Assignment lifecycle side effects: start, complete, skip, archive.

3. Add bounded metadata keys where needed.
   - Assignment ID, source type, exercise ID, batch/candidate/policy IDs.
   - No prompts, answers, notes, rationales, provider payloads, or private artifact keys.

4. Verify with focused tests and Ruff.

## Verification

- `.venv/bin/python -m pytest tests/test_curriculum_analytics.py::test_practice_answer_records_usage_ledger_without_raw_answer tests/test_curriculum_analytics.py::test_lesson_completion_records_usage_ledger tests/test_curriculum_analytics.py::test_hint_request_records_counter_backed_usage_ledger tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger -q`
- `.venv/bin/python -m pytest tests/test_usage_ledger.py -q`
- `.venv/bin/python -m ruff check src/stoa/routers/practice.py src/stoa/services/adaptive_learning_service.py src/stoa/services/usage_ledger_service.py tests/test_curriculum_analytics.py tests/test_adaptive_learning.py`
