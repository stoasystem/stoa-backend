---
phase: 234
name: Backend Content Migration Service And APIs
status: planned
created: 2026-07-05
---

# Phase 234 Context: Backend Content Migration Service And APIs

## Milestone

v5.12 Curriculum Editor And Content Migration Buildout

## Why This Phase Exists

Production curriculum content should not be imported through manual database writes or ad hoc scripts. v5.1 defined migration readiness; Phase 234 builds the backend service and APIs that make migration repeatable, reviewable, idempotent, and auditable.

## Inputs From Phase 233

- Special curriculum authorization exists.
- Draft patch/update and validation preview exist.
- Diff and audit-read APIs exist.
- Published curriculum reads are still stable.

## Migration Boundary

- Dry-run must be non-mutating.
- Apply must require `migration_operator` or equivalent publisher capability plus explicit confirmation.
- Migration must produce evidence and audit references.
- Actual import of an approved production content source may remain separate if the source material is not yet available.
