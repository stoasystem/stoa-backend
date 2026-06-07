# Phase 78 Live Verification

**Status:** passed
**Created:** 2026-06-07

## API Smoke

Evidence file: `/private/tmp/stoa_phase78_api_smoke.json`

| Check | Result | Request ID |
|-------|--------|------------|
| Admin login | 200 | `phase78-remediated-login` |
| Health | 200 | `phase78-remediated-health` |
| Unauthenticated immutable status | 401 | `phase78-remediated-unauth-gate` |
| Authenticated immutable status | 200 | `phase78-remediated-immutable-readonly` |
| Authenticated legal hold status | 200 | `phase78-remediated-legalhold-readonly` |

Result flags:

- `health.passed=true`
- `auth.login_passed=true`
- `auth.admin_gate_passed=true`
- `immutable_evidence_status.passed=true`
- `immutable_evidence_status.storage_status=not_configured`
- `immutable_evidence_status.resource_configured=false`
- `legal_hold_status.passed=true`
- `privacy.passed=true`
- `report_artifact_mutation_attempted=false`
- `audit_delete_attempted=false`
- `immutable_write_attempted=false`
- `legal_hold_mutation_attempted=false`
- `external_write_attempted=false`

The API smoke used only read-only status paths for immutable evidence and legal hold metadata against backend commit `2e2d9429c41453b23835a8a8692dd76c3fc8d57d`. It did not call immutable manifest persistence or legal-hold apply/release.

## Browser Smoke

Evidence file: `/private/tmp/stoa_phase78_browser_smoke.json`
Screenshot: `/private/tmp/stoa-phase78-production-report-operations.png`

Result flags:

- `loaded=true`
- `current_url=https://app.stoaedu.ch/admin/report-operations`
- `immutable_evidence_visible=true`
- `legal_hold_visible=true`
- `blocked_mutation_attempts=[]`
- `page_errors=[]`
- `safety.immutable_write_attempted=false`
- `safety.legal_hold_mutation_attempted=false`
- `safety.report_operation_mutation_attempted=false`

Observed read-only API requests:

- `GET /auth/me`
- `GET /admin/reports/ops`
- `GET /admin/reports/recovery-jobs`

The browser smoke injected the production admin access token into the deployed app's normal local storage key, allowed the app to validate `/auth/me`, and guarded report-operation mutation routes. No guarded mutation route was attempted.

## Privacy

The API smoke checked for private markers:

- `access_token`
- `id_token`
- `refresh_token`
- `authorization`
- `bearer `
- `password`
- `secret`
- `weekly-reports/`
- `s3://`
- `https://s3`

No marker hit was found in the smoke evidence responses.

## Result

Production live verification passed. The deployed backend and frontend expose the immutable evidence/legal hold foundation to admins, fail closed when CDK-managed immutable storage is absent, and preserve the privacy and no-mutation release boundary.
