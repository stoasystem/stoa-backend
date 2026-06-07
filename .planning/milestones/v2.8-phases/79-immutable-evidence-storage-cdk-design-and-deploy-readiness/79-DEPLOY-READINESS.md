# Deploy Readiness: Immutable Evidence Storage

**Phase:** 79
**Status:** Complete

## Required Evidence Before Phase 80

- CDK stack file and construct path: `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` → `StorageStack/StoaImmutableEvidenceBucket`.
- API integration path: `/Users/zhdeng/stoa-infra/app.py` passes the bucket into `/Users/zhdeng/stoa-infra/stacks/api_stack.py`.
- CDK diff must show exactly one new immutable evidence bucket, API Lambda env vars, scoped `s3:PutObject`/`s3:GetObject` permissions for `audit-retention/*`, and storage outputs.
- Removal policy is `RETAIN`; teardown/destructive cleanup is not part of v2.8.
- Object Lock posture is `object_lock_enabled=True`, versioning enabled, default GOVERNANCE retention for 365 days.
- Backend runtime configuration names are documented in `79-BACKEND-CONFIG-CONTRACT.md`.
- Production deploy workflow: `/Users/zhdeng/stoa-infra/.github/workflows/deploy.yml` (`Deploy Infrastructure`) with diff and deploy jobs.
- Backend deploy workflow remains `/Users/zhdeng/stoa-backend/.github/workflows/deploy.yml` for Lambda code updates.
- No-go list below reviewed.

## No-Go Conditions

Do not deploy if:

- The resource requires manual AWS console creation or post-deploy console edits.
- CDK cannot represent the retention/object-lock behavior needed.
- API Lambda permissions require broad report artifact bucket access.
- Backend would silently fall back to mutable storage.
- Production verification requires customer report artifact mutation.
- Release evidence would need to record raw artifacts, S3 keys, presigned URLs, raw JSON/HTML, secrets, cookies, or tokens.

## Rollback And Teardown Expectations

Immutable storage has intentionally limited rollback behavior:

- Bucket removal policy is `RETAIN`.
- Object Lock is a creation-time capability and must not be treated as reversible.
- If Phase 80 deploy fails before bucket creation, rerun/fix CDK normally.
- If Phase 80 creates the bucket but later stack steps fail, keep the retained bucket and repair CDK alignment; do not manually delete or empty it.
- If Phase 81 backend enablement fails, leave the bucket deployed and remove/disable only API Lambda runtime configuration in a future CDK change if needed.
- Manual destructive cleanup is out of scope.

## Production Verification Boundary

First live verification should use metadata-only evidence or a named non-customer safe fixture. It must not delete audit rows, mutate customer report artifacts, write external support tickets, or expose private artifact identifiers.

## Phase 80 Entry Criteria

Phase 80 may proceed when:

- CDK code implements the chosen design exactly.
- `cdk synth` and `cdk diff` show no broad S3 permission expansion.
- Diff confirms existing reports bucket is unchanged except unrelated CDK metadata noise.
- Diff confirms API Lambda gets immutable env vars and scoped immutable object permissions.
- Operator accepts that Object Lock bucket rollback is retained/no-destructive-cleanup.
