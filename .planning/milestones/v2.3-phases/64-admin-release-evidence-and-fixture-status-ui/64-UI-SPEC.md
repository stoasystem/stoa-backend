# Phase 64 UI Spec: Release Evidence And Fixture Status

## Surface

Existing admin `/admin/report-operations` page.

## Controls

- Release bundle JSON textarea for a redacted evidence bundle.
- Validate release evidence button.
- Safe fixture name input.
- Check fixture status button.

## States

- Empty: no validation result or fixture status loaded.
- Validated: show validation status, missing field count, privacy violation count, allowlisted deploy/request metadata, and structured issue rows.
- Fixture loaded: show fixture status, approval flag, audit reference count, current version, expected baseline, and sanitized report ID.
- Error: show mutation/query error text in the panel message area.

## Privacy Rules

The UI must not render:

- Private S3 keys.
- Presigned URLs.
- Raw report JSON.
- Raw report HTML.
- Auth tokens, refresh tokens, or session secrets.
- Raw artifact payloads.

## Layout

Use the existing dense admin operations layout with restrained cards, compact metrics, and small status badges. The release evidence panel should sit near the existing recovery evidence panel and should not interrupt report triage workflows.

## Verification

- Build and lint pass.
- Playwright verifies validation result, fixture status, and privacy denylist.
- UI review verifies the validation result is not rendered as raw JSON.
