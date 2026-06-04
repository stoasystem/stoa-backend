# Phase 34 Context: Recovery Service Extraction And Audit Foundation

**Milestone:** v1.6 Report Recovery Operations Hardening
**Date:** 2026-06-04
**Status:** Complete

## Goal

Existing single-report and selected bulk recovery actions must use one shared backend service path and produce append-only audit evidence without exposing private report artifacts.

## Starting Point

Phase 33 completed the recovery contract and Lambda dist guard. Before Phase 34, admin report operations were implemented inline in `src/stoa/routers/admin.py`:

- single `resend_email`
- selected bulk `resend_email`
- single `retry_generation`
- mutable report summary status fields such as `last_operation`, `last_operation_by`, and error metadata

The system had no append-only audit rows and no audit timeline read API.

## Constraints

- Reuse the existing DynamoDB single table.
- Keep report artifacts private; do not expose raw HTML/JSON, S3 keys, presigned URLs, auth tokens, or browser artifacts in admin audit responses.
- Phase 34 audit immutability is application-enforced by conditional DynamoDB writes. It is not compliance-grade WORM storage.
- AUDIT-05 cancelled recovery-path coverage remains Phase 35 because cancellation exists only after async jobs are implemented.

## Implementation Notes

- `src/stoa/services/report_recovery_service.py` owns shared resend/retry behavior and audit event construction.
- Audit rows are stored under the relevant report or job partition with `SK=AUDIT#{event_at}#{event_id}`.
- `report_repo.put_report_audit_event` and `put_recovery_job_audit_event` use `ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)"`.
- Report-local and job-local audit timelines are exposed through admin-only metadata APIs.
