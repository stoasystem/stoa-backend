# CDK Readiness: Immutable Audit Storage And Legal Hold

**Phase:** 75
**Status:** Complete

## Decision

Phase 75 inspected the CDK source of truth. Current infra does not yet define a dedicated CDK-managed immutable audit evidence resource, Object Lock-enabled bucket, legal hold resource, or immutable evidence environment variables.

Classification:

- Existing application-enforced DynamoDB audit rows are not sufficient to claim compliance-grade immutable/WORM storage.
- v2.6 metadata-only manifests are readiness artifacts, not immutable object persistence.
- v2.7 backend writes require a CDK-managed immutable evidence resource before production persistence can be enabled.
- Phase 76 backend work must fail closed while immutable storage configuration is absent.
- Legal hold metadata can be modeled in backend/DynamoDB, but must not claim infrastructure-enforced retention until CDK/deploy evidence proves it.

## Resources Reviewed During Phase 75 Execution

| Resource | Evidence | Current posture | Phase 76 implication |
|----------|----------|-----------------|----------------------|
| Reports bucket | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` `StoaReportsBucket` | Private, HTTPS enforced, retained, S3-managed encryption; no Object Lock/legal hold settings | Do not use as compliance-grade immutable storage without CDK change |
| API Lambda env | `/Users/zhdeng/stoa-infra/stacks/api_stack.py` `StoaApiFunction.environment` | Has `S3_REPORTS_BUCKET`; no immutable evidence bucket/prefix/policy env vars | Backend writer must report `not_configured` until env exists |
| API Lambda S3 permissions | `/Users/zhdeng/stoa-infra/stacks/api_stack.py` `_grant_report_artifact_read_write` | Scoped to `weekly-reports/*` with Get/Put/Delete for report artifacts | Do not reuse this prefix or delete-capable policy for immutable evidence |
| DynamoDB audit rows | `src/stoa/db/repositories/report_repo.py` audit put methods | Conditional append rows for report, recovery job, support handoff, audit retention events | Continue using as application audit timeline and metadata reference audit |
| v2.6 retention APIs | `src/stoa/routers/admin.py`, audit retention service/tests | Metadata-only status/manifest with digest and refusal behavior | Reuse canonical manifest and privacy validation before persistence |

## CDK Evidence To Collect

Before enabling immutable writes, release evidence must include:

- Relevant stack files in `/Users/zhdeng/stoa-infra`.
- Resource name, retention/Object Lock settings if applicable, encryption, access policy, and removal policy.
- API Lambda permissions scoped to the approved immutable evidence prefix/resource with no delete permission for retained objects.
- Environment variables injected into the API Lambda, such as immutable evidence bucket/resource name, prefix, mode, and policy ID source.
- CDK diff output showing the immutable evidence resource and Lambda permission/env changes.
- CDK deploy run ID or explicit no-deploy classification.
- Commit SHA for infra and backend code used for deployment.

## Backend Preconditions For Phase 76

Before backend immutable writes are enabled:

- Immutable storage configuration must come from CDK-managed environment variables.
- Writer permissions must be scoped to immutable evidence only and must not reuse `weekly-reports/*`.
- Privacy validation must run before object persistence.
- Failure mode must be refusal, not fallback to mutable storage.
- Tests must cover missing configuration and denylist refusal.
- Admin APIs must not return bucket names, object keys, presigned URLs, or raw object payloads.
- Persistence must never require deleting existing audit rows or report artifacts.

## No-Go Conditions

Do not implement production immutable writes if:

- Storage was created or changed manually outside CDK.
- CDK diff/deploy evidence is missing.
- API Lambda permissions require broad bucket access beyond the approved prefix/resource.
- The storage contract would require raw artifacts, S3 keys, presigned URLs, or raw JSON/HTML.
- Legal hold state changes would delete or overwrite prior audit evidence.

## Phase 76 Decision

Phase 76 may implement backend immutable-persistence and legal-hold metadata APIs behind fail-closed configuration gates. It must not enable production immutable object writes until the infra repo adds a CDK-owned immutable evidence resource, scoped Lambda permissions, and environment variables with diff/deploy evidence.
