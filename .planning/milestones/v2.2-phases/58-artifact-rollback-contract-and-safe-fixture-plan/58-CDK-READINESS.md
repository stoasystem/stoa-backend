# Phase 58 CDK Readiness

**Status:** Existing resources are sufficient for Phase 59.
**Checked:** 2026-06-06

## Reviewed Files

- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py`

## Required Capabilities

| Capability | Required For | Current Resource | Status |
|------------|--------------|------------------|--------|
| Report metadata read/write | Rollback current artifact pointer update | Existing `stoa-main` table read/write grant to API Lambda | Sufficient |
| Conditional metadata update | Reject stale current artifact state | Existing DynamoDB conditional update pattern in report repository | Sufficient |
| Private artifact key validation | Validate rollback target stays under private prefix | Existing backend key validation and `weekly-reports/*` contract | Sufficient |
| Optional artifact read | Safe fixture or validation may read current/target JSON metadata | `stoa-api` has `s3:GetObject` on `weekly-reports/*` | Sufficient |
| Optional fixture artifact write | Safe fixture mutation smoke applies bounded artifact edit before rollback | `stoa-api` has `s3:PutObject` on `weekly-reports/*` | Sufficient |
| Optional cleanup/delete | Existing failed-write cleanup path if fixture edit write partially fails | `stoa-api` has `s3:DeleteObject` on `weekly-reports/*` | Sufficient |
| Audit rows | Store rollback preview/apply/refusal events | Existing single-table `PK=REPORT#{report_id}` partition | Sufficient |

## API Stack Finding

`ApiStack._grant_report_artifact_read_write` grants the API Lambda:

- `s3:GetObject`
- `s3:PutObject`
- `s3:DeleteObject`

Resource scope is `reports_bucket.arn_for_objects("weekly-reports/*")`.

Rollback is primarily a DynamoDB metadata pointer update. Safe-fixture mutation uses the v2.1 artifact edit path, which already writes versioned keys under `weekly-reports/*`. No IAM expansion is required.

## Storage Stack Finding

The reports bucket remains private, HTTPS-only, retained, and compatible with versioned objects under `weekly-reports/{parent_id}/{student_id}/{week_start}/versions/{version_id}/`.

Rollback must not require S3 list operations and must not delete prior versioned objects.

## Database Stack Finding

Rollback preview/apply rows and audit events can use the existing report partition model:

- `PK=REPORT#{report_id}`
- `SK=ARTIFACT_ROLLBACK_PREVIEW#{preview_id}` if persisted.
- Existing audit sort-key pattern for rollback events.

No new table or GSI is required because selected-report rollback is addressed by parent/student/week route parameters and existing report lookup.

## Decision

Phase 59 should proceed without CDK changes.

Required implementation constraints:

- Keep all artifact keys under `weekly-reports/*`.
- Do not add broad S3 list operations.
- Do not add a new bucket, table, GSI, Lambda, queue, Step Function, or public URL path.
- Re-run CDK diff during Phase 61 release gate to prove no unintended infra drift.

## Residual Risk

The rollback target set is limited by currently stored metadata. v2.2 should support immediate prior-version rollback first; richer version history may require a later metadata index or sanitized audit-derived history model.
