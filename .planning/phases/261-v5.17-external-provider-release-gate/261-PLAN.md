# Phase 261 Plan: v5.17 External Provider Release Gate

## Objective

Close v5.17 with honest external provider activation evidence, rollback controls, blocked prerequisites, and next milestone recommendation.

## Tasks

1. Run focused release-gate backend tests and lint.
2. Record provider activation outcomes and blocked prerequisites.
3. Document rollback/disable controls for each external surface.
4. Update roadmap, requirements, state, milestone summary, and next milestone recommendation.

## Verification

- Focused pytest coverage for all v5.17 external activation smoke surfaces and related existing provider/readiness paths.
- Ruff on touched release-operation source/tests.
- GSD roadmap analysis confirms all phases complete.
