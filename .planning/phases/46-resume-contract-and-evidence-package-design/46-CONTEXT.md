# Phase 46 Context

**Phase:** 46 - Resume Contract And Evidence Package Design
**Milestone:** v1.9 Recovery Resume And Support Evidence Packages
**Created:** 2026-06-05

## Context

v1.8 left recovery jobs capable of two bounded async operation types:

- `resend_email`
- `retry_generation`

Each recovery job already stores:

- job metadata under `REPORT_RECOVERY_JOB#{job_id}`
- stable target snapshots under the job partition
- target results such as `pending`, `success`, `refused`, `not_found`, `failed`, and `skipped_cancelled`
- job audit events under the job partition

v1.9 adds two operational capabilities:

1. Create a new recovery job from a prior job's failed/refused/not_found/skipped targets.
2. Generate a support-safe incident evidence package that can be shared internally without private report artifact exposure.

## Existing Capabilities

- `report_repo.list_recovery_job_targets(job_id, limit, last_key)` can page through stable source targets.
- `report_recovery_job_service._execute_job` already processes pending targets generically by job type.
- `report_recovery_evidence_service.build_export_response` already emits metadata-only job/target/audit summaries.
- Admin router already protects recovery job and evidence routes with admin auth.

## Constraints

- Resume must not scan all reports.
- Resume must derive targets from the stable source job target snapshot.
- Resume must preserve source job linkage in new job metadata and audit.
- Evidence package must remain metadata-only and bounded.
- Production smoke for v1.9 remains read-only unless a named safe fixture is approved.

