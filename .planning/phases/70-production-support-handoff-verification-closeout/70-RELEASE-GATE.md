# Phase 70 Release Gate

**Status:** Planned
**Recorded at:** TBD

## Deploy Evidence

### Backend

| Field | Value |
|-------|-------|
| Workflow | Deploy Backend |
| Run ID | TBD |
| Run URL | TBD |
| Job ID | TBD |
| Head SHA | TBD |
| Status | Pending |
| Created | TBD |
| Completed | TBD |

### Frontend

| Field | Value |
|-------|-------|
| Workflow | Deploy Frontend |
| Run ID | TBD |
| Run URL | TBD |
| Job ID | TBD |
| Head SHA | TBD |
| Status | Pending |
| Created | TBD |
| Completed | TBD |

## Lambda Manifest And Runtime

| Function | State | LastUpdateStatus | LastModified | CodeSha256 | Runtime | Architecture |
|----------|-------|------------------|--------------|------------|---------|--------------|
| `stoa-api` | TBD | TBD | TBD | TBD | TBD | TBD |
| `stoa-weekly-report` | TBD | TBD | TBD | TBD | TBD | TBD |

## CDK Diff

Command:

```text
uv run cdk diff --profile stoa-prod-admin
```

Result: Pending.

Expected classification:

- No new DynamoDB table, GSI, S3 bucket, IAM expansion, Cognito resource, API Gateway route, CloudFront resource, or public artifact path.
- Lambda code asset drift may be expected if direct GitHub Lambda deploys updated code outside CDK asset deployment.

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/support_handoff_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py
```

Result: Pending.

```text
.venv/bin/python -m pytest tests/test_admin_report_ops.py -k "support_handoff or recovery_job_support_package or recovery_evidence" -q
```

Result: Pending.
