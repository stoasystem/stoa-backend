# Phase 68 UI Spec: Admin Support Handoff UI

**Status:** Approved for implementation
**Created:** 2026-06-07

## Design Direction

Operational, dense, and quiet. The page is an admin control surface, so the implementation should extend existing cards, badges, segmented buttons, compact textareas, preformatted JSON panes, and icon buttons already used on `/admin/report-operations`.

## Required Controls

- Operator reason textarea.
- Operator note textarea.
- Destination segmented controls:
  - Preview
  - Copy
  - Download
  - External write
- Include toggles/checkboxes:
  - Selected recovery job
  - Release evidence JSON
  - Safe fixture status
- Primary action button: Generate handoff package.
- Secondary actions when package exists:
  - Copy
  - Download

## Required States

- Empty/no package state.
- Loading state while package is generating.
- Success state with package id, destination status, validation status, evidence reference count, and section names.
- Refused state with refusal reasons.
- JSON parse error for release evidence input.
- Privacy-safe JSON preview with bounded height.

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

Place the panel between the existing recovery evidence panel and release evidence automation panel. This keeps the workflow order:

1. Generate/export recovery evidence.
2. Compose a support handoff package.
3. Validate release evidence and inspect fixture status.

## Verification

- Existing admin report operations E2E covers the new route mock and UI flow.
- Local build/lint pass.
