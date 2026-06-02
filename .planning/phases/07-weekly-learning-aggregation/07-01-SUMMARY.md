---
phase: 07-weekly-learning-aggregation
plan: 01
subsystem: backend
tags: [reports, aggregation, dynamodb, parent-portal]
requires:
  - phase: 06-cdk-report-automation-foundation
    provides: Weekly report Lambda infrastructure and reports bucket env/permissions
provides:
  - Weekly learning aggregation service
  - Deterministic empty weekly report payloads
  - Focused report service tests
affects: [reports, weekly-report-job, bedrock-report-generation]
tech-stack:
  added: []
  patterns:
    - Service-level aggregation with repository monkeypatch tests
    - Timestamp-free records are skipped instead of fabricated
key-files:
  created:
    - src/stoa/services/report_service.py
    - tests/test_report_service.py
  modified: []
key-decisions:
  - "Weekly report aggregation lives in report_service.py rather than parent route helpers."
  - "Aggregation output includes parent/student metadata, week window, metrics, weak topics, activities, and source counts."
  - "Malformed or timestamp-free source records are excluded from weekly activity instead of receiving fallback dates."
patterns-established:
  - "Weekly report payloads use deterministic ordering for weak topics and activity events."
requirements-completed: [AGGR-01, AGGR-02]
duration: 35min
completed: 2026-06-02
---

# Phase 7 Plan 01 Summary

**Weekly learning aggregation service for linked parent/student/week report payloads**

## Accomplishments

- Added `src/stoa/services/report_service.py`.
- Added week-window parsing and conservative ISO timestamp filtering.
- Added linked student validation using the existing local parent/child profile convention.
- Aggregated weekly questions, AI-resolved counts, teacher help requests, practice lesson completions, mistakes, weak topics, conversations, and activity events.
- Added deterministic empty payload behavior with zero counts and empty arrays.
- Added focused tests that monkeypatch repositories/table access and do not require AWS.

## Task Commits

1. **Weekly report aggregation service** - `f3f3c2d` (`feat(07): add weekly report aggregation service`)

## Verification

- `uv run --extra dev pytest tests/test_report_service.py -q` - passed, 5 tests
- `uv run --extra dev ruff check src/stoa/services/report_service.py tests/test_report_service.py` - passed

## Issues Encountered

None.

## Next Phase Readiness

Phase 8 can consume the aggregation payload as compact structured input for Bedrock report generation and deterministic fallback content.
