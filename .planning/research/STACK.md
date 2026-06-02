# STACK Research: v1.2 S3 Report Artifact Infrastructure

**Project:** STOA Backend / Infra  
**Slice:** v1.2 S3 Report Artifact Infrastructure  
**Researched:** 2026-06-03  
**Overall confidence:** HIGH for CDK/S3/Lambda stack guidance; MEDIUM for deployed runtime state until `cdk diff` and deployed smoke tests are run.

## Existing Stack Evidence

These are code facts from the requested files, not external recommendations.

| Area | Evidence | Conclusion |
|------|----------|------------|
| Reports bucket | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py:46` defines `StoaReportsBucket`; lines 49-54 set name `stoa-reports-{account}`, `BlockPublicAccess.BLOCK_ALL`, `BucketEncryption.S3_MANAGED`, server access log prefix `reports/`, and `RemovalPolicy.RETAIN`. | Existing CDK already has a private retained reports bucket suitable for report artifacts. |
| API Lambda env | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:52-64` injects `S3_REPORTS_BUCKET` into `stoa-api`. | No backend settings addition is required for the API Lambda. |
| API Lambda IAM | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:67-70` grants `reports_bucket.grant_read_write(self.api_function)`. | API Lambda can read/write report objects after deploy. |
| Weekly report Lambda env | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:83-91` injects `S3_REPORTS_BUCKET` into `stoa-weekly-report`. | No env var addition is required for the report Lambda. |
| Weekly report Lambda IAM | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:94-95` grants `reports_bucket.grant_read_write(self.weekly_report_function)`. | Weekly report Lambda can read/write report objects after deploy. |
| App wiring | `/Users/zhdeng/stoa-infra/app.py:34-48` passes `reports_bucket=storage.reports_bucket` into `ApiStack`. | Stack wiring is present in source. |
| Backend setting | `src/stoa/config.py:24-27` exposes `settings.s3_reports_bucket`, defaulting locally to `stoa-reports`. | Production must rely on CDK-injected `S3_REPORTS_BUCKET`; no new config field is needed. |
| Artifact writes | `src/stoa/services/report_service.py:337-349` writes JSON and HTML artifacts with boto3 `put_object`, using `settings.s3_reports_bucket` and explicit `ContentType`. | Write helper behavior exists, though embedded in `report_service.py` rather than a separate artifact service. |
| Artifact key builder | `src/stoa/services/report_service.py:754-759` currently builds keys as `weekly-reports/{parent_id}/{student_id}/{week_start}/report.json|html`; `src/stoa/services/report_service.py:762-764` sanitizes key segments. | There is a key contract, but it differs from the milestone recommendation of `reports/...`. Lock one prefix before adding smoke assertions. |
| Tests | `tests/test_report_service.py:456-468` verifies two S3 writes, bucket, content types, and JSON body; `tests/test_report_flow.py:256-275` verifies S3 failure prevents metadata/email progression. | Unit coverage exists for writes and failure ordering, but not for deployed Lambda read/write or anonymous/private access. |

## Official Guidance

| Topic | Official guidance | Implementation implication |
|-------|-------------------|----------------------------|
| Private bucket/public access | AWS recommends turning on all four S3 Block Public Access settings for buckets that should not be public. | Current `BlockPublicAccess.BLOCK_ALL` on the reports bucket matches the private artifact requirement. Keep report artifacts backend-served; do not expose public S3 URLs. |
| CDK grants | AWS CDK grant helpers give resource access to grantable entities such as Lambda functions; `Bucket.grant_read_write` supports an optional object key pattern. | Current `grant_read_write(lambda)` is enough for this slice. For tighter hardening, use `reports_bucket.grant_read_write(function, "weekly-reports/*")` after the key prefix is locked. |
| Lambda configuration | Lambda environment variables are intended for behavior/configuration values and are surfaced to runtime code. AWS recommends Secrets Manager for secrets. | `S3_REPORTS_BUCKET` is a non-secret resource name and is appropriate as a Lambda env var. |
| Object key naming | S3 is flat storage; prefixes and `/` delimiters are only key naming conventions. AWS lists alphanumeric, hyphen, underscore, and period as generally safe key characters and notes a 1,024-byte key limit. | Keep deterministic slash-delimited keys. The current `_safe_s3_segment` behavior is consistent with safe-key guidance. Avoid emails and arbitrary user text in keys. |
| PutObject | Boto3 `put_object` adds an object to a bucket; `ContentType` is an accepted parameter; objects are private by default unless ACLs/policies grant access. | Current JSON/HTML writes with explicit `ContentType` are correct. Do not add ACLs. |
| GetObject | `GetObject` requires `s3:GetObject`; if the object is missing, S3 returns 404 only when the caller also has `s3:ListBucket`, otherwise 403. | If backend reads JSON artifacts, implement error handling that can tolerate either 403 or 404 for missing keys depending on final IAM scope. |
| Encryption | AWS states all new S3 object uploads are encrypted at rest by default with SSE-S3; CDK `BucketEncryption.S3_MANAGED` explicitly configures SSE-S3. | No KMS key is required for this slice unless STOA adds a compliance requirement for customer-managed keys. Adding KMS would add Lambda KMS permissions and smoke-test complexity. |
| Access logging | AWS supports S3 server access logging and recommends bucket policy over ACLs for log delivery when applicable. | Existing `server_access_logs_bucket` is appropriate. Verify synth/deploy includes log delivery permissions if CDK feature flags affect bucket policy generation. |
| HTTPS-only access | AWS Security Hub S3.5 expects S3 bucket policies to deny non-SSL requests using `aws:SecureTransport`; CDK exposes `enforce_ssl`. | Recommended CDK hardening: add `enforce_ssl=True` to `StoaReportsBucket` unless it would create an unwanted bucket policy diff. This is a best-practice change, not a functional blocker for Lambda S3 SDK access. |

## Required/Not Required Stack Changes

### Required

1. **No new AWS service, bucket, table, queue, or Lambda is required.** Existing S3 + Lambda + CDK + boto3 are sufficient.
2. **Deploy/synth verification is required.** Source code has the required wiring, but the runtime stack may still be older. Run `cdk synth` and `cdk diff StoaApiStack` before treating the environment as ready.
3. **Lock the S3 key prefix.** Current backend uses:

   ```text
   weekly-reports/{parent_id}/{student_id}/{week_start}/report.json
   weekly-reports/{parent_id}/{student_id}/{week_start}/report.html
   ```

   The v1.2 milestone text recommends:

   ```text
   reports/{parent_id}/{student_id}/{week_start}/report.json
   reports/{parent_id}/{student_id}/{week_start}/report.html
   ```

   Recommendation: keep the existing `weekly-reports/...` prefix unless there is a product reason to rename it. It is already implemented and tested. If the milestone wants `reports/...`, change `_report_artifact_keys` and update tests before adding deployed smoke checks.

4. **Add read helper only if this slice verifies reads through backend code.** Existing code writes artifacts; I did not find a `get_object` artifact read helper in `report_service.py`. If v1.2 requires backend read verification, add a small helper around `s3.get_object(Bucket=settings.s3_reports_bucket, Key=key)` and JSON decode.
5. **Add deployed smoke test path.** Unit tests are not enough for the quality gate. The deployed smoke must prove the Lambda execution role can write and read a private key.

### Recommended Hardening

| Change | Why | Priority |
|--------|-----|----------|
| Add `enforce_ssl=True` to `StoaReportsBucket`. | Aligns with AWS Security Hub S3.5 HTTPS-only bucket policy guidance. | Medium |
| Scope grants to the final artifact prefix, e.g. `grant_read_write(function, "weekly-reports/*")`. | Reduces blast radius while staying in CDK. | Medium after key prefix is locked |
| Keep `BucketEncryption.S3_MANAGED`; do not add KMS yet. | SSE-S3 is explicit and sufficient for this slice; KMS would require new permissions and extra failure modes. | Keep current |
| Keep report objects private and backend-mediated. | Block Public Access plus IAM role reads matches parent portal authorization needs. | High |

### Not Required

| Item | Reason |
|------|--------|
| New reports bucket | Existing `StoaReportsBucket` is present and wired. |
| Public bucket policy, public ACLs, CloudFront, or presigned frontend GET URLs | This slice is for private report artifacts; parent authorization should remain in backend routes. |
| S3 CORS for reports bucket | Frontend should not directly read/write private report artifacts. |
| New Python dependency | boto3 is already used in `report_service.py`; Lambda AWS SDK access is adequate. |
| KMS CMK | No stated compliance requirement; SSE-S3 is already explicit. |
| DynamoDB schema change | Artifact object storage is independent of report metadata indexes for this slice. |

## Verification Notes

### CDK Verification

Run from `/Users/zhdeng/stoa-infra`:

```bash
uv run cdk synth
uv run cdk diff StoaApiStack
```

Check for:

- `StoaReportsBucket` retains `BlockPublicAccess`, SSE-S3, access logs, and retain policy.
- `stoa-api` environment contains `S3_REPORTS_BUCKET`.
- `stoa-weekly-report` environment contains `S3_REPORTS_BUCKET`.
- Both Lambda execution roles include S3 read/write permissions for the reports bucket, preferably prefix-scoped after the key contract is finalized.
- No replacement of the existing reports bucket.

### Backend Verification

Run from `/Users/zhdeng/stoa-backend`:

```bash
uv run pytest tests/test_report_service.py tests/test_report_flow.py
```

Add or update focused tests for:

- Canonical artifact keys use the final prefix exactly.
- Key segments sanitize unsafe characters and never include parent/student email addresses.
- JSON artifact writes use `ContentType="application/json"`.
- HTML artifact writes use `ContentType="text/html; charset=utf-8"`.
- Optional read helper calls `get_object`, decodes JSON, and handles missing-key 403/404 behavior intentionally.

### Deployed Smoke Test

Use a deterministic test key under the final prefix, for example:

```text
weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json
```

Expected result:

- Lambda writes a JSON object to `settings.s3_reports_bucket`.
- Lambda reads the same object back using `GetObject`.
- Anonymous/public HTTP access is denied; no public URL is required.
- Smoke cleanup deletes the object only if delete permission is intentionally available. If grants are read/write only and delete is not present, use an overwrite-safe smoke key and leave lifecycle/manual cleanup as an operational decision.

## Source Links

Primary external sources only:

- AWS CDK permissions guide, grant helpers and Lambda grantable behavior: https://docs.aws.amazon.com/cdk/v2/guide/permissions.html
- AWS CDK S3 `Bucket` API, `grant_read_write`, key-pattern grants, `enforce_ssl`, encryption, object ownership: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/Bucket.html
- AWS CDK S3 `BucketProps`, `enforce_ssl` and Security Hub S3.5 reference: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketProps.html
- Amazon S3 Block Public Access: https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- Amazon S3 object key naming guidelines: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html
- Amazon S3 encryption: https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html
- Amazon S3 server access logging: https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html
- AWS Lambda environment variables: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
- Boto3 S3 `put_object`: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/bucket/put_object.html
- Boto3 S3 `get`: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/object/get.html
- AWS Security Hub S3 controls, S3.5 HTTPS-only bucket policy: https://docs.aws.amazon.com/securityhub/latest/userguide/s3-controls.html
