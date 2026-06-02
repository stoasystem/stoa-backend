# Phase 12: Backend Report Flow Verification - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase verifies the backend weekly report flow across already implemented services. It should primarily add or strengthen tests. Product behavior changes are in scope only when a verification test exposes a real defect.

Phase 12 covers backend behavior only:

- Zurich week-window calculation and scheduled job idempotency.
- Weekly aggregation for empty and mixed activity.
- Bedrock parser, compact input, and deterministic fallback.
- DynamoDB metadata plus S3 artifact writes.
- SES success/failure state transitions.
- Parent report API generated, missing, pending, failed, and email-failed responses.

It does not add frontend tests; Phase 13 owns frontend verification.

</domain>

<decisions>

## Implementation Decisions

- Prefer focused pytest tests over new abstractions.
- Add an integration-style backend test module only if it reduces duplication and makes the full flow easier to reason about.
- Keep AWS clients faked in tests; no live AWS calls.
- Verify failure ordering explicitly:
  - S3 artifact failure must prevent DynamoDB metadata writes and email sends.
  - Email failure must happen after artifacts and metadata are stored.
  - Post-claim job failures must mark `generation_failed`.
- Verify parent API responses do not expose raw generation failure messages.

## the agent's Discretion

The agent may refactor local test fixtures in `tests/test_report_service.py`, `tests/test_weekly_reports_job.py`, or `tests/test_parent_children.py` when needed to keep the verification readable.

</decisions>

<code_context>

## Existing Coverage

- `tests/test_weekly_reports_job.py` already covers:
  - Previous Zurich week start.
  - Explicit and EventBridge event week selection.
  - Linked pair discovery pagination.
  - Existing generated/email-sent/email-failed skips.
  - Atomic claim skip.
  - Successful pair processing.
  - Pair failure continuing and marking `generation_failed`.

- `tests/test_report_service.py` already covers:
  - Week window parsing.
  - Empty aggregation.
  - Mixed aggregation.
  - Compact Bedrock input.
  - Strict generated JSON parser and parent-safe internal-term rejection.
  - Bedrock malformed/error fallback.
  - S3 before metadata before SES ordering.
  - Parent-only email recipient and parent portal link.
  - SES failure marking `email_failed`.

- `tests/test_parent_children.py` already covers:
  - Parent report generated detail fields.
  - Missing state.
  - Email-failed, generation-pending, and generation-failed states.
  - Week-specific sibling guard.
  - Repository report lookup/update/claim helpers.

## Likely Verification Gaps

- A true one-pair backend flow test that exercises job orchestration through aggregation, fallback generation, storage, and email with faked repositories/clients.
- S3 failure ordering: artifact write failure should not produce DynamoDB metadata or email side effects.
- Question pagination in aggregation, since report aggregation uses `_list_all_questions`.
- Invalid EventBridge time fallback/validation behavior if not already covered.
- Consolidated Phase 12 verification artifact summarizing which requirement each test covers.

</code_context>

<specifics>

## Target Files

- `tests/test_report_flow.py`
- `.planning/phases/12-backend-report-flow-verification/12-01-PLAN.md`
- `.planning/phases/12-backend-report-flow-verification/12-01-SUMMARY.md`
- `.planning/phases/12-backend-report-flow-verification/12-VERIFICATION.md`

## Verification Commands

- `uv run --extra dev pytest tests/test_report_flow.py tests/test_weekly_reports_job.py tests/test_report_service.py tests/test_parent_children.py -q`
- `uv run --extra dev ruff check src/stoa/jobs/weekly_reports.py src/stoa/services/report_service.py src/stoa/db/repositories/report_repo.py src/stoa/routers/parents.py tests/test_report_flow.py tests/test_weekly_reports_job.py tests/test_report_service.py tests/test_parent_children.py`

</specifics>

<deferred>

## Deferred Ideas

- Live AWS smoke testing remains outside local Phase 12 because the milestone explicitly uses local fakes and CDK binding evidence.
- Frontend state verification remains Phase 13.

</deferred>
