# Deploy Readiness: Immutable Evidence Storage

**Phase:** 79
**Status:** Planned

## Required Evidence Before Phase 80

- CDK stack file and construct path for immutable evidence storage.
- CDK diff showing the resource, environment variables, and IAM permissions.
- Removal policy and retention/object-lock behavior documented.
- Backend runtime configuration names documented.
- Production deploy workflow path and expected run evidence documented.
- No-go list reviewed.

## No-Go Conditions

Do not deploy if:

- The resource requires manual AWS console creation or post-deploy console edits.
- CDK cannot represent the retention/object-lock behavior needed.
- API Lambda permissions require broad report artifact bucket access.
- Backend would silently fall back to mutable storage.
- Production verification requires customer report artifact mutation.
- Release evidence would need to record raw artifacts, S3 keys, presigned URLs, raw JSON/HTML, secrets, cookies, or tokens.

## Rollback And Teardown Expectations

Immutable storage can have limited or intentionally restricted rollback behavior. Phase 79 must document whether a failed deploy can be rolled back automatically, whether objects/resources are retained, and what operator steps are allowed. Manual destructive cleanup is out of scope unless separately approved and documented.

## Production Verification Boundary

First live verification should use metadata-only evidence or a named non-customer safe fixture. It must not delete audit rows, mutate customer report artifacts, write external support tickets, or expose private artifact identifiers.
