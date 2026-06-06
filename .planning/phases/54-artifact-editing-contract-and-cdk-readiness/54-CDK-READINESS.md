# Phase 54 CDK Readiness

**Status:** Existing resources are sufficient for Phase 55.
**Checked:** 2026-06-06

## Reviewed Files

- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py`

## Required Capabilities

| Capability | Required For | Current Resource | Status |
|------------|--------------|------------------|--------|
| Private report artifact reads | Load current JSON/HTML for preview/apply | `stoa-api` has `s3:GetObject` on `weekly-reports/*` | Sufficient |
| Versioned artifact writes | Write `versions/{version_id}/report.{json,html}` | `stoa-api` has `s3:PutObject` on `weekly-reports/*` | Sufficient |
| Failed partial cleanup | Best-effort delete when HTML write fails after JSON write | `stoa-api` has `s3:DeleteObject` on `weekly-reports/*` | Sufficient |
| Report metadata updates | Move current artifact pointer after writes pass | Existing `stoa-main` table read/write grant | Sufficient |
| Draft and audit rows | Store artifact edit draft/preview and append audit events | Existing single-table `PK=REPORT#{report_id}` partition | Sufficient |
| Report lookup | Admin selected-report lookup and audit timeline | Existing report repository/admin operations | Sufficient |

## Storage Stack Finding

`StorageStack` defines `StoaReportsBucket` as:

- Private with `BlockPublicAccess.BLOCK_ALL`.
- S3-managed encryption.
- `enforce_ssl=True`.
- Server access logs under `reports/`.
- `RemovalPolicy.RETAIN`.

This is compatible with versioned object writes under the existing `weekly-reports/` prefix.

## API Stack Finding

`ApiStack._grant_report_artifact_read_write` grants the API Lambda:

- `s3:GetObject`
- `s3:PutObject`
- `s3:DeleteObject`

Resource scope is `reports_bucket.arn_for_objects("weekly-reports/*")`.

The Phase 55 versioned key pattern remains under `weekly-reports/*`, so no IAM change is required.

## Database Stack Finding

`DatabaseStack` defines a retained single-table DynamoDB table with:

- Primary key: `PK`, `SK`.
- Existing `GSI-ParentId` for report lookup by parent/week.
- Read/write grants to `stoa-api` via `table.grant_read_write_data`.

Artifact edit drafts and audit rows can be stored under existing `REPORT#{report_id}` partitions without a new table or GSI because access is by selected report ID/draft ID and existing audit query patterns.

## Decision

Phase 55 should proceed without CDK changes.

Required implementation constraints:

- Keep all artifact keys under `weekly-reports/*`.
- Do not add broad S3 list operations.
- Do not add a new bucket, table, GSI, Lambda, queue, Step Function, or public URL path.
- Re-run CDK diff during Phase 57 release gate to prove no unintended infra drift.

## Residual Risk

The current audit model is application-enforced append-only in DynamoDB, not compliance-grade WORM storage. This is acceptable for v2.1 and remains a future requirement if regulatory evidence demands immutable storage.
