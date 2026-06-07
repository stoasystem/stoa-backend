# Phase 71 CDK Readiness

**Status:** Planned
**Checked:** 2026-06-07

## Resources To Review During Phase 71 Execution

| Area | Current Expected Source | Required For | Expected Decision |
|------|-------------------------|--------------|-------------------|
| Audit rows | Existing DynamoDB single-table report/recovery audit rows | Manifest composition | Likely sufficient for metadata-only manifests |
| API Lambda | Existing FastAPI Lambda/API Gateway | Manifest/status APIs | Likely sufficient |
| Report artifacts bucket | Existing private reports bucket | Artifact privacy boundary | No direct manifest artifact reads by default |
| Release evidence tooling | Existing backend scripts/services | Privacy validation | Reuse expected |
| Admin frontend | Existing `/admin/report-operations` | UI surface | Reuse expected |
| Immutable storage | CDK-managed future resource if approved | WORM storage | Not claimed until explicitly designed/deployed |

## Default Decision

Phase 72 should proceed without new AWS resources if it implements metadata-only retention manifests and status checks.

Implementation constraints:

- Do not add broad S3 list/read permissions.
- Do not add deletion/expiry workflows.
- Do not add WORM/Object Lock resources unless Phase 71 final decision says the milestone requires them.
- Do not store raw report artifacts or private object keys in manifests.
- Re-run CDK diff during release gate to prove no unintended infrastructure drift.

## Open Questions For Execution

- Which existing audit row types should be in the first manifest allowlist?
- Should manifest hashes be computed from canonical JSON summaries or individual item digests?
- Should manifests be persisted as audit child rows, returned ephemerally, or both?
