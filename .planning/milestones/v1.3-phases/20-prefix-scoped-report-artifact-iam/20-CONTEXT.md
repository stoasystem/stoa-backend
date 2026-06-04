# Phase 20: Prefix-Scoped Report Artifact IAM - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

Phase 20 narrows Lambda S3 permissions for the reports bucket to the canonical private report artifact prefix `weekly-reports/*` while preserving current report artifact read/write behavior, weekly report smoke behavior, and existing image bucket behavior.

In scope:
- Replace broad `reports_bucket.grant_read_write(...)` usage for `stoa-api` and `stoa-weekly-report` with prefix-scoped IAM policy statements.
- Scope report artifact object actions to `reports_bucket.arn_for_objects("weekly-reports/*")`.
- Preserve `images_bucket.grant_read_write(self.api_function)`.
- Verify synth/diff/live IAM evidence and deployed weekly report smoke.

Out of scope:
- Reports bucket HTTPS enforcement, completed in Phase 19.
- Smoke/orphan cleanup behavior, owned by Phase 21.
- Report retry/resend/admin tooling, owned by Phase 22.
- Changing artifact key prefix or backend artifact helper behavior.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
- Current backend report artifact behavior uses `PutObject` and `GetObject`; no bucket listing is needed for current read/write/smoke behavior.
- Include only `GetObject`, `PutObject`, and `DeleteObject` under `weekly-reports/*`: current read/write paths use get/put, and Phase 21 cleanup needs delete.
- Do not add bucket-level `ListBucket` unless synth or live smoke proves it is required.
- Keep the policy helper local to `ApiStack` unless additional stacks need it later.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` already imports `aws_iam as iam` and owns Lambda role policies.
- `/Users/zhdeng/stoa-backend/src/stoa/services/report_artifact_service.py` uses canonical `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` keys.
- `run_report_artifact_s3_smoke` writes then reads a deterministic JSON object under `weekly-reports/`.

### Established Patterns
- CDK is the source of truth for Lambda IAM.
- Image uploads remain separate from report artifacts and use the images bucket.
- Verification should separate expected IAM policy changes from unrelated Lambda asset-hash drift.

### Integration Points
- `stoa-api` currently receives reports bucket access from `reports_bucket.grant_read_write(self.api_function)`.
- `stoa-weekly-report` currently receives reports bucket access from `reports_bucket.grant_read_write(self.weekly_report_function)`.
- Both Lambdas receive `S3_REPORTS_BUCKET` from CDK and must continue to do so.

</code_context>

<specifics>
## Specific Ideas

No user-facing design requirements. Prefer least privilege while preserving deployed smoke and current backend behavior.

</specifics>

<deferred>
## Deferred Ideas

- Object lifecycle/explicit smoke cleanup implementation for Phase 21.
- Admin/report operations tooling for Phase 22.

</deferred>
