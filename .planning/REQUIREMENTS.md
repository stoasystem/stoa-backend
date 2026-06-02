# Requirements: STOA Backend v1.2 S3 Report Artifact Infrastructure

**Defined:** 2026-06-03
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Milestone Decision

The canonical report artifact prefix for this milestone is:

```text
weekly-reports/{parent_id}/{student_id}/{week_start}/report.json
weekly-reports/{parent_id}/{student_id}/{week_start}/report.html
```

This blesses the shipped v1.1 backend convention instead of migrating to the shorter `reports/...` prefix from the slice note. The milestone should update tests, docs, smoke paths, and metadata expectations to this single convention.

## v1.2 Requirements

### Infrastructure

- [ ] **INFRA-01**: Operator can verify through CDK synth/diff that `StoaReportsBucket` remains private, retained, encrypted, access-logged, and is not replaced.
- [ ] **INFRA-02**: Operator can verify that the API Lambda receives `S3_REPORTS_BUCKET` from CDK.
- [ ] **INFRA-03**: Operator can verify that the weekly report Lambda receives `S3_REPORTS_BUCKET` from CDK.
- [ ] **INFRA-04**: Operator can verify that both API and weekly report Lambdas have reports bucket read/write permissions.
- [ ] **INFRA-05**: Production report artifact code cannot silently use the local placeholder bucket name `stoa-reports` when a CDK-injected bucket is required.

### Artifact Contract

- [ ] **ARTIFACT-01**: Backend code builds JSON and HTML report artifact keys with the canonical `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` shape.
- [ ] **ARTIFACT-02**: Backend tests assert exact JSON and HTML artifact keys, including the `weekly-reports/` prefix.
- [ ] **ARTIFACT-03**: Report artifact keys use canonical backend parent/student IDs and ISO `week_start` values.
- [ ] **ARTIFACT-04**: Report artifact keys never include parent email, student email, display names, or arbitrary user-facing text.
- [ ] **ARTIFACT-05**: Invalid or blank production artifact key inputs fail closed instead of collapsing into shared `unknown` paths.

### Backend Storage

- [ ] **STORAGE-01**: Backend code exposes a report artifact helper or equivalently testable functions for building keys and writing JSON/HTML artifacts.
- [ ] **STORAGE-02**: JSON artifacts are written to `settings.s3_reports_bucket` with `ContentType="application/json"`.
- [ ] **STORAGE-03**: HTML artifacts are written to `settings.s3_reports_bucket` with `ContentType="text/html; charset=utf-8"`.
- [ ] **STORAGE-04**: Report artifact writes do not pass S3 ACL parameters and rely on bucket privacy plus Lambda IAM.
- [ ] **STORAGE-05**: DynamoDB report metadata is saved only after both JSON and HTML S3 artifact writes succeed.
- [ ] **STORAGE-06**: SES email delivery is attempted only after S3 artifact writes and DynamoDB metadata storage succeed.
- [ ] **STORAGE-07**: Backend tests prove that failure after the first artifact write does not create report metadata or send email.
- [ ] **STORAGE-08**: Backend code can read a JSON report artifact by S3 key when needed for smoke or future backend-mediated reads.

### Runtime Smoke

- [ ] **SMOKE-01**: Maintainer can invoke a narrow weekly report Lambda smoke event that does not expose a public API route.
- [ ] **SMOKE-02**: Smoke execution writes a deterministic private JSON object under the canonical `weekly-reports/` prefix.
- [ ] **SMOKE-03**: Smoke execution reads the same private object back immediately and verifies its content.
- [ ] **SMOKE-04**: Smoke output records bucket, key, content type, and readback success without exposing report content.
- [ ] **SMOKE-05**: Smoke verification does not require public S3 URLs, frontend S3 access, bucket listing, or S3 access-log delivery.

### Privacy Boundary

- [ ] **PRIVACY-01**: Parent report access remains backend-mediated through authorized parent API routes.
- [ ] **PRIVACY-02**: No frontend direct S3 fetch, public S3 URL, public bucket policy, or public object ACL is introduced for report artifacts.
- [ ] **PRIVACY-03**: Any future backend artifact read path must preserve existing parent-child ownership checks before returning report data.

### Evidence

- [ ] **EVIDENCE-01**: Milestone closure records backend test commands and results for artifact storage behavior.
- [ ] **EVIDENCE-02**: Milestone closure records CDK synth/diff evidence for reports bucket, Lambda env vars, IAM grants, and no bucket replacement.
- [ ] **EVIDENCE-03**: Milestone closure records deployed Lambda env/IAM verification or explicitly marks deployed-state confidence as incomplete.
- [ ] **EVIDENCE-04**: Milestone closure records private-object smoke result and any smoke object cleanup decision.
- [ ] **EVIDENCE-05**: Milestone closure records follow-ups for `enforce_ssl=True`, prefix-scoped IAM, lifecycle cleanup, and broader operational tooling if they are not implemented in v1.2.

## Future Requirements

### Security Hardening

- **SEC-01**: CDK can restrict reports bucket read/write permissions to the final artifact prefix, such as `weekly-reports/*`.
- **SEC-02**: CDK can enforce HTTPS-only S3 access for the reports bucket with `enforce_ssl=True`.
- **SEC-03**: Smoke artifacts can be cleaned up automatically through lifecycle policy or explicit delete permissions.

### Operations

- **OPS-01**: Admin can view report artifact metadata and storage health from an operational surface.
- **OPS-02**: Admin can retry or resend failed report delivery without regenerating unrelated report data.
- **OPS-03**: Support can generate authorized presigned artifact downloads with short TTL and audit logging.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Bedrock report content changes | v1.2 verifies artifact storage, not report generation quality. |
| SES delivery expansion | Existing email flow is sufficient; this milestone only preserves ordering guarantees. |
| Parent frontend changes | Parent frontend should keep using backend report routes, not S3 directly. |
| PDF report artifacts | Explicitly deferred; JSON and HTML artifacts are enough for this storage slice. |
| DynamoDB report metadata redesign | Existing metadata fields already store artifact keys. |
| New AWS bucket, queue, table, or Lambda | Existing CDK resources are sufficient unless verification proves otherwise. |
| Public S3 access or bucket website hosting | Conflicts with private report artifact storage. |
| Manual AWS console fixes | CDK remains the infrastructure source of truth. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | TBD | Pending |
| INFRA-02 | TBD | Pending |
| INFRA-03 | TBD | Pending |
| INFRA-04 | TBD | Pending |
| INFRA-05 | TBD | Pending |
| ARTIFACT-01 | TBD | Pending |
| ARTIFACT-02 | TBD | Pending |
| ARTIFACT-03 | TBD | Pending |
| ARTIFACT-04 | TBD | Pending |
| ARTIFACT-05 | TBD | Pending |
| STORAGE-01 | TBD | Pending |
| STORAGE-02 | TBD | Pending |
| STORAGE-03 | TBD | Pending |
| STORAGE-04 | TBD | Pending |
| STORAGE-05 | TBD | Pending |
| STORAGE-06 | TBD | Pending |
| STORAGE-07 | TBD | Pending |
| STORAGE-08 | TBD | Pending |
| SMOKE-01 | TBD | Pending |
| SMOKE-02 | TBD | Pending |
| SMOKE-03 | TBD | Pending |
| SMOKE-04 | TBD | Pending |
| SMOKE-05 | TBD | Pending |
| PRIVACY-01 | TBD | Pending |
| PRIVACY-02 | TBD | Pending |
| PRIVACY-03 | TBD | Pending |
| EVIDENCE-01 | TBD | Pending |
| EVIDENCE-02 | TBD | Pending |
| EVIDENCE-03 | TBD | Pending |
| EVIDENCE-04 | TBD | Pending |
| EVIDENCE-05 | TBD | Pending |

**Coverage:**
- v1.2 requirements: 31 total
- Mapped to phases: 0
- Unmapped: 31

---
*Requirements defined: 2026-06-03*
*Last updated: 2026-06-03 after research synthesis*
