# Architecture: v1.2 S3 Report Artifact Infrastructure

**Question:** How should S3 report artifact storage verification, key-building helper behavior, and smoke tests integrate with the existing backend/infra architecture?

## Current Data Flow

1. EventBridge Scheduler invokes the existing weekly report Lambda handler, `stoa.jobs.weekly_reports.handler`.
2. `run_weekly_report_job` discovers parent/student pairs, checks existing DynamoDB report metadata, writes a `generation_claimed` record, builds the weekly payload, generates content, then calls `report_service.store_and_send_weekly_report`.
   - Evidence: [src/stoa/jobs/weekly_reports.py](/Users/zhdeng/stoa-backend/src/stoa/jobs/weekly_reports.py:25)
3. `store_and_send_weekly_report` builds a report record, renders JSON and HTML artifacts, writes both artifacts to S3, then writes DynamoDB metadata and sends email.
   - JSON is written first with `ContentType="application/json"`.
   - HTML is written second with `ContentType="text/html; charset=utf-8"`.
   - Metadata is written only after both S3 writes succeed.
   - Evidence: [src/stoa/services/report_service.py](/Users/zhdeng/stoa-backend/src/stoa/services/report_service.py:323), [tests/test_report_service.py](/Users/zhdeng/stoa-backend/tests/test_report_service.py:429), [tests/test_report_flow.py](/Users/zhdeng/stoa-backend/tests/test_report_flow.py:256)
4. Parent report API routes currently read DynamoDB metadata only. They do not expose S3 keys, presigned report URLs, or private S3 objects to the frontend.
   - Evidence: [src/stoa/routers/parents.py](/Users/zhdeng/stoa-backend/src/stoa/routers/parents.py:591)
5. CDK already defines a private retained reports bucket and injects it into both the FastAPI API Lambda and weekly report Lambda.
   - Reports bucket: [storage_stack.py](/Users/zhdeng/stoa-infra/stacks/storage_stack.py:45)
   - API Lambda env/grant: [api_stack.py](/Users/zhdeng/stoa-infra/stacks/api_stack.py:52)
   - Weekly Lambda env/grant: [api_stack.py](/Users/zhdeng/stoa-infra/stacks/api_stack.py:83)

## Proposed Integration Points

### Infrastructure

No new AWS resource is needed. Treat `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` and `/Users/zhdeng/stoa-infra/stacks/api_stack.py` as the source of truth and verify the existing wiring:

| Component | Current State | v1.2 Action |
|-----------|---------------|-------------|
| `StoaReportsBucket` | Private S3 bucket, public access blocked, S3-managed encryption, access logs, retain policy | Verify synth/diff and deployed state |
| `StoaApiFunction` | Receives `S3_REPORTS_BUCKET`; has `reports_bucket.grant_read_write` | Verify CDK template; do not add a public smoke route |
| `StoaWeeklyReportFunction` | Receives `S3_REPORTS_BUCKET`; has `reports_bucket.grant_read_write` | Add runtime smoke event path because this Lambda owns report artifact writes |
| `settings.s3_reports_bucket` | Existing env-backed backend setting | Verify Lambda env overrides local default |

### Backend Service

Use the existing report service as the integration boundary. Do not create a broad new storage subsystem.

Recommended modification:

- Promote `_report_artifact_keys` into a small public helper such as `build_report_artifact_keys(parent_id, student_id, week_start)`.
- Keep `build_weekly_report_record` and `build_weekly_report_claim` calling that helper so generated metadata and claim metadata cannot diverge.
- Validate `week_start` as an ISO date and fail closed for blank `parent_id`, `student_id`, or `week_start`. Current `_safe_s3_segment` sanitizes and falls back to `"unknown"`; that is acceptable for display links but too quiet for production artifact keys.
- Keep IDs as canonical backend user IDs, not email addresses.
- Keep artifacts private; the backend may read them later, but the frontend should continue using parent API responses.

Key contract recommendation:

```text
weekly-reports/{safe_parent_id}/{safe_student_id}/{iso_week_start}/report.json
weekly-reports/{safe_parent_id}/{safe_student_id}/{iso_week_start}/report.html
```

This matches current code in [src/stoa/services/report_service.py](/Users/zhdeng/stoa-backend/src/stoa/services/report_service.py:754). The milestone note also mentions `reports/...`; do not support both conventions. If the shorter `reports/...` prefix is preferred, make that a deliberate one-time code and test migration before deployment.

### Metadata Repository

No DynamoDB schema or index change is needed. The existing metadata fields already store:

- `s3_key`
- `html_s3_key`
- `json_s3_key`

Evidence: [src/stoa/services/report_service.py](/Users/zhdeng/stoa-backend/src/stoa/services/report_service.py:422)

### Parent API

Do not change parent report routes for this slice. They should continue to:

- Resolve the authenticated parent.
- Verify child ownership.
- Read report metadata through `report_repo`.
- Return generated/missing/pending/failed/email-failed state from backend data.

If a later phase needs full JSON artifact reads, add the S3 read behind these same ownership checks. Do not let the frontend fetch private S3 directly.

### Smoke Test Hook

Add a narrow internal smoke path to the weekly report Lambda, not a new API Gateway route:

```json
{
  "source": "stoa.smoke",
  "job": "report_artifact_s3_smoke",
  "parent_id": "smoke-parent",
  "student_id": "smoke-student",
  "week_start": "2026-06-01"
}
```

The smoke function should:

- Build keys through the same report artifact key helper.
- Put a small JSON object to the reports bucket.
- Get the object back and verify content.
- Optionally put/get HTML too if the milestone wants both formats proven.
- Return bucket, keys, content types, and readback result.
- Avoid public URLs, ACL changes, and frontend access.

This proves the weekly report Lambda role, env var, S3 bucket, and key contract together without adding product surface area.

## Build Order

1. **Lock key contract in backend tests**
   - Add tests for full key values, not only `.endswith("/report.json")`.
   - Cover safe segment behavior and invalid/blank IDs.
   - Decide now whether prefix is `weekly-reports/` or `reports/`.

2. **Harden helper behavior**
   - Promote the key helper or add a minimal report artifact helper.
   - Make claim metadata and generated metadata use the same helper.
   - Keep S3 write order and metadata-after-S3 behavior unchanged.

3. **Add smoke implementation**
   - Add `run_report_artifact_s3_smoke` in the report service or a small smoke module.
   - Dispatch to it only from `stoa.jobs.weekly_reports.handler` when the explicit smoke event is present.
   - Keep normal scheduled weekly report behavior unchanged.

4. **Add verification tests**
   - Unit tests: key helper, content types, write order, no metadata/email when S3 fails.
   - Flow tests: weekly report job still claims, generates, writes artifacts, writes metadata, sends/updates email status.
   - CDK verification: synth/diff confirms env vars and IAM grants for both Lambdas.

5. **Run deployed smoke**
   - Deploy or confirm deployed stack.
   - Invoke `stoa-weekly-report` with the smoke event.
   - Confirm put/get succeeds against `S3_REPORTS_BUCKET`.
   - Confirm no frontend or public S3 read is required.

## Verification Strategy

### Static/CDK Verification

Run from `/Users/zhdeng/stoa-infra`:

```bash
uv run cdk synth
uv run cdk diff StoaApiStack
```

Verify:

- `StoaApiFunction` has `S3_REPORTS_BUCKET`.
- `StoaWeeklyReportFunction` has `S3_REPORTS_BUCKET`.
- Both Lambdas have reports bucket read/write IAM.
- The reports bucket is not replaced.

### Backend Test Verification

Run focused backend tests:

```bash
uv run pytest tests/test_report_service.py tests/test_report_flow.py tests/test_weekly_reports_job.py
```

Add/keep assertions for:

- Canonical full keys.
- JSON and HTML content types.
- S3 writes before DynamoDB metadata and SES.
- S3 failure does not create metadata or send email.
- Weekly flow still stores `json_s3_key` and `html_s3_key`.

### Runtime Smoke Verification

Invoke the weekly report Lambda with the explicit smoke event after deployment. Expected result:

- The Lambda reads `S3_REPORTS_BUCKET` from its environment.
- It writes and reads a private test artifact using the canonical helper-built key.
- It returns success without requiring public object access.

For the API Lambda, CDK template verification is enough in this slice because no current API route reads report artifacts from S3. Add API runtime S3 smoke only when an API S3 read path exists behind parent/admin authorization.

## Risks

| Risk | Consequence | Mitigation |
|------|-------------|------------|
| CDK code is correct but not deployed | Runtime Lambda still lacks env var or S3 permissions | Require synth/diff plus deployed smoke before extending report operations |
| Key prefix mismatch: `weekly-reports/` vs `reports/` | Artifacts and metadata split across conventions | Pick one now; recommendation is current `weekly-reports/` unless intentionally migrated |
| Silent `"unknown"` key segment | Bad input can create shared or misleading artifact paths | Validate key inputs and fail closed for production artifact keys |
| S3 write partially succeeds | First artifact may exist without metadata if second write fails | Keep metadata-after-both-writes; smoke/test retry behavior; tolerate orphan cleanup as operational follow-up |
| API Lambda runtime S3 access remains unproven | Future API artifact reads may fail despite CDK-looking-correct | Defer runtime API smoke until a real API read path exists, then test through authorized backend route |
| Frontend direct S3 assumption | Private bucket access breaks or leaks implementation detail | Keep parent frontend on backend report routes only |
| Overbroad S3 read/write grant | Larger blast radius than key-scoped report access | Accept for v1.2 verification; consider `weekly-reports/*` IAM scoping in a later security hardening phase |
