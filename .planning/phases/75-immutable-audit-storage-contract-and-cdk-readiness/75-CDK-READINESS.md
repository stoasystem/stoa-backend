# CDK Readiness: Immutable Audit Storage And Legal Hold

**Phase:** 75
**Status:** Planned

## Decision

Phase 75 must inspect the CDK source of truth before Phase 76 adds backend immutable persistence writes.

Expected classification:

- Existing application-enforced DynamoDB audit rows are not sufficient to claim compliance-grade immutable/WORM storage.
- v2.6 metadata-only manifests are readiness artifacts, not immutable object persistence.
- v2.7 backend writes require either a CDK-managed immutable storage resource or an explicit documented refusal that leaves immutable persistence disabled.

## CDK Evidence To Collect

- Relevant stack files in `/Users/zhdeng/stoa-infra`.
- Resource name, retention/object-lock settings if applicable, encryption, access policy, and removal policy.
- API Lambda permissions scoped to the approved immutable evidence prefix/resource.
- Environment variables injected into the API Lambda.
- CDK diff output.
- CDK deploy run ID or explicit no-deploy classification.
- Commit SHA for infra and backend code used for deployment.

## Backend Preconditions For Phase 76

Before backend immutable writes are enabled:

- Immutable storage configuration must come from CDK-managed environment variables.
- Writer permissions must be scoped to immutable evidence only.
- Privacy validation must run before object persistence.
- Failure mode must be refusal, not fallback to mutable storage.
- Tests must cover missing configuration and denylist refusal.

## No-Go Conditions

Do not implement production immutable writes if:

- Storage was created or changed manually outside CDK.
- CDK diff/deploy evidence is missing.
- API Lambda permissions require broad bucket access beyond the approved prefix/resource.
- The storage contract would require raw artifacts, S3 keys, presigned URLs, or raw JSON/HTML.
- Legal hold state changes would delete or overwrite prior audit evidence.
