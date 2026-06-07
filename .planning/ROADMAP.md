# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05.
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05.
- [x] **v1.9 Recovery Resume And Support Evidence Packages** - Shipped 2026-06-05.
- [x] **v2.0 Controlled Report Editing MVP** - Shipped 2026-06-05.
- [x] **v2.1 Report Artifact Versioning And Safe Edit Preview** - Shipped 2026-06-06.
- [x] **v2.2 Report Artifact Rollback And Safe Fixture Verification** - Shipped 2026-06-06.
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06. Archive: `.planning/milestones/v2.3-ROADMAP.md`.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5. Archive: `.planning/milestones/v2.4-ROADMAP.md`.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07. Archive: `.planning/milestones/v2.5-ROADMAP.md`.
- [x] **v2.6 Audit Retention And Immutable Evidence Readiness** - Shipped 2026-06-07. Archive: `.planning/milestones/v2.6-ROADMAP.md`.

## Current Milestone

**v2.7 Immutable Audit Storage And Legal Hold Foundation** - Active.

Goal: implement the foundation for CDK-managed immutable audit evidence storage and legal hold/retention policy administration for report operations audit evidence, without exposing private report artifacts, deleting existing audit rows, or claiming compliance-grade immutability before deploy evidence proves it.

## Phases

| Phase | Name | Status | Requirement |
|-------|------|--------|-------------|
| 75 | Immutable Audit Storage Contract And CDK Readiness | Complete | IMMUTABLE-01 |
| 76 | Backend Immutable Retention Persistence And Legal Hold Metadata | Complete | IMMUTABLE-02, LEGALHOLD-01 |
| 77 | Admin Immutable Evidence And Legal Hold UI | Planned | UI-14 |
| 78 | v2.7 Release Gate And Live Verification | Planned | VERIFY-10 |

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 75 | v2.7 | 1/1 | Complete | 2026-06-07 |
| 76 | v2.7 | 1/1 | Complete | 2026-06-07 |
| 77 | v2.7 | 0/1 | Planned | - |
| 78 | v2.7 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMMUTABLE-01 | Phase 75 | Complete |
| IMMUTABLE-02 | Phase 76 | Complete |
| LEGALHOLD-01 | Phase 76 | Complete |
| UI-14 | Phase 77 | Planned |
| VERIFY-10 | Phase 78 | Planned |

---
*Last updated: 2026-06-07 after completing Phase 76*
