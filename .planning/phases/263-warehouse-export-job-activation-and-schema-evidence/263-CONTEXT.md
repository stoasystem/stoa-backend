# Phase 263 Context: Warehouse Export Job Activation And Schema Evidence

## Goal

Make aggregate warehouse exports repeatable, bounded, idempotent, and support-safe across product/provider readiness surfaces.

## Scope

- Add cross-product BI warehouse readiness and export APIs.
- Preserve the existing curriculum-only warehouse export.
- Use local/read-only evidence when live BI warehouse config is unavailable.
