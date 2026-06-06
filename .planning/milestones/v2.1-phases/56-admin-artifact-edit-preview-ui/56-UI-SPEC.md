# Phase 56 UI Spec: Admin Artifact Edit Preview UI

**Status:** Complete
**Date:** 2026-06-06

## Experience Goal

Admins reviewing a selected report can propose bounded artifact edits, preview the sanitized backend diff, and apply the versioned artifact update without seeing private artifact storage details.

## Screen

- Existing route: `/admin/report-operations`
- Surface: selected report details panel
- Audience: admin operators handling report recovery/edit workflows

## Controls

- Operator reason textarea.
- Editable summary textarea.
- Editable recommendation inputs.
- Preview button for non-mutating draft creation.
- Apply button shown after a successful preview.

## States

- No selected report: no artifact edit controls.
- Artifact edit disabled by backend action state: preview/apply controls disabled with existing action availability semantics.
- Preview pending: preview button loading/disabled through mutation state.
- Preview success: sanitized draft metadata, validation state, field diffs, and preview text are shown.
- Apply pending: apply button loading/disabled through mutation state.
- Apply success: version ID and audit reference are shown.
- Error/stale state: backend error message is surfaced without private payload data.

## Safety Rules

- Preview and apply are visually and behaviorally separate.
- Reason text is required before preview and apply.
- UI never displays `weekly-reports/`, `json_s3_key`, `html_s3_key`, presigned URLs, raw report JSON, raw unreviewed HTML, auth tokens, or session tokens.
- Backend responses remain the source of truth for sanitized diff and validation state.

## Verification

- Focused lint passed for the changed frontend files.
- Production build passed.
- Playwright admin report operations spec passed and asserts private marker denylist cleanliness.
