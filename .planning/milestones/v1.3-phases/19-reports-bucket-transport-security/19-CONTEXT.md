# Phase 19: Reports Bucket Transport Security - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

Phase 19 hardens the existing CDK reports bucket so S3 access requires secure transport. It should change the reports bucket policy or bucket construct settings only, prove the deployed bucket is not replaced, and record live bucket security evidence.

In scope:
- Add CDK-managed HTTPS-only enforcement for `StoaReportsBucket`.
- Preserve the existing bucket name `stoa-reports-{account}`, block-public-access settings, SSE-S3 encryption, access logging, and retain policy.
- Run CDK synth/diff or equivalent source/template checks that distinguish expected policy-only changes from Lambda code asset drift.
- Query live bucket public access block and encryption where AWS CLI credentials are available.

Out of scope:
- Prefix-scoped Lambda IAM grants. Phase 20 owns that.
- Smoke artifact cleanup or lifecycle changes. Phase 21 owns that.
- Report retry/resend/admin tooling. Phase 22 owns that.
- New buckets, public S3 access, frontend direct S3 access, or report artifact prefix changes.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
- Use the CDK `s3.Bucket(enforce_ssl=True)` construct option if available in the installed CDK version; otherwise add an equivalent deny-insecure-transport bucket policy.
- Keep the implementation narrowly scoped to `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`.
- Treat Lambda `Code.S3Key` asset-hash drift as separate from reports bucket transport security.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` defines `StoaReportsBucket` with fixed bucket name, `BLOCK_ALL`, SSE-S3 encryption, access logging, and `RemovalPolicy.RETAIN`.
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` injects `S3_REPORTS_BUCKET` into `stoa-api` and `stoa-weekly-report`.
- `.planning/milestones/v1.2-phases/14-cdk-runtime-configuration-verification/14-VERIFICATION.md` records prior synth evidence for bucket privacy, encryption, access logging, retain policy, Lambda env, and IAM.

### Established Patterns
- CDK is the infrastructure source of truth; manual AWS console fixes are out of scope.
- Bucket privacy is enforced through block-public-access and backend-mediated report routes.
- Verification artifacts should record exact commands and separate local/source evidence from live AWS evidence.

### Integration Points
- `StoaStorageStack` exports the reports bucket to `StoaApiStack`.
- Future phases depend on this bucket still being the same deployed physical bucket.

</code_context>

<specifics>
## Specific Ideas

No specific user-facing design requirements. Use the standard CDK bucket hardening pattern and keep the change as narrow as possible.

</specifics>

<deferred>
## Deferred Ideas

- Prefix-scoped report artifact IAM for Phase 20.
- Smoke/orphan cleanup for Phase 21.
- Report operations tooling for Phase 22.

</deferred>
