# Phase 60 Context: Admin Artifact Rollback UI

## Goal

Admins can review sanitized artifact rollback metadata and apply rollback from `/admin/report-operations` without seeing private artifact payloads or S3 internals.

## Inputs

- Phase 58 rollback contract and privacy model.
- Phase 59 backend rollback APIs:
  - `POST /admin/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews`
  - `POST /admin/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews/{preview_id}/apply`
- Phase 59 `rollback_artifact` action eligibility on report operation rows.
- Existing Phase 56 artifact edit UI pattern in `stoa-frontend`.

## Scope

- Add frontend API types and clients for rollback preview/apply.
- Add React Query mutations that invalidate report operations after rollback preview/apply.
- Add selected-report UI controls for rollback reason, preview, apply, sanitized version metadata, validation status, and outcome.
- Extend Playwright coverage for rollback preview/apply and private marker denylist.

## Non-Goals

- Rich version history browser.
- Arbitrary target selection beyond the backend-provided previous artifact version.
- Raw JSON/HTML artifact preview.
- Production mutation verification; Phase 61 owns deploy and live safe-fixture evidence.

## Safety Constraints

- UI must require an operator reason before preview/apply.
- Apply must remain a separate button from preview.
- UI may show current/target artifact version IDs and validation/apply status only.
- UI must not render S3 keys, presigned URLs, raw report JSON, raw HTML, or private artifact marker fields.
