# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification. Record: `.planning/milestones/s3-report-artifact-infrastructure.md`.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.3-ROADMAP.md`.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.4-ROADMAP.md`.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.5-ROADMAP.md`.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05. Archive: `.planning/milestones/v1.6-ROADMAP.md`.

## Current Milestone

No active milestone. Run `$gsd-new-milestone` to define the next milestone requirements and roadmap.

## Next Candidates

Deferred from v1.6:

- Incident-wide `generation_failed` retry.
- Resume failed/skipped recovery subsets as a new audit-linked job.
- Metadata-only recovery target/job/audit export.
- Support ticket or incident note integration.
- Stronger orchestration resources if evidence requires Step Functions, SQS, a dedicated worker Lambda, a new table, a new bucket, or a new GSI.
- Compliance-grade WORM audit storage if legal/security requires it.
- Report editing, PDF generation, multilingual delivery, billing, analytics, and broader admin operations expansion.

---
*Last updated: 2026-06-05 after archiving v1.6*
