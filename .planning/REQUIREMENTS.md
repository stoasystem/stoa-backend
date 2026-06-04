# Requirements: STOA Backend v1.3 Report Artifact Security & Operations Hardening

**Defined:** 2026-06-04
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Milestone Decision

v1.3 builds on the verified v1.2 private artifact contract:

```text
weekly-reports/{parent_id}/{student_id}/{week_start}/report.json
weekly-reports/{parent_id}/{student_id}/{week_start}/report.html
```

This milestone hardens the existing reports bucket and operational paths. It should not introduce public S3 access, frontend direct S3 reads, a new reports bucket, or a new artifact prefix unless implementation proves the existing contract cannot support the requirement.

## v1.3 Requirements

### Reports Bucket Transport Security

- [x] **SEC-01**: CDK enforces HTTPS-only S3 access for the reports bucket through `enforce_ssl=True` or an equivalent deny-insecure-transport bucket policy.
- [x] **SEC-02**: CDK diff/deploy evidence proves report bucket security hardening does not replace the deployed `stoa-reports-562923011260` bucket.
- [x] **SEC-03**: Live bucket verification confirms public access block and default encryption remain enabled after hardening.

### Prefix-Scoped IAM

- [x] **IAM-01**: API Lambda report artifact S3 object permissions are narrowed to the canonical `weekly-reports/*` prefix where S3 supports prefix scoping.
- [x] **IAM-02**: Weekly report Lambda S3 object permissions are narrowed to the canonical `weekly-reports/*` prefix while preserving generation and smoke read/write behavior.
- [x] **IAM-03**: Non-report storage behavior remains unaffected, especially existing API Lambda access to the images bucket.
- [x] **IAM-04**: CDK and live IAM verification records any unavoidable bucket-level permissions and their rationale.

### Artifact Cleanup

- [x] **CLEAN-01**: Smoke artifacts under deterministic smoke paths are cleaned up automatically through lifecycle policy or explicit smoke cleanup.
- [x] **CLEAN-02**: Failed partial artifact writes do not leave untracked long-lived orphan JSON objects without a cleanup path.
- [x] **CLEAN-03**: Cleanup behavior is verified with tests and/or live smoke evidence without deleting real parent report artifacts.

### Report Operations

- [ ] **OPS-01**: Maintainer/admin can inspect report artifact metadata and delivery status for a parent, student, and week without direct S3 console use.
- [ ] **OPS-02**: Maintainer/admin can retry or resend failed report delivery without regenerating unrelated successful reports.
- [ ] **OPS-03**: Operations visibility preserves parent-child authorization boundaries and does not expose public S3 URLs or raw private report content to unauthorized users.
- [ ] **OPS-04**: Report operation actions are auditable through logs or persisted status fields sufficient for support triage.

## Future Requirements

### Operations Expansion

- **OPS-F01**: Rich admin UI dashboard for report health if v1.3 only delivers backend/API/CLI primitives.
- **OPS-F02**: Bulk retry workflows for incident recovery across many failed reports.

### Report Product Expansion

- **PDF-F01**: PDF report artifacts.
- **I18N-F01**: Multi-language reports.
- **BILL-F01**: Billing-gated report access.

## Out of Scope

| Feature | Reason |
|---------|--------|
| New reports bucket | v1.2 verified the existing reports bucket and v1.3 should harden it in place. |
| Public S3 access, public bucket policy, or public URLs | Conflicts with private backend-mediated report artifact access. |
| Frontend direct S3 fetch | Parent report access must remain backend-mediated and ownership-checked. |
| Report generation quality changes | This milestone hardens storage and operations, not Bedrock prompt/content quality. |
| PDF report artifacts | Deferred product expansion; JSON and HTML remain sufficient for this milestone. |
| Multi-language reports | Separate report product scope. |
| Billing or subscription enforcement | Separate access-control and product scope. |
| Broad frontend redesign | v1.3 can add minimal admin visibility if needed, but not a parent portal redesign. |
| Manual AWS console fixes | CDK remains the infrastructure source of truth. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 19 | Complete |
| SEC-02 | Phase 19 | Complete |
| SEC-03 | Phase 19 | Complete |
| IAM-01 | Phase 20 | Complete |
| IAM-02 | Phase 20 | Complete |
| IAM-03 | Phase 20 | Complete |
| IAM-04 | Phase 20 | Complete |
| CLEAN-01 | Phase 21 | Complete |
| CLEAN-02 | Phase 21 | Complete |
| CLEAN-03 | Phase 21 | Complete |
| OPS-01 | Phase 22 | Planned |
| OPS-02 | Phase 22 | Planned |
| OPS-03 | Phase 22 | Planned |
| OPS-04 | Phase 22 | Planned |

**Coverage:**

- v1.3 requirements: 14 total
- Complete: 10
- Mapped to phases: 14
- Unmapped: 0

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 after Phase 21 completion*
