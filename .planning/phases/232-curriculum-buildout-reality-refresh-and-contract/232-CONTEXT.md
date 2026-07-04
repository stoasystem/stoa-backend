---
phase: 232
name: Curriculum Buildout Reality Refresh And Contract
status: active-planning
created: 2026-07-05
---

# Phase 232 Context: Curriculum Buildout Reality Refresh And Contract

## Milestone

v5.12 Curriculum Editor And Content Migration Buildout

## Why This Phase Exists

v5.1 made curriculum editor and migration readiness explicit, but it did not implement the full editor frontend, draft patch/diff/validation APIs, or migration service/API/UI. v5.10 and v5.11 then closed account operations and multi-action usage ledger gaps.

The next buildable product gap is now curriculum operations implementation, not more planning-only readiness and not external activation work that depends on live provider credentials.

## Backend Reality To Preserve

- Curriculum authoring lifecycle foundation exists in `curriculum_ops_service` and `curriculum_ops_repo`.
- Content-quality analytics foundation exists in `curriculum_analytics_service` and `curriculum_analytics_repo`.
- Published student/parent curriculum reads exist through practice routes and must remain stable.
- Adaptive assignment and sequencing routes already consume curriculum and assignment signals.
- v5.11 usage ledger instrumentation should remain compatible with practice, lesson, assignment, and generation flows.

## Frontend Reality To Fix

- Admin/tutor curriculum authoring workbench is not a complete implemented surface.
- Rich editor clients/hooks/routes are not complete.
- Migration dry-run/apply operator UI is missing.
- Validation, diff, audit, evidence, conflict, partial-success, and API-error states are missing for curriculum operations.

## Planning Boundary

Phase 232 is planning and contract alignment. Implementation starts in Phase 233 for backend editor APIs, then Phase 234 migration APIs, then Phase 235 frontend tooling.
