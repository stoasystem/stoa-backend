# Phase 21: Smoke and Orphan Artifact Cleanup - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (backend cleanup phase)

<domain>
## Phase Boundary

Phase 21 adds explicit cleanup for deterministic smoke artifacts and failed partial report artifact writes. Cleanup must avoid deleting successfully generated real report artifacts and must use the prefix-scoped `s3:DeleteObject` permission deployed in Phase 20.

In scope:
- Delete the deterministic smoke JSON object after smoke readback succeeds.
- Return clear smoke cleanup status in Lambda smoke output.
- Delete the first JSON artifact when the second HTML artifact write fails.
- Test cleanup behavior without deleting successful real report artifacts.
- Deploy updated Lambda code and live-verify smoke cleanup.

Out of scope:
- Bucket lifecycle rules for real report retention.
- Broad orphan scanning/listing of the reports bucket.
- Admin retry/resend tooling, owned by Phase 22.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
- Prefer explicit cleanup over lifecycle because current smoke and partial-write cleanup targets are known object keys and do not require bucket listing.
- Treat smoke cleanup failure as a smoke failure, because Phase 21 specifically verifies cleanup behavior.
- Preserve fail-closed report metadata ordering: if cleanup after partial write fails, still raise the original storage failure and do not create report metadata or send email.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/report_artifact_service.py` centralizes artifact key building, JSON/HTML writes, JSON reads, and smoke behavior.
- `tests/test_report_artifact_service.py` already uses a fake S3 client for put/get behavior and smoke assertions.
- Phase 20 deployed `s3:DeleteObject` scoped to `weekly-reports/*` for both API and weekly report Lambdas.

### Established Patterns
- Report metadata is only saved after both artifacts write successfully.
- Smoke output records bucket, key, content type, readback status, and cleanup status without exposing content.
- Tests use focused fake clients instead of AWS for helper behavior.

### Integration Points
- `stoa.jobs.weekly_reports.handler` routes `{"job":"report_artifact_s3_smoke"}` to `run_report_artifact_s3_smoke`.
- Live verification invokes `stoa-weekly-report` directly through AWS CLI.

</code_context>

<specifics>
## Specific Ideas

Use explicit `delete_object` for the deterministic smoke key and the failed JSON partial key. Do not add S3 listing or broad lifecycle deletion in this phase.

</specifics>

<deferred>
## Deferred Ideas

- Operational retry/resend/admin visibility for Phase 22.
- Broader historical orphan discovery if support evidence later proves it is needed.

</deferred>
