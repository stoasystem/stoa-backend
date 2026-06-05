# Phase 53 Live Verification

**Status:** Passed
**Recorded at:** 2026-06-05T15:24:00+02:00

## Production API Smoke

Script: `/private/tmp/stoa_phase53_api_smoke.mjs`

Safety:

- Used secret-backed real production admin path.
- Redacted token/password from output.
- No production edit draft, apply, recovery retry, resend, job create, resume, or cancel mutation was attempted.

Result:

- API base: `https://api.stoaedu.ch`
- Admin email domain recorded only as `gmail.com`
- `mutationAttempted`: `false`
- `privacyPassed`: `true`
- `authGatePassed`: `true`
- `adminListPassed`: `true`
- `editDraftReadOnlyPassed`: `true`

Requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| POST | `/auth/login` | 200 | `efUKQjtM5icEPRg=` |
| GET | `/health` | 200 | `efUKWhO75icEPSw=` |
| GET | `/admin/reports/ops?limit=1` without token | 401 | `efUKYj2A5icEPHQ=` |
| GET | `/admin/reports/ops?limit=5` | 200 | `efUKZj2CZicEPHQ=` |
| GET | `/admin/reports/recovery-evidence?limit=1&include_targets=false&include_job_audit=false` | 200 | `efUKagfT5icEP2w=` |

Notes:

- Production report operations list returned `count=0` during smoke.
- Because no report row existed, report detail/audit/edit-draft nonexistent GET checks were skipped rather than creating data.

Privacy denylist result:

- No `weekly-reports/`
- No `json_s3_key`
- No `html_s3_key`
- No `s3_key`
- No presigned URL marker
- No S3 URL
- No raw report HTML/JSON payload
- No auth token field in recorded evidence

## Production Browser Smoke

Script: `/private/tmp/stoa_phase53_browser_smoke.mjs`

Safety:

- Used real admin auth token from secret-backed login.
- Set browser `localStorage.stoa_access_token` directly to avoid entering secrets into form fields.
- Installed request guard blocking any non-GET/HEAD/OPTIONS request to `/admin/reports/**`.
- Did not click create/apply/retry/resend/job/cancel controls.

Result:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Admin role: `admin`
- Route loaded: `true`
- `mutationAttempted`: `false`
- `blockedMutations`: `[]`
- Visible text privacy hits: `[]`
- Screenshot: `/private/tmp/stoa-phase53-production-report-operations.png`

Browser API requests:

| Method | Path | Status | Request ID | Private Hits |
|--------|------|--------|------------|--------------|
| GET | `/admin/reports/ops` | 200 | `efUfahVIZicEJuQ=` | `[]` |
| GET | `/admin/reports/recovery-jobs` | 200 | `efUfahMkZicEJ7A=` | `[]` |

Bundle marker evidence:

- `Create draft`: present
- `Apply draft`: present
- `edit-drafts`: present

Production list was empty during smoke, so the selected-report edit panel was not visible. Bundle markers prove the deployed frontend includes the v2.0 edit draft/apply UI and API path, while browser smoke proved the route/auth/GET/privacy boundary without production mutation.
