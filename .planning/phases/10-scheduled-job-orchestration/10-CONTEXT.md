# Phase 10: Scheduled Job Orchestration - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase replaces the scheduled Lambda stub with the orchestration pipeline for weekly reports. It accepts EventBridge scheduled events, defaults to the previous Zurich calendar week, discovers linked parent/student pairs, skips existing reports idempotently, runs aggregation/generation/storage/email for eligible pairs, and returns structured job counts. It does not expand parent API/frontend rendering.

</domain>

<decisions>

## Implementation Decisions

### Week Selection

- Accept explicit `week_start` or `weekStart` in event payload for tests/manual runs.
- Otherwise use EventBridge `time` when present, falling back to current time.
- Calculate the previous Zurich calendar week start with `zoneinfo.ZoneInfo("Europe/Zurich")`.

### Pair Discovery

- Discover eligible pairs by scanning local user/profile records where `role = student` and `parent_id` exists.
- Return `(parent_id, student_id)` pairs and let Phase 7 aggregation validate parent-child ownership and load metadata.
- Page through DynamoDB scan results.

### Idempotency

- Before generation, call `report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)`.
- Skip existing generated/email-sent/email-failed reports to avoid duplicate artifacts and emails.
- Count attempted only for pairs that are not skipped and enter the generation pipeline.

### Error Handling

- Treat per-pair failures as isolated job failures and continue processing remaining pairs.
- Return structured counts: attempted, generated, skipped_existing, email_sent, failed.
- Log identifiers and error classes, not full activity content.

### the agent's Discretion

The agent may add small helper functions under `src/stoa/jobs/weekly_reports.py` and tests under `tests/test_weekly_reports_job.py`.

</decisions>

<code_context>

## Existing Code Insights

### Reusable Assets

- `src/stoa/jobs/weekly_reports.py` currently returns a safe `not_implemented` response.
- `src/stoa/services/report_service.py` exposes:
  - `build_weekly_learning_payload`
  - `generate_weekly_report_content`
  - `store_and_send_weekly_report`
- `src/stoa/db/repositories/report_repo.py` exposes `get_report_for_child_by_week`.
- `src/stoa/db.dynamodb.get_table` provides scan access for pair discovery.

### Established Patterns

- Backend job/service tests use fake clients and monkeypatches.
- Existing linked-student lookup is scan-based MVP; Phase 10 can use the same convention.
- Job logs should be operational and terse.

### Integration Points

- CDK Phase 6 already targets `stoa.jobs.weekly_reports.handler`.
- Phase 11 will consume generated report statuses through parent report APIs.
- Phase 12 will broaden backend report flow verification.

</code_context>

<specifics>

## Specific Ideas

- Add `previous_zurich_week_start(now=None)`.
- Add `target_week_start_from_event(event, now=None)`.
- Add `discover_linked_parent_student_pairs()`.
- Add `run_weekly_report_job(event, now=None)` for testable orchestration and have `handler` call it.

</specifics>

<deferred>

## Deferred Ideas

- Retry policy is CDK-defined and outside this code phase.
- Rich generated report API/frontend display belongs to Phase 11.
- Full E2E backend coverage belongs to Phase 12.

</deferred>
