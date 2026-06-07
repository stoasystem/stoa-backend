# Phase 73 UI Spec: Admin Audit Retention UI

**Status:** Approved for implementation
**Created:** 2026-06-07

## Design Direction

Operational, compact, and consistent with the existing `/admin/report-operations` panels. The UI should feel like another admin evidence tool, not a new product surface.

## Required Controls

- Manifest reason textarea.
- Include checkboxes:
  - Selected recovery job.
  - Selected report.
  - Release evidence JSON.
- Primary actions:
  - Check retention status.
  - Generate manifest.
- Secondary actions:
  - Copy manifest.
  - Download JSON.

## Required States

- Empty state before status/manifest.
- Loading states for status and manifest requests.
- Status rows with scope, state, reason, and privacy result.
- Manifest preview with manifest id, digest, category, generated timestamp, item digest badges, refusal reasons, and bounded JSON preview.
- JSON parse errors for release evidence input.

## Privacy Requirements

Rendered UI text must not include:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- `presignedUrl`
- `presigned_url`
- `https://s3`
- raw HTML
- auth token names

## Layout

Place the panel after recovery evidence export and before support handoff so the operator workflow remains:

1. Export recovery evidence.
2. Seal metadata-only retention evidence.
3. Compose support handoff package.
4. Validate release evidence and fixture status.

## Verification

- Frontend lint/build pass.
- Existing admin report operations Playwright test covers the new mocked status/manifest flow and privacy denylist assertions.
