# Domain Pitfalls: v1.2 S3 Report Artifact Infrastructure

**Domain:** Private S3 report artifacts written/read by Lambda and defined in CDK  
**Researched:** 2026-06-03  
**Overall confidence:** HIGH for AWS/CDK mechanics verified with official docs; HIGH for STOA-specific findings from local source inspection.

## Context Snapshot

Current infra already defines a private reports bucket in `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` with `BlockPublicAccess.BLOCK_ALL`, S3-managed encryption, server access logs, and `RemovalPolicy.RETAIN`.

Current API stack already passes the bucket to both Lambda functions:

- API Lambda receives `S3_REPORTS_BUCKET` and `reports_bucket.grant_read_write(self.api_function)`.
- Weekly report Lambda receives `S3_REPORTS_BUCKET` and `reports_bucket.grant_read_write(self.weekly_report_function)`.
- `/Users/zhdeng/stoa-infra/app.py` passes `storage.reports_bucket` into `ApiStack`.

Current backend already writes JSON and HTML artifacts in `src/stoa/services/report_service.py`, but the implemented key prefix is `weekly-reports/...`, while the v1.2 milestone text recommends `reports/...`. v1.2 should resolve that mismatch explicitly.

## Critical Pitfalls

### Pitfall 1: CDK Source Looks Correct, But Deployed Lambda Still Lacks Runtime Wiring

**Why It Matters:**  
`S3_REPORTS_BUCKET` and IAM grants in CDK do not prove the deployed Lambda configuration or role policy has been updated. Lambda environment variables live in function configuration, and AWS notes they are literal strings available to runtime code. If production still runs an older Lambda config, backend code will silently fall back to the local default `stoa-reports`, causing writes to the wrong/nonexistent bucket or `AccessDenied`.

**Prevention:**  
Treat this milestone as deploy verification, not code inspection only:

- Run `uv run cdk synth` and inspect the synthesized `StoaApiFunction` and `StoaWeeklyReportFunction` environment blocks.
- Run `uv run cdk diff StoaApiStack` and confirm no report bucket replacement.
- After deploy, verify both Lambda configurations contain `S3_REPORTS_BUCKET=stoa-reports-{account}`.
- Add a backend config check that fails in `ENVIRONMENT=production` if `s3_reports_bucket` is the placeholder default `stoa-reports`.

**Phase/Requirement Implication:**  
Phase 1 / CDK verification. Blocks "Confirm `S3_REPORTS_BUCKET` is injected" and "Prove deployed Lambda read/write access."

**Source Links:**  
[AWS Lambda environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html), [AWS CDK permissions and grants](https://docs.aws.amazon.com/cdk/v2/guide/permissions.html), [CDK S3 BucketGrants read_write](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketGrants.html)

### Pitfall 2: Key Contract Drift Between Roadmap, Code, Tests, and Stored Metadata

**Why It Matters:**  
The milestone recommends:

```text
reports/{parent_id}/{student_id}/{week_start}/report.json
reports/{parent_id}/{student_id}/{week_start}/report.html
```

Current code writes:

```text
weekly-reports/{parent_id}/{student_id}/{week_start}/report.json
weekly-reports/{parent_id}/{student_id}/{week_start}/report.html
```

If v1.2 documents one convention while `report_service.py` stores another, future readers, smoke tests, restore tooling, and any artifact read helper will disagree about the canonical object location.

**Prevention:**  
Choose one canonical prefix in v1.2 and enforce it everywhere. Given v1.1 already shipped current code and tests only assert suffixes, prefer blessing `weekly-reports/` unless there is a migration reason to rename. Add tests for the full exact key, not only `endswith("/report.html")`. Store the same key in DynamoDB metadata and smoke-test the same key format.

**Phase/Requirement Implication:**  
Phase 2 / artifact contract. Directly maps to "Lock the private S3 key convention for report artifacts."

**Source Links:**  
Local source: `src/stoa/services/report_service.py` `_report_artifact_keys`; milestone file `.planning/milestones/s3-report-artifact-infrastructure.md`

### Pitfall 3: Placeholder Bucket Defaults Mask Missing Production Configuration

**Why It Matters:**  
`src/stoa/config.py` defaults `s3_reports_bucket` to `stoa-reports`, while CDK creates `stoa-reports-{account}`. A default is useful locally, but in Lambda it can hide missing env injection until the first S3 write fails. Because the reports bucket is account-qualified in CDK, `stoa-reports` is not the production bucket name.

**Prevention:**  
Keep the local default, but make production validation strict:

- In production startup or the report artifact helper, reject empty or placeholder `settings.s3_reports_bucket`.
- Unit-test that `ENVIRONMENT=production` cannot use the placeholder.
- In smoke tests, log the resolved bucket name without exposing report content.

**Phase/Requirement Implication:**  
Phase 1 / runtime configuration. Supports "Confirm backend settings already expose `settings.s3_reports_bucket`" and makes that confirmation meaningful.

**Source Links:**  
[AWS Lambda environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html), local source: `src/stoa/config.py`, `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`

### Pitfall 4: Private S3 Bucket Accidentally Treated Like a Frontend Asset Host

**Why It Matters:**  
Report artifacts contain student/parent learning data and should not be publicly readable. S3 Block Public Access is designed to override public policies and permissions, and current CDK uses `BlockPublicAccess.BLOCK_ALL`. If later work exposes public URLs, enables bucket website hosting, or adds `public-read` ACLs/policies, the privacy model breaks.

**Prevention:**  
Keep report artifacts backend-mediated:

- No public bucket policy.
- No S3 static website hosting for reports.
- No frontend direct S3 fetch.
- No presigned report URLs unless a later requirement explicitly designs authorization, TTL, and audit behavior.
- Smoke test should prove Lambda can read/write private objects, not that a browser can fetch them.

**Phase/Requirement Implication:**  
Phase 2 / artifact contract and Phase 4 / smoke test. Reinforces "private S3 report artifact key contract."

**Source Links:**  
[Amazon S3 Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html), [S3 Object Ownership and ACL guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership)

### Pitfall 5: ACL Usage Reintroduced Through `put_object`

**Why It Matters:**  
Modern S3 defaults to Bucket owner enforced Object Ownership, where ACLs are disabled and access is controlled by policies. Adding `ACL="public-read"` or cross-account ACL assumptions to `put_object` can fail or conflict with the private-bucket model. Current `report_service.py` does not set ACLs, which is correct for this slice.

**Prevention:**  
Make "no ACLs on report artifacts" part of the artifact helper contract. Unit-test fake S3 calls to assert no `ACL` parameter is passed. Rely on IAM role grants and bucket policy, not object ACLs.

**Phase/Requirement Implication:**  
Phase 3 / backend helper coverage. Prevents a common regression when developers copy image upload or public asset code.

**Source Links:**  
[S3 Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership), [Boto3 PutObject notes on bucket owner enforced ACLs](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)

### Pitfall 6: IAM Permissions Are Either Too Broad Forever or Too Narrow for Verification

**Why It Matters:**  
`reports_bucket.grant_read_write(...)` is acceptable for this hardening slice because both Lambdas currently need artifact writes and reads. But leaving unrestricted bucket-wide read/write forever is broader than necessary for report objects. Conversely, a too-narrow policy can break `HeadObject`/read-back verification: AWS documents that `HEAD` needs `s3:GetObject`, and missing-object errors differ depending on `s3:ListBucket`.

**Prevention:**  
Use a two-step approach:

- v1.2: verify current `grant_read_write` works for both Lambdas.
- Follow-up hardening: narrow object access to the canonical prefix, e.g. `weekly-reports/*`, using CDK object key patterns or explicit IAM statements.
- Smoke tests should validate `PutObject` plus `GetObject` on a known key. Avoid depending on negative missing-object semantics unless the test also controls `ListBucket`.

**Phase/Requirement Implication:**  
Phase 1 / CDK verification and Phase 4 / smoke checks. Add a future security hardening note if not narrowing in v1.2.

**Source Links:**  
[CDK S3 BucketGrants read_write and object key patterns](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketGrants.html), [S3 HeadObject permissions and 403/404 behavior](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html), [IAM least privilege best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

### Pitfall 7: Smoke Test Uses List/Public URL Instead of the Actual Runtime Contract

**Why It Matters:**  
The application contract is "Lambda can write and read a private object." A smoke test that lists bucket contents, checks console visibility, or fetches an unsigned public URL tests the wrong behavior. S3 now provides strong read-after-write consistency, so a direct `PutObject` followed by `GetObject` on the exact key is a valid runtime verification.

**Prevention:**  
Implement a one-off smoke operation from the same deployed role/path that production uses:

```text
weekly-reports/smoke/parent-test/student-test/2026-06-01/report.json
```

Expected checks:

- Lambda writes JSON with `ContentType=application/json`.
- Lambda reads the same key back immediately.
- The object is not fetched through an unsigned public URL.
- Smoke keys are clearly prefixed and can be cleaned up manually or by lifecycle later.

**Phase/Requirement Implication:**  
Phase 4 / deployed smoke test. This is the main acceptance proof for "Lambda can write/read private report artifacts."

**Source Links:**  
[Amazon S3 strong consistency](https://aws.amazon.com/s3/consistency/), [S3 PutObject required permissions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html), [S3 HeadObject permissions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)

### Pitfall 8: Partial Writes Leave Orphaned or Inconsistent Report Artifacts

**Why It Matters:**  
Current `store_and_send_weekly_report` writes JSON, then HTML, then DynamoDB metadata, then email. This correctly stores before email, but if one S3 write succeeds and the next write or DynamoDB write fails, artifacts can be orphaned or metadata can point to only part of the artifact set. S3 strong consistency means reads after successful writes are reliable, but it does not make the multi-step workflow transactional.

**Prevention:**  
Make artifact writes idempotent and deterministic:

- Use stable keys based on `(parent_id, student_id, week_start)`.
- Overwrite the same JSON/HTML keys on retry.
- Put DynamoDB metadata only after both artifact writes succeed.
- Add a test for S3 failure after the first `put_object` and confirm no email is sent.
- Add operational guidance that orphaned smoke/report objects under the canonical prefix are tolerable and can be reconciled by metadata.

**Phase/Requirement Implication:**  
Phase 3 / helper behavior and Phase 4 / verification. Extends current tests, which cover email failure ordering but not S3 partial failure.

**Source Links:**  
[Amazon S3 strong consistency](https://aws.amazon.com/s3/consistency/), local source: `src/stoa/services/report_service.py` `store_and_send_weekly_report`

### Pitfall 9: Server Access Logs Treated as Immediate Acceptance Evidence

**Why It Matters:**  
Current CDK enables server access logs for the reports bucket. That is useful for audit, but AWS describes S3 server access logging as best-effort. Logs can be delayed or incomplete for real-time validation. A milestone smoke test that waits for access logs as proof will be flaky.

**Prevention:**  
Use direct Lambda write/read success and CloudWatch Lambda logs as acceptance evidence. Treat S3 server access logs as retrospective audit data, not the pass/fail mechanism for v1.2.

**Phase/Requirement Implication:**  
Phase 4 / smoke checks. Prevents a slow or flaky verification loop.

**Source Links:**  
[S3 server access logging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html), local source: `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`

### Pitfall 10: Encryption Expectations Drift Beyond Current CDK

**Why It Matters:**  
Current CDK uses `BucketEncryption.S3_MANAGED`, and AWS states S3 encrypts new objects by default with SSE-S3. That is enough for this private artifact hardening slice. If a later requirement switches to SSE-KMS, Lambda roles also need KMS decrypt/encrypt permissions; otherwise S3 access can fail even when S3 IAM actions look correct.

**Prevention:**  
For v1.2, document "SSE-S3 / S3-managed encryption is the expected encryption mode." Do not add per-object SSE-KMS headers in backend code unless CDK also defines the key and grants both Lambdas KMS permissions. In smoke output, optionally capture the object metadata encryption header for evidence.

**Phase/Requirement Implication:**  
Phase 1 / CDK verification and Phase 4 / smoke checks. KMS is out of scope unless explicitly added as a security hardening phase.

**Source Links:**  
[S3 default server-side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html), [CDK BucketGrants KMS behavior](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketGrants.html)

## Moderate Pitfalls

### Pitfall 11: Lambda Package Drift From Gitignored `dist`

**Why It Matters:**  
Infra deploys use `../stoa-backend/dist` as the Lambda asset. If the deploy package was not rebuilt after backend report artifact changes, CDK can deploy correct infrastructure with stale Python code. The milestone context already notes `dist` is gitignored and CI must build it.

**Prevention:**  
Make the verification runbook rebuild `stoa-backend/dist` before `cdk synth/diff/deploy`, or require the existing CI deploy job that builds the asset. The post-deploy smoke test should identify the handler version or at least exercise the new helper path.

**Phase/Requirement Implication:**  
Phase 1 / deployment readiness and Phase 4 / smoke test.

**Source Links:**  
Local source: `/Users/zhdeng/stoa-infra/stacks/api_stack.py` Lambda `Code.from_asset("../stoa-backend/dist")`; `.planning/PROJECT.md` infrastructure context

### Pitfall 12: Unsafe or Colliding Key Segments

**Why It Matters:**  
Current `_safe_s3_segment` replaces unsupported characters with `-`. That avoids raw email addresses and unsafe path separators, but it can also collapse different values to the same segment if identifiers contain unusual characters. The project intends canonical backend user identifiers, so this is probably low risk, but it should not be left implicit.

**Prevention:**  
Require parent/student IDs to be canonical backend IDs, not emails or display names. Validate `week_start` as ISO date before key construction. Add test cases for IDs containing `/`, whitespace, and email-like input to confirm expected sanitization or rejection.

**Phase/Requirement Implication:**  
Phase 2 / key contract and Phase 3 / helper tests.

**Source Links:**  
Local source: `src/stoa/services/report_service.py` `_safe_s3_segment`, `_report_artifact_keys`

### Pitfall 13: Report Artifacts Expose More Data Than Parent APIs Should Return

**Why It Matters:**  
JSON artifacts include activities and generated content. Even if S3 is private, any backend read path must still enforce parent-child ownership before returning artifact contents. Prior milestones made `/parents/me/...` ownership checks a core invariant; S3 reads must not bypass it.

**Prevention:**  
Keep frontend report views backed by authorized backend routes. If a future route reads JSON artifacts from S3, it must first resolve the local parent profile and verify the requested child is linked before `GetObject`.

**Phase/Requirement Implication:**  
Phase 3 / artifact read helper if added; otherwise carry as follow-up warning for any future S3 artifact read route.

**Source Links:**  
Local source: `src/stoa/routers/parents.py`, `src/stoa/services/report_service.py`; project decision in `.planning/PROJECT.md`

## Phase-Specific Warnings

| Phase / Requirement | Likely Pitfall | Mitigation |
|---|---|---|
| Phase 1: CDK and runtime config verification | CDK code is correct but deployed Lambda env/role is stale | `cdk synth`, `cdk diff`, deploy confirmation, then inspect deployed Lambda config |
| Phase 1: report bucket permissions | `grant_read_write` works but remains broader than future least privilege | Accept for v1.2; record follow-up to restrict to canonical prefix |
| Phase 2: key convention | `reports/` vs `weekly-reports/` disagreement persists | Bless current `weekly-reports/` or migrate deliberately; assert exact keys in tests |
| Phase 3: backend helper/tests | Tests only check suffix and happy path | Add exact-key, no-ACL, content-type, production bucket validation, and S3 partial-failure tests |
| Phase 4: deployed smoke | Smoke test checks public URL/listing/access logs instead of real contract | Use Lambda `PutObject` + immediate `GetObject` on known private smoke key |
| Future artifact read routes | S3 read bypasses parent-child authorization | Resolve parent profile and verify child ownership before any `GetObject` |

## Recommended v1.2 Prevention Checklist

- [ ] Decide canonical prefix: prefer `weekly-reports/` unless migration is intentional.
- [ ] Add exact-key tests for JSON and HTML artifact writes.
- [ ] Add test that production cannot use placeholder `stoa-reports`.
- [ ] Add fake S3 test asserting no `ACL` parameter is sent.
- [ ] Add S3 partial-failure test proving no email is sent when artifact storage fails.
- [ ] Run CDK synth/diff and verify both Lambdas receive `S3_REPORTS_BUCKET`.
- [ ] Confirm deployed Lambda env vars and IAM role policies after deploy.
- [ ] Run deployed private-object smoke test using Lambda write/read, not public URL access.
- [ ] Record follow-up least-privilege narrowing to the canonical report prefix if not done in v1.2.

## Source Index

- AWS Lambda environment variables: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
- AWS CDK permissions and grants: https://docs.aws.amazon.com/cdk/v2/guide/permissions.html
- CDK S3 BucketGrants: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketGrants.html
- Amazon S3 Block Public Access: https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- Amazon S3 Object Ownership / ACLs: https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership
- Amazon S3 default encryption: https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html
- Amazon S3 strong consistency: https://aws.amazon.com/s3/consistency/
- Amazon S3 PutObject API: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
- Amazon S3 HeadObject API: https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html
- Amazon S3 server access logging: https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html
- IAM least privilege best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
