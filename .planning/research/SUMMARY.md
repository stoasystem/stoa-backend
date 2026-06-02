# Project Research Summary

**Project:** STOA Backend
**Domain:** v1.2 S3 report artifact infrastructure and verification
**Researched:** 2026-06-03
**Confidence:** HIGH for source-level stack, feature, architecture, and pitfall findings; MEDIUM for deployed AWS runtime state until synth/diff/deployed smoke evidence is captured.

## Executive Summary

STOA is a parent-facing learning platform backend where weekly report artifacts contain sensitive student and parent learning data. Experts should build this slice as private, backend-mediated artifact storage: S3 remains non-public, Lambda roles write/read objects through IAM, report metadata stays in DynamoDB, and parent-facing APIs continue to enforce parent-child ownership before returning report state.

The research converges on a verification and hardening milestone, not a greenfield build. CDK source already defines a private retained reports bucket, injects `S3_REPORTS_BUCKET` into both API and weekly report Lambdas, and grants read/write access. Backend code already writes JSON and HTML report artifacts with correct content types. v1.2 should verify this wiring in synth/diff/deployed runtime, lock the artifact key contract, harden helper behavior, and add a Lambda-context private-object smoke test.

The main product/architecture risk is key contract drift: the milestone document recommends `reports/...`, while shipped backend code uses `weekly-reports/...`. Recommendation: canonically bless `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` because it is already implemented and aligns with v1.1 behavior. If `reports/...` is required, make it a deliberate one-time migration with exact-key tests before deployment. The main operational risk is assuming CDK source equals deployed state; mitigate with `cdk synth`, `cdk diff`, Lambda env/role verification, and runtime smoke proof.

## Key Findings

### Stack Additions and Changes

The stack does not need a new AWS service, bucket, table, queue, Lambda, or Python dependency. Existing S3 + Lambda + CDK + boto3 are sufficient for v1.2. What must change is the evidence standard: source inspection is not enough because deployed Lambda configuration and packaged code can lag behind CDK/backend source.

**Already present:**
- S3 reports bucket: `StoaReportsBucket` is private, blocks public access, uses S3-managed encryption, logs access, and has retain policy in `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`.
- Lambda environment: API and weekly report Lambdas receive `S3_REPORTS_BUCKET` in `/Users/zhdeng/stoa-infra/stacks/api_stack.py`.
- Lambda IAM: both Lambdas receive `reports_bucket.grant_read_write(...)`.
- App wiring: `/Users/zhdeng/stoa-infra/app.py` passes `storage.reports_bucket` into `ApiStack`.
- Backend config: `src/stoa/config.py` exposes `settings.s3_reports_bucket`.
- Artifact writes: `src/stoa/services/report_service.py` writes JSON and HTML via boto3 `put_object` with explicit content types.
- Tests: existing backend tests cover artifact writes, content types, and failure ordering.

**v1.2 must verify or harden:**
- Run CDK synth/diff and verify no reports bucket replacement.
- Confirm deployed Lambda env vars and IAM role policies, not only CDK source.
- Ensure production does not silently use the placeholder local default `stoa-reports`.
- Lock one key prefix and assert exact JSON/HTML keys in tests.
- Add read helper behavior if the milestone requires read verification through backend code.
- Add deployed Lambda-context smoke that writes and reads a private artifact.
- Consider `enforce_ssl=True` on the reports bucket as a medium-priority CDK hardening item.
- Record least-privilege IAM prefix scoping, e.g. `weekly-reports/*`, as follow-up unless included after the key contract is locked.

### Expected Features

**Must have table stakes:**
- CDK reports bucket wiring verification for API and weekly report Lambdas.
- Backend runtime config proof that production uses CDK-injected `S3_REPORTS_BUCKET`.
- Stable artifact key contract with exact tests.
- Canonical key builder/helper behavior, either extracted or equivalently testable in `report_service.py`.
- JSON and HTML artifact writes with `application/json` and `text/html; charset=utf-8`.
- Failure ordering: no DynamoDB metadata or SES email after S3 artifact storage failure.
- Private-object Lambda smoke write/read proof without public URLs.
- Privacy and identifier hygiene: canonical backend IDs, ISO week start, no email addresses in keys.
- Evidence capture for closure: CDK synth/diff, env/IAM checks, backend tests, smoke result.

**Should have or follow-up hardening:**
- Production validation that rejects placeholder bucket defaults.
- Tests asserting no `ACL` parameter is passed to S3.
- S3 partial-failure tests after the first artifact write.
- Prefix-scoped IAM grants once the canonical prefix is locked.
- Optional smoke cleanup or deterministic smoke namespace.

**Defer v2+:**
- Presigned downloads, admin artifact viewer, PDF artifacts, object versioning/retention workflows, artifact schema versioning, frontend direct S3 reads, broad regeneration tooling, Bedrock prompt/content changes, SES delivery changes, and DynamoDB metadata redesign.

### Architecture Approach

Use the existing weekly report service flow as the integration boundary. EventBridge invokes the weekly report Lambda, the backend generates report content, writes JSON then HTML artifacts to S3, then writes DynamoDB metadata and sends email. Parent APIs remain backend-mediated and should not expose S3 keys, public S3 URLs, or direct frontend S3 access.

**Major components:**
1. `StoaReportsBucket` in CDK - private retained artifact storage with public access blocked, encryption, and access logs.
2. API Lambda - receives bucket config and IAM for future/backend-mediated artifact access; no public smoke route needed in v1.2.
3. Weekly report Lambda - owns report artifact writes and should own the runtime smoke hook.
4. Backend report artifact helper/key builder - builds canonical keys, sanitizes or validates key segments, writes JSON/HTML, and optionally reads JSON.
5. Report metadata repository - keeps existing `s3_key`, `html_s3_key`, and `json_s3_key`; no DynamoDB schema/index change needed.
6. Parent API routes - preserve ownership checks and metadata-backed report states.

**Canonical key prefix recommendation:**

```text
weekly-reports/{safe_parent_id}/{safe_student_id}/{iso_week_start}/report.json
weekly-reports/{safe_parent_id}/{safe_student_id}/{iso_week_start}/report.html
```

Do not support both `weekly-reports/...` and `reports/...`. Bless the current `weekly-reports/...` implementation unless product explicitly requires a migration. If migration is chosen, update `_report_artifact_keys`, metadata expectations, smoke keys, and tests in one phase.

### Critical Pitfalls

1. **CDK source looks correct but deployed Lambda is stale** - require synth/diff plus deployed env/role verification and smoke proof.
2. **Key contract drift** - choose one prefix now; assert full exact keys in tests and smoke output.
3. **Placeholder bucket default masks missing production config** - reject or alert on `stoa-reports` in production runtime.
4. **Private bucket treated as frontend asset host** - no public bucket policy, public ACLs, website hosting, or frontend direct S3 fetch.
5. **ACLs reintroduced through `put_object`** - assert no ACL parameter; rely on IAM and bucket policy.
6. **Smoke tests check the wrong contract** - test Lambda `PutObject` + immediate `GetObject`, not list output, access logs, or unsigned public URLs.
7. **Partial writes create orphaned artifacts** - keep deterministic idempotent keys and metadata-after-both-writes ordering; add partial-failure coverage.
8. **Gitignored Lambda asset drift** - ensure deployment rebuilds `stoa-backend/dist` before CDK deploy or smoke may test stale code.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: CDK and Runtime Configuration Verification

**Rationale:** Runtime readiness blocks all later artifact claims. Existing source is promising but not sufficient because deployed env vars, IAM policies, and Lambda assets may be stale.
**Delivers:** CDK synth/diff evidence, no bucket replacement evidence, API/weekly Lambda env var confirmation, IAM read/write confirmation, production bucket-default guard decision.
**Addresses:** S3ART-01, backend runtime config proof, deployed-state confidence.
**Avoids:** stale CDK deployment, wrong bucket runtime, gitignored `dist` package drift.

### Phase 2: Artifact Key Contract Lock

**Rationale:** Helper behavior, smoke tests, metadata, and future read tooling all depend on one canonical key shape.
**Delivers:** Decision record blessing `weekly-reports/...` or deliberate migration to `reports/...`; exact-key tests for JSON and HTML; tests proving IDs are canonical and keys exclude email addresses.
**Addresses:** S3ART-02, privacy and identifier hygiene.
**Avoids:** roadmap/code/test/storage prefix drift and unsafe key segments.

### Phase 3: Backend Artifact Helper Hardening

**Rationale:** The artifact behavior already exists but is embedded in `report_service.py`; v1.2 needs stable and testable behavior before extending operations.
**Delivers:** Public helper or equivalently testable functions for key building, JSON write, HTML write, optional JSON read, content types, no ACLs, validation/fail-closed behavior, and partial-failure tests.
**Addresses:** S3ART-03, S3ART-04.
**Avoids:** silent `unknown` path collisions, ACL regressions, metadata/email after failed storage, orphan inconsistency surprises.

### Phase 4: Deployed Private-Object Smoke

**Rationale:** The acceptance contract is deployed Lambda write/read access to a private S3 object.
**Delivers:** Narrow weekly report Lambda smoke event path, deterministic smoke key under the canonical prefix, `PutObject` + `GetObject` verification, bucket/key/content-type/readback result, no public URL requirement.
**Addresses:** S3ART-05 and acceptance criteria from the milestone slice.
**Avoids:** false confidence from listing, S3 access logs, unsigned URLs, or local-only tests.

### Phase 5: Evidence Ledger and Closure

**Rationale:** This is a hardening milestone; downstream work needs durable proof of what was verified and what remains follow-up.
**Delivers:** Captured backend test output, CDK synth/diff snippets, deployed env/IAM evidence, smoke result, follow-up notes for `enforce_ssl`, prefix-scoped IAM, and cleanup/lifecycle.
**Addresses:** S3ART-07 and handoff to later weekly report operations.
**Avoids:** reopening the same infrastructure uncertainty in later milestones.

### Phase Ordering Rationale

- Verify deployed infrastructure before changing backend behavior because missing env/IAM would invalidate smoke and helper conclusions.
- Lock the key contract before helper extraction or smoke implementation so all tests and evidence use one prefix.
- Harden helper behavior before runtime smoke so the smoke exercises the same canonical path production uses.
- Capture evidence last because it should summarize actual verification, not intended design.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Deployed AWS inspection may require current account-specific Lambda/IAM/CDK evidence and build pipeline confirmation.
- **Phase 4:** Smoke invocation details may need phase research if no existing internal Lambda smoke/event pattern exists.

Phases with standard patterns where research can usually be skipped:
- **Phase 2:** Key contract tests and decision record are local code/product decisions.
- **Phase 3:** boto3 put/get helper behavior and failure-order tests are well documented by current tests and AWS SDK patterns.
- **Phase 5:** Evidence capture is process work unless deployment tooling is unclear.

## Requirement Seeds

### Infrastructure and Deployment

- Verify `StoaReportsBucket` remains private, retained, encrypted with SSE-S3, access-logged, and not replaced.
- Verify API Lambda and weekly report Lambda both receive `S3_REPORTS_BUCKET`.
- Verify both Lambdas have read/write permissions to the reports bucket.
- Confirm production runtime cannot silently use local placeholder bucket `stoa-reports`.
- Rebuild or otherwise verify Lambda deploy asset freshness before deployed smoke.
- Record follow-up for `enforce_ssl=True` and prefix-scoped IAM if not implemented in v1.2.

### Artifact Contract

- Decide canonical prefix; recommendation is `weekly-reports/`.
- Assert exact JSON and HTML keys for parent ID, student ID, and ISO week start.
- Use canonical backend IDs, not emails or display names.
- Validate `week_start` as ISO date.
- Fail closed for blank production artifact key inputs instead of collapsing to shared `unknown` paths.

### Backend Helper and Storage Behavior

- Build keys through one helper or one equivalently testable implementation.
- Write JSON before HTML with explicit content types.
- Do not pass S3 ACLs.
- Store DynamoDB metadata only after both artifact writes succeed.
- Attempt SES only after artifact writes and metadata storage.
- Add JSON read helper only if this milestone needs backend read validation.
- Handle missing S3 reads intentionally, noting 403/404 behavior can vary by IAM scope.

### Runtime Smoke and Verification

- Add a weekly report Lambda smoke event rather than a public API route.
- Smoke writes a deterministic private JSON object under the canonical prefix.
- Smoke reads the same object back immediately and verifies content.
- Smoke output records bucket, key, content type, and readback success without exposing report content.
- Smoke does not require public URLs, frontend fetches, bucket listing, or access-log delivery.

### Privacy and API Boundaries

- Keep parent report access backend-mediated.
- Do not expose S3 object URLs or keys to the frontend in v1.2.
- Preserve parent-child ownership checks before any future artifact read route.
- Defer presigned URLs, admin viewers, PDFs, and frontend changes.

### Evidence and Closure

- Capture exact commands and results for backend tests.
- Capture CDK synth/diff evidence.
- Capture deployed Lambda env/IAM confirmation if deployment occurs.
- Capture smoke result and any cleanup decision.
- Mark code-state confidence separately from deployed-state confidence if runtime deployment is not completed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH for source, MEDIUM for deployed state | CDK/backend source findings are concrete; deployed Lambda env/IAM and asset freshness still need runtime proof. |
| Features | HIGH | Feature boundaries are clear from `.planning/PROJECT.md`, milestone slice, and current tests. |
| Architecture | HIGH | Current flow, boundaries, and no-new-resource recommendation are consistent across architecture, stack, and project context. |
| Pitfalls | HIGH | Pitfalls are grounded in local source plus official AWS/CDK/S3 documentation. |

**Overall confidence:** HIGH for roadmap direction; MEDIUM for production readiness until Phase 1 and Phase 4 evidence exists.

### Gaps to Address

- **Canonical prefix decision:** Research recommends `weekly-reports/`, but the milestone file says `reports/`. Planning must explicitly accept the recommendation or schedule a migration.
- **Deployed AWS state:** No current synth/diff/deployed Lambda output was captured in research files; Phase 1 must gather it.
- **Smoke mechanism:** Architecture recommends a weekly Lambda smoke event, but implementation details still need planning.
- **Production default guard:** Research recommends rejecting placeholder bucket defaults in production; decide whether this is in v1.2 or documented follow-up.
- **IAM hardening:** Current grant is acceptable for v1.2; decide whether prefix scoping is in scope after the prefix is locked.

## Sources

### Local Planning Sources

- `.planning/research/STACK.md` - stack state, official AWS/CDK guidance, required vs not required changes, verification notes.
- `.planning/research/FEATURES.md` - table stakes, defer list, anti-features, S3ART requirement seeds.
- `.planning/research/ARCHITECTURE.md` - current data flow, integration points, canonical prefix recommendation, smoke design, build order.
- `.planning/research/PITFALLS.md` - critical/moderate pitfalls, prevention strategies, phase warnings.
- `.planning/PROJECT.md` - current v1.2 milestone goal, active requirements, constraints, infrastructure context, key decisions.
- `.planning/milestones/s3-report-artifact-infrastructure.md` - original slice objective, expected CDK state, artifact contract, verification plan, acceptance criteria.

### Local Code Sources Referenced by Research

- `src/stoa/config.py` - `settings.s3_reports_bucket`.
- `src/stoa/services/report_service.py` - artifact writes, key builder, metadata fields.
- `src/stoa/jobs/weekly_reports.py` - weekly report Lambda job flow.
- `src/stoa/db/repositories/report_repo.py` - report metadata access patterns.
- `src/stoa/routers/parents.py` - backend-mediated parent report access and ownership checks.
- `tests/test_report_service.py` - S3 write/content-type coverage.
- `tests/test_report_flow.py` - flow coverage for S3 failure ordering.
- `tests/test_weekly_reports_job.py` - weekly job verification target.
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` - reports bucket definition.
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` - Lambda env vars, IAM grants, Lambda asset path.
- `/Users/zhdeng/stoa-infra/app.py` - reports bucket stack wiring.

### External Sources Aggregated from Research

- AWS CDK permissions guide: https://docs.aws.amazon.com/cdk/v2/guide/permissions.html
- AWS CDK S3 Bucket API: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/Bucket.html
- AWS CDK S3 BucketProps: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketProps.html
- AWS CDK S3 BucketGrants: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/BucketGrants.html
- Amazon S3 Block Public Access: https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- Amazon S3 object key naming: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html
- Amazon S3 Object Ownership and ACLs: https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership
- Amazon S3 encryption: https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html
- Amazon S3 default bucket encryption: https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html
- Amazon S3 strong consistency: https://aws.amazon.com/s3/consistency/
- Amazon S3 PutObject API: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
- Amazon S3 HeadObject API: https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html
- Amazon S3 server access logging: https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html
- AWS Lambda environment variables: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
- Boto3 S3 `put_object`: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/bucket/put_object.html
- Boto3 S3 object `get`: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/object/get.html
- AWS Security Hub S3 controls: https://docs.aws.amazon.com/securityhub/latest/userguide/s3-controls.html
- IAM least privilege best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html

---
*Research completed: 2026-06-03*
*Ready for roadmap: yes*
