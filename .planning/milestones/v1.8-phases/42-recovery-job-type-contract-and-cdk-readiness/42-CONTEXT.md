# Phase 42 Context

**Phase:** 42 - Recovery Job Type Contract And CDK Readiness
**Milestone:** v1.8 Incident Generation Retry Jobs
**Created:** 2026-06-05
**Status:** Complete

## Inputs

- v1.6 shipped async `resend_email` recovery jobs with durable job/target/audit records.
- v1.7 shipped metadata-only recovery evidence export and production read-only browser smoke.
- Single-report `retry_generation` already exists in `report_recovery_service.retry_report_generation`.
- `stoa-api` can invoke `stoa-weekly-report` asynchronously.
- `stoa-weekly-report` has DynamoDB read/write, report bucket read/write, SES, and Bedrock permissions.

## Decision

v1.8 will add `retry_generation` as a second recovery job type using the existing job platform.

No Step Functions, SQS, new worker Lambda, table, bucket, or GSI is required for the bounded MVP.

## Production Safety Boundary

Implementation may add mutation-capable APIs and UI controls, but Phase 45 production smoke remains read-only unless a named safe fixture and explicit mutation approval path exists.

