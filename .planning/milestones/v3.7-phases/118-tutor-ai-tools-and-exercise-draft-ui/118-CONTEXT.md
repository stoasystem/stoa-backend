---
phase: 118
name: Tutor AI Tools And Exercise Draft UI
milestone: v3.7
status: complete
created: 2026-06-09
completed: 2026-06-09
requirement: UI-22
---

# Phase 118 Context

## Objective

Expose the v3.7 AI teacher tools in the tutor workflow so a teacher can generate, inspect, regenerate, accept, reject, or archive summary and exercise drafts from the current visible help request.

## Inputs

- Phase 116 AI teacher tools contract.
- Phase 117 backend draft API endpoints and lifecycle behavior.
- Existing frontend tutor help request detail workflow in `/Users/zhdeng/stoa-frontend`.
- Existing demo API fallback pattern used by tutor e2e coverage.

## Decisions

- Place the first UI inside the tutor help request detail page, immediately after the existing teacher assistance seed.
- Treat generated content as review-only; the UI shows `Draft only` and `not delivered` status.
- Keep state local to the current detail page after create/review/regenerate, while exposing list/detail query hooks for the backend API contract.
- Add deterministic demo fallbacks so Playwright can verify the workflow without a live backend.

## Verification Targets

- Frontend lint.
- Frontend production build.
- Targeted tutor/admin Playwright workflow.
