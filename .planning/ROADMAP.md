# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.

## Current Milestone

### v1.2 S3 Report Artifact Infrastructure

**Milestone Goal:** Make report artifact storage deployable and verifiable before extending weekly report operations further.

This milestone verifies the existing CDK reports bucket wiring, locks the private artifact key contract, hardens backend artifact storage behavior, proves deployed Lambda private-object access, and records closure evidence for the next weekly report operations slice.

## Phases

**Phase Numbering:**
- Integer phases continue from previous milestones.
- v1.1 ended at Phase 13, so v1.2 starts at Phase 14.
- Decimal phases are reserved for urgent insertions.

- [ ] **Phase 14: CDK & Runtime Configuration Verification** - Operators can prove reports bucket privacy, Lambda env vars, IAM grants, and production bucket config are deployment-ready.
- [ ] **Phase 15: Artifact Key Contract & Helper Hardening** - Backend artifact keys and helper behavior use one canonical private S3 contract.
- [ ] **Phase 16: Storage Failure Ordering & Privacy Boundary** - Report metadata, email delivery, and parent access remain correct when artifact storage succeeds or fails.
- [ ] **Phase 17: Deployed Private-Object Smoke** - Maintainers can prove a deployed weekly report Lambda can write and read a private report artifact object.
- [ ] **Phase 18: Evidence Ledger & Milestone Closure** - Milestone closure records test, CDK, deployed-state, smoke, and follow-up evidence.

## Phase Details

### Phase 14: CDK & Runtime Configuration Verification
**Goal**: Operators can verify the existing CDK and runtime configuration are ready for private report artifact storage.
**Depends on**: Phase 13
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. Operator can inspect CDK synth/diff evidence showing `StoaReportsBucket` remains private, retained, encrypted, access-logged, and unreplaced.
  2. Operator can verify both the API Lambda and weekly report Lambda receive `S3_REPORTS_BUCKET` from CDK.
  3. Operator can verify both Lambdas have read/write IAM access to the reports bucket.
  4. Production report artifact code surfaces missing CDK-injected bucket configuration instead of silently using the local `stoa-reports` placeholder.
**Plans**: TBD

### Phase 15: Artifact Key Contract & Helper Hardening
**Goal**: Backend report artifact helpers enforce one canonical private S3 key contract for JSON and HTML artifacts.
**Depends on**: Phase 14
**Requirements**: ARTIFACT-01, ARTIFACT-02, ARTIFACT-03, ARTIFACT-04, ARTIFACT-05, STORAGE-01, STORAGE-02, STORAGE-03, STORAGE-04, STORAGE-08
**Success Criteria** (what must be TRUE):
  1. Maintainer can confirm JSON and HTML artifact keys are built exactly as `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
  2. Backend tests fail if artifact keys lose the `weekly-reports/` prefix, use non-canonical IDs, or use a non-ISO `week_start`.
  3. Maintainer can verify artifact keys exclude parent email, student email, display names, and arbitrary user-facing text.
  4. JSON and HTML artifacts are written to `settings.s3_reports_bucket` with the required content types and no S3 ACL parameters.
  5. Backend code can read a JSON report artifact by S3 key for smoke verification or future backend-mediated reads.
**Plans**: TBD

### Phase 16: Storage Failure Ordering & Privacy Boundary
**Goal**: Report storage failure behavior and parent report access boundaries remain safe and observable.
**Depends on**: Phase 15
**Requirements**: STORAGE-05, STORAGE-06, STORAGE-07, PRIVACY-01, PRIVACY-02, PRIVACY-03
**Success Criteria** (what must be TRUE):
  1. DynamoDB report metadata is created only after both JSON and HTML S3 artifact writes succeed.
  2. SES email delivery is attempted only after artifact writes and DynamoDB metadata storage succeed.
  3. Backend tests prove a failure after the first artifact write creates no report metadata and sends no email.
  4. Parent report access remains backend-mediated and ownership-checked, with no public S3 route, public object ACL, or client direct S3 fetch introduced.
**Plans**: TBD

### Phase 17: Deployed Private-Object Smoke
**Goal**: Maintainers can prove deployed Lambda read/write access to a private report artifact object without exposing S3 publicly.
**Depends on**: Phase 16
**Requirements**: SMOKE-01, SMOKE-02, SMOKE-03, SMOKE-04, SMOKE-05
**Success Criteria** (what must be TRUE):
  1. Maintainer can invoke a narrow weekly report Lambda smoke event without exposing a public API route.
  2. Smoke execution writes a deterministic private JSON object under the canonical `weekly-reports/` prefix.
  3. Smoke execution immediately reads the same private object back and verifies its content.
  4. Smoke output records bucket, key, content type, and readback success without exposing report content.
  5. Smoke verification does not depend on public S3 URLs, bucket listing, S3 access-log delivery, or client S3 access.
**Plans**: TBD

### Phase 18: Evidence Ledger & Milestone Closure
**Goal**: Milestone closure contains durable evidence of what was verified and what remains follow-up work.
**Depends on**: Phase 17
**Requirements**: EVIDENCE-01, EVIDENCE-02, EVIDENCE-03, EVIDENCE-04, EVIDENCE-05
**Success Criteria** (what must be TRUE):
  1. Milestone closure records backend test commands and results for artifact storage behavior.
  2. Milestone closure records CDK synth/diff evidence for the reports bucket, Lambda env vars, IAM grants, and no bucket replacement.
  3. Milestone closure records deployed Lambda env/IAM verification or explicitly marks deployed-state confidence as incomplete.
  4. Milestone closure records the private-object smoke result and any smoke object cleanup decision.
  5. Milestone closure records follow-ups for `enforce_ssl=True`, prefix-scoped IAM, lifecycle cleanup, and broader operational tooling if not implemented in v1.2.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 14 -> 15 -> 16 -> 17 -> 18

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 14. CDK & Runtime Configuration Verification | v1.2 | 0/TBD | Not started | - |
| 15. Artifact Key Contract & Helper Hardening | v1.2 | 0/TBD | Not started | - |
| 16. Storage Failure Ordering & Privacy Boundary | v1.2 | 0/TBD | Not started | - |
| 17. Deployed Private-Object Smoke | v1.2 | 0/TBD | Not started | - |
| 18. Evidence Ledger & Milestone Closure | v1.2 | 0/TBD | Not started | - |
