---
phase: 227
name: Usage Action Taxonomy And Ledger Contract
status: complete
completed: 2026-07-04
---

# Phase 227 Summary: Usage Action Taxonomy And Ledger Contract

## Completed

- Added centralized `UsageActionDefinition` taxonomy in `usage_ledger_service.py`.
- Preserved the existing `question_submission` action and daily question counter contract.
- Added governed v5.11 action candidates for chat messages, hint requests, question teacher-help, conversation teacher-help, practice answers, lesson completion, assignment lifecycle events, and reviewed assignment generation.
- Added `build_usage_idempotency_key`, `get_usage_action_definition`, `list_usage_action_definitions`, `safe_usage_metadata`, and shared privacy flags.
- Added tests for taxonomy coverage, question compatibility, idempotency, and metadata privacy filtering.

## Files Changed

- `src/stoa/services/usage_ledger_service.py`
- `tests/test_usage_ledger.py`

## Verification

- `.venv/bin/python -m pytest tests/test_usage_ledger.py -q` — passed, 7 tests.
- `.venv/bin/python -m ruff check src/stoa/services/usage_ledger_service.py tests/test_usage_ledger.py` — passed.

## Deferred

- Route-level chat and teacher-help ledger writes are deferred to Phase 228.
- Practice/generation route writes are deferred to Phase 229.
- Multi-action summary aggregation is deferred to Phase 230.
