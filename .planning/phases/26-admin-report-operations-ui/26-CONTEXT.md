---
phase: 26
phase_name: Admin Report Operations UI
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 26: Admin Report Operations UI - Context

## Phase Boundary

Build a real admin frontend workflow for report operations triage and recovery.

This phase delivers:

- Admin navigation route for report operations.
- Real API integration for report list, detail, retry generation, single resend, and selected bulk resend.
- Filters, loading, empty, error, paginated list, status badges, detail inspection, action eligibility, and result rendering.
- No demo fallback for operational report data.

This phase does not deploy or live-verify the UI; live evidence is Phase 27.

## Frontend Context

- Frontend repo: `/Users/zhdeng/stoa-frontend`.
- Stack: Vite, React 19, React Router 7, React Query, Tailwind, lucide-react.
- Admin pages live in `src/pages/admin`.
- Admin service layer lives in `src/services/admin/adminApi.ts`.
- Admin hooks live in `src/hooks/admin`.
- Admin routes are configured in `src/app/router/AppRouter.tsx` and `src/app/router/routeConfig.ts`.
- Layout should reuse `DashboardLayout`, `PageContainer`, `PageHeader`, and existing UI primitives.

## Design Direction

This is an operations console for repeated triage. The UI should be dense, restrained, and scan-friendly:

- Use filters and tables instead of hero/card-heavy presentation.
- Keep controls compact and predictable.
- Use status badges and action buttons with icons.
- Show detail in an adjacent panel or workflow area so admins do not leave the triage context.
- Avoid exposing raw report artifacts, S3 keys, URLs, or HTML/JSON previews.

## API Context

Backend endpoints available from Phases 23-25:

- `GET /admin/reports/ops`
- `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops`
- `POST /admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation`
- `POST /admin/reports/{parent_id}/{student_id}/{week_start}/resend`
- `POST /admin/reports/bulk-resend`

## Deferred Ideas

- Immutable audit timeline UI.
- Async incident recovery jobs.
- Report content preview/editor.
- Frontend live verification, covered by Phase 27.
