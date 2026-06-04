---
phase: 27
phase_name: Report Recovery Verification and Live Evidence
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 27: Report Recovery Verification and Live Evidence - Context

## Phase Boundary

Verify the full report operations recovery workflow built in Phases 23-26.

This phase delivers:

- Backend authorization and privacy coverage for report operations endpoints.
- Frontend e2e coverage for report operations navigation, filters, detail, action eligibility, selected bulk resend, and result rendering.
- Local/browser evidence that the UI does not expose private artifact paths or keys.
- Live AWS evidence for deployed API state, auth gate behavior, Lambda status, and frontend SPA route handling.

This phase does not execute production retry/resend mutations without a safe target report.

## Verification Sources

- Backend focused tests: `tests/test_admin_report_ops.py`, `tests/test_parent_children.py`.
- Frontend e2e: `/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts`.
- Frontend build/lint.
- AWS CLI profile `stoa` in `eu-central-2`.
- CDK diff from `/Users/zhdeng/stoa-infra`.

## Live Verification Boundary

- Safe live checks are read-only or auth-gate checks:
  - STS caller identity.
  - Lambda configuration state.
  - API `/health`.
  - Unauthenticated `/admin/reports/ops` rejection.
  - Frontend SPA path response for `/admin/report-operations`.
  - CDK diff.
- Production retry/resend mutations are not executed because no approved safe failed report target was available.
