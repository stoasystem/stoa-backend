# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification.

## Current Milestone

### v1.3 Report Artifact Security & Operations Hardening

**Milestone Goal:** Harden private weekly report artifact storage and add operational controls so report artifacts are safer, cleaner, and easier to support after v1.2 live verification.

This milestone adds HTTPS-only reports bucket access, narrows report artifact IAM toward the canonical `weekly-reports/*` prefix, adds cleanup for smoke/orphan artifacts, and creates report operations visibility and recovery tooling.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.2 ended at Phase 18, so v1.3 starts at Phase 19.
- Decimal phases are reserved for urgent insertions.

- [ ] **Phase 19: Reports Bucket Transport Security** - Operators can prove the deployed reports bucket enforces HTTPS-only access without bucket replacement.
- [ ] **Phase 20: Prefix-Scoped Report Artifact IAM** - Lambda report artifact permissions are narrowed toward `weekly-reports/*` without breaking report generation, smoke, or image storage.
- [ ] **Phase 21: Smoke and Orphan Artifact Cleanup** - Smoke and failed partial report artifacts have a safe cleanup path that preserves real report artifacts.
- [ ] **Phase 22: Report Operations Visibility and Recovery** - Maintainers can inspect report artifact/delivery state and retry or resend failed delivery safely.

## Phase Details

### Phase 19: Reports Bucket Transport Security

**Goal**: CDK enforces HTTPS-only access for the reports bucket without replacing the deployed bucket or weakening existing privacy.
**Depends on**: Phase 18
**Requirements**: SEC-01, SEC-02, SEC-03
**Success Criteria** (what must be TRUE):

  1. CDK change adds `enforce_ssl=True` or an equivalent deny-insecure-transport policy to the reports bucket.
  2. `cdk diff` evidence shows the reports bucket is not replaced.
  3. Live bucket checks confirm public access block and default encryption remain enabled.
  4. Verification records any expected policy-only change separately from Lambda code asset drift.

**Plans**: 0/1 planned

### Phase 20: Prefix-Scoped Report Artifact IAM

**Goal**: Lambda report artifact permissions are narrowed toward `weekly-reports/*` without breaking API image uploads or weekly report artifact reads/writes.
**Depends on**: Phase 19
**Requirements**: IAM-01, IAM-02, IAM-03, IAM-04
**Success Criteria** (what must be TRUE):

  1. CDK policies scope reports S3 object actions to the canonical `weekly-reports/*` prefix where feasible.
  2. Bucket-level permissions are preserved only where S3 requires them and are documented with rationale.
  3. API Lambda image bucket permissions and behavior remain unaffected.
  4. Backend tests and live smoke prove report artifact read/write behavior still works.

**Plans**: 0/1 planned

### Phase 21: Smoke and Orphan Artifact Cleanup

**Goal**: Smoke and partial report artifacts have a safe cleanup path that avoids long-lived test/orphan objects while preserving real report artifacts.
**Depends on**: Phase 20
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03
**Success Criteria** (what must be TRUE):

  1. Smoke artifact cleanup is implemented through lifecycle policy or explicit smoke cleanup behavior.
  2. A failure after the first artifact write has a cleanup path or bounded lifecycle retention.
  3. Tests verify cleanup behavior does not delete real parent report artifacts.
  4. Live smoke output records cleanup status clearly.

**Plans**: 0/1 planned

### Phase 22: Report Operations Visibility and Recovery

**Goal**: Maintainers can inspect report artifact/delivery state and retry or resend failed delivery without unsafe S3 exposure or unrelated regeneration.
**Depends on**: Phase 21
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04
**Success Criteria** (what must be TRUE):

  1. An operational API, CLI, or service path exposes report artifact metadata and delivery status for a parent, student, and week.
  2. Retry/resend behavior targets a specific failed report and avoids regenerating unrelated successful reports.
  3. Authorization and audit behavior prevent unauthorized access to raw private report content or public S3 URLs.
  4. Tests cover operations visibility, retry/resend targeting, and support-triage audit evidence.

**Plans**: 0/1 planned

## Progress

**Execution Order:**
Phases execute in numeric order: 19 -> 20 -> 21 -> 22

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 19. Reports Bucket Transport Security | v1.3 | 0/1 | Planned | - |
| 20. Prefix-Scoped Report Artifact IAM | v1.3 | 0/1 | Planned | - |
| 21. Smoke and Orphan Artifact Cleanup | v1.3 | 0/1 | Planned | - |
| 22. Report Operations Visibility and Recovery | v1.3 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 19 | Planned |
| SEC-02 | Phase 19 | Planned |
| SEC-03 | Phase 19 | Planned |
| IAM-01 | Phase 20 | Planned |
| IAM-02 | Phase 20 | Planned |
| IAM-03 | Phase 20 | Planned |
| IAM-04 | Phase 20 | Planned |
| CLEAN-01 | Phase 21 | Planned |
| CLEAN-02 | Phase 21 | Planned |
| CLEAN-03 | Phase 21 | Planned |
| OPS-01 | Phase 22 | Planned |
| OPS-02 | Phase 22 | Planned |
| OPS-03 | Phase 22 | Planned |
| OPS-04 | Phase 22 | Planned |

**Coverage:**

- v1.3 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0

---
*Roadmap created: 2026-06-04*
