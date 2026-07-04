---
phase: 227
name: Usage Action Taxonomy And Ledger Contract
status: planned
---

# Phase 227 Plan: Usage Action Taxonomy And Ledger Contract

## Goal

Define the governed usage action taxonomy and ledger contract needed by v5.11 while preserving existing question usage behavior.

## Tasks

1. Add centralized usage action definitions in `usage_ledger_service.py`.
   - Define action names, usage types, summary groups, quota/counter semantics, default quantities, and privacy classification.
   - Preserve existing `QUESTION_SUBMISSION_ACTION`, `QUESTION_COUNTER_USAGE_TYPE`, and schema version compatibility.

2. Add reusable idempotency and metadata helpers.
   - Keep question idempotency unchanged.
   - Add generic action idempotency key construction.
   - Add safe metadata filtering so later phases cannot accidentally store raw content/provider payloads.

3. Add contract tests.
   - Verify taxonomy contains v5.11 action candidates.
   - Verify question compatibility.
   - Verify idempotency helpers.
   - Verify metadata filtering rejects raw/private fields and keeps bounded support fields.

4. Update phase artifacts and progress state.
   - Write summary and verification artifacts.
   - Commit Phase 227 work.

## Verification

- `pytest tests/test_usage_ledger.py -q`
- `python -m ruff check src/stoa/services/usage_ledger_service.py tests/test_usage_ledger.py`

## Expected Outcome

Phase 227 completes the contract layer only. New ledger writes for chat, teacher-help, practice, and generation remain deferred to later phases.
