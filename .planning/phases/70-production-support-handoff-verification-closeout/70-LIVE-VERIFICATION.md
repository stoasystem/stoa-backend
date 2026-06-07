# Phase 70 Live Verification

**Status:** Planned
**Recorded at:** TBD

## Production API Smoke

Safety:

- Use the long-lived secret-backed production admin credential path.
- Do not print passwords, tokens, cookies, or AWS credentials.
- Do not mutate report artifacts.
- Do not write to external support systems.

Planned checks:

| Method | Path | Expected | Request ID |
|--------|------|----------|------------|
| POST | `/auth/login` | 200 | TBD |
| GET | `/health` | 200 | TBD |
| POST | `/admin/reports/support-handoff-package` without token | 401 or 403 | TBD |
| POST | `/admin/reports/support-handoff-package` preview | 200 metadata-only package | TBD |
| POST | `/admin/reports/support-handoff-package` external_write | 200 refused, no external write | TBD |

Expected result:

- `mutationAttempted`: `false`
- `externalWriteAttempted`: `false`
- `authGatePassed`: TBD
- `previewPassed`: TBD
- `externalWriteRefused`: TBD
- `privacyPassed`: TBD

## Production Browser Smoke

Safety:

- Use admin auth without typing secrets into visible form fields.
- Install a request guard that blocks report mutation endpoints and external write attempts.
- Do not click mutation controls.

Planned result fields:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Route loaded: TBD
- Support handoff marker observed: TBD
- `mutationAttempted`: `false`
- `blockedMutations`: TBD
- Visible privacy hits: TBD
- Screenshot or marker evidence: TBD

## Privacy Denylist

Recorded API/browser evidence must not include:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- `presigned`
- raw report JSON/HTML payloads
- access tokens, passwords, cookies, or AWS secrets.
