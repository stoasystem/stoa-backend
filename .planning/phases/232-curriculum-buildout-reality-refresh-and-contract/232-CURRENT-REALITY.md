# Phase 232 Current Reality

**Date:** 2026-07-05
**Purpose:** Reconcile current implementation reality before starting v5.12 curriculum editor and migration buildout.

## Completed Reality

| Area | Evidence | Status |
|------|----------|--------|
| Account operations frontend | v5.10 roadmap/requirements/phase evidence | Complete local frontend/readiness milestone. |
| Multi-action usage ledger | v5.11 audit and Phase 231 verification | Complete local backend milestone. |
| Curriculum authoring foundation | `src/stoa/services/curriculum_ops_service.py`, `src/stoa/db/repositories/curriculum_ops_repo.py` | Foundation complete; editor API gaps remain. |
| Curriculum analytics foundation | `src/stoa/services/curriculum_analytics_service.py`, `src/stoa/db/repositories/curriculum_analytics_repo.py` | Foundation complete; warehouse/BI remains future. |
| Published curriculum reads | `src/stoa/routers/practice.py` and frontend practice pages/components | Student-facing published reads exist and must remain stable. |
| Adaptive assignment foundation | `src/stoa/routers/adaptive.py`, `src/stoa/services/adaptive_learning_service.py` | Existing assignment and sequencing contracts must stay compatible. |

## Remaining Build Gaps

| Gap | Evidence | v5.12 Treatment |
|-----|----------|-----------------|
| Rich editor frontend | v5.1 audit says full frontend implementation remains deferred; frontend scan has no dedicated curriculum authoring workbench | Build in Phase 235. |
| Draft patch/update API | v5.1 audit says draft update/patch remains future work | Build in Phase 233. |
| Structured validation preview | v5.1 audit says validation preview remains future work | Build in Phase 233. |
| Diff endpoint | v5.1 audit says diff endpoint remains future work | Build in Phase 233. |
| Audit-read endpoint | v5.1 audit says audit-read remains future work | Build in Phase 233. |
| Migration service/API/UI | v5.1 audit says manifest parsing, dry-run/apply APIs, evidence persistence, rollback metadata, and operator UI remain future work | Build in Phases 234 and 235. |
| Special curriculum authorization | User clarified ordinary teachers must not all receive edit permission | Add to Phase 233 backend authorization and Phase 235 unauthorized UI states. |
| Production content import | v5.1 audit says no production source was imported/published through the pipeline | Enable repeatable pipeline; actual approved source import remains dependent on source availability. |

## Candidate Milestones Rejected For v5.12

- Native app buildout: important, but larger platform expansion after core web operator tooling.
- Live payment/support/notification activation: valuable but blocked by external credentials, provider approval, or deployment prerequisites.
- Warehouse/BI deployment: useful after migration/content analytics data stabilizes.
- Broad CMS/collaboration: too broad for the current internal buildout milestone.

## Decision

Start v5.12 as `Curriculum Editor And Content Migration Buildout`.

The milestone should implement the editor and migration tooling that v5.1 intentionally left as readiness/deferred scope, while preserving published curriculum reads, usage ledger compatibility, adaptive assignment behavior, and the boundary that curriculum editing requires explicit backend authorization.
