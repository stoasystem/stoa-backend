# Phase 35 Context: Async Resend Job Backend

**Milestone:** v1.6 Report Recovery Operations Hardening
**Date:** 2026-06-04
**Status:** Complete

## Goal

Admins need bounded async `email_failed` resend jobs with fixed targets, progress, cooperative cancellation, per-target results, and audit-backed worker execution.

## Starting Point

Phase 34 introduced shared recovery service paths and append-only report/job audit timelines. The remaining incident-wide operation risk was that selected bulk resend still ran synchronously inside the API Lambda and could not support durable progress, cancellation, or worker-side stop conditions.

## Constraints

- Reuse the existing `stoa-api` and `stoa-weekly-report` Lambdas.
- Reuse the existing DynamoDB single-table design.
- Do not add SQS, Step Functions, a new table, a new worker Lambda, or a new GSI in Phase 35.
- Async jobs must stay metadata-only and must not expose raw report artifacts, private S3 keys, presigned URLs, or tokens.
- API Lambda must not perform incident-wide SES work; it should persist a job and invoke the weekly report Lambda asynchronously.

## Implementation Notes

- `report_recovery_job_service` owns preview/create/cancel/worker orchestration.
- Admin API creates jobs only after a preview token confirms the current target scope.
- Job snapshots are persisted as `REPORT_RECOVERY_JOB#{job_id}` summary and `TARGET#...` rows.
- Worker events route through `stoa.jobs.weekly_reports.handler` with `job=report_recovery_resend_email`.
- Infra grants `stoa-api` scoped invoke permission to `stoa-weekly-report` and injects `WEEKLY_REPORT_FUNCTION_NAME`.
