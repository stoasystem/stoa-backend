---
phase: 08-bedrock-report-generation
plan: 01
subsystem: backend
tags: [reports, bedrock, generation, fallback, validation]
requires:
  - phase: 07-weekly-learning-aggregation
    provides: Weekly learning aggregation payload
provides:
  - Compact Bedrock report input builder
  - Strict generated report JSON parser
  - Deterministic parent-facing fallback content
  - Focused report generation tests
affects: [reports, report-storage, scheduled-weekly-report-job]
tech-stack:
  added: []
  patterns:
    - Injected Bedrock client for testable service helpers
    - Strict generated-output schema validation before accepting model content
    - Deterministic fallback content with the same shape as generated content
key-files:
  created: []
  modified:
    - src/stoa/services/report_service.py
    - tests/test_report_service.py
key-decisions:
  - "Report generation helpers live in report_service.py next to aggregation helpers."
  - "Bedrock input sends bounded weekly report metadata, metrics, weak topics, source counts, and activity samples."
  - "Strict JSON parsing rejects markdown-wrapped, partial, missing-field, invalid-list, and unsafe internal-term output."
  - "Generation failures and rejected output return deterministic parent-facing fallback content."
patterns-established:
  - "Phase 9 can persist generated or fallback report content without re-invoking Bedrock."
requirements-completed: [AI-01, AI-02, AI-03, AI-04]
duration: 45min
completed: 2026-06-02
---

# Phase 8 Plan 01 Summary

**Bedrock report generation service with strict validation and deterministic fallback**

## Accomplishments

- Added compact structured report input generation for Bedrock.
- Added strict JSON parser for parent report output sections: summary, strengths, weak topics, recommendations, and optional teacher note.
- Added parent-facing internal-term validation for provider, model, prompt, inference, and implementation terms.
- Added Bedrock invocation using the existing Anthropic Messages body shape and backend settings.
- Added deterministic fallback report content for model failures, malformed output, or unsafe output.
- Added focused tests for compact input, strict parsing, safety rejection, injected Bedrock invocation, malformed output fallback, and Bedrock error fallback.

## Task Commits

1. **Weekly report generation service** - `9169e63` (`feat(08): add weekly report generation fallback`)

## Verification

- `uv run --extra dev pytest tests/test_report_service.py -q` - passed, 13 tests
- `uv run --extra dev ruff check src/stoa/services/report_service.py tests/test_report_service.py` - passed

## Issues Encountered

- Code review found that the first parser version accepted invalid list elements and missed some internal provider/model terms.
- Fixed by rejecting any malformed list item, requiring weak-topic objects with `topic` and `note`, adding word-boundary internal-term matching, and expanding tests.

## Next Phase Readiness

Phase 9 can persist generated content, fallback content, metadata, and artifacts without needing another generation contract change.
